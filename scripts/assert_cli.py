#!/usr/bin/env python3
"""Run one allowlisted CDIN CLI contract case against the built executable."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_BIN = ROOT / "build" / "stack" / "cdin"
INSTALL_BIN = ROOT / ".deps" / "install" / "bin"

VALID_INVOCATIONS = {
    ("--help",),
    ("--version",),
    ("--not-a-cdin-option",),
    ("--runtime-root",),
    ("--runtime-entry",),
    ("--frontend",),
    ("--frontend", "gui-sdl"),
    ("--frontend", "unknown"),
    ("--frontend", "tui"),
    ("--extension-root",),
    ("--load-extension",),
    ("--load-extension", "demo"),
}


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_cdin_executable(raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ValueError("CDIN executable path must be absolute")

    try:
        executable = candidate.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"CDIN executable does not exist: {error}") from error

    allowed_roots = (
        BUILD_BIN.resolve(strict=False),
        INSTALL_BIN.resolve(strict=False),
    )
    if not any(is_within(executable, root) for root in allowed_roots):
        raise ValueError("CDIN executable must be inside the repository build/install bin directory")
    if executable.name.lower() not in {"cdin", "cdin.exe"} or not executable.is_file():
        raise ValueError("target must be the built CDIN executable")
    return executable


def main() -> int:
    if len(sys.argv) < 5:
        print(
            "usage: assert_cli.py EXECUTABLE EXIT STDOUT_TOKEN STDERR_TOKEN [ARGS...]",
            file=sys.stderr,
        )
        return 2

    executable_arg, expected_status, stdout_token, stderr_token, *arguments = sys.argv[1:]
    try:
        expected = int(expected_status)
    except ValueError:
        print(f"invalid expected exit status: {expected_status}", file=sys.stderr)
        return 2

    if tuple(arguments) not in VALID_INVOCATIONS:
        print("CLI test invocation is not allowlisted", file=sys.stderr)
        return 2

    try:
        executable = resolve_cdin_executable(executable_arg)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    completed = subprocess.run(
        [str(executable), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
    )
    failures = []
    if completed.returncode != expected:
        failures.append(f"exit status: expected {expected}, got {completed.returncode}")
    if stdout_token != "-" and stdout_token not in completed.stdout:
        failures.append(f"stdout did not contain {stdout_token!r}: {completed.stdout!r}")
    if stderr_token != "-" and stderr_token not in completed.stderr:
        failures.append(f"stderr did not contain {stderr_token!r}: {completed.stderr!r}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"PASS: {' '.join(arguments)} (exit {expected})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
