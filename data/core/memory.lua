-- Memory accounting, as a report rather than a counter.
--
-- The point of this module is that one call tells you where the bytes are,
-- so "the editor got slow" becomes a number instead of a guess. It reads the
-- C counters the host publishes (system.memory_stats) and adds what only the
-- Lua side can know: the Lua heap, and the documents.
--
-- Nothing here allocates and caches a number. Every call re-reads the live
-- counters, because the interesting moment is "why is it big right now", and a
-- cached snapshot answers that question with the value from whenever the
-- snapshot was taken.
--
-- Later phases replace the document accounting with the C buffer's own
-- accounting (Phase 4) and the Lua heap share with per-subsystem allocator
-- tags (Phase 1). This is the version that is true of the runtime as it
-- exists today, which is what a baseline is.

local memory = {}

local function kbytes(bytes)
  if type(bytes) ~= "number" or bytes < 0 then return nil end
  return bytes / 1024
end


-- The C side, or nil when the host is an older build (and the stub in the
-- tests, which has no such function). Absent is reported as absent rather
-- than as zero: "0 bytes of glyphs" and "not measurable" are different facts,
-- and collapsing them is how a regression hides.
local function native_stats()
  if type(system) ~= "table" or type(system.memory_stats) ~= "function" then
    return nil
  end
  local ok, stats = pcall(system.memory_stats)
  if not ok or type(stats) ~= "table" then return nil end
  return stats
end


-- Bytes held by documents, and the line/token table overhead implied by it.
--
-- doc.lines is a Lua array of strings, one per line, each carrying a trailing
-- newline the editor keeps in the buffer. The reported figure is the sum of
-- those string lengths plus the array's own slots, which is what the file
-- actually costs to hold — deliberately NOT including the highlighter's token
-- tables, which are counted separately because they are the part that grows
-- with syntax definitions rather than with the file.
local function doc_stats()
  local out = { count = 0, lines = 0, bytes = 0, array_slots = 0 }
  local core = rawget(_G, "core")
  local docs = core and core.docs
  if type(docs) ~= "table" then return out end

  for i = 1, #docs do
    local doc = docs[i]
    out.count = out.count + 1
    local lines = doc and doc.lines
    if type(lines) == "table" then
      -- A Lua array slot is one TValue; the value itself is counted by the
      -- string length below. This is the per-line floor that makes a file of
      -- many tiny lines more expensive than its size.
      local n = #lines
      out.lines      = out.lines + n
      out.array_slots = out.array_slots + n
      for j = 1, n do
        local line = lines[j]
        if type(line) == "string" then out.bytes = out.bytes + #line end
      end
    end
  end
  return out
end


-- Per-subsystem accounting from the C allocator, biggest live figure first.
--
-- Returns an array of {name, live, peak, blocks}. nil — not an empty array —
-- when the host does not publish the figures, so a caller can tell "nothing is
-- allocated" from "this build cannot say". Collapsing those two is how a
-- subsystem's absence turns into a reassuring zero.
--
-- The names come from C, so a subsystem cannot be reported here under a name the
-- allocator does not use. The five arrays are parallel; their lengths are
-- reduced to the shortest before indexing, because a length mismatch is a C-side
-- bug and reading past the end of a Lua array to find out is not worth the risk.
local function subsystem_rows(native)
  local names  = native.names
  local live   = native.alloc_by
  local peak   = native.peak_by
  local blocks = native.blocks_by
  if type(names) ~= "table" or type(live) ~= "table"
     or type(peak) ~= "table" or type(blocks) ~= "table" then
    return nil
  end

  local n = #names
  for _, arr in ipairs({ live, peak, blocks }) do
    if #arr < n then n = #arr end
  end
  if n == 0 then return nil end

  local rows = {}
  for i = 1, n do
    rows[i] = { name = names[i] or ("tag" .. i), live = live[i],
                peak = peak[i], blocks = blocks[i] }
  end

  -- Sorted by live descending, with the name as a tiebreaker so two equal
  -- figures do not swap places between runs and make a diff look like a change.
  table.sort(rows, function(x, y)
    if x.live ~= y.live then return x.live > y.live end
    return tostring(x.name) < tostring(y.name)
  end)
  return rows
end


