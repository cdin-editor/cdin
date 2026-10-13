local core    = require "core"
local common  = require "core.utils.common"
local View    = require "core.views.view"
local DocView = require "core.views.docview"
local Node    = require "core.rootview.node"

local RootView = View:extend()

function RootView:new()
  RootView.super.new(self)
  self.root_node     = Node()
  self.deferred_draws = {}
  self.mouse         = { x = 0, y = 0 }
end

function RootView:defer_draw(fn, ...)
  table.insert(self.deferred_draws, 1, { fn = fn, ... })
end

function RootView:get_active_node()
  return self.root_node:get_node_for_view(core.active_view)
end

-- The outermost node on one side of the layout.
--
-- Not the active node: "the node that happens to hold focus" is a property of
-- the moment, and a panel that attaches itself to it lands wherever the user
-- last clicked. Two panels doing that is worse than either one alone — the
-- second split is taken out of the first panel's node, so the file tree ends
-- up wedged between the document and the extension panel, and which of the
-- two ends up outermost depends on load order.
--
-- The edge is a property of the layout, so it is the same every time.
--
-- Sides are HORIZONTAL only, and that is the whole subtlety. The layout is
-- built out of rows as well as columns — the title bar on top, the status bar
-- and the command line at the bottom, each a locked pane of its own (see
-- core/state.lua) — and for those, `b` is the bottom of the window, not the
-- right of it. Walking `b` down a vertical split therefore lands in the status
-- bar, and a panel attached there opens from the bottom edge of the screen and
-- grows across it: which is what the file tree and the extension panel did
-- before this took sides into account.
--
-- So: follow `a`/`b` through horizontal splits, and on a vertical split take
-- `a` — the content pane, with the rows beneath it. Any number of nested splits
-- in either direction; it always ends on a leaf in the content region.
function RootView:get_edge_node(side)
  -- A subtree that still holds somewhere a document can live. The title bar is
  -- a locked leaf, and so are the command line and the status bar.
  local function has_free_leaf(n)
    if n.type == "leaf" then return not n.locked end
    return has_free_leaf(n.a) or has_free_leaf(n.b)
  end

  local node = self.root_node
  while node.type ~= "leaf" do
    if node.type == "hsplit" then
      node = (side == "left") and node.a or node.b
    else
      -- Which child is "the content" depends on how the row was split off:
      -- `split("up", ...)` (the title bar) puts the new row in `a`, while
      -- `split("down", ...)` (command line, status bar) leaves the content in
      -- `a`. So `a` is not always the content — taking it blindly landed on
      -- the title bar, and the panel was split out of it. Follow the child that
      -- still has a free leaf in it.
      node = has_free_leaf(node.a) and node.a or node.b
    end
  end
  return node
end

-- Puts `view` in its own pane on one edge of the layout, and returns the node
-- it landed in.
--
--   side      "left" or "right". Anything else is treated as "right".
--   opts.locked   keep the pane out of document routing (default true)
--   opts.width    the pane's share of the split, 0.01..0.99
--
-- Idempotent: a view already in the tree is left where it is rather than split
-- out a second time, which is what makes it safe to call from init() on every
-- enable cycle. It is deliberately NOT activated on that path either — a panel
-- that grabs focus every time it is reloaded is a panel that fights the
-- document for the caret. Focusing it is a separate command.
function RootView:attach_side_view(view, side, opts)
  opts  = opts or {}
  side  = (side == "left") and "left" or "right"

  local existing = self.root_node:get_node_for_view(view)
  if existing then return existing end

  -- The edge is a leaf by construction, and Node:split asserts it.
  local node = self:get_edge_node(side)
  node:split(side, view, opts.locked ~= false)
  -- No update_layout here: a caller may be a plugin's init(), which runs before
  -- the first frame has sized the tree. The divider is read by the layout, and
  -- the loop calls update_layout every frame anyway.
  if opts.width then node.divider = common.clamp(opts.width, 0.01, 0.99) end

  return self.root_node:get_node_for_view(view) or node
end

