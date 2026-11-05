#!/usr/bin/env python3
"""Audit compiler-resolved include dependencies of CDIN translation units.

The compiler's own include trace is authoritative here: this check does not
infer dependency edges from textual include spelling. Component source
checkouts and component build trees are private implementation details;
CDIN may consume only headers from the installed component prefix.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "build" / "stack" / "cdin" / "compile_commands.json"
DEPENDENCY_ROOT = ROOT / ".deps"
INSTALL_PREFIX = DEPENDENCY_ROOT / "install"
PRIVATE_BUILD_ROOTS = tuple(
    ROOT / "build" / "stack" / name
    for name in ("logger", "kernel", "backend", "frontend")
)


def absolute(path: str | Path, base: Path) -> Path:
    value = Path(path)
    if not value.is_absolute():
        value = base / value
    return value.resolve(strict=False)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def classify_include(
    include_path: str | Path,
    *,
    working_directory: Path,
    dependency_root: Path = DEPENDENCY_ROOT,
    install_prefix: Path = INSTALL_PREFIX,
    private_build_roots: tuple[Path, ...] = PRIVATE_BUILD_ROOTS,
) -> str | None:
    """Return a violation reason, or None for an allowed resolved header."""
    resolved = absolute(include_path, working_directory)
    dependency_root = dependency_root.resolve(strict=False)
    install_prefix = install_prefix.resolve(strict=False)

    if is_within(resolved, dependency_root):
        if is_within(resolved, install_prefix):
            return None
        return "component source/build checkout (not installed public headers)"

    for build_root in private_build_roots:
        if is_within(resolved, build_root.resolve(strict=False)):
            return "component build tree (not installed public headers)"
    return None


def command_from_entry(entry: dict[str, Any]) -> list[str]:
    arguments = entry.get("arguments")
    if isinstance(arguments, list) and arguments:
        return [str(argument) for argument in arguments]

    command = entry.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("compile command entry has neither arguments nor command")

    if os.name == "nt":
        # CMake's Windows command strings follow Windows quoting rules.
        # posix=False preserves backslashes in MSYS2/UCRT64 executable paths.
        parts = shlex.split(command, posix=False)
        return [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in "'\"" else part
            for part in parts
        ]
    return shlex.split(command, posix=True)


def dependency_probe_command(arguments: list[str]) -> list[str]:
    """Turn one compile command into a compiler -H dependency trace."""
    if not arguments:
        raise ValueError("empty compiler command")

    result = [arguments[0]]
    takes_value = {"-o", "-MF", "-MT", "-MQ", "-MJ"}
    no_compile = {"-c", "-MD", "-MMD", "-MP"}
    index = 1
    while index < len(arguments):
        argument = arguments[index]
        if argument in takes_value:
            index += 2
            continue
        if argument in no_compile:
            index += 1
            continue
        if argument.startswith("-o") and len(argument) > 2:
            index += 1
            continue
        result.append(argument)
        index += 1

    result.extend(["-E", "-H", "-o", os.devnull])
    return result


def traced_headers(stderr: str, working_directory: Path) -> list[Path]:
    headers: list[Path] = []
    for line in stderr.splitlines():
        match = re.match(r"^\s*\.+\s+(.+?)\s*$", line)
        if match is None:
            continue
        candidate = match.group(1).strip()
        path = absolute(candidate, working_directory)
        if path.exists():
            headers.append(path)
    return headers


def main() -> int:
    if len(sys.argv) > 2:
        print("usage: check_include_graph.py [COMPILE_COMMANDS_JSON]", file=sys.stderr)
        return 2

    database = Path(sys.argv[1]) if len(sys.argv) == 2 else DEFAULT_DATABASE
    database = database if database.is_absolute() else ROOT / database
    if not database.is_file():
        print(
            f"compiler database not found: {database}; run pipeline run stack first",
            file=sys.stderr,
        )
        return 2

    try:
        entries = json.loads(database.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"could not read compiler database: {error}", file=sys.stderr)
        return 2
    if not isinstance(entries, list):
        print("compile_commands.json must contain an array", file=sys.stderr)
        return 2

    source_root = (ROOT / "src").resolve(strict=False)
    checked = 0
    violations: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            continue
        working_directory = absolute(entry.get("directory", ROOT), ROOT)
        translation_unit = absolute(entry["file"], working_directory)
        if not is_within(translation_unit, source_root):
            continue

        checked += 1
        try:
            probe = dependency_probe_command(command_from_entry(entry))
            completed = subprocess.run(
                probe,
                cwd=working_directory,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except (OSError, ValueError) as error:
            violations.append(f"{translation_unit}: include trace could not run: {error}")
            continue

        if completed.returncode != 0:
            detail = "\n".join(completed.stderr.strip().splitlines()[-8:])
            violations.append(
                f"{translation_unit}: compiler include trace failed "
                f"(exit {completed.returncode})\n{detail}"
            )
            continue

        for header in traced_headers(completed.stderr, working_directory):
            reason = classify_include(header, working_directory=working_directory)
            if reason is not None:
                violations.append(
                    f"{translation_unit}: resolved private dependency header "
                    f"{header} ({reason})"
                )

    if checked == 0:
        print(f"no CDIN translation units were found in {database}", file=sys.stderr)
        return 2
    if violations:
        print("Compiler-resolved include boundary violations:", file=sys.stderr)
        print("\n".join(sorted(set(violations))), file=sys.stderr)
        return 1

    print(
        f"Compiler-resolved include graph: OK "
        f"({checked} CDIN translation units; no component source/build headers)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
