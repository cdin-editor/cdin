-- bench_draw_line.lua — cost and allocation rate of the per-line draw path.
--
-- WHY THIS BENCHMARK EXISTS
-- AGENTS.md §7 forbids per-line and per-token tables for text and allocations on
-- the steady-state draw path. DocView:draw_line_text() (data/core/views/docview.lua)
-- is the place those rules apply to, and config.direction defaults to "auto", so
-- the expensive branch is the DEFAULT branch, not an opt-in one.
--
-- WHAT IT MEASURES, EXACTLY
-- The real DocView, the real Highlighter, the real tokenizer and the real
-- core.text.bidi — loaded from data/, not reimplemented here. Only `renderer`
-- is stubbed, because the Lua binding is not what is under test; the C side is
-- measured separately by bench_rencache.c.
--
-- Two numbers per line:
--
--   time    os.clock() CPU seconds. A CPU-bound benchmark, so this is process
--           CPU time, NOT wall time, and is labelled as such.
--   bytes   Lua heap growth with the collector STOPPED across the measured
--           loop, so it is bytes allocated and not bytes that happened to
--           survive. This is the number AGENTS.md §8 means by "the counter must
--           not move across 1000 frames of typing".
--
-- Run: lua tests/bench/bench_draw_line.lua [lines] [reps]

package.path = "data/?.lua;data/?/init.lua;tests/bench/?.lua;" .. package.path

local _stub = dofile("scripts/_stub_env.lua")
package.preload["fs"]   = function() return _stub.fs end
package.preload["path"] = function() return _stub.path end

-- The highlighter registers an incremental-tokenizing thread in new(). This
-- benchmark drives the editor's own draw path without running core.step(), so
-- there is no thread scheduler to call it. A no-op is the honest equivalent of
-- "the background worker never runs": get_line() still tokenizes on demand,
-- which is exactly the lazy behaviour being measured.
core_stub_add_thread = nil

rawset(_G, "SCALE", 1)
rawset(_G, "VERSION", "bench")
rawset(_G, "PLATFORM", "bench")
rawset(_G, "EXEDIR", ".")
rawset(_G, "EXEFILE", "./cdin")
rawset(_G, "ARGS", {})
rawset(_G, "PATHSEP", package.config:sub(1, 1))
rawset(_G, "LOGFILE", "")

-- ── the host stubs ────────────────────────────────────────────────────────────
--
-- `renderer` is deliberately the CHEAPEST thing that can legally be a draw_text:
-- it counts the call and advances x. Making it expensive would fold the C
-- renderer's cost into a number labelled "Lua draw path", and making it free
-- would hide the real per-call boundary crossing. bench_rencache.c covers the
-- other half.
local draw_calls = 0

-- A font that measures like a monospace one. get_width is O(1) per call here on
-- purpose: suspect D (repeated prefix measurement) is measured on its own, and
-- folding a synthetic O(n) cost in here would blur the two.
local BENCH_FONT = {
  get_height = function() return 16 end,
  get_width  = function(self, s) return #s * 8 end,
}
local BIG_FONT = {
  get_height = function() return 34 end,
  get_width  = function(self, s) return #s * 16 end,
}
local ICON_FONT = {
  get_height = function() return 16 end,
  get_width  = function(self, s) return #s * 8 end,
}

-- style.lua loads four real fonts at require time, so the stub has to answer
-- `renderer.font.load` or core.style cannot be loaded at all.
rawset(_G, "renderer", {
  draw_text = function(font, text, x, y, color)
    draw_calls = draw_calls + 1
    return x + #text
  end,
  draw_rect = function(x, y, w, h, c) return draw_calls end,
  draw_image = function(img, sub, x, y, c) return draw_calls end,
  set_clip_rect = function(r) end,
  font = {
    load = function(path, size)
      if type(path) ~= "string" then return BENCH_FONT end
      if path:find("icons") then return ICON_FONT end
      return BENCH_FONT
    end,
    add_fallback   = function() end,
    get_height     = function() return 16 end,
    get_width      = function(self, s) return #s * 8 end,
    set_tab_width  = function() end,
    get_tab_width  = function() return 4 end,
  },
})

rawset(_G, "system", {
  get_file_info = function() return nil end,
  get_time      = function() return 0 end,
  fuzzy_match   = function() return nil end,
  list_dir      = function() return {} end,
  jobs_run      = function() end,
  jobs_pending  = function() return 0 end,
  sleep         = function() end,
})

