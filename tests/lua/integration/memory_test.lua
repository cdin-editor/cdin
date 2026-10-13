local T = require "harness"

-- core.memory: the accounting a "why is it big" question gets answered with.
--
-- Two things are worth testing here, and one of them is a bug this module would
-- otherwise ship:
--
--  1. The report never claims a number it does not have. A missing measurement
--     and a measurement of zero are different facts, and a memory report that
--     prints "0 bytes of glyphs" when the host cannot measure glyphs is worse
--     than one that prints nothing — it is actively misleading about where the
--     memory went.
--  2. doc_ratio, the figure the whole rewrite is aimed at, is computed against
--     the text bytes rather than the file size. Getting that denominator wrong
--     would flatter every measurement in every later phase's report.

T.stub("system", {
  get_file_info = function() return nil end,
  get_time = function() return 0 end,
  fuzzy_match = function() return nil end,
  list_dir = function() return {} end,
  -- Deliberately partial: only some counters exist. The module must not care.
  memory_stats = function()
    return {
      glyph_bytes = 1048576,
      glyph_pages = 12,
      log_bytes = 4096,
      command_buf_peak = 131072,
      command_buf_capacity = 524288,
      draw_text_count = 40,
      draw_rect_count = 7,
    }
  end,
})

local memory = require "core.memory"

-- ── a document's bytes and the ratio over them ──────────────────────────

-- core.memory reads the document list off the global `core`, which is where
-- data/core/init.lua puts it — and the stub has to be the global, not just
-- package.loaded["core"], because the module does not require it.
T.stub("core", { docs = {} })
local core = rawget(_G, "core")

T.eq(memory.stats().doc_count, 0, "no documents, nothing counted")

core.docs = {
  { lines = { "hello\n", "world\n" } },
  { lines = { "a\n", "bb\n", "ccc\n" } },
}
local s = memory.stats()

T.eq(s.doc_count, 2, "two documents counted")
T.eq(s.doc_lines, 5, "five lines counted")
-- "hello\n" 6 + "world\n" 6 + "a\n" 2 + "bb\n" 3 + "ccc\n" 4
T.eq(s.doc_bytes, 21, "doc bytes are the sum of the line strings")
T.ok("doc overhead is counted per line: " and s.doc_overhead > 0)
T.eq(s.doc_total, s.doc_bytes + s.doc_overhead, "total is bytes plus overhead")

-- The Lua heap is mostly unattributed, and saying so is the point. src/fs,
-- src/lua and src/search make no C allocations at all, so every byte they put
-- into Lua belongs to the Lua heap and no per-subsystem tag can see it. A report
-- showing only the total reads as though the per-subsystem table covered the
-- process, which it does not.
local heap_bytes = math.floor(s.lua_kb * 1024)
T.eq(s.lua_attributed, s.doc_bytes + s.doc_overhead,
  "the attributed part of the Lua heap is the documents")
T.eq(s.lua_unattributed, heap_bytes - s.lua_attributed,
  "and the rest is reported as unattributed rather than hidden")
T.eq(s.lua_attributed + s.lua_unattributed, heap_bytes,
  "the two add up to the heap")

-- With no documents the whole heap is unattributed, and the figure must not go
-- negative: lua_bytes is the Lua allocator's own number and a document count
-- taken a moment earlier can exceed it.
core.docs = {}
s = memory.stats()
T.eq(s.lua_attributed, 0, "no documents, nothing attributed")
T.ok("and no negative residue: " and s.lua_unattributed >= 0)

-- Put the documents back AND re-read the stats: the assertions below are about
-- the document ratio, and `s` still describes an empty document list. Leaving it
-- stale made the ratio nil, which is the same falsy-field mistake as everywhere
-- else in this project.
core.docs = { { lines = { "hello\n", "world\n" } },
              { lines = { "a\n", "bb\n", "ccc\n" } } }
s = memory.stats()
T.ok("the ratio is over the text bytes: " and s.doc_ratio > 1.0)
-- The denominator is doc_bytes, not doc_total. Dividing by the total would make
-- the ratio exactly 1.0 always, which is how a 4x figure becomes a 1x figure.
T.ok("doc_ratio is doc_total over doc_bytes: "
     and math.abs(s.doc_ratio - (s.doc_total / s.doc_bytes)) < 1e-9)
