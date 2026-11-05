#!/usr/bin/env python3
"""Exercise the real POSIX TUI process through a pseudo-terminal."""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

SCRATCH_RE = re.compile(rb"cdin-untitled-[0-9]+-[0-9]+-[0-9]+\\.cdin")
PAYLOAD = b"PTY_EDIT_7391"
RESTORE = (b"\\x1b[?25h", b"\\x1b[?2004l", b"\\x1b[?1049l")
ENTER = (b"\\x1b[?25l", b"\\x1b[?2004h", b"\\x1b[?1049h")


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


def read_until(master: int, process: subprocess.Popen[bytes], output: bytearray,
               predicate, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"cdin exited before {what} ({process.returncode}); output={bytes(output)!r}")
        ready, _, _ = select.select([master], [], [], 0.05)
        if ready:
            try:
                chunk = os.read(master, 8192)
            except OSError:
                chunk = b""
            if chunk:
                output.extend(chunk)
        if predicate(output):
            return
    raise TimeoutError(f"{what} not observed; output={bytes(output)!r}")


def wait_exit(master: int, process: subprocess.Popen[bytes], output: bytearray,
              timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        drain(master, output)
        select.select([master], [], [], 0.05)
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)
        raise TimeoutError("TUI did not exit before timeout")
    drain(master, output)
    return process.returncode


def assert_restored(slave: int, before_termios, before_flags: int, output: bytearray) -> None:
    missing = [token for token in RESTORE if token not in output]
    if missing:
        raise AssertionError(f"terminal restore sequences missing: {missing!r}")
    if termios.tcgetattr(slave) != before_termios:
        raise AssertionError("terminal mode was not restored")
    if fcntl.fcntl(slave, fcntl.F_GETFL) != before_flags:
        raise AssertionError("terminal descriptor flags were not restored")


def run_live_edit(executable: str) -> None:
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    before_termios = termios.tcgetattr(slave)
    before_flags = fcntl.fcntl(slave, fcntl.F_GETFL)
    output = bytearray()
    process = None
    with tempfile.TemporaryDirectory(prefix="cdin-tui-pty-") as working:
        try:
            os.set_blocking(master, False)
            env = os.environ.copy()
            env["CDIN_ENABLE_EXPERIMENTAL_TUI"] = "1"
            process = subprocess.Popen(
                [executable, "--frontend", "tui"],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=working, env=env, close_fds=True,
            )
            read_until(master, process, output,
                       lambda b: SCRATCH_RE.search(b) is not None, 10.0, "TUI title")
            match = SCRATCH_RE.search(output)
            assert match is not None
            scratch_path = Path(working) / match.group(0).decode("ascii")

            # Force a signal to interrupt the platform wait while the loop is
            # live; the self-pipe must turn it into a resize notification.
            os.kill(process.pid, signal.SIGWINCH)
            os.write(master, PAYLOAD)
            read_until(master, process, output,
                       lambda b: PAYLOAD in b, 10.0, "canonical text to render")

            # Save and quit in one input batch. This leaves a UI update pending
            # at teardown while the save itself must finish atomically.
            os.write(master, b"\\x13\\x11")
            code = wait_exit(master, process, output, 10.0)
            if code != 0:
                raise RuntimeError(f"cdin exited with {code}; output={bytes(output)!r}")
            if not scratch_path.is_file() or scratch_path.read_bytes() != PAYLOAD:
                raise AssertionError("shutdown lost the completed Ctrl+S save")
            assert_restored(slave, before_termios, before_flags, output)
            print("CDIN TUI PTY smoke passed: render, SIGWINCH interruption, save+quit with pending UI work, terminal restore")
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            os.close(slave)
            os.close(master)


def run_startup_failure(executable: str) -> None:
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    before_termios = termios.tcgetattr(slave)
    before_flags = fcntl.fcntl(slave, fcntl.F_GETFL)
    output = bytearray()
    process = None
    with tempfile.TemporaryDirectory(prefix="cdin-tui-startup-failure-") as working:
        try:
            os.set_blocking(master, False)
            env = os.environ.copy()
            env["CDIN_ENABLE_EXPERIMENTAL_TUI"] = "1"
            env["CDIN_RUNTIME_ROOT"] = str(Path(working) / "missing-runtime-root")
            process = subprocess.Popen(
                [executable, "--frontend", "tui"],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=working, env=env, close_fds=True,
            )
            code = wait_exit(master, process, output, 10.0)
            if code == 0:
                raise AssertionError("TUI unexpectedly started with a missing Runtime root")
            if any(token in output for token in ENTER):
                assert_restored(slave, before_termios, before_flags, output)
            else:
                if termios.tcgetattr(slave) != before_termios:
                    raise AssertionError("startup failure changed terminal mode without restoring it")
                if fcntl.fcntl(slave, fcntl.F_GETFL) != before_flags:
                    raise AssertionError("startup failure changed terminal flags without restoring them")
            print("CDIN TUI startup-failure smoke passed: terminal state remained unchanged or was restored")
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            os.close(slave)
            os.close(master)


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
    run_live_edit(executable)
    run_startup_failure(executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
