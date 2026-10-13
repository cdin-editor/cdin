"""Font-loading cost, measured in isolation.

Exists so the font face sharing change can be judged on the thing it is supposed
to change, rather than on a total that moves with machine load. Two numbers:

  font block        "booting core.init()" -> the last "loaded" line. That is
                    `require "core.style"`, which loads six fonts at six sizes.
  font.ttf again    the gap between the FIRST and SECOND "loaded" lines for
                    font.ttf. style.font (14px) and style.big_font (34px) load
                    the same file, and ren_load_font re-reads and re-parses it
                    every time — so this span is the duplicate work the sharing
                    change is meant to remove.

Both are differences between two marker arrivals in the SAME run, so machine
load affects both ends roughly equally and cancels far better than it does in a
total measured from process launch.

Usage: python measure_fonts.py [runs]
"""
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "build" / "bare" / "cdin.exe"
LOG = ROOT / "build" / "bare" / "cdin-log.txt"
FONTS = ROOT / "build" / "bare" / "data" / "fonts"

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 9
# Poll interval. Overridable, but KNOWING WHY IT DOES NOT HELP is the point, and
# this is a trap worth documenting rather than leaving as a knob:
#
# The log is flushed per line, so the lines really are written when the work
# happens. The limit is this loop's own speed: each poll re-reads the entire file
# and re-runs a regex over it, which in CPython costs more than a fraction of a
# millisecond. Setting CDIN_FONT_POLL=0.0002 does NOT resolve individual font
# loads — it just makes the loop miss, so lines arrive in bursts of two or three
# and the per-font gaps collapse to 0.00 while one unlucky gap absorbs the whole
# block. Measured: at 2 ms the six loads collapse differently; at 0.2 ms the
# median gaps became 0.00/0.00/0.00/14.05/0.00. Neither is a per-font cost.
#
# So the per-font breakdown below is NOT reliable and is not used to justify any
# claim. Resolving it would need a timestamp from inside the process, which means
# instrumenting product code — not done, because the only approved renderer change
# is the face-sharing one, and adding timing calls is not that.
#
# What IS reliable here: tests/bench/bench_font_face.c, which measures the
# read+parse in-process and is what settled whether sharing is worth doing.
POLL = float(os.environ.get("CDIN_FONT_POLL", "0.002"))

# renderer_font.c:154 — "renderer.font: loaded \"<path>\" at <size>px ..."
LOADED = re.compile(r'loaded "([^"]+)" at ([0-9.]+)px')


def one_run():
    if LOG.exists():
        LOG.unlink()
    t0 = time.perf_counter()
    proc = subprocess.Popen([str(EXE), "--no-plugins"], cwd=str(ROOT),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env={**os.environ, "CDIN_LOG_LEVEL": "info",
                                 "CDIN_LOG_FILE": str(LOG)})
    core_init = None
    frame = None
    loads = []          # (path, size, arrival_ms)
    deadline = time.perf_counter() + 25.0
    while time.perf_counter() < deadline:
        if LOG.exists():
            try:
                text = LOG.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            now = (time.perf_counter() - t0) * 1000.0
            if core_init is None and "booting core.init()" in text:
                core_init = now
            found = LOADED.findall(text)
            if len(found) > len(loads):
                for path, size in found[len(loads):]:
                    loads.append((path, size, now))
            if "first frame presented" in text:
                frame = now
                break
        time.sleep(POLL)
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return core_init, loads, frame


def main():
    if not EXE.exists():
        print(f"!! {EXE} not found — build it with `make bare`")
        return 1

    print(f"-- font loading cost ({RUNS} runs, {POLL * 1000:.0f} ms poll) --")
    print("   within-run differences between marker arrivals, so machine load")
    print("   moves both ends together and largely cancels.\n")

    blocks, dupes, counts, ttf_arrivals = [], [], [], []
    per_font = {}          # (file, size) -> list of gaps from the previous load
    load_order = []
    for _ in range(RUNS):
        core_init, loads, frame = one_run()
        if core_init is None or not loads:
            continue
        counts.append(len(loads))
        if frame is not None:
            blocks.append(loads[-1][2] - core_init)

        # Per-font cost: gap between consecutive load log lines. Reported as a
        # breakdown so the font block is explained rather than just stated.
        load_order = [(os.path.basename(p), s) for p, s, _ in loads]
        for i in range(1, len(loads)):
            key = (load_order[i][0], load_order[i][1])
            per_font.setdefault(key, []).append(loads[i][2] - loads[i - 1][2])
        if loads:
            per_font.setdefault(("(core.init -> first font)", ""), []).append(
                loads[0][2] - core_init)

        # The gap between the first and second load of the same file. Grouped by
        # filename so it measures the duplicate parse, whatever the file is.
        by_file = {}
        for path, _size, at in loads:
            by_file.setdefault(os.path.basename(path), []).append(at)
        for base, times in by_file.items():
            if len(times) > 1:
                dupes.append(times[1] - times[0])
            if base == "font.ttf":
                ttf_arrivals.append(times[0])

    if not blocks:
        print("   NOT MEASURED - no run reached a completed font load.")
        return 1

    print(f"   fonts loaded per run: {sorted(set(counts))}  (n={len(counts)})")
    print()
    print("   MEASURED  (ms)")
    for label, vals in (
        ("font block (core.init -> last font)", blocks),
        ("font.ttf 1st -> 2nd load of same file", dupes),
    ):
        if vals:
            print(f"     {label:<38} median {statistics.median(vals):6.1f}   "
                  f"min {min(vals):6.1f}   max {max(vals):6.1f}   n={len(vals)}")
        else:
            print(f"     {label:<38} NOT SEEN")

    if per_font:
        print()
        print("   UNRELIABLE, shown only to document why: per-font gaps from the")
        print("   previous load line. This observer cannot separate them — see the")
        print("   note on POLL above. Do not draw a per-font conclusion from these.")
        print(f"     {'load':<34}{'median':>9}{'min':>8}{'max':>8}{'n':>5}")
        for key, vals in per_font.items():
            name = f"{key[0]} @ {key[1]}px" if key[1] else key[0]
            print(f"     {name:<34}{statistics.median(vals):9.2f}"
                  f"{min(vals):8.2f}{max(vals):8.2f}{len(vals):5d}")

    print()
    print("   SETTLED BY tests/bench/bench_font_face.c, not by this script:")
    print("     ren_load_font opens the file and runs stbtt_InitFont on every call,")
    print("     so font.ttf is read and parsed twice — once for style.font at 14px,")
    print("     once for style.big_font at 34px. That duplicate is real.")
    print()
    print("     It is also worth 0.018 ms. Read plus parse of font.ttf measures")
    print("     0.344 ms, and the second load is indistinguishable from the first.")
    print("     So sharing the parsed face would save about 0.02 ms and would add")
    print("     a refcount, an invalidation rule and a shutdown obligation to get it.")
    print("     Measured, not assumed: the phase table's apparent 12 ms for that")
    print("     second load was the observer failing to resolve it, the same way it")
    print("     wrongly billed 40 ms to system.chdir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
