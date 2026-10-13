#!/usr/bin/env python3
"""The memory harness: what a file costs to open, hold, highlight and close.

Phase 0 measures the runtime as it exists so every later phase has a number to
be compared against. The claim this exists to test is specific:

    opening a code file costs about 4.3x the file size in RAM

so the harness synthesises files of a given size, opens them through the real
Doc code path, and reports RSS at four points — before, after load, after the
highlighter has caught up, and after close — plus the ratio against file size.

It runs the measurement inside a real `lua` with the data layer loaded through
scripts/_stub_env.lua, which is the same path the pure-Lua suites use. That
means no window, no SDL, and identical numbers to what the editor does, because
the document representation is entirely Lua.

RSS comes from the process itself (Windows: GetProcessMemoryInfo through ctypes;
elsewhere: /proc/self/statm), because a child process's memory would not be the
editor's.

    python scripts/bench.py                     # the standard sweep
    python scripts/bench.py --sizes 4 16 64     # MB, subset
    python scripts/bench.py --baseline tests/bench_baseline.json
    python scripts/bench.py --save              # record as the baseline
"""

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
BASELINE_PATH = ROOT / "tests" / "bench_baseline.json"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    GREEN = RED = YELLOW = DIM = RESET = ""

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

SYSTEM = platform.system()


def head(text):
    print(f"\n{DIM}── {text} ──{RESET}")


# ── resident memory ────────────────────────────────────────────────────────

def rss_bytes():
    """Resident set size of this process.

    Windows reports it directly. Elsewhere /proc/self/statm's second field is
    resident pages, which is what "RSS" means; falling back to the resource
    module's ru_maxrss is a high-water mark rather than a current value, and
    that difference matters here — the measurement is of growth."""
    if SYSTEM == "Windows":
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb)
        if ok:
            return int(counters.WorkingSetSize)
        raise RuntimeError("GetProcessMemoryInfo failed")

    statm = Path("/proc/self/statm")
    if statm.exists():
        fields = statm.read_text().split()
        return int(fields[1]) * os.sysconf("SC_PAGE_SIZE")

    import resource
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def lua_mib(n):
    return n / (1024.0 * 1024.0)


def fmt_mib(n):
    return f"{lua_mib(n):.1f}"


# ── synthetic files ────────────────────────────────────────────────────────

# Line content chosen so the tokenizer has something to do and the highlighter
# is not measuring an empty buffer: comments, strings, keywords and numbers, at
# roughly the density of real code. A file of blank lines would make the
# highlight-memory figure meaningless.
LINE = (
    'local function process_%d(items, count) -- count the items we have\r\n'
    '  local total = 0\r\n'
    '  for i = 1, count do\r\n'
    '    local item = items[i]\r\n'
    '    if item ~= nil and item.value > 0 then\r\n'
    '      total = total + item.value * 2\r\n'
    '    end\r\n'
    '  end\r\n'
    '  return total\r\n'
    'end\r\n'
)

# Bytes per repetition of LINE, so a requested size is met exactly rather than
# approximately.
LINE_BLOCK_BYTES = len(LINE % (0,)) * 40


