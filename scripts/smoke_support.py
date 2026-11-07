#!/usr/bin/env python3
"""Trusted paths shared by the CDIN CTest smoke harnesses."""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Pattern

ROOT = Path(__file__).resolve().parents[1]
BUILD_BIN = ROOT / "build" / "stack" / "cdin"
INSTALL_BIN = ROOT / ".deps" / "install" / "bin"
RUNTIME_LUA = ROOT / ".deps" / "src" / "runtime" / "lua"


def resolve_cdin_executable() -> Path:
    """Return CDIN from one of the two fixed build outputs, never from argv."""
    name = "cdin.exe" if os.name == "nt" else "cdin"
    for candidate in (BUILD_BIN / name, INSTALL_BIN / name):
        try:
            parent = candidate.parent.resolve(strict=True)
            executable = candidate.resolve(strict=True)
        except OSError:
            continue
        if executable.parent != parent or not executable.is_file():
            continue
        if executable.name.lower() != name.lower():
            continue
        return executable
    raise FileNotFoundError("built CDIN executable was not found in the fixed build/install directories")


def resolve_runtime_root() -> Path:
    """Return only the pinned Runtime Lua tree inside this repository."""
    expected = Path(os.path.abspath(os.fspath(RUNTIME_LUA)))
    runtime_root = RUNTIME_LUA.resolve(strict=True)
    if runtime_root != expected or not runtime_root.is_dir():
        raise ValueError("pinned Runtime Lua directory must not be a symlink or missing")
    return runtime_root


def scratch_file_from_output(output: bytes, working: Path, pattern: Pattern[bytes]) -> Path:
    """Convert a constrained numeric TUI title into a private scratch path."""
    matches = set(pattern.findall(output))
    if len(matches) != 1:
        raise AssertionError("expected one unique scratch title")
    fields = next(iter(matches))
    numbers = tuple(int(field) for field in fields)
    if len(numbers) != 3 or any(value < 0 or value > 2147483647 for value in numbers):
        raise AssertionError("scratch title contains out-of-range numeric fields")
    filename = f"cdin-untitled-{numbers[0]}-{numbers[1]}-{numbers[2]}.cdin"
    root = working.resolve(strict=True)
    candidate = root / filename
    try:
        information = candidate.lstat()
    except OSError as error:
        raise AssertionError("scratch document was not created in its private working directory") from error
    if not stat.S_ISREG(information.st_mode):
        raise AssertionError("scratch document is not a regular file")
    resolved = candidate.resolve(strict=True)
    if resolved.parent != root:
        raise AssertionError("scratch document escaped its private working directory")
    return resolved
