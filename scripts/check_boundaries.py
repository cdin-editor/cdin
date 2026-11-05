#!/usr/bin/env python3
"""Static guard: Composition Root may orchestrate APIs, not copy component logic."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FORBIDDEN = {
    "kernel implementation": re.compile(r"\b(kernel_(?:insert|delete|replace|undo|redo)|rope_(?:split|merge|insert|erase))\s*\("),
    "runtime policy implementation": re.compile(r"\b(luaL_(?:loadfile|requiref)|lua_(?:pcall|resume))\s*\("),
    "frontend rendering implementation": re.compile(r"\b(SDL_(?:CreateWindow|Render|PollEvent)|cdin_frontend_tui_render)\s*\("),
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
print("Composition Root boundaries: OK")
