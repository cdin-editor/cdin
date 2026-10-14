local core      = require "core"
local common    = require "core.utils.common"
local config    = require "core.config"
local style     = require "core.style"
local keymap    = require "core.input.keymap"
local translate = require "core.doc.translate"
local View      = require "core.views.view"

local DocView = View:extend()

local _text_direction
local function text_direction_module()
  if _text_direction == nil then
    local ok, m = pcall(require, "core.text")
    _text_direction = (ok and m) or false
  end
  return _text_direction or nil
end

local BLINK_PERIOD = 0.8

DocView.translate = {
  ["previous_page"] = function(doc, line, col, dv)
    local min, max = dv:get_visible_line_range()
    return line - (max - min), 1
  end,
  ["next_page"] = function(doc, line, col, dv)
    local min, max = dv:get_visible_line_range()
    return line + (max - min), 1
  end,
  ["previous_line"] = function(doc, line, col, dv)
    if line == 1 then return 1, 1 end
    return dv:_move_to_line_offset(line, col, -1)
  end,
  ["next_line"] = function(doc, line, col, dv)
    if line == #doc.lines then return #doc.lines, math.huge end
    return dv:_move_to_line_offset(line, col, 1)
  end,
}

function DocView:new(doc)
  DocView.super.new(self)
  self.cursor     = "ibeam"
  self.scrollable = true
  self.doc        = assert(doc)
  self.font       = "code_font"
  self.last_x_offset = {}
  self.blink_timer   = 0
  self._gutter_width  = 0   -- cached; recomputed when line count changes
  self._gutter_lines  = 0   -- line count at last gutter_width computation
end

