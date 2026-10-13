local core      = require "core"
local common    = require "core.utils.common"
local style     = require "core.style"
local Object    = require "core.utils.object"
local EmptyView = require "core.rootview.empty_view"

local Node = Object:extend()

local type_map = { up="vsplit", down="vsplit", left="hsplit", right="hsplit" }

function Node:new(type)
  self.type     = type or "leaf"
  self.position = { x = 0, y = 0 }
  self.size     = { x = 0, y = 0 }
  self.views    = {}
  self.divider  = 0.5
  if self.type == "leaf" then
    self:add_view(EmptyView())
  end
end

function Node:consume(node)
  for k in pairs(self)  do self[k] = nil  end
  for k, v in pairs(node) do self[k] = v  end
end

function Node:split(dir, view, locked)
  assert(self.type == "leaf", "Tried to split non-leaf node")
  local split_type  = assert(type_map[dir], "Invalid direction")
  local last_active = core.active_view

  local child = Node()
  child:consume(self)
  self:consume(Node(split_type))
  self.a = child
  self.b = Node()

  if view   then self.b:add_view(view) end
  if locked then
    self.b.locked = locked
    core.set_active_view(last_active)
  end
  if dir == "up" or dir == "left" then
    self.a, self.b = self.b, self.a
  end
  return child
end

-- This node is done: give its space back to its sibling and remove it from the
-- tree. Shared by closing the last view in a node and by detaching a view, so
-- the two cannot disagree about what an empty node means.
--
-- `reclaim` says *why* this node is going away, and it is the difference
-- between an empty column and a closed one:
--
--   nil     the last view was closed and this pane is the document area. A
--           locked sibling (a side panel) means the space is not free to be
--           taken, so this node becomes the empty view instead.
--   true    this node is empty and nothing is managing it any more, so the
--           space goes to the sibling whatever that sibling is. Otherwise
--           disabling a side panel leaves behind a locked column of nothing
--           that no key can close.
function Node:collapse(root, reclaim)
  local parent = self:get_parent_node(root)
  if not parent then return end
  local is_a  = (parent.a == self)
  local other = parent[is_a and "b" or "a"]
  if not reclaim and other:get_locked_size() then
    -- The lock goes with it: add_view refuses a locked node, and there is
    -- nothing left here to protect.
    self.locked = nil
    self.views = {}
    self:add_view(EmptyView())
  else
    parent:consume(other)
    local p = parent
    while p.type ~= "leaf" do p = p[is_a and "a" or "b"] end
    p:set_active_view(p.active_view)
  end
  core.last_active_view = nil
end