def make_file(path, megabytes):
    """Writes a file of about `megabytes` MiB of code-like text."""
    target = int(megabytes * 1024 * 1024)
    reps = max(1, target // (len(LINE % (0,)) * 40))
    written = 0
    with open(path, "wb") as f:
        for block in range(reps):
            chunk = "".join(LINE % (block * 40 + i) for i in range(40))
            f.write(chunk.encode("utf-8"))
            written += len(chunk)
            if written >= target:
                break
    return written


# The syntax definition the harness registers, so the highlighter has real work
# to do. Registered from Lua (below) rather than here, because a set literal is
# not a Python dict — the tokenizer's `patterns` is a Lua array of tables.
SYNTAX_LUA = r"""
local syntax = require "core.syntax"
syntax.add {
  files    = "%.lua$",
  comment  = "--",
  patterns = {
    { type = "comment", pattern = "%-%-[^\n]*" },
    { type = "string",  pattern = "\"[^\"]*\"" },
    { type = "keyword", pattern = "local|function|for|do|end|if|then|else|return|and|or" },
    { type = "number",  pattern = "%d+" },
    { type = "symbol",  pattern = "[%a_][%w_]*" },
  },
  symbols = {},
}
"""


# ── the measurement, in Lua ────────────────────────────────────────────────

MEASURE_LUA = r"""
-- Runs inside a plain `lua`. Reports one JSON line.
--
-- Every number is a measurement, not an estimate, and the points are chosen so
-- the four interesting costs are separable: the Lua heap before anything is
-- opened, after the text is loaded (the per-line string table), after the
-- highlighter has tokenized what is visible (the per-token tables), and after
-- the document is dropped (what close returns).

-- RSS of this process.
--
-- Lua cannot read /proc/self/statm portably (io.open on /proc works on Linux
-- and nowhere else) and Windows needs a syscall, so this reports the Lua heap
-- where RSS is unavailable and says so. The Lua heap is the number that matters
-- for this harness: the document representation is entirely Lua, so the heap
-- difference IS the cost of the document, and RSS would only add the fixed
-- interpreter overhead that is the same for every file size.
--
-- Returns rss_bytes, or -1 when it cannot be read. A caller that gets -1 must
-- report "unavailable", never 0 — a missing measurement and a measurement of
-- zero are different facts, and the difference is how a broken harness gets
-- mistaken for a fast editor.
local function measure()
  local s = io.open("/proc/self/statm", "rb")
  if s then
    local line = s:read("*a"); s:close()
    local rss_pages = tonumber(line:match("^%d+%s+(%d+)"))
    if rss_pages then return rss_pages * 4096 end
  end
  return tonumber(os.getenv("CDIN_RSS_FALLBACK") or "-1")
end

local base_rss = measure()
local base_lua = collectgarbage("count") * 1024

local Doc = require "core.doc"
local doc = Doc()

local t0 = os.clock()
doc:load(os.getenv("BENCH_FILE"))
local load_seconds = os.clock() - t0
collectgarbage("collect")

local after_load_rss = measure()
local after_load_lua = collectgarbage("count") * 1024

-- BENCH_MODE selects how much of the file is highlighted:
--
--   "load"   stop after the text is in the buffer — the per-line string table.
--   "window" tokenize only what a window shows. This is what the editor
--            actually holds after opening a file and drawing it, because
--            Highlighter:get_line is called for the visible lines and
--            max_wanted_line follows the viewport. It is the steady state.
--   "full"   tokenize every line — what scrolling through the whole file
--            eventually costs, and the upper bound the buffer has to survive.
--
-- Three processes, not three phases of one, because measuring them together
-- makes each include the last, and a per-line token table then looks free.
local mode = os.getenv("BENCH_MODE") or "full"
local WINDOW_LINES = 50   -- a screenful at any font size worth the name

local nlines = #doc.lines
local highlight_seconds = 0
local lines_tokenized = 0

if mode ~= "load" then
  local hl = doc.highlighter
  local upto = (mode == "window") and math.min(nlines, WINDOW_LINES) or nlines
  lines_tokenized = upto
  local t1 = os.clock()
  for i = 1, upto do
    hl:get_line(i)
    -- consume, so the tokens are still live when the heap is read
    local count = 0
    for _, _type, text in hl:each_token(i) do count = count + #text end
  end
  highlight_seconds = os.clock() - t1
  collectgarbage("collect")
end

local after_hl_rss = measure()
local after_hl_lua = collectgarbage("count") * 1024

local text_bytes = 0
for i = 1, nlines do text_bytes = text_bytes + #doc.lines[i] end

-- What closing a file returns.
--
-- Every reference has to go, and the order matters enough to be worth stating,
-- because getting it wrong looks exactly like a leak. Highlighter:new stores
-- `self.doc`, so the highlighter is a *second* reference to the whole document:
-- dropping `doc` alone releases nothing at all. Measured here, not assumed —
-- the first version of this harness reported the document as fully retained and
-- was wrong, because it only cleared its own local.
--
-- core.threads and core.docs are cleared the way closing a view clears them.
-- core.root_view holds the view, which holds the doc again; there is no window
-- in a headless harness, so it does not exist here.
if core then
  core.threads = setmetatable({}, { __mode = "k" })
  core.docs = {}
end
doc = nil
hl = nil
collectgarbage("collect")
collectgarbage("collect")
local after_close_rss = measure()
local after_close_lua = collectgarbage("count") * 1024

-- Why is anything still allocated?
--
-- Only when BENCH_DIAGNOSE is set, because it walks the reachable graph and that
-- is not free. What it answers is the question a residue raises: is this memory
-- still *reachable* (so something holds it and that something is a bug) or is
-- it the collector's own bookkeeping (so the number is a floor, not a leak)?
-- Those look identical from the outside and need opposite fixes.
--
-- Strings are bucketed by their first 24 bytes rather than listed individually,
-- because at 256 MiB there can be ten million of them and one line of output per
-- line of file helps nobody. A bucket that dominates the byte count names the
-- retainer: a bucket of line texts means the document is still reachable, and a
-- bucket of anything else names itself.
if os.getenv("BENCH_DIAGNOSE") then
  local out_path = os.getenv("BENCH_DIAG_FILE")
  local out = out_path and io.open(out_path, "w") or io.stderr
  local seen = {}
  local strings = {}   -- prefix -> {n, bytes, sample}
  local visited = 0
  local CAPPED  = 2000000

  local queue = { _G }
  seen[_G] = true
  local upvalues_walked = 0
  local saw_suspended = 0
  while #queue > 0 and visited < CAPPED do
    local t = table.remove(queue)
    visited = visited + 1
    if type(t) == "table" then
      for k, v in pairs(t) do
        if type(v) == "table" and not seen[v] then
          seen[v] = true
          queue[#queue + 1] = v
        elseif type(v) == "string" then
          local key = v:sub(1, 24)
          local b = strings[key]
          if not b then b = { n = 0, bytes = 0, sample = v }; strings[key] = b end
          b.n = b.n + 1
          b.bytes = b.bytes + #v
        elseif type(v) == "function" and not seen[v] then
          -- Upvalues, not just tables. A module's own locals live here, and a
          -- suspended coroutine holds its captured `self` this way — which is
          -- exactly how a document can stay reachable without appearing anywhere
          -- in _G. A walk that stops at tables cannot see it, which is how a
          -- leak survives three looks at the heap.
          seen[v] = true
          upvalues_walked = upvalues_walked + 1
          local i = 1
          while true do
            local name, val = debug.getupvalue(v, i)
            if not name then break end
            if type(val) == "table" and not seen[val] then
              seen[val] = true
              queue[#queue + 1] = val
            elseif type(val) == "function" and not seen[val] then
              seen[val] = true
              upvalues_walked = upvalues_walked + 1
            elseif type(val) == "string" then
              local key = name .. "|" .. val:sub(1, 20)
              local b = strings[key]
              if not b then b = { n = 0, bytes = 0, sample = name .. "=" .. val }; strings[key] = b end
              b.n = b.n + 1
              b.bytes = b.bytes + #val
            end
            i = i + 1
          end
          -- Count suspended coroutines: their stacks are unreachable from here,
          -- so a non-zero count is the honest limit of what this walk can see.
          local info = debug.getinfo(v, "S")
          if info and info.what == "main" then saw_suspended = saw_suspended + 1 end
        elseif type(k) == "table" and not seen[k] then
          seen[k] = true
          queue[#queue + 1] = k
        end
      end
    end
  end

  local buckets, nkeys, total = {}, 0, 0
  for key, b in pairs(strings) do
    buckets[#buckets + 1] = b
    nkeys = nkeys + 1
    total = total + b.bytes
  end
  table.sort(buckets, function(a, b) return a.bytes > b.bytes end)

  out:write(string.format(
    "visited=%d capped=%s functions-walked=%d distinct-prefixes=%d " ..
    "reachable-string-bytes=%d\n",
    visited, tostring(visited >= CAPPED), upvalues_walked, nkeys, total))
  out:write("note: a suspended coroutine's own stack is not walkable from " ..
            "here,\n")
  out:write("      so this is a lower bound on what is still alive.\n")
  for i = 1, math.min(12, #buckets) do
    local b = buckets[i]
    out:write(string.format("%10d bytes %8d count  %q\n",
      b.bytes, b.n, b.sample:sub(1, 48)))
  end
  if out ~= io.stderr then out:close() end
end

print(string.format(
  "BENCH %d %d %d %d %d %d %d %d %d %d %d %d %.4f %.4f",
  tonumber(os.getenv("BENCH_FILE_BYTES")),
  text_bytes, nlines,
  base_rss, after_load_rss, after_hl_rss, after_close_rss,
  base_lua, after_load_lua, after_hl_lua, after_close_lua,
  lines_tokenized, load_seconds, highlight_seconds))
"""


def lua_interpreter():
    for name in ("lua5.4", "lua", "lua5.3", "luajit"):
        if shutil_which(name):
            return name
    return None


def shutil_which(name):
    from shutil import which
    return which(name)


# Whether the residue after close is a leak or a floor.
#
# The "after close" figure alone cannot tell them apart. A leak and an allocator
# that keeps the pages it grew print the same number for one open/close cycle,
# and they need opposite fixes: one is a missing reference release, the other is
# nothing to fix. What separates them is the SHAPE across cycles.
#
#   leak        every cycle adds roughly the same amount, forever
#   free list   cycle 1 pays for the high-water mark, cycles 2..N add ~nothing
#
# So this loads, fully highlights and closes the same file N times in one
# process, reporting the heap after each. Per-line token tables are the most
# likely thing to leak and the most expensive thing to allocate, so every cycle
# does the full highlight rather than the window — a probe that under-allocates
# would not notice the leak it is looking for.
#
# It is a separate process and a separate script from MEASURE_LUA on purpose: the
# measurement above reports one cycle per process because RSS is process-wide,
# and folding N cycles into that number would make the first cycle's cost
# indistinguishable from the second's.
RESIDENCY_LUA = r"""
local core = _G.core
local Doc  = require "core.doc"

-- collectgarbage("count") already returns KiB. Dividing it by 1024 here made a
-- 142 KiB heap report as 0.14 KiB, which read as "everything is released" when
-- the real question is how much of it is. The multiplier is gone rather than
-- moved, because a unit error in a residency probe cannot be spotted from its
-- own output — the numbers looked plausible.
local function kib() return collectgarbage("count") end

local cycles    = tonumber(os.getenv("BENCH_CYCLES") or "5")
local bench_file = os.getenv("BENCH_FILE")

local base = kib()
print(string.format("RESIDENCY base %.1f", base))

local previous = base
for cycle = 1, cycles do
  local doc = Doc()
  doc:load(bench_file)

  -- Full highlight: every line, not the visible window.
  local hl = doc.highlighter
  for i = 1, #doc.lines do hl:get_line(i) end

  -- Drop every reference, the way closing a view does.
  --
  -- The order matters and is the same as measure.lua's: Highlighter:new stores
  -- self.doc, so the highlighter is a second reference to the whole document and
  -- clearing only `doc` releases nothing at all. core.threads is keyed weakly,
  -- but the keys are pruned by loop.lua and this harness never runs a loop step,
  -- so it is replaced outright rather than waited on.
  hl = nil
  core.threads = setmetatable({}, { __mode = "k" })
  core.docs    = {}
  doc = nil

  collectgarbage("collect")
  collectgarbage("collect")

  local now = kib()
  print(string.format("RESIDENCY %d %.1f %.1f", cycle, now, now - previous))
  previous = now
end
"""


def run_one(interp, file_bytes, file_path, tmpdir, mode="full"):
    """One size, one mode, one child process.

    A fresh process per measurement, always. RSS is process-wide, and the point
    of reporting "load" and "load + highlight" side by side is that neither
    includes the other's allocations — measuring both in one process makes the
    second contain the first, and a per-line token table then looks free.
    """
    probe = tmpdir / "measure.lua"
    probe.write_text(MEASURE_LUA, encoding="utf-8")

    residency = tmpdir / "residency.lua"
    residency.write_text(RESIDENCY_LUA, encoding="utf-8")

    # --stage runs this instead, from a file the caller supplies through
    # BENCH_INNER_OVERRIDE. It exists because a one-off question ("what is the
    # heap at each stage?") is worth answering without embedding a throwaway
    # script in a Python string, where quoting mistakes are invisible until the
    # inner interpreter fails on them.
    if os.environ.get("BENCH_INNER_OVERRIDE"):
        override = Path(os.environ["BENCH_INNER_OVERRIDE"])
        if override.is_file():
            (tmpdir / override.name).write_text(
                override.read_text(encoding="utf-8"), encoding="utf-8")

    env = dict(os.environ)
    env["BENCH_FILE"] = str(file_path)
    env["BENCH_FILE_BYTES"] = str(file_bytes)
    env["BENCH_MODE"] = mode
    env["BENCH_SCRIPT_DIR"] = str(SCRIPTS_DIR)
    env["BENCH_WORK_DIR"] = str(tmpdir)
    env["CDIN_SRC"] = str(ROOT)
    env["CDIN_RSS_FALLBACK"] = "-1"

    # Which inner script the runner dofiles. The residency probe is opt-in: it is
    # a diagnostic for a specific question (is the residue a leak?), not part of
    # every measurement, and running it by default would multiply the runtime.
    #
    # A bare filename, never a path: the runner builds `work_dir .. "/" .. name`,
    # so an absolute path would be concatenated onto the directory and fail to
    # open. The override is a path here only so the caller can point at a file
    # that is not generated by this script; its name is what gets passed on.
    _override = os.environ.get("BENCH_INNER_OVERRIDE")
    if _override:
        env["BENCH_INNER"] = Path(_override).name
    else:
        env["BENCH_INNER"] = ("residency.lua"
                              if os.environ.get("BENCH_RESIDENCY")
                              else "measure.lua")
    if os.environ.get("BENCH_RESIDENCY"):
        env["BENCH_CYCLES"] = os.environ.get("BENCH_CYCLES", "5")

    # BENCH_DIAGNOSE asks the inner process to report what is still reachable
    # after close. It writes to a file rather than stdout because stdout is
    # parsed for the "BENCH " measurement line and anything else on it is
    # discarded — a diagnostic that the harness throws away is not one.
    diag_file = None
    if os.environ.get("BENCH_DIAGNOSE"):
        diag_file = tmpdir / "close-diagnose.txt"
        env["BENCH_DIAGNOSE"] = "1"
        env["BENCH_DIAG_FILE"] = str(diag_file)

    # cwd is the repository root, because package.path is relative to it; the
    # runner and the measurement scripts are named by absolute path.
    proc = subprocess.run(
        [interp, str(tmpdir / "bench_runner.lua")],
        capture_output=True, text=True, cwd=str(ROOT), env=env,
    )
    residency_lines = [ln.strip() for ln in proc.stdout.splitlines()
                       if ln.startswith("RESIDENCY ")]
    for line in proc.stdout.splitlines():
        if line.startswith("BENCH "):
            parts = line.split()
            result = {
                "file_bytes":   int(parts[1]),
                "text_bytes":   int(parts[2]),
                "lines":        int(parts[3]),
                "rss_base":     int(parts[4]),
                "rss_load":     int(parts[5]),
                "rss_hl":       int(parts[6]),
                "rss_close":    int(parts[7]),
                "lua_base":     int(parts[8]),
                "lua_load":     int(parts[9]),
                "lua_hl":        int(parts[10]),
                "lua_close":     int(parts[11]),
                "lines_tokenized": int(parts[12]),
                "load_s":        float(parts[13]),
                "highlight_s":   float(parts[14]),
            }
            if diag_file and diag_file.is_file():
                result["close_diagnose"] = diag_file.read_text(
                    encoding="utf-8", errors="replace")
            return result

    # The residency probe reports no BENCH line by design — it answers a
    # different question than the measurement does. Falling through to the error
    # path would call that a failure, which would be wrong, so it is returned as
    # its own result and reported as such.
    if residency_lines:
        return {"residency": residency_lines,
                "stderr": (proc.stderr or "").strip()[:400]}

    err = (proc.stderr or proc.stdout or "").strip()
    return {"error": err[:400] or "no BENCH line in output", "rc": proc.returncode}


def ratio(numerator, denominator):
    if denominator <= 0:
        return None
    return numerator / denominator


def fmt_ratio(value):
    return f"{value:.2f}x" if value is not None else "n/a"


def measure_all(sizes, tmpdir, verbose=True, repeat=3):
    """Every size, measured `repeat` times, keeping the fastest run.

    The fastest, not the mean or the median. Every sample is the same code on
    the same input, so the differences between samples are the machine — a
    build running beside it, a thermal cap, a page cache that was cold on the
    first pass. The minimum is the sample least contaminated by that, and it is
    the one that reproduces. The mean of three samples is dragged by whichever
    one met a background process.

    This matters more than it sounds: an earlier version of this harness
    reported 4x swings in load time between identical runs on an idle machine,
    and a gate that fires on noise gets ignored, which is worse than no gate.
    Memory figures are exact and do not need this — they are read from the
    allocator, not timed — and they are stable to 0.0%.
    """
    interp = lua_interpreter()
    if not interp:
        print(f"{RED}no lua interpreter found{RESET}")
        print(f"   install one (apt: sudo apt install lua5.4) and re-run")
        return []

    runner = tmpdir / "bench_runner.lua"
    runner.write_text(BENCH_RUNNER, encoding="utf-8")

    # The syntax definition and the measurement script both live in tmpdir, so
    # the runner is told where that is rather than assuming its own directory is
    # the scripts directory (BENCH_SCRIPT_DIR is scripts/, for _stub_env.lua).
    (tmpdir / "syntax.lua").write_text(SYNTAX_LUA, encoding="utf-8")

    results = []
    for mb in sizes:
        path = tmpdir / f"synthetic-{mb}mb.lua"
        if verbose:
            print(f"   generating {mb} MiB …", end="", flush=True)
        nbytes = make_file(path, mb)
        if verbose:
            print(f" {fmt_mib(nbytes)} MiB")

        # Three modes per attempt: `full` is the headline, `window` is the steady
        # state the editor actually sits in, `load` gives the text-only column.
        full_runs, load_runs, window_runs = [], [], []
        for attempt in range(repeat):
            full_runs.append(run_one(interp, nbytes, path, tmpdir, mode="full"))
            window_runs.append(run_one(interp, nbytes, path, tmpdir, mode="window"))
            load_runs.append(run_one(interp, nbytes, path, tmpdir, mode="load"))
            if verbose and attempt == 0:
                print(f"  running {repeat}x", end="", flush=True)
            elif verbose:
                print(".", end="", flush=True)

        good_full = [r for r in full_runs if "error" not in r]
        if not good_full:
            res = dict(full_runs[0])
            res["nominal_mb"] = mb
            results.append(res)
            if verbose:
                print(f"   {RED}error:{RESET} {res.get('error', '')[:70]}")
            continue

        # The residency probe reports no timings and no memory columns, so every
        # step below — picking the fastest run, deriving the window cost — has
        # nothing to work from. It is passed through instead, which is why this
        # check sits before the selection rather than after it.
        if "residency" in good_full[0]:
            res = dict(good_full[0])
            res["nominal_mb"] = mb
            results.append(res)
            if verbose:
                print(f"   {len(res['residency'])} residency rows")
            continue

        # Fastest run wins. The memory figures are identical across samples, so
        # choosing on time is choosing on nothing else.
        best = min(good_full, key=lambda r: r["load_s"] + r["highlight_s"])
        res = dict(best)
        res["nominal_mb"] = mb
        res["repeats"] = len(good_full)
        res["best_load_s"] = min(r["load_s"] for r in good_full)
        res["best_highlight_s"] = min(r["highlight_s"] for r in good_full)

        # Carry the residue of every mode, not just the headline one. This is
        # what bisects a retainer: if the residue appears in `load` mode, where
        # nothing is ever tokenized, then nothing in the highlighter is holding
        # it — it is in the document's own load path. If it appears only in
        # `full`, it is the highlighter or its thread. One number would not
        # distinguish those, and guessing is how a two-day hunt starts.
        def _best_of(runs, key):
            ok = [r for r in runs if "error" not in r]
            if not ok:
                return None
            return min(ok, key=lambda r: r["load_s"] + r["highlight_s"])

        for label, runs in (("load", load_runs), ("window", window_runs)):
            pick = _best_of(runs, lambda r: r["load_s"] + r["highlight_s"])
            if pick:
                res[f"lua_close_{label}"] = pick["lua_close"]
                res[f"close_diagnose_{label}"] = pick.get("close_diagnose")
        res["worst_load_s"] = max(r["load_s"] for r in good_full)
        res["worst_highlight_s"] = max(r["highlight_s"] for r in good_full)

        good_load = [r for r in load_runs if "error" not in r]
        if good_load:
            res["lua_text_only"] = good_load[0]["lua_load"] - good_load[0]["lua_base"]
        else:
            res["lua_text_only_error"] = load_runs[0].get("error", "unknown")

        good_window = [r for r in window_runs if "error" not in r]
        if good_window:
            # The window cost over the text-only cost: the tokens for what is on
            # screen, which is the part that must not grow with the file.
            res["lua_window"] = (good_window[0]["lua_hl"] - good_window[0]["lua_base"])
            res["window_lines"] = good_window[0].get("lines_tokenized", 0)
        else:
            res["lua_window_error"] = window_runs[0].get("error", "unknown")

        results.append(res)
        if verbose:
            spread = (res["worst_load_s"] / res["best_load_s"]
                      if res["best_load_s"] > 0 else 1.0)
            flag = "" if spread < 1.5 else f"  {YELLOW}(noisy: {spread:.1f}x spread){RESET}"
            print(f"   {len(good_full)} run(s), load {res['best_load_s']:.2f}s"
                  f" best{flag}")

    return results


# The child needs the data layer on package.path and the host globals, which is
# what scripts/_stub_env.lua provides. Written as a separate file because it has
# to run in the child, with `arg` for the scratch path.
BENCH_RUNNER = r"""
-- Runs from the repository root, not from the scratch directory: the data layer
-- is found through a relative package.path, so the working directory is part of
-- how the module is located. The scripts are named by absolute path in
-- BENCH_SCRIPT_DIR for the same reason.
local script_dir = os.getenv("BENCH_SCRIPT_DIR")   -- scripts/
local work_dir   = os.getenv("BENCH_WORK_DIR")     -- build/bench/
package.path = "tests/lua/?.lua;data/?.lua;data/?/init.lua;" .. package.path

local stub = dofile(script_dir .. "/_stub_env.lua")
package.preload["fs"]   = function() return stub.fs end
package.preload["path"] = function() return stub.path end

rawset(_G, "SCALE", 1)
rawset(_G, "VERSION", "0.0.0-bench")
rawset(_G, "PLATFORM", "bench")
rawset(_G, "EXEDIR", ".")
rawset(_G, "EXEFILE", "./cdin")
rawset(_G, "ARGS", {})
rawset(_G, "PATHSEP", package.config:sub(1, 1))
rawset(_G, "LOGFILE", "")

-- No window, no SDL: the document is entirely Lua, and the stub's renderer is
-- only reached for font metrics, which the harness never asks for.
--
-- `threads` and `docs` are real registries the measure script clears when it
-- wants to know what closing a document returns. `add_thread` is a no-op so the
-- highlighter's coroutine is never actually scheduled — this harness drives
-- tokenizing synchronously, which is what the view's own get_line does.
core = {
  add_thread = function() end,
  threads = {},
  redraw = function() end,
  log_items = {},
  docs = {},
}
package.loaded["core"] = core

-- A syntax definition, so the highlighter measures real work. Registered before
-- the measured script so it is in place before Doc:load picks a definition for
-- the synthetic file.
local sok, serr = pcall(dofile, work_dir .. "/syntax.lua")
if not sok then
  io.stderr:write("syntax: " .. tostring(serr) .. "\n")
  os.exit(1)
end

-- Which inner script to run. measure.lua reports one open/close cycle;
-- residency.lua reports N of them in one process, which is the only way to tell
-- a leak from an allocator floor. BENCH_INNER selects, so the environment setup
-- above stays in one place either way.
local inner = os.getenv("BENCH_INNER") or "measure.lua"
local ok, err = pcall(dofile, work_dir .. "/" .. inner)
if not ok then
  io.stderr:write("runner: " .. tostring(err) .. "\n")
  os.exit(1)
end
"""


def report_residency(results):
    """Interprets the N-cycle probe: is the residue after close a leak, or a floor?

    The judgement is made on the LATER cycles, not on the total. Cycle 1 always
    grows the heap — the allocator had not yet reached the high-water mark this
    file needs — so counting it makes every run look like a leak. What separates
    them is what cycles 2..N add: a leak keeps adding on every cycle, a floor
    adds nothing once the high-water mark is reached.

    The threshold is a tenth of cycle 1's cost, and it is a judgement call rather
    than a derived constant. It is stated as a fraction of the first cycle so it
    scales with the file instead of being an absolute number of kilobytes that
    means one thing at 4 MiB and something else at 256.
    """
    head("residency — is the residue after close a leak?")
    ran = False
    for r in results:
        if "residency" not in r:
            continue
        ran = True
        rows = []
        for ln in r["residency"]:
            parts = ln.split()
            # "RESIDENCY base <kib>" has no cycle number; the rest are
            # "RESIDENCY <cycle> <total> <delta>".
            if len(parts) >= 4 and parts[1] != "base":
                rows.append((int(parts[1]), float(parts[2]), float(parts[3])))
        if not rows:
            print(f"   {DIM}no residency rows for {r['nominal_mb']} MiB{RESET}")
            continue

        for cycle, total, delta in rows:
            print(f"   {r['nominal_mb']:>4d} MiB  cycle {cycle:<2d} "
                  f"heap {total:9.1f} KiB   delta {delta:+8.1f} KiB")

        later = [d for _, _, d in rows[1:]]
        if not later:
            print(f"   {DIM}one cycle only — cannot tell a leak from a floor; "
                  f"raise BENCH_CYCLES{RESET}")
            continue

        # The question is whether the heap TRENDS UP, not whether any single
        # cycle added bytes. Two things look like growth and are not:
        #
        #   cycle 1  — the allocator reaching its high-water mark for this file.
        #               Excluded: every run would look like a leak.
        #   cycling  — the heap oscillating between two values forever. A
        #               collect-when-over-a-threshold allocator does this, and a
        #               4 MiB file settles into a permanent 174 <-> 142 KiB
        #               alternation. Reading the LAST cycle against the FIRST
        #               does not survive that: with an even cycle count the two
        #               land on opposite phases and the comparison reports a
        #               shrink, which then gets called a leak for growing
        #               "upward". Two wrong turns, both from using endpoints.
        #
        # The mean of the post-warmup cycles is the statistic that survives
        # alternation, because a phase-independent average of an oscillation is
        # its midpoint. A leak compounds and shows in the mean; a steady state
        # does not.
        steady = [t for _, t, _ in rows[1:]] or [t for _, t, _ in rows]
        mean = sum(steady) / len(steady)
        span = max(steady) - min(steady)
        # How much the first cycle cost, as the scale for "this is real growth".
        first = rows[0][2]

        if first <= 0:
            verdict = ("inconclusive — cycle 1 did not grow the heap, so there is "
                       "no baseline to compare later cycles against")
        elif span <= max(abs(first), 1.0) * 0.1:
            verdict = (f"floor — steady at {mean:.1f} KiB, varying only "
                       f"{span:.1f} KiB across {len(steady)} cycles. A leak "
                       f"compounds; this does not.")
        else:
            # The comparison that survives alternation: the mean of the last half
            # against the mean of the first half, both after the warmup cycle.
            half = len(steady) // 2
            if half:
                early = sum(steady[:half]) / half
                late = sum(steady[half:]) / len(steady[half:])
            else:
                early = late = mean
            drift = late - early
            verdict = (f"DRIFT — mean moved {drift:+.1f} KiB from the first "
                       f"{half} steady cycles to the last, while varying "
                       f"{span:.1f} KiB cycle to cycle")
        print(f"   {r['nominal_mb']:>4d} MiB: {verdict}\n")

    if not ran:
        print(f"   {DIM}not run — pass --residency{RESET}\n")


def compare(results, baseline):
    """Prints each measurement next to the baseline, and the regressions.

    A regression is >10% worse than the recorded figure, per AGENTS.md §8.
    Every quantity here is one where larger is worse — bytes and seconds — so
    the test is one-sided: a large improvement is not a regression and is
    reported as such, but it also never masks a regression on the same run.
    """
    head("vs baseline")
    if not baseline:
        print(f"   {DIM}no baseline recorded — run with --save{RESET}")
        return []

    prev = {r["nominal_mb"]: r for r in baseline.get("runs", [])}
    regressions = []
    inconclusive = []

    for r in results:
        if "error" in r:
            continue
        was = prev.get(r["nominal_mb"])
        if not was:
            continue

        # How much this measurement moves between identical runs on this
        # machine. A spread wider than the regression threshold means the
        # measurement cannot distinguish a real regression from the machine,
        # and gating on it would fire constantly and get ignored — which is
        # worse than not gating, because it teaches the reader to ignore red.
        best_l = r.get("best_load_s") or r["load_s"]
        worst_l = r.get("worst_load_s") or r["load_s"]
        load_spread = (worst_l / best_l) if best_l > 0 else 1.0
        best_h = r.get("best_highlight_s") or r["highlight_s"]
        worst_h = r.get("worst_highlight_s") or r["highlight_s"]
        hl_spread = (worst_h / best_h) if best_h > 0 else 1.0

        NOISE_LIMIT = 1.15

        checks = [
            # (label, now, before, is_memory, spread)
            ("lua after highlight", r["lua_hl"], was["lua_hl"], True, 1.0),
            ("lua after close",     r["lua_close"], was["lua_close"], True, 1.0),
            ("load seconds",        r["load_s"],   was["load_s"],   False, load_spread),
            ("highlight seconds",   r["highlight_s"], was["highlight_s"], False, hl_spread),
        ]
        for label, now, before, is_memory, spread in checks:
            if before <= 0:
                continue
            delta = (now - before) / before

            if not is_memory and spread > NOISE_LIMIT:
                # The measurement is noisier than the threshold it would be
                # compared against. Say so, and do not fail.
                arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
                print(f"   {YELLOW}noisy{RESET}  {r['nominal_mb']:>4} MiB  {label:<20} "
                      f"{delta * 100:+6.1f}% {arrow}   "
                      f"({before:.3f} -> {now:.3f} s, {spread:.1f}x spread between "
                      f"identical runs — not gated)")
                inconclusive.append((r["nominal_mb"], label, delta, spread))
                continue

            bad = delta > 0.10
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
            mark = f"{RED}REGRESS{RESET}" if bad else f"{GREEN}ok{RESET}    "
            change = (f"{fmt_mib(before)} -> {fmt_mib(now)} MiB" if is_memory
                      else f"{before:.3f} -> {now:.3f} s")
            print(f"   {mark} {r['nominal_mb']:>4} MiB  {label:<20} "
                  f"{delta * 100:+6.1f}% {arrow}   ({change})")
            if bad:
                regressions.append((r["nominal_mb"], label, delta))
    if not prev:
        print(f"   {DIM}baseline has no matching sizes{RESET}")
    if inconclusive:
        # Naming which ones, because the previous wording ("timings not gated on
        # this run") read as if no timing had been gated — while the lines above
        # could carry a REGRESS for a timing that *was* gated. A summary that
        # contradicts its own table is worse than no summary.
        skipped = sorted({label for _, label, _, _ in inconclusive})
        gated = [label for label, _, _, is_mem, _ in checks
                 if not is_mem and label not in skipped]
        print(f"   {DIM}timings NOT gated on this run: {', '.join(skipped)} — the")
        print(f"   spread between identical runs exceeded {NOISE_LIMIT:.0%}, wider")
        print(f"   than the 10% threshold they would be compared against.")
        if gated:
            print(f"   Gated and compared as normal: {', '.join(gated)}.")
            print(f"   A REGRESS on one of those is real as far as this box is concerned;")
            print(f"   on a shared machine it may still be noise.{RESET}")
        else:
            print(f"   The memory figures are exact and were gated.{RESET}")
    return regressions


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", nargs="*", type=float, default=[4, 16, 64, 256])
    ap.add_argument("--baseline", default=str(BASELINE_PATH))
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep the synthetic files")
    ap.add_argument("--repeat", type=int, default=3,
                    help="runs per measurement; the fastest is kept (default 3)")
    ap.add_argument("--residency", action="store_true",
                    help="run the N-cycle probe instead of the measurement, to "
                         "tell a close-time leak from an allocator floor")
    ap.add_argument("--cycles", type=int, default=5,
                    help="open/close cycles for --residency (default 5)")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes if s > 0]
    if not sizes:
        print("no sizes requested")
        return 1

    tmpdir = ROOT / "build" / "bench"
    tmpdir.mkdir(parents=True, exist_ok=True)

    # The residency probe answers a different question from the measurement, so
    # it is its own pass. One run per size, not --repeat: it is a heap *total*
    # after a full collection, which is deterministic, so repeating it would
    # report the same number three times and imply a variance that is not there.
    if args.residency:
        os.environ["BENCH_RESIDENCY"] = "1"
        os.environ["BENCH_CYCLES"] = str(max(2, args.cycles))
        head(f"residency probe ({', '.join(str(s) for s in sizes)} MiB, "
             f"{max(2, args.cycles)} cycles each)")
        try:
            residency = measure_all(sizes, tmpdir, repeat=1)
        finally:
            os.environ.pop("BENCH_RESIDENCY", None)
            os.environ.pop("BENCH_CYCLES", None)
        report_residency(residency)
        bad = [r for r in residency
               if "error" in r
               or ("residency" in r and r.get("stderr"))]
        return 1 if bad else 0

    head(f"synthetic files ({', '.join(str(s) for s in sizes)} MiB)")
    results = measure_all(sizes, tmpdir, repeat=max(1, args.repeat))
    if not results or all("error" in r for r in results):
        print(f"{RED}nothing measured{RESET}")
        return 1

    head("results")
    hdr = (f"   {'size':>6} {'file':>9} {'lines':>10} | "
           f"{'lua text':>9} {'lua win':>9} {'lua +hl':>9} {'ratio':>7} | "
           f"{'load':>7} {'hl all':>7}")
    print(f"{DIM}{hdr}{RESET}")
    print(f"{DIM}{'─' * 104}{RESET}")

    ok_rows = 0
    rss_available = False
    for r in results:
        if "error" in r:
            print(f"   {r['nominal_mb']:>5} MiB  {RED}error{RESET} {r['error'][:70]}")
            continue
        ok_rows += 1
        # The headline figure: the Lua heap holding the highlighted document,
        # over the bytes of text in it. This is the "4.3x" number.
        hl_ratio = ratio(r["lua_hl"] - r["lua_base"], r["text_bytes"])
        rss_ok = r["rss_hl"] > 0 and r["rss_base"] > 0
        rss_available = rss_available or rss_ok
        rss_ratio = ratio(r["rss_hl"] - r["rss_base"], r["text_bytes"]) if rss_ok else None

        # "lua text" comes from a separate child process that never touches the
        # highlighter (run_one with mode="load"). Measuring both in one process
        # makes the second figure include the first, which is how a per-line
        # token table ends up looking as though it costs nothing.
        text_lua = r.get("lua_text_only")
        win_lua = r.get("lua_window")
        win_ratio = ratio(win_lua, r["text_bytes"]) if win_lua is not None else None
        print(f"   {r['nominal_mb']:>5} MiB {fmt_mib(r['text_bytes']):>9} "
              f"{r['lines']:>10,} | "
              f"{(fmt_mib(text_lua) if text_lua is not None else 'n/a'):>9} "
              f"{(fmt_mib(win_lua) if win_lua is not None else 'n/a'):>9} "
              f"{fmt_mib(r['lua_hl'] - r['lua_base']):>9} "
              f"{fmt_ratio(hl_ratio):>7} | "
              f"{r['load_s']:>6.2f}s {r['highlight_s']:>6.2f}s")

    print(f"\n   {DIM}'lua text'  the per-line string table alone.")
    print(f"   'lua win'   that plus tokens for the ~50 lines a window shows —")
    print(f"               the steady state the editor sits in after opening a file,")
    print(f"               because Highlighter:get_line is only called for what is drawn.")
    print(f"   'lua +hl'   that plus tokens for EVERY line: what scrolling the whole")
    print(f"               file costs, and the upper bound the buffer must survive.")
    print(f"   ratio is 'lua +hl' over text bytes — the '4.3x' figure, measured.{RESET}")
    if not rss_available:
        print(f"   {YELLOW}note{RESET}  process RSS needs /proc/self/statm, which this "
              f"platform lacks; the lua-heap columns are the measurement")
    else:
        print(f"   rss is the process total over text bytes — the number a user feels.")
    if not rss_available:
        print(f"   {YELLOW}note{RESET}  process RSS needs /proc/self/statm, which this "
              f"platform lacks; the lua-heap columns are the measurement")
    else:
        print(f"   rss is the process total over text bytes — the number a user feels.")

    # What closing returns.
    released = [r for r in results if "error" not in r]
    if released:
        head("close")
        # Measured against the heap *before* the file was opened, not against
        # the peak: "what close returns" means how much of the process is still
        # holding the file afterwards. Comparing against the peak would report
        # peak-minus-peak and call it a full release.
        #
        # The verdict is an absolute byte figure, not a ratio. After a correct
        # release there is a fixed residue — the syntax registry, the module
        # state, whatever the runtime keeps by design — and on a 3.8 MiB file
        # that residue is 0.01x while still being 14 KiB. A ratio test would
        # call a clean release a leak on small files and a leak a clean release
        # on large ones.
        RESIDUE_BYTES = 1 << 20   # 1 MiB
        for r in released:
            residue = r["lua_close"] - r["lua_base"]
            rss_ok = r["rss_hl"] > 0 and r["rss_close"] > 0
            freed = (f"RSS returned {fmt_mib(r['rss_hl'] - r['rss_close'])} MiB"
                     if rss_ok else "RSS unavailable")
            ok_close = residue <= RESIDUE_BYTES
            color = GREEN if ok_close else RED
            verdict = "released" if ok_close else "RETAINED"
            print(f"   {r['nominal_mb']:>5} MiB  {freed:<28}   "
                  f"heap holds {color}{residue / 1024:.1f} KiB{RESET} after close "
                  f"({verdict})")

            # The same residue per mode, side by side. `load` never tokenizes
            # anything, so a residue that appears there cannot be the
            # highlighter; one that appears only in `full` is.
            per_mode = []
            for label in ("load", "window"):
                v = r.get(f"lua_close_{label}")
                if v is not None:
                    per_mode.append(f"{label} {(v - r['lua_base']) / 1024:.1f} KiB")
            if per_mode:
                print(f"        by mode:{'   '.join(per_mode)}"
                      f"   (full {residue / 1024:.1f} KiB)")

            # A RETAINED verdict says the memory is still allocated, not what is
            # holding it. With BENCH_DIAGNOSE set, print what survived, so the
            # question has an answer instead of becoming the next phase's
            # archaeology.
            diag = r.get("close_diagnose")
            if diag and diag.strip():
                print(f"        still reachable after close:")
                for line in diag.strip().splitlines():
                    print(f"          {line}")

    baseline = {}
    bp = Path(args.baseline)
    if bp.exists():
        try:
            baseline = json.loads(bp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            baseline = {}

    regressions = compare(results, baseline)

    if args.save:
        runs = [r for r in results if "error" not in r]
        payload = {
            "_comment": (
                "Recorded by scripts/bench.py --save. `make bench` compares "
                "against this and fails on a regression worse than 10% "
                "(AGENTS.md §8). Commit a regenerated file with the change "
                "that caused it."
            ),
            "_platform": f"{platform.system()} {platform.machine()}",
            "runs": runs,
        }
        bp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\n   recorded {len(runs)} run(s) to {bp.relative_to(ROOT)}")

    # The synthetic files are large and entirely reproducible from this script,
    # so they are removed unless --keep says otherwise. Leaving a 256 MiB file
    # behind after a bench run is its own kind of leak.
    if not args.keep:
        for mb in sizes:
            p = tmpdir / f"synthetic-{mb}mb.lua"
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    print(f"\n{DIM}{'─' * 44}{RESET}")
    if regressions:
        print(f"{RED}bench REGRESSED{RESET}: {len(regressions)} measurement(s) worse than baseline")
        return 1
    if ok_rows:
        print(f"{GREEN}bench OK{RESET} ({ok_rows} size(s) measured)")
        if not baseline:
            print(f"{DIM}   no baseline yet — run `make bench` with --save to record one{RESET}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
