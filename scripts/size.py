#!/usr/bin/env python3
"""`make size`: what the editor weighs, and where the bytes are.

Two questions a reviewer asks about a release: how big is it, and which of its
decisions is responsible. The second is the interesting one for this project —
the master prompt's whole direction is "cdin ships nothing heavy", so the
numbers below are the evidence for that, and a number that is only measured
once at the start is not evidence for anything later.

Nothing here guesses at a size on a platform it cannot measure: a directory that
does not exist prints "-" rather than 0.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    GREEN = RED = YELLOW = DIM = RESET = ""

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

# What counts as heavy. Chosen for this project's goals (a runtime that ships
# no fonts of its own beyond a small fallback), not as an industry rule.
BUDGETS = {
    "data/core":   1 << 20,    # 1 MiB of Lua runtime
    "data/fonts":  300 << 10,  # 300 KiB of fonts — the embedded fallback cap
    "data/plugins": 0,         # bundled plugins are cdin-x's, not counted
    "src":         0,
}


def dir_size(path: Path) -> int:
    """Total bytes of every file under `path`. Symlinks are counted by their
    target's size if it resolves, and skipped otherwise, so a dangling link does
    not make a build look smaller than it is."""
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            p = Path(root) / name
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total


def human(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n / 1048576:.2f} MiB"


def path_str(p: Path) -> str:
    """A path as something to print. A path outside ROOT is printed absolute
    rather than raising, because a size report that crashes is worse than one
    that prints a long path."""
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def largest_files(base: Path, count=8):
    out = []
    if not base.exists():
        return out
    for root, _dirs, files in os.walk(base):
        for name in files:
            p = Path(root) / name
            try:
                out.append((p.stat().st_size, p.relative_to(ROOT)))
            except OSError:
                continue
    out.sort(reverse=True)
    return out[:count]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None,
                    help="the built tree to measure (default: build/*-release)")
    args = ap.parse_args()

    if args.out:
        # Resolved against ROOT so a relative --out still produces paths that
        # can be printed relative to it.
        build_dirs = [(ROOT / args.out).resolve()]
    else:
        build_dirs = sorted(
            d for d in (ROOT / "build").glob("*-release") if d.is_dir()
        ) if (ROOT / "build").exists() else []

    if not build_dirs:
        print(f"{YELLOW}no build to measure{RESET}")
        print(f"   run `make` first; sizes below are source-only")
        build_dirs = []

    print(f"\n{DIM}── binaries ──{RESET}")
    for bd in build_dirs:
        # Match the executable by name, not by prefix: a `cdin*` glob picks up
        # cdin-log.txt, which is not the editor and would be reported as its
        # size. The suffix is optional because the name differs by platform.
        exe = next((p for p in (bd / "cdin.exe", bd / "cdin")
                    if p.is_file()), None)
        if exe:
            print(f"   {human(exe.stat().st_size):>10}  {path_str(exe)}")
        else:
            print(f"   {'-':>10}  (no binary in {path_str(bd)})")

        data = bd / "data"
        if data.exists():
            size = dir_size(data)
            print(f"   {human(size):>10}  {path_str(data)}  "
                  f"{DIM}(bundled data){RESET}")
        else:
            print(f"   {'-':>10}  (no data/ — run `make bundle`)")

    print(f"\n{DIM}── source ──{RESET}")
    for sub in ("src", "data", "tests", "scripts", "mk"):
        p = ROOT / sub
        if p.exists():
            print(f"   {human(dir_size(p)):>10}  {sub}/")
        else:
            print(f"   {'-':>10}  {sub}/  {DIM}(absent){RESET}")

    print(f"\n{DIM}── data/ by directory ──{RESET}")
    data = ROOT / "data"
    if not data.exists():
        print(f"   {DIM}no data/ directory{RESET}")
    else:
        rows = []
        for d in sorted(data.iterdir()):
            if d.is_dir():
                rows.append((dir_size(d), d.name))
        rows.sort(reverse=True)
        for size, name in rows:
            budget = BUDGETS.get(f"data/{name}")
            flag = ""
            if budget:
                mark = f"{GREEN}ok{RESET}" if size <= budget else f"{RED}over{RESET}"
                flag = f"  {mark} budget {human(budget)}"
            elif BUDGETS.get(f"data/{name}") == 0:
                flag = f"  {DIM}not counted (cdin-x owns it){RESET}"
            print(f"   {human(size):>10}  {name}{flag}")

    print(f"\n{DIM}── largest files under data/ ──{RESET}")
    lf = largest_files(ROOT / "data")
    if not lf:
        print(f"   {DIM}none{RESET}")
    for size, rel in lf:
        print(f"   {human(size):>10}  {rel}")

    print(f"\n{DIM}── fonts ──{RESET}")
    fonts = largest_files(ROOT / "data" / "fonts", count=20)
    total_fonts = dir_size(ROOT / "data" / "fonts") if (ROOT / "data" / "fonts").exists() else 0
    if not total_fonts:
        print(f"   {DIM}no data/fonts in the source tree{RESET}"
              f"  {DIM}(they arrive with the cdin-x bundle){RESET}")
    else:
        for size, rel in fonts:
            print(f"   {human(size):>10}  {rel}")
        print(f"   {human(total_fonts):>10}  total  "
              f"{DIM}(embedded fallback budget: {human(300 << 10)}){RESET}")

    print(f"\n{DIM}── symbol count ──{RESET}")
    c_lines = lua_lines = 0
    for p in (ROOT / "src").rglob("*.c"):
        try:
            c_lines += len(p.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            pass
    for p in (ROOT / "src").rglob("*.h"):
        try:
            c_lines += len(p.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            pass
    for p in (ROOT / "data").rglob("*.lua"):
        try:
            lua_lines += len(p.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            pass
    print(f"   {c_lines:>10,}  C   (src/**.c, src/**.h)")
    print(f"   {lua_lines:>10,}  Lua (data/**.lua)")

    print(f"\n{GREEN}size OK{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
