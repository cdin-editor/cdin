#!/usr/bin/env python3
"""Audit compiler-resolved include dependencies of CDIN translation units.

The compiler's own include trace is authoritative. Compile-database paths and
compiler names are validated before they are used; the probe receives only
allowlisted compiler options and a resolved CDIN source file.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build" / "stack" / "cdin"
SOURCE_ROOT = ROOT / "src"
DEFAULT_DATABASE = BUILD_ROOT / "compile_commands.json"
DEPENDENCY_ROOT = ROOT / ".deps"
INSTALL_PREFIX = DEPENDENCY_ROOT / "install"
PRIVATE_BUILD_ROOTS = tuple(
    ROOT / "build" / "stack" / name
    for name in ("logger", "kernel", "backend", "frontend")
)
ALLOWED_SYSTEM_ROOTS = tuple(
    Path(value)
    for value in (
        "/usr",
        "/opt",
        "/Library",
        "/Applications",
        "/ucrt64",
        "/mingw64",
        "C:/msys64",
    )
)
ALLOWED_COMPILERS = {
    "cc", "cc.exe", "gcc", "gcc.exe", "clang", "clang.exe",
    "x86_64-w64-mingw32-gcc", "x86_64-w64-mingw32-gcc.exe",
}
ALLOWED_STANDARDS = {"c11", "gnu11", "c17", "gnu17"}


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_trusted_path(
    raw: str | Path,
    base: Path,
    trusted_roots: tuple[Path, ...],
    *,
    strict: bool = True,
) -> Path:
    """Resolve a path only after proving its lexical and real paths stay allowlisted."""
    raw_value = os.fspath(raw)
    joined = raw_value if os.path.isabs(raw_value) else os.path.join(os.fspath(base), raw_value)
    candidate = os.path.normcase(os.path.abspath(os.path.normpath(joined)))

    for root in trusted_roots:
        # Compare lexical absolute paths first. Resolving the root before this
        # check breaks valid macOS paths under /var, which aliases /private/var.
        root_lexical = os.path.normcase(
            os.path.abspath(os.path.normpath(os.fspath(root)))
        )
        try:
            if os.path.commonpath((candidate, root_lexical)) != root_lexical:
                continue
        except ValueError:
            continue

        # A lexical match is not sufficient: resolve symlinks for both sides
        # and prove the physical candidate still belongs to the trusted root.
        resolved = Path(candidate).resolve(strict=strict)
        resolved_root = Path(root_lexical).resolve(strict=False)
        if is_within(resolved, resolved_root):
            return resolved
        raise ValueError("resolved path escaped its allowlisted root")

    raise ValueError("path is outside the allowlisted roots")


def resolve_entry_paths(
    entry: dict[str, Any],
    *,
    build_root: Path,
    source_root: Path,
) -> tuple[Path, Path]:
    """Resolve one compile-database entry inside the trusted build/source roots."""
    raw_directory = entry.get("directory")
    raw_file = entry.get("file")
    if not isinstance(raw_directory, str) or not isinstance(raw_file, str):
        raise ValueError("compile entry must contain string directory and file fields")

    working_directory = resolve_trusted_path(raw_directory, ROOT, (build_root,))
    if not working_directory.is_dir():
        raise ValueError("compile entry working directory is outside the CDIN build tree")

    translation_unit = resolve_trusted_path(raw_file, working_directory, (source_root,))
    if not translation_unit.is_file() or translation_unit.suffix.lower() != ".c":
        raise ValueError("compile entry must resolve to a C source file")
    return working_directory, translation_unit


def classify_include(
    include_path: str | Path,
    *,
    working_directory: Path,
    dependency_root: Path = DEPENDENCY_ROOT,
    install_prefix: Path = INSTALL_PREFIX,
    private_build_roots: tuple[Path, ...] = PRIVATE_BUILD_ROOTS,
) -> str | None:
    """Return a violation reason, or None for an allowed resolved header."""
    trusted_roots = (
        working_directory,
        ROOT,
        dependency_root,
        install_prefix,
        *private_build_roots,
        *ALLOWED_SYSTEM_ROOTS,
    )
    resolved = resolve_trusted_path(include_path, working_directory, trusted_roots)
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
        parts = shlex.split(command, posix=False)
        return [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in "'\"" else part
            for part in parts
        ]
    return shlex.split(command, posix=True)


def resolve_compiler(raw: str) -> str:
    name = Path(raw).name.lower()
    if name not in ALLOWED_COMPILERS:
        raise ValueError(f"compiler is not allowlisted: {name}")
    compiler = shutil.which(name)
    if compiler is None:
        raise ValueError(f"allowlisted compiler was not found on PATH: {name}")
    return str(Path(compiler).resolve(strict=True))


def resolve_include_directory(raw: str, working_directory: Path) -> Path:
    trusted_roots = (
        ROOT,
        DEPENDENCY_ROOT,
        *PRIVATE_BUILD_ROOTS,
        *ALLOWED_SYSTEM_ROOTS,
    )
    directory = resolve_trusted_path(raw, working_directory, trusted_roots)
    if not directory.is_dir():
        raise ValueError("compiler include path is not a directory")
    return directory


def dependency_probe_command(
    arguments: list[str],
    *,
    translation_unit: Path,
    working_directory: Path,
) -> list[str]:
    """Build a safe compiler include-trace command from a compile entry."""
    if not arguments:
        raise ValueError("empty compiler command")

    result = [resolve_compiler(arguments[0])]
    index = 1
    include_flags = {"-I", "-isystem", "-iquote", "-idirafter", "-isysroot"}
    while index < len(arguments):
        argument = arguments[index]

        if argument in include_flags:
            if index + 1 >= len(arguments):
                raise ValueError(f"compiler option is missing its value: {argument}")
            directory = resolve_include_directory(arguments[index + 1], working_directory)
            result.extend([argument, str(directory)])
            index += 2
            continue

        matched_include = next(
            (flag for flag in ("-isystem", "-iquote", "-idirafter", "-I")
             if argument.startswith(flag) and len(argument) > len(flag)),
            None,
        )
        if matched_include is not None:
            directory = resolve_include_directory(argument[len(matched_include):], working_directory)
            result.append(matched_include + str(directory))
            index += 1
            continue

        if argument in {"-D", "-U"}:
            if index + 1 >= len(arguments):
                raise ValueError(f"compiler option is missing its value: {argument}")
            value = arguments[index + 1]
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:=.*)?", value):
                raise ValueError(f"unsafe preprocessor definition: {value!r}")
            result.extend([argument, value])
            index += 2
            continue

        if argument.startswith("-D") or argument.startswith("-U"):
            value = argument[2:]
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:=.*)?", value):
                raise ValueError(f"unsafe preprocessor definition: {value!r}")
            result.append(argument)
            index += 1
            continue

        if argument.startswith("-std="):
            standard = argument.removeprefix("-std=")
            if standard not in ALLOWED_STANDARDS:
                raise ValueError(f"C language standard is not allowlisted: {standard}")
            result.append(argument)
            index += 1
            continue

        if argument == "-pthread":
            result.append(argument)

        # All other compiler flags (outputs, warning flags, plugins, response
        # files, linker options and code-generation options) are intentionally
        # omitted from this preprocessing-only inspection pass.
        index += 1

    result.extend([str(translation_unit), "-E", "-H", "-o", os.devnull])
    return result


def traced_headers(stderr: str, working_directory: Path) -> list[Path]:
    headers: list[Path] = []
    for line in stderr.splitlines():
        match = re.match(r"^\s*\.+\s+(.+?)\s*$", line)
        if match is None:
            continue
        candidate = match.group(1).strip()
        try:
            path = resolve_trusted_path(
                candidate,
                working_directory,
                (working_directory, ROOT, DEPENDENCY_ROOT, *PRIVATE_BUILD_ROOTS, *ALLOWED_SYSTEM_ROOTS),
            )
        except (OSError, ValueError):
            continue
        if path.is_file():
            headers.append(path)
    return headers


def main() -> int:
    if len(sys.argv) != 1:
        print("usage: check_include_graph.py", file=sys.stderr)
        return 2

    database = DEFAULT_DATABASE.resolve(strict=False)
    if not database.is_file() or not is_within(database, BUILD_ROOT.resolve(strict=False)):
        print(f"compiler database not found in the CDIN build tree: {database}", file=sys.stderr)
        return 2

    try:
        entries = json.loads(database.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"could not read compiler database: {error}", file=sys.stderr)
        return 2
    if not isinstance(entries, list):
        print("compile_commands.json must contain an array", file=sys.stderr)
        return 2

    build_root = BUILD_ROOT.resolve(strict=True)
    source_root = SOURCE_ROOT.resolve(strict=True)
    checked = 0
    violations: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            violations.append("compile database contains a non-object entry")
            continue

        try:
            working_directory, translation_unit = resolve_entry_paths(
                entry,
                build_root=build_root,
                source_root=source_root,
            )
            arguments = command_from_entry(entry)
            probe = dependency_probe_command(
                arguments,
                translation_unit=translation_unit,
                working_directory=working_directory,
            )
            checked += 1
            completed = subprocess.run(
                probe,
                cwd=working_directory,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                shell=False,
            )
        except (OSError, ValueError) as error:
            violations.append(f"compile entry rejected: {error}")
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
        print(f"no CDIN translation units were checked in {database}", file=sys.stderr)
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