T.ok("and so it is not the vacuous 1.0: " and math.abs(s.doc_ratio - 1.0) > 0.001)

-- A document with no lines at all must not be a division by zero, and must not
-- make the whole report nil: a malformed document should show up as one document
-- with no lines, not as an error.
core.docs = { { lines = {} } }
s = memory.stats()
T.eq(s.doc_count, 1, "a document with no lines is still counted")
T.eq(s.doc_lines, 0, "…and contributes no lines")
T.eq(s.doc_bytes, 0, "…and no text bytes")
T.eq(s.doc_ratio, nil, "no ratio when there are no text bytes to divide by")
T.ok(memory.report():find("documents", 1, true) ~= nil,
  "and the report still renders")

-- ── the C counters come through ──────────────────────────────────────────

core.docs = {}
s = memory.stats()
T.eq(s.glyph_bytes, 1048576, "glyph bytes come from the host")
T.eq(s.glyph_pages, 12, "glyph page count comes from the host")
T.eq(s.command_buf_peak, 131072, "command buffer peak comes from the host")
T.eq(s.command_buf_capacity, 524288, "command buffer capacity comes from the host")

-- ── a host that cannot measure reports nothing ───────────────────────────

-- The old host, and the stub in the other suites. memory_stats is absent, and
-- every C-backed field must be absent rather than zero.
local saved = system.memory_stats
system.memory_stats = nil
s = memory.stats()
T.eq(s.glyph_bytes, nil, "no glyph figure when the host cannot measure it")
T.eq(s.log_bytes, nil, "no log figure when the host cannot measure it")
T.eq(s.command_buf_peak, nil, "no command buffer figure when the host cannot measure it")
T.eq(s.doc_count, 0, "the Lua-side figures still work")

local report = memory.report()
T.ok(report:find("memory:", 1, true) ~= nil, "the report still renders")
T.ok(report:find("glyph cache", 1, true) == nil,
  "and omits the rows it cannot fill, rather than printing zeros")
T.ok(report:find("lua heap", 1, true) ~= nil, "while keeping the rows it can")

-- A host that reports a negative size (my sentinel for "off") is shown as off.
system.memory_stats = function()
  return { log_bytes = -1, glyph_bytes = 0, glyph_pages = 0 }
end
report = memory.report()
T.ok(report:find("off", 1, true) ~= nil,
  "a log that is off says so, rather than reporting zero bytes")

system.memory_stats = saved

-- ── the report's shape ───────────────────────────────────────────────────

core.docs = { { lines = { "hello\n" } } }
system.memory_stats = saved
report = memory.report()

T.ok(report:find("lua heap", 1, true) ~= nil, "report: lua heap row")
T.ok(report:find("documents", 1, true) ~= nil, "report: document count row")
T.ok(report:find("doc bytes", 1, true) ~= nil, "report: doc bytes row")
T.ok(report:find("glyph cache", 1, true) ~= nil, "report: glyph cache row")
T.ok(report:find("command buf", 1, true) ~= nil, "report: command buffer row")
T.ok(report:find("log file", 1, true) ~= nil, "report: log file row")
T.ok(report:find("KiB", 1, true) ~= nil, "report: sizes are human-readable")
T.ok(report:find("documents", 1, true) ~= nil and report:find("1 ", 1, true) ~= nil,
  "report: the document count appears")