-- Everything, as one flat table. Fields are bytes unless the name says
-- otherwise. Values that cannot be measured are nil, never 0.
function memory.stats()
  local native = native_stats()
  local docs   = doc_stats()

  local lua_kb = collectgarbage("count")

  local out = {
    -- Lua heap: the allocator's own number, which includes the strings in
    -- doc.lines above. Reported separately rather than added in, because
    -- summing them would double-count every line.
    lua_kb       = lua_kb,
    lua_bytes    = math.floor(lua_kb * 1024),

    doc_count    = docs.count,
    doc_lines    = docs.lines,
    doc_bytes    = docs.bytes,
    doc_slots    = docs.array_slots,
  }

  -- File bytes are what a user would recognise, and the ratio against
  -- doc_bytes is the 4.3x figure the whole rewrite is about. sum() over the
  -- line lengths is the file size minus nothing, so this is exact for a loaded
  -- document.
  out.doc_overhead = docs.array_slots * 16
  out.doc_total    = docs.bytes + out.doc_overhead
  out.doc_ratio    = (docs.bytes > 0) and (out.doc_total / docs.bytes) or nil

  -- What part of the Lua heap is accounted for, and what part is not.
  --
  -- Most of the Lua heap is not attributed to any subsystem, and saying only
  -- "lua heap 678 KiB" hides that. The C allocator sees the renderer's own
  -- allocations and nothing else: src/fs, src/lua and src/search make no C
  -- allocations at all, so every byte they put into Lua — paths, search results,
  -- the strings they push — belongs to the Lua heap and is invisible to the
  -- per-subsystem table. That is a fact about where memory lives, not a gap in
  -- the measurement, and it is what the later phases change.
  --
  -- So: documents are attributed, and the remainder is reported as
  -- unattributed rather than being quietly absent. A reader who sees the
  -- unattributed figure knows there is more to find; a reader who sees only the
  -- total does not.
  local attributed = out.doc_bytes + out.doc_overhead
  out.lua_attributed   = attributed
  out.lua_unattributed = (out.lua_bytes > attributed)
                        and (out.lua_bytes - attributed) or 0

  if native then
    out.glyph_bytes          = native.glyph_bytes
    out.glyph_pages          = native.glyph_pages
    out.log_bytes            = native.log_bytes
    out.command_buf_peak     = native.command_buf_peak
    out.command_buf_capacity = native.command_buf_capacity
    out.draw_text_count      = native.draw_text_count
    out.draw_rect_count      = native.draw_rect_count

    -- Per-subsystem accounting. `subsystems` is the sorted row list the report
    -- prints; the totals are kept as scalars so a caller can watch one number
    -- without building anything.
    out.subsystems  = subsystem_rows(native)
    out.alloc_total = native.alloc_total
    out.peak_total  = native.peak_total
    out.live_blocks = native.live_blocks
    -- 1 when the C allocator is compiled with its live-block registry, 0 when
    -- it is not. With 0, `live_blocks` is 0 for want of a counter rather than
    -- because nothing leaked, and a report that showed "0 blocks" would be
    -- claiming a cleanliness it did not check for.
    out.accounted   = native.accounted
  end

  return out
end


-- The same numbers as short, aligned lines, for `core:memory` on the command
-- line and for the log view. Sorted biggest first: the question is always
-- "what is the big thing", and a reader should not have to work it out.
function memory.report()
  local s = memory.stats()
  local lines = {}

  local function row(label, value)
    if value ~= nil then
      lines[#lines + 1] = string.format("  %-22s %s", label, value)
    end
  end

  row("lua heap",     s.lua_kb and string.format("%.1f KiB", s.lua_kb) or nil)
  row("  attributed", s.lua_attributed and string.format("%.1f KiB (documents)",
         kbytes(s.lua_attributed) or 0) or nil)
  row("  unattributed", s.lua_unattributed and string.format("%.1f KiB",
         kbytes(s.lua_unattributed) or 0) or nil)
  row("documents",    string.format("%d (%d lines)", s.doc_count, s.doc_lines))
  row("doc bytes",    s.doc_bytes and string.format("%.1f KiB", kbytes(s.doc_bytes)) or nil)
  row("doc ratio",    s.doc_ratio and string.format("%.2fx", s.doc_ratio) or nil)
  row("glyph cache",  s.glyph_bytes and string.format("%.1f KiB in %d pages",
         kbytes(s.glyph_bytes), s.glyph_pages or 0) or nil)
  row("command buf",  s.command_buf_peak and string.format("%.1f of %.0f KiB",
         kbytes(s.command_buf_peak), kbytes(s.command_buf_capacity or 0)) or nil)
  -- The log's three states are three different facts and each needs its own
  -- branch: a positive size, -1 meaning "no file log", and nil meaning "this
  -- host cannot say". The guard has to be on kbytes(), not on log_bytes:
  -- -1 is truthy in Lua, so `s.log_bytes and format(... kbytes(s.log_bytes))`
  -- passes the guard and then hands nil to a %f.
  local log_kib = s.log_bytes and kbytes(s.log_bytes)
  if log_kib then
    row("log file", string.format("%.1f KiB", log_kib))
  elseif s.log_bytes == -1 then
    row("log file", "(off)")
  end

  -- Per-subsystem accounting, only when the host publishes it. Every subsystem
  -- is listed rather than the top few: the question is always "which subsystem",
  -- and a truncated list makes a reader assume the missing ones were zero.
  --
  -- A subsystem with nothing live is still listed, with a 0, because "the rope
  -- holds nothing" and "the rope does not exist yet" are different answers and
  -- the order of the phases decides which one this is.
  --
  -- The header says "requested bytes" because these figures do NOT include the
  -- allocator's own per-block headers, while the `glyph cache` row above does not
  -- include the font *files* the font subsystem is holding. So `font` is
  -- legitimately larger than `glyph cache`, and the two are not competing
  -- measurements of one thing — saying so here is cheaper than a reader
  -- concluding that one of them is broken.
  if s.subsystems then
    lines[#lines + 1] =
      "  by subsystem (requested bytes live / peak; the glyph cache above is a subset):"
    for _, r in ipairs(s.subsystems) do
      lines[#lines + 1] = string.format("    %-12s %12s / %12s  %d blk",
        tostring(r.name), tostring(r.live), tostring(r.peak),
        r.blocks or 0)
    end
    if s.alloc_total ~= nil then
      lines[#lines + 1] = string.format("    %-12s %12s / %12s",
        "TOTAL", tostring(s.alloc_total), tostring(s.peak_total or 0))
    end
    -- Only meaningful with the allocator's registry compiled in. Saying so is
    -- better than printing a reassuring 0 that means "not measured".
    if s.accounted == 0 then
      lines[#lines + 1] =
        "    (leak counting off in this build; live_blocks is not measured)"
    end
  end

  return "memory:\n" .. table.concat(lines, "\n")
end


return memory
