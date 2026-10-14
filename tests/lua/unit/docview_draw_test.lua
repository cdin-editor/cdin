local T = require "harness"
local env = require "dv_env"

local DocView, Highlighter, config, style, syntax =
  env.DocView, env.Highlighter, env.config, env.style, env.syntax

-- Syntax definitions live in cdin-x. Without them every line tokenizes to one
-- "normal" token and the per-token behaviour under test would be invisible.
if #syntax.items == 0 then
  syntax.add({
    files = { "%.lua$" },
    symbols = { ["local"] = "keyword", ["function"] = "keyword", ["end"] = "keyword" },
    patterns = {
      { type = "comment", pattern = "%-%-.*$" },
      { type = "string",  pattern = '".*"' },
      { type = "number",  pattern = "%d+%.?%d*" },
      { type = "keyword", pattern = "%a[%w_]*" },
      { type = "normal",  pattern = "%s+" },
      { type = "normal",  pattern = "%a[%w_]*" },
      { type = "normal",  pattern = "." },
    },
  })
end

-- A doc with a real highlighter, so each_token() returns real cached tokens.
local function doc_with(lines)
  local doc = { lines = lines, syntax = syntax.get("t.lua") }
  doc.highlighter = Highlighter(doc)
  return doc
end

-- Capture the draw_text sequence instead of submitting it.
local function capturing_renderer()
  local calls = {}
  T.stub("renderer", {
    draw_text = function(font, text, x, y, color)
      calls[#calls + 1] = { text = text, color = color }
      return x + #text
    end,
    draw_rect = function() end,
    draw_image = function() end,
    set_clip_rect = function() end,
  })
  return calls
end

local function view_for(doc)
  local v = DocView(doc)
  v.size = { x = 800, y = 600 }
  v.doc  = doc
  return v
end

local saved_dir = config.direction
local function with_direction(dir, fn)
  config.direction = dir
  local ok, err = pcall(fn)
  config.direction = saved_dir
  if not ok then error(err, 0) end
end

-- ── the default path must draw one command per token ───────────────────────
with_direction("auto", function()
  local calls = capturing_renderer()
  local view  = view_for(doc_with({ "local x = 1" }))
  view:draw_line_text(1, 0, 0)

  T.ok(#calls >= 3, "an ascii line draws one command per token (got " .. #calls .. ")")
  local texts = {}
  for _, c in ipairs(calls) do texts[#texts + 1] = c.text end
  T.eq(table.concat(texts), "local x = 1",
    "the per-token commands reconstruct the line exactly, with no extra copy")
  for i, c in ipairs(calls) do
    T.eq(type(c.color), "table", "token " .. i .. " carries a syntax color")
  end
  T.eq(calls[1].color, style.syntax.keyword, "a keyword token keeps its keyword color")
end)

-- ── an RTL line must still take the shaping path ───────────────────────────
with_direction("auto", function()
  local calls = capturing_renderer()
  local view  = view_for(doc_with({ "سلام" }))
  view:draw_line_text(1, 0, 0)

  T.eq(#calls, 1, "an rtl line is drawn as one shaped visual run")
  T.eq(calls[1].text, "ﻡﻼﺳ", "the rtl run is shaped then reversed for display")
end)

-- ── mixed ltr/rtl is detected from the line, not from a token boundary ─────
with_direction("auto", function()
  local calls = capturing_renderer()
  local view  = view_for(doc_with({ "abc سلام def" }))
  view:draw_line_text(1, 0, 0)

  T.eq(#calls, 1, "a mixed line is drawn as one shaped run")
  T.eq(calls[1].text, "abc  ﻡﻼﺳdef", "ltr base: rtl run mirrored in place")
end)

-- ── forced ltr never shapes, even for rtl text ────────────────────────────
with_direction("ltr", function()
  local calls = capturing_renderer()
  local view  = view_for(doc_with({ "سلام" }))
  view:draw_line_text(1, 0, 0)

  T.ok(#calls >= 1, "direction=ltr draws the line")
  local joined = {}
  for _, c in ipairs(calls) do joined[#joined + 1] = c.text end
  T.eq(table.concat(joined), "سلام", "direction=ltr does not reverse an rtl run")
end)

-- ── an empty line draws nothing ───────────────────────────────────────────
with_direction("auto", function()
  local calls = capturing_renderer()
  local view  = view_for(doc_with({ "" }))
  view:draw_line_text(1, 0, 0)
  T.eq(#calls, 0, "an empty line submits no draw commands")
end)

-- ── a missing line is safe ────────────────────────────────────────────────
with_direction("auto", function()
  local calls = capturing_renderer()
  local view  = view_for(doc_with({ "x" }))
  view:draw_line_text(99, 0, 0)
  T.eq(#calls, 0, "a line index past the end submits no draw commands")
end)

-- ── the steady-state rule: no allocation on the per-line draw path ─────────
-- AGENTS.md §7 forbids per-line tables and draw-path allocation. Measured
-- with the collector stopped, so this is bytes allocated, not bytes that
-- merely survived.
--
-- The capturing renderer is released FIRST: it builds a table per draw_text
-- call, and T.unstub_all only runs after the whole file, so leaving it
-- installed would measure the capture harness rather than the draw path.
with_direction("auto", function()
  T.unstub("renderer")
  local view = view_for(doc_with({ "local x = 1 -- note", "function f() return 2 end" }))
  for i = 1, 2 do view:draw_line_text(i, 0, 0) end   -- warm the highlighter

  collectgarbage("collect")
  collectgarbage("stop")
  local k0 = collectgarbage("count")
  for _ = 1, 200 do
    view:draw_line_text(1, 0, 0)
    view:draw_line_text(2, 0, 0)
  end
  local k1 = collectgarbage("count")
  collectgarbage("restart")
  collectgarbage("collect")

  local bytes = (k1 - k0) * 1024
  T.ok(bytes < 512,
    "the default draw path allocates nothing measurable (got " ..
    string.format("%.0f", bytes) .. " bytes over 400 line draws)")
end)

-- ── editing a line must change what is drawn (no stale cached verdict) ────
with_direction("auto", function()
  local doc  = doc_with({ "abc" })
  local view = view_for(doc)
  view:draw_line_text(1, 0, 0)

  local calls = capturing_renderer()
  doc.lines[1] = "سلام"
  view:draw_line_text(1, 0, 0)
  T.eq(#calls, 1, "replacing an ltr line with an rtl one is detected")
  T.eq(calls[1].text, "ﻡﻼﺳ", "the new rtl line is shaped")
end)