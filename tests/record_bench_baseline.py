#!/usr/bin/env python3
"""Regenerate tests/bench_baseline.json — the numbers `make bench` gates on.

Run this when a measurement is expected to change and commit the result with the
change that caused it. A regression is worse than 10% against this file
(AGENTS.md §8); a large improvement is not a failure, but it should be
deliberate, so both directions show up in the diff of this file.

    python tests/record_bench_baseline.py             # 4/16/64 MiB
    python tests/record_bench_baseline.py --sizes 4   # quick, for a smoke test
"""

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "bench_baseline.json"

# Kept here as a separate script rather than as a flag on scripts/bench.py so
# that recording the baseline is an explicit, greppable act: someone has to type
# this to move the goalposts, and the commit says so.
DEFAULT_SIZES = [4, 16, 64]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", nargs="*", type=int, default=DEFAULT_SIZES)
    args = ap.parse_args()

    cmd = [sys.executable, str(ROOT / "scripts" / "bench.py"),
           "--sizes", *[str(s) for s in args.sizes], "--save"]
    proc = subprocess.run(cmd, cwd=str(ROOT))

    if proc.returncode != 0:
        print("\n!! bench did not complete; the baseline was not written")
        return proc.returncode

    if not OUT.exists():
        print(f"\n!! {OUT} was not written")
        return 1

    data = json.loads(OUT.read_text(encoding="utf-8"))
    runs = data.get("runs", [])
    print(f"\n   baseline: {len(runs)} run(s) on {data.get('_platform')}")
    for r in runs:
        print(f"     {r['nominal_mb']:>4} MiB  "
              f"text {r['text_bytes'] / 1048576:.1f} MiB  "
              f"highlighted {r['lua_hl'] / 1048576:.1f} MiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