-- Every row is indented, so the report is readable when it is pasted into the
-- log view as a block.
local lines = {}
for line in report:gmatch("[^\n]+") do lines[#lines + 1] = line end
T.ok(#lines >= 6, "the report has a row per figure")
for _, line in ipairs(lines) do
  if line ~= "memory:" then
    T.ok(line:sub(1, 2) == "  ", "every report row is indented: " .. line)
  end
end

-- ── per-subsystem accounting ──────────────────────────────────────────────
--
-- The shape here is the one src/api/system.c pushes: five parallel arrays
-- (names, tags, alloc_by, peak_by, blocks_by) plus the totals. Written out long
-- hand rather than generated, so that a change on the C side has to be made
-- twice to go unnoticed — which is the point of the exercise. It cannot check
-- that the C code really pushes these; see the note at the end.

system.memory_stats = function()
  return {
    glyph_bytes = 0, glyph_pages = 0, log_bytes = -1,
    names   = { "base", "buffer", "syntax" },
    tags    = { 0, 1, 2 },
    alloc_by = { 100, 4096, 0 },
    peak_by  = { 100, 8192, 0 },
    blocks_by = { 1, 12, 0 },
    alloc_total = 4196,
    peak_total  = 8192,
    live_blocks = 13,
    accounted   = 1,
  }
end

s = memory.stats()
T.eq(#s.subsystems, 3, "one row per subsystem")

-- Sorted by live bytes, biggest first: the question is always "which subsystem".
T.eq(s.subsystems[1].name, "buffer", "the biggest live figure sorts first")
T.eq(s.subsystems[1].live, 4096, "with its live bytes")
T.eq(s.subsystems[1].peak, 8192, "and its own peak, which is higher than live")
T.eq(s.subsystems[1].blocks, 12, "and its block count")
T.eq(s.subsystems[2].name, "base", "then the next biggest")
T.eq(s.subsystems[3].name, "syntax", "and the smallest")

-- A subsystem holding nothing is still listed. "The rope holds nothing" and "the
-- rope does not exist yet" are different answers, and the order of the phases
-- decides which one this is.
T.eq(s.subsystems[3].live, 0, "an empty subsystem reports zero, not nothing")
T.eq(s.subsystems[3].blocks, 0, "and zero blocks")

T.eq(s.alloc_total, 4196, "the total is passed through")
T.eq(s.peak_total, 8192, "and the peak total, which is not the sum of the peaks")
T.eq(s.live_blocks, 13, "the live block count is passed through")
T.eq(s.accounted, 1, "and whether leak counting was even possible")

report = memory.report()
T.ok(report:find("by subsystem", 1, true) ~= nil, "report: the subsystem block header")
-- The header must say these are requested bytes and that the glyph row is a
-- subset of them. `font` legitimately exceeds `glyph cache` because the font
-- subsystem also holds the font files; without that note a reader concludes one
-- of the two numbers is broken.
T.ok(report:find("subset", 1, true) ~= nil,
  "report: the header says the glyph row is a subset, so the two are not in conflict")
T.ok(report:find("buffer", 1, true) ~= nil, "report: a subsystem by name")
T.ok(report:find("TOTAL", 1, true) ~= nil, "report: the subsystem total")

-- Sort stability: equal live figures must not swap between runs, or a diff of
-- two reports looks like a change when nothing changed.
system.memory_stats = function()
  return {
    names = { "zeta", "alpha" }, tags = { 1, 2 },
    alloc_by = { 100, 100 }, peak_by = { 100, 100 }, blocks_by = { 1, 1 },
  }
end
s = memory.stats()
T.ok(s.subsystems[1].name == "alpha" and s.subsystems[2].name == "zeta",
  "equal figures are ordered by name, so two reports diff cleanly")

-- A host with no subsystem figures must not produce an empty block that reads
-- like "every subsystem holds zero bytes".
system.memory_stats = function()
  return { glyph_bytes = 0, glyph_pages = 0, log_bytes = -1 }
end
s = memory.stats()
T.eq(s.subsystems, nil, "absent figures are nil, not an empty list")
report = memory.report()
T.ok(report:find("by subsystem", 1, true) == nil,
  "and the report omits the block rather than listing zeros")

-- Arrays of mismatched length are truncated to the shortest, never indexed past
-- the end. A C-side length bug must degrade, not crash the reporter.
system.memory_stats = function()
  return {
    names = { "a", "b", "c" }, tags = { 0, 1, 2 },
    alloc_by = { 10, 20 }, peak_by = { 10, 20, 30 },
    blocks_by = { 1, 1, 1 },
  }
end
s = memory.stats()
T.eq(#s.subsystems, 2, "mismatched array lengths are truncated to the shortest")

-- accounted == 0 means leak counting was not compiled in, so live_blocks is
-- zero for want of a counter. Printing that 0 as a clean bill of health is how a
-- leak report becomes a lie, so the report has to say so.
system.memory_stats = function()
  return {
    names = { "base" }, tags = { 0 }, alloc_by = { 0 }, peak_by = { 0 },
    blocks_by = { 0 }, alloc_total = 0, peak_total = 0,
    live_blocks = 0, accounted = 0,
  }
end
report = memory.report()
T.ok(report:find("leak counting off", 1, true) ~= nil,
  "a build without leak counting says the figure was not measured")

system.memory_stats = saved
