#!/usr/bin/env python3
"""Trusted paths shared by the CDIN CTest smoke harnesses."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Pattern

ROOT = Path(__file__).resolve().parents[1]
BUILD_BIN = ROOT / "build" / "stack" / "cdin"
INSTALL_BIN = ROOT / ".deps" / "install" / "bin"
CMAKE_CACHE = ROOT / "build" / "stack" / "cdin" / "CMakeCache.txt"


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
    """Return the Runtime Lua tree selected by the active Composition Root build.

    The configured CMake cache records the exact Runtime package root chosen
    from the verified Registry Manifest. This works for both immutable module
    archives and explicit developer-source builds; it never assumes that a
    Runtime Git checkout exists in normal artifact-first mode.
    """
    if CMAKE_CACHE.is_symlink() or not CMAKE_CACHE.is_file():
        raise FileNotFoundError(f"CDIN CMake cache is missing or unsafe: {CMAKE_CACHE}")
    try:
        cache_lines = CMAKE_CACHE.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise RuntimeError(f"cannot read CDIN CMake cache: {error}") from error
    values = [
        line.split("=", 1)[1]
        for line in cache_lines
        if line.startswith("CDIN_RUNTIME_SOURCE_DIR:PATH=")
    ]
    if len(values) != 1 or not values[0]:
        raise RuntimeError(
            "CDIN CMake cache must contain exactly one CDIN_RUNTIME_SOURCE_DIR:PATH entry"
        )

    configured = Path(values[0])
    if not configured.is_absolute():
        raise RuntimeError("configured Runtime package root must be absolute")
    expected = Path(os.path.abspath(os.fspath(configured)))
    deps_root = ROOT / ".deps"
    if deps_root.is_symlink() or not deps_root.is_dir():
        raise RuntimeError("CDIN dependency root is missing or unsafe")
    deps_resolved = deps_root.resolve(strict=True)

    # Reject symlinks in every path component, including ancestors, before
    # resolving the selected package and checking its containment.
    for path in (configured, configured / "lua", configured / "lua" / "cdin",
                 configured / "lua" / "cdin" / "runtime.lua"):
        current = path
        while current != ROOT.parent and current != current.parent:
            if current.is_symlink():
                raise RuntimeError(f"configured Runtime package contains a symlink: {current}")
            current = current.parent

    runtime_root = configured.resolve(strict=True)
    if runtime_root != expected or not runtime_root.is_relative_to(deps_resolved):
        raise RuntimeError("configured Runtime package must be a real path inside CDIN .deps")
    lua_root = runtime_root / "lua"
    entry = lua_root / "cdin" / "runtime.lua"
    if not lua_root.is_dir() or entry.is_symlink() or not entry.is_file():
        raise RuntimeError(f"configured Runtime Lua modules are missing or unsafe: {entry}")
    return lua_root.resolve(strict=True)


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