-- ── the real code under test ──────────────────────────────────────────────────
-- core.runtime.strict makes reading an undefined global a hard error, so every
-- host global data/core reads at require time (renderer, system) is already set
-- above. Highlighter:new registers a thread and there is no scheduler here.
local _core = require "core"
_core.add_thread = function() return nil end

-- Syntax definitions live in cdin-x, which a benchmark cannot fetch. Without
-- them every line tokenizes to ONE token, and the per-token cost this
-- benchmark exists to measure would be invisible. Register a small Lua syntax
-- so token density matches a real source file. Guarded so a real site bundle
-- still wins.
local syntax = require "core.syntax"
if #syntax.items == 0 then
  syntax.add({
    files = { "%.lua$" },
    symbols = {
      ["local"] = "keyword", ["function"] = "keyword", ["end"] = "keyword",
      ["return"] = "keyword", ["if"] = "keyword", ["then"] = "keyword",
      ["for"] = "keyword", ["do"] = "keyword", ["in"] = "keyword",
      ["true"] = "keyword", ["false"] = "keyword", ["nil"] = "keyword",
      ["and"] = "keyword", ["or"] = "keyword", ["not"] = "keyword",
    },
    patterns = {
      { type = "comment", pattern = "%-%-.*$" },
      { type = "string",  pattern = '".*"' },
      { type = "string",  pattern = "'.*'" },
      { type = "number",  pattern = "%d+%.?%d*" },
      { type = "keyword", pattern = "%a[%w_]*" },
      { type = "normal",  pattern = "%s+" },
      { type = "normal",  pattern = "%a[%w_]*" },
      { type = "normal",  pattern = "." },
    },
  })
end

local DocView    = require "core.views.docview"
local Highlighter = require "core.doc.highlighter"
local config     = require "core.config"
local style      = require "core.style"

-- DocView:new() sets self.font = "code_font", and DocView:get_font() is
-- style[self.font]. Draw calls need a font that answers get_width/get_height
-- without touching the C renderer, and whose answers are O(1) per call.
style.code_font = BENCH_FONT
style.default   = BENCH_FONT