-- Takes a view out of this node. `root` is needed for the same reason
-- close_active_view takes it: an emptied node collapses into its sibling.
--
-- An emptied node is collapsed BEFORE the active view is repaired, because
-- collapse picks the replacement itself — handing set_active_view a nil
-- instead is how the active view ends up pointing at a view nobody draws.
function Node:remove_view(view, root)
  local idx = self:get_view_idx(view)
  if not idx then return false end

  table.remove(self.views, idx)
  if #self.views == 0 then
    self:collapse(root, true)
    return true
  end
  if self.active_view == view then
    self:set_active_view(self.views[idx] or self.views[#self.views])
  end
  return true
end

function Node:close_active_view(root)
  local do_close = function()
    if #self.views > 1 then
      local idx = self:get_view_idx(self.active_view)
      table.remove(self.views, idx)
      self:set_active_view(self.views[idx] or self.views[#self.views])
    else
      self:collapse(root)
    end
    core.last_active_view = nil
  end
  self.active_view:try_close(do_close)
end

function Node:add_view(view)
  assert(self.type == "leaf", "Tried to add view to non-leaf node")
  assert(not self.locked,     "Tried to add view to locked node")
  if self.views[1] and self.views[1]:is(EmptyView) then
    table.remove(self.views)
  end
  table.insert(self.views, view)
  self:set_active_view(view)
end

function Node:set_active_view(view)
  assert(self.type == "leaf", "Tried to set active view on non-leaf node")
  self.active_view = view
  core.set_active_view(view)
end

function Node:get_view_idx(view)
  for i, v in ipairs(self.views) do
    if v == view then return i end
  end
end

function Node:get_node_for_view(view)
  for _, v in ipairs(self.views) do
    if v == view then return self end
  end
  if self.type ~= "leaf" then
    return self.a:get_node_for_view(view) or self.b:get_node_for_view(view)
  end
end

function Node:get_parent_node(root)
  if root.a == self or root.b == self then return root end
  if root.type ~= "leaf" then
    return self:get_parent_node(root.a) or self:get_parent_node(root.b)
  end
end

function Node:get_children(t)
  t = t or {}
  for _, view in ipairs(self.views) do table.insert(t, view) end
  if self.a then self.a:get_children(t) end
  if self.b then self.b:get_children(t) end
  return t
end

local DIVIDER_GRAB_CELLS = 6

function Node:get_divider_overlapping_point(px, py)
  if self.type == "leaf" then return nil end
  local p = DIVIDER_GRAB_CELLS * SCALE
  local x, y, w, h = self:get_divider_rect()
  if px > x-p and py > y-p and px < x+w+p and py < y+h+p then
    return self
  end
  return self.a:get_divider_overlapping_point(px, py)
      or self.b:get_divider_overlapping_point(px, py)
end

function Node:get_tab_overlapping_point(px, py)
  if #self.views == 1 then return nil end
  local x, y, w, h = self:get_tab_rect(1)
  if px >= x and py >= y and px < x + w * #self.views and py < y + h then
    return math.floor((px - x) / w) + 1
  end
end

function Node:get_tab_close_overlapping_point(px, py)
  if #self.views == 1 then return nil end
  for i in ipairs(self.views) do
    local x, y, w, h = self:get_tab_rect(i)
    local close_x = x + w - style.padding.x - style.font:get_width("x")
    local close_w = style.font:get_width("x")
    if px >= close_x and py >= y and px < close_x + close_w and py < y + h then
      return i
    end
  end
end

function Node:get_child_overlapping_point(x, y)
  if self.type == "leaf" then return self end
  local child
  if self.type == "hsplit" then
    child = (x < self.b.position.x) and self.a or self.b
  else -- vsplit
    child = (y < self.b.position.y) and self.a or self.b
  end
  return child:get_child_overlapping_point(x, y)
end

function Node:get_tab_rect(idx)
  local tw = math.min(style.tab_width, math.ceil(self.size.x / #self.views))
  local h  = style.font:get_height() + style.padding.y * 2
  return self.position.x + (idx-1) * tw, self.position.y, tw, h
end

function Node:get_divider_rect()
  local x, y = self.position.x, self.position.y
  if self.type == "hsplit" then
    return x + self.a.size.x, y, style.divider_size, self.size.y
  else -- vsplit
    return x, y + self.a.size.y, self.size.x, style.divider_size
  end
end

function Node:get_locked_size()
  if self.type == "leaf" then
    if self.locked then
      return self.active_view.size.x, self.active_view.size.y
    end
  else
    local x1, y1 = self.a:get_locked_size()
    local x2, y2 = self.b:get_locked_size()
    if x1 and x2 then
      -- Along the split's own axis the two panes sit side by side, so their
      -- sizes add (plus the divider). Across it they share the same extent, so
      -- the size is the larger of the two. Summing both axes made a locked pane
      -- split out of another locked pane (title bar + panel) report twice its
      -- height, and since each child is then handed the parent's height, the
      -- height doubled every frame.
      local dsx = (x1 < 1 or x2 < 1) and 0 or style.divider_size
      local dsy = (y1 < 1 or y2 < 1) and 0 or style.divider_size
      if self.type == "hsplit" then
        return x1 + x2 + dsx, math.max(y1, y2)
      end
      return math.max(x1, x2), y1 + y2 + dsy
    end
  end
end

function Node:get_locked_leaf()
  if self.type == "leaf" then
    return self.locked and self or nil
  end
  return self.a:get_locked_leaf() or self.b:get_locked_leaf()
end

function Node:get_locked_pane()
  if self.type == "leaf" then return nil end
  local a = self.a:get_locked_leaf()
  if a then return "a", a end
  local b = self.b:get_locked_leaf()
  if b then return "b", b end
  return nil
end

local MIN_PANE_CELLS = 8

function Node:drag_divider(dx, dy)
  local axis  = (self.type == "hsplit") and "x" or "y"
  local delta = (axis == "x") and dx or dy

  local side, leaf = self:get_locked_pane()
  local view = leaf and leaf.active_view or nil
  if view and type(view.set_locked_size) == "function" then
    -- "a" grows as the pointer moves right and "b" shrinks: the divider is one
    -- edge shared by two panes, and only one of them can answer for it.
    local width = view.size[axis] + (side == "a" and delta or -delta)
    -- Both ends clamp. A pane narrower than its own edge cannot be grabbed
    -- again, so an overshooting drag would have to be undone by disabling the
    -- plugin rather than by dragging back; and `calc_split_sizes` will happily
    -- hand the sibling a negative size if the pane claims the whole split.
    local least = MIN_PANE_CELLS * SCALE
    local most  = math.max(self.size[axis] - least - style.divider_size, least)
    view:set_locked_size(axis, common.clamp(width, least, most))
    return
  end

  local span = self.size[axis]
  self.divider = common.clamp(self.divider + delta / span, 0.01, 0.99)
end

local function copy_pos_size(dst, src)
  dst.position.x, dst.position.y = src.position.x, src.position.y
  dst.size.x,     dst.size.y     = src.size.x,     src.size.y
end

local function calc_split_sizes(self, x, y, x1, x2)
  local ds = (x1 and x1 < 1 or x2 and x2 < 1) and 0 or style.divider_size
  local n
  if     x1 then n = x1 + ds
  elseif x2 then n = self.size[x] - x2
  else             n = math.floor(self.size[x] * self.divider)
  end
  self.a.position[x] = self.position[x]
  self.a.position[y] = self.position[y]
  -- Each locked child gets the width it asked for. Handing b the *remainder*
  -- instead is correct only while at most one side is locked, and two side
  -- panels is exactly the case that breaks: the second one was being given
  -- everything the first had not claimed, so a 460px extension panel next to a
  -- 200px file tree filled the window.
  self.a.size[x]     = x1 or (n - ds)
  self.a.size[y]     = self.size[y]
  self.b.position[x] = self.position[x] + n
  self.b.position[y] = self.position[y]
  self.b.size[x]     = x2 or (self.size[x] - n)
  self.b.size[y]     = self.size[y]
end

function Node:update_layout()
  if self.type == "leaf" then
    local av = self.active_view
    if #self.views > 1 then
      local _, _, _, th = self:get_tab_rect(1)
      av.position.x = self.position.x
      av.position.y = self.position.y + th
      av.size.x     = self.size.x
      av.size.y     = self.size.y - th
    else
      copy_pos_size(av, self)
    end
  else
    local x1, y1 = self.a:get_locked_size()
    local x2, y2 = self.b:get_locked_size()
    if self.type == "hsplit" then
      calc_split_sizes(self, "x", "y", x1, x2)
    else -- vsplit
      calc_split_sizes(self, "y", "x", y1, y2)
    end
    self.a:update_layout()
    self.b:update_layout()
  end
end

function Node:propagate(fn, ...)
  self.a[fn](self.a, ...)
  self.b[fn](self.b, ...)
end

function Node:on_mouse_moved(x, y, ...)
  self.hovered_tab = self:get_tab_overlapping_point(x, y)
  if self.type == "leaf" then
    self.active_view:on_mouse_moved(x, y, ...)
  else
    self:propagate("on_mouse_moved", x, y, ...)
  end
end

function Node:on_mouse_released(...)
  if self.type == "leaf" then
    self.active_view:on_mouse_released(...)
  else
    self:propagate("on_mouse_released", ...)
  end
end

function Node:update()
  if self.type == "leaf" then
    for _, view in ipairs(self.views) do view:update() end
  else
    self.a:update()
    self.b:update()
  end
end

function Node:draw_tabs()
  local x, y, _, h = self:get_tab_rect(1)
  local ds = style.divider_size

  core.push_clip_rect(x, y, self.size.x, h)
  renderer.draw_rect(x, y, self.size.x, h, style.background2)
  renderer.draw_rect(x, y + h - ds, self.size.x, ds, style.divider)

  for i, view in ipairs(self.views) do
    local tx, ty, tw, th = self:get_tab_rect(i)
    local text  = view:get_name()
    local color = style.dim

    if view == self.active_view then
      color = style.text
      renderer.draw_rect(tx, ty, tw, th, style.background)
      renderer.draw_rect(tx + tw, ty, ds, th, style.divider)
      renderer.draw_rect(tx - ds, ty, ds, th, style.divider)
    end
    if i == self.hovered_tab then color = style.text end

    core.push_clip_rect(tx, ty, tw, th)
    local cx = tx + style.padding.x
    local cw = tw - style.padding.x * 2
    local close_w  = style.font:get_width("x")
    local text_w   = style.font:get_width(text)
    local avail_w  = cw - close_w - style.padding.x

    local align = text_w > avail_w and "left" or "center"
    common.draw_text(style.font, color, text, align, cx, ty, avail_w, th)
    common.draw_text(style.font, color, "x", "right", cx + cw - close_w, ty, close_w, th)
    core.pop_clip_rect()
  end
  core.pop_clip_rect()
end

function Node:draw()
  if self.type == "leaf" then
    if #self.views > 1 then self:draw_tabs() end
    local pos, size = self.active_view.position, self.active_view.size
    core.push_clip_rect(pos.x, pos.y, size.x + pos.x % 1, size.y + pos.y % 1)
    self.active_view:draw()
    core.pop_clip_rect()
  else
    local x, y, w, h = self:get_divider_rect()
    renderer.draw_rect(x, y, w, h, style.divider)
    self:propagate("draw")
  end
end

return Node