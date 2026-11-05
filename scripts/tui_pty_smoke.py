#!/usr/bin/env python3
"""Exercise the real POSIX TUI process through a pseudo-terminal."""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

SCRATCH_RE = re.compile(rb"cdin-untitled-[0-9]+-[0-9]+-[0-9]+\.cdin")
PAYLOAD = b"PTY_EDIT_7391"


def drain(master: int, output: bytearray) -> None:
    while True:
        ready, _, _ = select.select([master], [], [], 0)
        if not ready:
            return
        try:
            chunk = os.read(master, 8192)
        except OSError:
            return
        if not chunk:
            return
        output.extend(chunk)


def wait_for_title(master: int, process: subprocess.Popen[bytes], output: bytearray) -> bytes:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"cdin exited early ({process.returncode}); output={bytes(output)!r}")
        ready, _, _ = select.select([master], [], [], 0.05)
        if ready:
            try:
                chunk = os.read(master, 8192)
            except OSError:
                chunk = b""
            if chunk:
                output.extend(chunk)
        match = SCRATCH_RE.search(output)
        if match:
            return match.group(0)
    raise TimeoutError(f"TUI title was not rendered; output={bytes(output)!r}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: tui_pty_smoke.py CDIN_EXECUTABLE", file=sys.stderr)
        return 2
    executable = os.path.abspath(sys.argv[1])
    if not os.path.isfile(executable):
        print(f"cdin executable not found: {executable}", file=sys.stderr)
        return 2
    if not os.environ.get("CDIN_RUNTIME_ROOT"):
        print("CDIN_RUNTIME_ROOT must point at the pinned Runtime Lua tree", file=sys.stderr)
        return 2

    master, slave = pty.openpty()
    before_termios = termios.tcgetattr(slave)
    before_flags = fcntl.fcntl(slave, fcntl.F_GETFL)
    output = bytearray()
    process = None
    scratch_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="cdin-tui-pty-") as working:
        try:
            os.set_blocking(master, False)
            process = subprocess.Popen(
                [executable, "--frontend", "tui"],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=working, env=os.environ.copy(), close_fds=True,
            )
            scratch_name = wait_for_title(master, process, output).decode("ascii")
            scratch_path = Path(working) / scratch_name

            # Send actual terminal text and the Runtime's Ctrl+S save keymap.
            os.write(master, PAYLOAD)
            os.write(master, b"\x13")
            deadline = time.monotonic() + 10.0
            saved = False
            while time.monotonic() < deadline:
                drain(master, output)
                try:
                    saved = scratch_path.is_file() and scratch_path.read_bytes() == PAYLOAD
                except OSError:
                    saved = False
                if saved:
                    break
                if process.poll() is not None:
                    break
                select.select([master], [], [], 0.05)
            if not saved:
                raise RuntimeError(
                    f"Ctrl+S did not persist exact canonical bytes; output={bytes(output)!r}"
                )
            if PAYLOAD not in output:
                raise AssertionError("the inserted document bytes were not rendered to the PTY")

            # Ctrl+Q must run orderly teardown and restore terminal/screen state.
            os.write(master, b"\x11")
            deadline = time.monotonic() + 10.0
            while process.poll() is None and time.monotonic() < deadline:
                drain(master, output)
                select.select([master], [], [], 0.05)
            if process.poll() is None:
                process.kill()
                raise TimeoutError("TUI did not exit after Ctrl+Q")
            drain(master, output)
            if process.returncode != 0:
                raise RuntimeError(f"cdin exited with {process.returncode}; output={bytes(output)!r}")

            required_restore = (b"\x1b[?25h", b"\x1b[?2004l", b"\x1b[?1049l")
            missing = [token for token in required_restore if token not in output]
            if missing:
                raise AssertionError(f"terminal restore sequences missing: {missing!r}")
            if termios.tcgetattr(slave) != before_termios:
                raise AssertionError("terminal mode was not restored after TUI shutdown")
            if fcntl.fcntl(slave, fcntl.F_GETFL) != before_flags:
                raise AssertionError("terminal descriptor flags were not restored after TUI shutdown")
            print("CDIN TUI PTY smoke passed: rendered edits, save/reopen bytes, Ctrl+Q and terminal restoration")
            return 0
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            os.close(slave)
            os.close(master)


if __name__ == "__main__":
    raise SystemExit(main())
