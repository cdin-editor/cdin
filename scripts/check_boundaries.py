#!/usr/bin/env python3
"""Static guard: Composition Root may orchestrate APIs, not copy component logic."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FORBIDDEN = {
    "kernel implementation": re.compile(r"\b(kernel_(?:insert|delete|replace|undo|redo)|rope_(?:split|merge|insert|erase))\s*\("),
    "runtime policy implementation": re.compile(r"\b(luaL_(?:loadfile|requiref)|lua_(?:pcall|resume))\s*\("),
    # The public TUI renderer is an adapter API the Composition Root is
    # expected to call. Only direct SDL rendering remains forbidden here.
    "frontend rendering implementation": re.compile(r"\bSDL_(?:CreateWindow|Render|PollEvent)\s*\("),
}
violations: list[str] = []
for path in SRC.rglob("*.c"):
    content = path.read_text(encoding="utf-8")
    for label, pattern in FORBIDDEN.items():
        if pattern.search(content):
            violations.append(f"{path.relative_to(ROOT)}: contains {label}")
if violations:
    print("Composition Root boundary violations:", file=sys.stderr)
    print("\n".join(violations), file=sys.stderr)
    raise SystemExit(1)
print("Composition Root source boundaries: OK")

unit_tests = subprocess.run(
    [sys.executable, "-m", "unittest", "discover",
     "-s", str(ROOT / "tests" / "architecture"), "-p", "test_*.py"],
    cwd=ROOT,
    check=False,
)
if unit_tests.returncode != 0:
    raise SystemExit(unit_tests.returncode)

include_graph = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "check_include_graph.py")],
    cwd=ROOT,
    check=False,
)
if include_graph.returncode != 0:
    raise SystemExit(include_graph.returncode)