-- Takes `view` back out of the layout. The counterpart of attach_side_view, and
-- what an extension's unload calls so that disabling it gives the space back
-- rather than leaving an empty pane the user cannot get rid of.
function RootView:detach_view(view)
  local node = self.root_node:get_node_for_view(view)
  if not node then return false end

  local was_active = (core.active_view == view)
  node:remove_view(view, self.root_node)

  -- core.active_view is a view, not a node, so removing the view leaves it
  -- pointing at something that is no longer drawn. The document it was covering
  -- is the natural replacement, and last_active_view is what the runtime keeps
  -- for exactly this. Failing that, the edge node is all that is left.
  if was_active then
    local last = core.last_active_view
    local back = (last and last ~= view and self.root_node:get_node_for_view(last))
      or self:get_edge_node("left")
    core.set_active_view(back.active_view)
  end

  self.root_node:update_layout()
  return true
end

function RootView:open_doc(doc)
  local node = self:get_active_node()

  if node.locked then
    if core.last_active_view then
      local last_node = self.root_node:get_node_for_view(core.last_active_view)
      if last_node and not last_node.locked then
        core.set_active_view(core.last_active_view)
        node = last_node
      end
    end

    if node.locked then
      local function find_unlocked(n)
        if n.type == "leaf" then return (not n.locked) and n or nil end
        return find_unlocked(n.a) or find_unlocked(n.b)
      end
      local unlocked = find_unlocked(self.root_node)
      if unlocked then
        node = unlocked
        core.set_active_view(node.active_view)
      end
    end
  end

  if node.locked then
    core.log("Cannot open doc: no unlocked editor node available")
    return
  end

  for i, view in ipairs(node.views) do
    if view.doc == doc then
      node:set_active_view(node.views[i])
      return view
    end
  end

  local view = DocView(doc)
  node:add_view(view)
  self.root_node:update_layout()
  view:scroll_to_line(view.doc:get_selection(), true, true)
  return view
end

function RootView:on_mouse_pressed(button, x, y, clicks)
  local div = self.root_node:get_divider_overlapping_point(x, y)
  if div then
    self.dragged_divider = div
    return
  end

  local node = self.root_node:get_child_overlapping_point(x, y)

  local close_idx = node:get_tab_close_overlapping_point(x, y)
  if close_idx then
    node:set_active_view(node.views[close_idx])
    node:close_active_view(self.root_node)
    return
  end

  local idx = node:get_tab_overlapping_point(x, y)
  if idx then
    node:set_active_view(node.views[idx])
    if button == "middle" then
      node:close_active_view(self.root_node)
    end
  else
    core.set_active_view(node.active_view)
    node.active_view:on_mouse_pressed(button, x, y, clicks)
  end
end

function RootView:on_mouse_released(...)
  self.dragged_divider = nil
  self.root_node:on_mouse_released(...)
end

function RootView:on_mouse_moved(x, y, dx, dy)
  if self.dragged_divider then
    self.dragged_divider:drag_divider(dx, dy)
    return
  end

  self.mouse.x, self.mouse.y = x, y
  self.root_node:on_mouse_moved(x, y, dx, dy)

  local node = self.root_node:get_child_overlapping_point(x, y)
  local div  = self.root_node:get_divider_overlapping_point(x, y)
  if div then
    system.set_cursor(div.type == "hsplit" and "sizeh" or "sizev")
  elseif node:get_tab_overlapping_point(x, y) then
    system.set_cursor("arrow")
  else
    system.set_cursor(node.active_view.cursor)
  end
end

function RootView:on_mouse_wheel(...)
  local node = self.root_node:get_child_overlapping_point(self.mouse.x, self.mouse.y)
  node.active_view:on_mouse_wheel(...)
end

function RootView:on_text_input(...)
  core.active_view:on_text_input(...)
end


function RootView:update()
  self.root_node.position.x = self.position.x
  self.root_node.position.y = self.position.y
  self.root_node.size.x     = self.size.x
  self.root_node.size.y     = self.size.y
  self.root_node:update()
  self.root_node:update_layout()
end

function RootView:draw()
  self.root_node:draw()
  while #self.deferred_draws > 0 do
    local t = table.remove(self.deferred_draws)
    t.fn(table.unpack(t))
  end
end

return RootView