-- ── a realistic source file, so token counts are real ────────────────────────
local function make_source(n_lines)
  local out = {}
  for i = 1, n_lines do
    if i % 7 == 0 then
      out[#out + 1] = '-- a comment line ' .. i .. ' with some words in it'
    elseif i % 5 == 0 then
      out[#out + 1] = 'local x' .. i .. ' = compute(' .. i .. ', "a string literal here")'
    else
      out[#out + 1] = 'function handler_' .. i .. '(request, response) return response end'
    end
  end
  return out
end

local function make_doc(lines)
  local doc = {
    lines   = lines,
    syntax  = syntax.get("bench.lua"),
    highlighter = Highlighter,
  }
  doc.highlighter = Highlighter(doc)
  return doc
end

-- ── the measurement ───────────────────────────────────────────────────────────
local function measure(label, fn, lines, reps)
  -- Warm up with a FULL pass over every line, not a fraction of one: the
  -- highlighter tokenizes lazily, so a partial warmup would fold one-time
  -- tokenization of the remaining lines into the measured window.
  fn(lines, 1)

  collectgarbage("collect")
  collectgarbage("stop")
  local k0 = collectgarbage("count")
  local t0 = os.clock()
  fn(lines, reps)
  local t1 = os.clock()
  local k1 = collectgarbage("count")
  collectgarbage("restart")
  collectgarbage("collect")

  local cpu_ms   = (t1 - t0) * 1000
  local per_line = cpu_ms / lines
  local bytes    = (k1 - k0) * 1024
  local bpl      = bytes / lines

  print(string.format(
    "%-34s  %4d lines x %-5d  %8.1f ms  %7.4f ms/line  %10.0f B/line  %10.1f KiB total",
    label, lines, reps, cpu_ms, per_line, bpl, bytes / 1024))
  return per_line, bpl
end

local N_LINES = tonumber(arg and arg[1]) or 400
local REPS    = tonumber(arg and arg[2]) or 50

print(string.format("config.direction = %q   shaping_enabled = %s   lua = %s",
  tostring(config.direction), tostring(config.shaping_enabled),
  tostring(_VERSION and _VERSION:match("%d+%.%d+") or "?")))
print("renderer.draw_text is a counting stub; the C renderer is bench_rencache.c")
print("")

local doc    = make_doc(make_source(N_LINES))
local view   = DocView(doc)
view.size    = { x = 800, y = 600 }
view.position = { x = 0, y = 0 }
view.doc     = doc

print("-- draw_line_text, one pass over the whole document per rep --")

local function draw_all(lines, reps)
  for _ = 1, reps do
    for i = 1, lines do
      view:draw_line_text(i, 0, i * 16)
    end
  end
end

measure("draw_line_text (direction=auto)", draw_all, N_LINES, REPS)

-- The same work with direction forced to ltr, which is the branch that does
-- NOT build token tables. This is the control: the difference between the two
-- rows is what the auto path costs beyond the drawing itself.
local saved_dir = config.direction
config.direction = "ltr"
draw_all(N_LINES, 1)
measure("draw_line_text (direction=ltr)", draw_all, N_LINES, REPS)
config.direction = saved_dir

-- A very long line: the concat and the has_rtl scan are O(line length), so this
-- is where a per-line cost that looks flat on short lines becomes visible.
local LONG = 4000
local long_lines = {}
long_lines[1] = string.rep("x = f(a, b) -- ", math.floor(LONG / 15))
local long_doc  = make_doc(long_lines)
local long_view = DocView(long_doc)
long_view.size = { x = 800, y = 600 }
long_view.doc  = long_doc
print(string.format("\n-- one line of %d bytes, %d reps --", #long_lines[1], REPS))
local function draw_all_long()
  for _ = 1, REPS do
    for i = 1, #long_lines do long_view:draw_line_text(i, 0, 0) end
  end
end
measure("draw_line_text (one long line)", draw_all_long, #long_lines, REPS)

-- D: cursor movement and hit-testing
--
-- get_col_x_offset() takes a text prefix and asks the font for its width;
-- get_x_offset_col() walks the line char by char asking the width of EACH one.
-- The real font measures O(n) per call (glyph lookups per codepoint), so this
-- section uses a font that does exactly that: one pass over its argument. With a
-- constant-width stand-in the shape of the curve would be invisible and only the
-- number of calls would show.
local NARROW = {
  get_height = function() return 16 end,
  get_width  = function(self, s)
    -- one pass over the string, like the real renderer's per-codepoint loop
    local w = 0
    for _ = 1, #s do w = w + 8 end
    return w
  end,
}
local col_doc   = make_doc(make_source(N_LINES))
local col_view  = DocView(col_doc)
col_view.size  = { x = 800, y = 600 }
col_view.doc   = col_doc
style.code_font = NARROW
print("\n-- get_col_x_offset / get_x_offset_col, font measures O(#chars) --")

local function col_only(reps)
  for _ = 1, reps do
    for i = 1, N_LINES do
      col_view:get_col_x_offset(i, math.max(1, #col_doc.lines[i] - 3))
    end
  end
end
measure("get_col_x_offset only", col_only, N_LINES, REPS)

local function hit_only(reps)
  for _ = 1, reps do
    for i = 1, N_LINES do
      col_view:get_x_offset_col(i, 120)
    end
  end
end
measure("get_x_offset_col only", hit_only, N_LINES, REPS)

-- Is the 275 KB/call in the iterator or in the font call? Iterate the same
-- iterator with a font that does nothing at all.
local FREE = { get_height = function() return 16 end, get_width = function() return 0 end }
style.code_font = FREE
local function iter_only(reps)
  for _ = 1, reps do
    for i = 1, N_LINES do
      local n = 0
      for _c in require("core.utils.common").utf8_chars(col_doc.lines[i]) do n = n + 1 end
    end
  end
end
measure("utf8_chars iteration only (free font)", iter_only, N_LINES, REPS)

-- The same iteration with pcall(require, ...) removed. If the byte count
-- collapses, the cost is in that call and not in gmatch.
local uf8 = require "core.text.utf8"
local function gmatch_only(reps)
  for _ = 1, reps do
    for i = 1, N_LINES do
      local n = 0
      for _c in uf8.chars(col_doc.lines[i]) do n = n + 1 end
    end
  end
end
measure("utf8.chars direct, no pcall(require)", gmatch_only, N_LINES, REPS)

-- Control: an empty loop through the same line array. If this also reports
-- ~275 KB/line at N_LINES=400, the figure above is a harness artifact (the
-- GC-stopped window counts one-time work that happens to be attributed per
-- line) and not a property of the code under test.
local function noop(reps)
  for _ = 1, reps do
    for i = 1, N_LINES do local _l = col_doc.lines[i] end
  end
end
measure("NO-OP control (index the array)", noop, N_LINES, REPS)