#!/usr/bin/env python3
"""Run one allowlisted CDIN CLI contract case against the built executable."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from smoke_support import resolve_cdin_executable

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


def main() -> int:
    if len(sys.argv) < 4:
        print(
            "usage: assert_cli.py EXIT STDOUT_TOKEN STDERR_TOKEN [ARGS...]",
            file=sys.stderr,
        )
        return 2

    expected_status, stdout_token, stderr_token, *arguments = sys.argv[1:]
    try:
        expected = int(expected_status)
    except ValueError:
        print(f"invalid expected exit status: {expected_status}", file=sys.stderr)
        return 2

    if tuple(arguments) not in VALID_INVOCATIONS:
        print("CLI test invocation is not allowlisted", file=sys.stderr)
        return 2

    try:
        executable = resolve_cdin_executable()
    except (OSError, ValueError) as error:
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
