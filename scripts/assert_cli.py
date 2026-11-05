#!/usr/bin/env python3
"""Executable-level CLI contract check; validates process status and output."""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 5:
        print("usage: assert_cli.py EXECUTABLE EXIT STDOUT_TOKEN STDERR_TOKEN [ARGS...]", file=sys.stderr)
        return 2
    executable, expected_status, stdout_token, stderr_token, *arguments = sys.argv[1:]
    try:
        expected = int(expected_status)
    except ValueError:
        print(f"invalid expected exit status: {expected_status}", file=sys.stderr)
        return 2
    completed = subprocess.run(
        [executable, *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
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
