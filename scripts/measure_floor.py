"""Startup floor: how much of the wait happens before cdin can influence anything.

Why this exists alongside scripts/measure_runtime.py. That harness reports the
total and a phase table built from per-marker MEDIANS. Summing independently
medianed spans is not the median of the sum: given samples like 194/136/210 ms
the medians add up to a number no single launch ever took. A "floor" quoted that
way is an artefact of the arithmetic, so this computes every quantity PER RUN
first and medians only at the end.

It also keeps two different kinds of claim apart, because they are different:

  MEASURED     the arrival time of each marker relative to process launch. An
               observation of this machine, on this day.
  ATTRIBUTION  whether a span is "platform cost" or "cdin cost". An argument
               from what the code between two markers does — not a measurement.

Read from the log file rather than an in-process clock, exactly as the main
harness does: the log is flushed per line, and its own timestamps are only
one-second resolution, so an external observer at 2 ms is the better instrument.
Every marker watched here is a string the binary already emits. No
instrumentation is added to the product for this.

Usage: python measure_floor.py [runs]
"""
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "build" / "bare" / "cdin.exe"
LOG = ROOT / "build" / "bare" / "cdin-log.txt"

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 15
POLL = 0.002

# (key, substring) — every one of these already exists in the log.
MARKERS = [
    ("first_log", "cdin starting"),
    ("sdl_init",  "SDL_Init begin"),
    ("sdl_done",  "SDL_Init done"),
    ("window",    "window created"),
    ("lua_state", "lua_state created"),
    ("globals",   "globals ready"),
    ("job_loop",  "job_loop: initialised"),
    ("core_init", "booting core.init()"),
    ("cwd",       "working directory changed"),
    ("frame",     "first frame presented"),
]
REQUIRED = ["first_log", "sdl_init", "sdl_done", "window", "core_init", "cwd", "frame"]

# (label, start key, end key, None == launch, attribution note)
SPANS = [
    ("loader: launch -> 1st log",  None,       "first_log",
     "CRT, Windows loader, mapping SDL3/Lua/libuv. No cdin code has run."),
    ("SDL_Init",                   "sdl_init",  "sdl_done",
     "SDL_Init(SDL_INIT_VIDEO|EVENTS). One library call."),
    ("display query + window",     "sdl_done",  "window",
     "SDL_GetPrimaryDisplay + GetDisplayUsableBounds, then src/core/window.c."),
    ("FLOOR: launch -> window",    None,       "window",
     "the three spans above, as one per-run number."),
    ("window -> core.init",        "window",    "core_init",
     "luaL_newstate, luaL_openlibs, api_load_libs, lua_setup_globals, job_loop_init."),
    ("core.init -> cwd",           "core_init", "cwd",
     "Lua core.init: module requires and the six fonts, among other things."),
    ("cwd -> first frame",         "cwd",       "frame",
     "rest of core.init, then core.run's first draw and present."),
    ("TOTAL: launch -> frame",     None,       "frame",
     "the figure the startup budget is judged against."),
]


def one_run():
    if LOG.exists():
        LOG.unlink()
    t0 = time.perf_counter()
    proc = subprocess.Popen([str(EXE), "--no-plugins"], cwd=str(ROOT),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env={**os.environ, "CDIN_LOG_LEVEL": "info",
                                 "CDIN_LOG_FILE": str(LOG)})
    seen = {}
    deadline = time.perf_counter() + 25.0
    while time.perf_counter() < deadline:
        if LOG.exists():
            try:
                text = LOG.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            now = (time.perf_counter() - t0) * 1000.0
            for key, needle in MARKERS:
                if key not in seen and needle in text:
                    seen[key] = now
            if "frame" in seen:
                break
        time.sleep(POLL)
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return seen


def span(run, start, end):
    """One span for one run, or None if a marker was missed."""
    if start is not None and start not in run:
        return None
    if end not in run:
        return None
    return run[end] - (0.0 if start is None else run[start])


def main():
    if not EXE.exists():
        print(f"!! {EXE} not found — build it with `make bare`")
        return 1

    print(f"-- startup floor ({RUNS} runs, {POLL * 1000:.0f} ms poll) --")
    print("   every span is computed PER RUN, then medianed. Sum-of-medians is")
    print("   not used anywhere below: it can produce a total no single run took.")
    print("   Poll resolution is 2 ms, so every figure is an upper bound.\n")

    runs = [one_run() for _ in range(RUNS)]
    complete = [r for r in runs if all(k in r for k in REQUIRED)]
    if not complete:
        print("   NOT MEASURED - no run reached a presented frame with every marker.")
        return 1
    if len(complete) < len(runs):
        print(f"   {len(runs) - len(complete)} of {len(runs)} runs were incomplete and"
              f" are excluded from every figure below.\n")

    print("   MEASURED  (ms from process launch; this machine, this day)")
    print(f"   {'quantity':<28}{'median':>9}{'min':>8}{'max':>8}{'n':>5}  spread")
    results = {}
    for label, start, end, _note in SPANS:
        vals = [v for v in (span(r, start, end) for r in complete) if v is not None]
        if not vals:
            print(f"   {label:<28}{'NOT MEASURED':>9}")
            continue
        results[label] = statistics.median(vals)
        spread = max(vals) / min(vals) if min(vals) > 0 else float("nan")
        print(f"   {label:<28}{statistics.median(vals):9.1f}{min(vals):8.1f}"
              f"{max(vals):8.1f}{len(vals):5d}  {spread:.1f}x")

    floor_key = "FLOOR: launch -> window"
    total_key = "TOTAL: launch -> frame"
    if floor_key in results:
        floors = sorted(v for v in (span(r, None, "window") for r in complete)
                        if v is not None)
        print()
        print(f"   FLOOR, every run individually (ms): "
              + ", ".join(f"{v:.0f}" for v in floors))
        print(f"   budget 100 ms.  floor median {statistics.median(floors):.1f} ms,"
              f"  lowest single run {min(floors):.1f} ms,"
              f"  runs over budget on the floor alone: "
              f"{sum(1 for v in floors if v > 100.0)}/{len(floors)}")

    if floor_key in results and total_key in results:
        print()
        print(f"   cdin's own work (TOTAL - FLOOR): median "
              f"{results[total_key] - results[floor_key]:.1f} ms "
              f"(difference of two medians — indicative, not a per-run figure)")

    print()
    print("   ATTRIBUTION  (an argument from the code between two markers,")
    print("                not a measurement of it)")
    for label, _s, _e, note in SPANS:
        print(f"     {label:<28} {note}")

    print()
    print("   WHAT THE FLOOR IS, PRECISELY")
    print("     It is an UPPER BOUND ON WHAT IS LEFT TO OPTIMISE: if cdin did no")
    print("     work at all after the window exists, a launch would still take")
    print("     about this long. It is NOT a prediction of what a rewritten startup")
    print("     would achieve, and it does NOT say these three spans are irreducible")
    print("     — only that they are what this binary does today. A different window")
    print("     API, or SDL built differently, would move the third span.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