function DocView:try_close(do_close)
  if self.doc:is_dirty()
  and #core.get_views_referencing_doc(self.doc) == 1 then
    core.command_view:enter("Unsaved Changes; Confirm Close", function(_, item)
      if item.text:match("^[cC]") then do_close()
      elseif item.text:match("^[sS]") then self.doc:save(); do_close()
      end
    end, function(text)
      local items = {}
      if not text:find("^[^cC]") then items[#items+1] = "Close Without Saving" end
      if not text:find("^[^sS]") then items[#items+1] = "Save And Close" end
      return items
    end)
  else
    do_close()
  end
end

function DocView:get_name()
  local post = self.doc:is_dirty() and "*" or ""
  return self.doc:get_name():match("[^/%\\]*$") .. post
end

function DocView:get_font()           return style[self.font] end
function DocView:get_line_height()    return math.floor(self:get_font():get_height() * config.line_height) end
function DocView:get_gutter_width()
  local n = #self.doc.lines
  if n ~= self._gutter_lines then
    self._gutter_lines = n
    self._gutter_width = self:get_font():get_width(n) + style.padding.x * 2
  end
  return self._gutter_width
end
function DocView:get_scrollable_size() return self:get_line_height() * (#self.doc.lines - 1) + self.size.y end

function DocView:get_line_screen_position(idx)
  local x, y = self:get_content_offset()
  return x + self:get_gutter_width(), y + (idx - 1) * self:get_line_height() + style.padding.y
end

function DocView:get_line_text_y_offset()
  return (self:get_line_height() - self:get_font():get_height()) / 2
end

function DocView:get_visible_line_range()
  local x, y, x2, y2 = self:get_content_bounds()
  local lh  = self:get_line_height()
  local min = math.max(1, math.floor(y / lh))
  local max = math.min(#self.doc.lines, math.floor(y2 / lh) + 1)
  return min, max
end

function DocView:get_col_x_offset(line, col)
  local text = self.doc.lines[line]
  if not text or type(col) ~= "number" then return 0 end
  col = math.max(1, math.min(col, #text + 1))
  local prefix = text:sub(1, col - 1)
  if #prefix > 8192 then prefix = prefix:sub(-8192) end
  local ok, w = pcall(self.get_font, self)
  if not ok then return 0 end
  local ok2, width = pcall(w.get_width, w, prefix)
  return (ok2 and type(width) == "number") and width or 0
end

function DocView:get_x_offset_col(line, x)
  local text    = self.doc.lines[line]
  local xoffset, last_i, i = 0, 1, 1
  for char in common.utf8_chars(text) do
    local w = self:get_font():get_width(char)
    if xoffset >= x then
      return (xoffset - x > w / 2) and last_i or i
    end
    xoffset = xoffset + w
    last_i  = i
    i       = i + #char
  end
  return #text
end

function DocView:resolve_screen_position(x, y)
  local ox, oy = self:get_line_screen_position(1)
  local line   = math.floor((y - oy) / self:get_line_height()) + 1
  line = common.clamp(line, 1, #self.doc.lines)
  return line, self:get_x_offset_col(line, x - ox)
end

function DocView:_move_to_line_offset(line, col, offset)
  local xo = self.last_x_offset
  if xo.line ~= line or xo.col ~= col then
    xo.offset = self:get_col_x_offset(line, col)
  end
  xo.line = line + offset
  xo.col  = self:get_x_offset_col(line + offset, xo.offset)
  return xo.line, xo.col
end

function DocView:scroll_to_line(line, ignore_if_visible, instant)
  local min, max = self:get_visible_line_range()
  if not (ignore_if_visible and line > min and line < max) then
    local lh = self:get_line_height()
    self.scroll.to.y = math.max(0, lh * (line - 1) - self.size.y / 2)
    if instant then self.scroll.y = self.scroll.to.y end
  end
end

function DocView:scroll_to_make_visible(line, col)
  local lh            = self:get_line_height()
  local visible_lines = math.max(1, math.floor(self.size.y / lh))
  local margin        = math.min(config.scrolloff, math.floor((visible_lines - 1) / 2))
  self.scroll.to.y    = math.min(self.scroll.to.y, lh * (line - 1 - margin))
  self.scroll.to.y    = math.max(self.scroll.to.y, lh * (line + margin + 1) - self.size.y)
  local gw     = self:get_gutter_width()
  local xoffset = self:get_col_x_offset(line, col)
  self.scroll.to.x = math.max(0, xoffset - self.size.x + gw + self.size.x / 5)
end

local function mouse_selection(doc, clicks, line1, col1, line2, col2)
  local swap = line2 < line1 or (line2 == line1 and col2 <= col1)
  if swap then line1, col1, line2, col2 = line2, col2, line1, col1 end
  if clicks == 2 then
    line1, col1 = translate.start_of_word(doc, line1, col1)
    line2, col2 = translate.end_of_word(doc, line2, col2)
  elseif clicks == 3 then
    if line2 == #doc.lines and doc.lines[#doc.lines] ~= "\n" then
      doc:insert(math.huge, math.huge, "\n")
    end
    line1, col1, line2, col2 = line1, 1, line2 + 1, 1
  end
  if swap then return line2, col2, line1, col1 end
  return line1, col1, line2, col2
end

function DocView:on_mouse_pressed(button, x, y, clicks)
  if DocView.super.on_mouse_pressed(self, button, x, y, clicks) then return end
  if keymap.modkeys["shift"] and clicks == 1 then
    local line1, col1 = select(3, self.doc:get_selection())
    local line2, col2 = self:resolve_screen_position(x, y)
    self.doc:set_selection(line2, col2, line1, col1)
  else
    local line, col = self:resolve_screen_position(x, y)
    self.doc:set_selection(mouse_selection(self.doc, clicks, line, col, line, col))
    self.mouse_selecting = { line, col, clicks = clicks }
  end
  self.blink_timer = 0
end

function DocView:on_mouse_moved(x, y, ...)
  DocView.super.on_mouse_moved(self, x, y, ...)
  self.cursor = (self:scrollbar_overlaps_point(x, y) or self.dragging_scrollbar)
    and "arrow" or "ibeam"
  if self.mouse_selecting then
    local l1, c1   = self:resolve_screen_position(x, y)
    local l2, c2   = table.unpack(self.mouse_selecting)
    local clicks   = self.mouse_selecting.clicks
    self.doc:set_selection(mouse_selection(self.doc, clicks, l1, c1, l2, c2))
  end
end

function DocView:on_mouse_released(button)
  DocView.super.on_mouse_released(self, button)
  self.mouse_selecting = nil
end

function DocView:on_text_input(text)
  self.doc:text_input(text)
end

function DocView:update()
  local line, col = self.doc:get_selection()

  if (line ~= self.last_line or col ~= self.last_col) and self.size.x > 0 then
    if core.active_view == self then
      self:scroll_to_make_visible(line, col)
    end
    self.blink_timer        = 0
    self.last_line, self.last_col = line, col
  end

  if self == core.active_view and not self.mouse_selecting then
    local n    = BLINK_PERIOD / 2
    local prev = self.blink_timer
    self.blink_timer = (self.blink_timer + 1 / config.fps) % BLINK_PERIOD
    if (self.blink_timer > n) ~= (prev > n) then core.redraw = true end
  end

  DocView.super.update(self)
end

function DocView:draw_line_highlight(x, y)
  renderer.draw_rect(x, y, self.size.x, self:get_line_height(), style.line_highlight)
end

function DocView:draw_line_text(idx, x, y)
  local tx, ty = x, y + self:get_line_text_y_offset()
  local font   = self:get_font()
  local dir = config.direction or "auto"
  if dir == "ltr" then
    for _, type, text in self.doc.highlighter:each_token(idx) do
      tx = renderer.draw_text(font, text, tx, ty, style.syntax[type])
    end
    return
  end
  local line = self.doc.lines[idx]
  if type(line) ~= "string" then return end

  -- Pure-ASCII lines cannot contain RTL codepoints: every RTL script starts
  -- above U+0590. One find() over the line replaces a per-codepoint decode
  -- loop, and source code is ASCII for the overwhelming majority of lines, so
  -- this is the case that has to be cheap. A single non-ASCII byte falls
  -- through to the exact check below.
  if not line:find("[^\0-\127]") then
    for _, type, text in self.doc.highlighter:each_token(idx) do
      tx = renderer.draw_text(font, text, tx, ty, style.syntax[type])
    end
    return
  end

  -- Does this line contain any RTL codepoint at all? Asked of the line that
  -- already exists, so the common case (an ordinary LTR source line) never
  -- builds the token table, the second string array and the concatenated
  -- copy that this function used to allocate on every drawn line, every frame.
  --
  -- Checking the line rather than each token is equivalent for a covering token
  -- set and is *more* correct when it is not: bidi.has_rtl scans for any
  -- codepoint of class "R", and a character no token claims would otherwise be
  -- invisible to the check.
  local textmod = text_direction_module()
  if not textmod or not textmod.bidi.has_rtl(line) then
    for _, type, text in self.doc.highlighter:each_token(idx) do
      tx = renderer.draw_text(font, text, tx, ty, style.syntax[type])
    end
    return
  end

  local toks = {}
  for _, type, text in self.doc.highlighter:each_token(idx) do
    toks[#toks + 1] = { type = type, text = text }
  end
  if #toks == 0 then return end
  local shaping = config.shaping_enabled ~= false
  local full = {}
  for _, t in ipairs(toks) do full[#full + 1] = t.text end
  full = table.concat(full)
  local shaped = shaping and textmod.shaper.shape(full) or full
  local visual = textmod.bidi.visual(shaped, dir)
  tx = renderer.draw_text(font, visual, tx, ty, style.syntax[toks[1].type] or style.syntax["normal"])
end

-- Draw all occurrences of the current search term on this line
function DocView:draw_line_search_highlights(idx, x, y)
  -- core.findreplace is set lazily when the module is first used
  local fr = rawget(core, "findreplace")
  if not fr then return end
  local hl = fr.get_highlight(self.doc)
  if not hl or not hl.text or hl.text == "" then return end

  local lh   = self:get_line_height()
  local text = hl.text
  local opt  = hl.opt or {}
  local line_text = self.doc.lines[idx]
  if not line_text then return end

  -- highlight colour: slightly brighter than line_highlight, distinct from selection
  local hl_color = style.search_highlight or { common.lerp(
    style.line_highlight, style.selection, 0.6) }
  -- fallback if theme doesn't define search_highlight
  if not style.search_highlight then
    hl_color = { 255, 200, 0, 80 }
  end

  local search_text = opt.no_case and text:lower() or text
  local src_text    = opt.no_case and line_text:lower() or line_text
  local col = 1
  while true do
    local s, e
    if opt.pattern then
      s, e = src_text:find(search_text, col)
    else
      s, e = src_text:find(search_text, col, true)
    end
    if not s then break end
    local x1 = x + self:get_col_x_offset(idx, s)
    local x2 = x + self:get_col_x_offset(idx, e + 1)
    renderer.draw_rect(x1, y, math.max(x2 - x1, 1), lh, hl_color)
    col = e + 1
    if col > #line_text then break end
  end
end


function DocView:draw_line_body(idx, x, y)
  local line, col         = self.doc:get_selection()
  local line1, col1, line2, col2 = self.doc:get_selection(true)
  local lh = self:get_line_height()

  -- draw search highlights first (behind selection)
  self:draw_line_search_highlights(idx, x, y)

  if idx >= line1 and idx <= line2 then
    local text = self.doc.lines[idx]
    local c1   = (line1 ~= idx) and 1 or col1
    local c2   = (line2 ~= idx) and #text + 1 or col2
    local x1   = x + self:get_col_x_offset(idx, c1)
    local x2   = x + self:get_col_x_offset(idx, c2)
    renderer.draw_rect(x1, y, x2 - x1, lh, style.selection)
  end

  if config.highlight_current_line and not self.doc:has_selection()
  and line == idx and core.active_view == self then
    self:draw_line_highlight(x + self.scroll.x, y)
  end

  self:draw_line_text(idx, x, y)

  if line == idx and core.active_view == self and system.window_has_focus()
  and self.blink_timer < BLINK_PERIOD / 2 then
    local x1 = x + self:get_col_x_offset(line, col)
    renderer.draw_rect(x1, y, style.caret_width, lh, style.caret)
  end
end

function DocView:draw_line_gutter(idx, x, y)
  local line1, _, line2 = self.doc:get_selection(true)
  local on_caret        = idx >= line1 and idx <= line2
  local color           = on_caret and style.line_number2 or style.line_number
  local number          = (config.line_number_relative and not on_caret)
    and math.abs(idx - line1) or idx
  renderer.draw_text(self:get_font(), number, x + style.padding.x,
    y + self:get_line_text_y_offset(), color)
end

function DocView:draw()
  self:draw_background(style.background)

  local font = self:get_font()
  font:set_tab_width(font:get_width(" ") * config.indent_size)

  local min, max = self:get_visible_line_range()
  local lh       = self:get_line_height()
  local gw       = self:get_gutter_width()

  local _, gy = self:get_line_screen_position(min)
  for i = min, max do
    self:draw_line_gutter(i, self.position.x, gy)
    gy = gy + lh
  end

  local bx, by = self:get_line_screen_position(min)
  core.push_clip_rect(self.position.x + gw, self.position.y, self.size.x, self.size.y)
  for i = min, max do
    self:draw_line_body(i, bx, by)
    by = by + lh
  end
  core.pop_clip_rect()

  self:draw_scrollbar()
end

return DocView