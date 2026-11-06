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

ROOT = Path(__file__).resolve().parents[1]
BUILD_BIN = ROOT / "build" / "stack" / "cdin"
INSTALL_BIN = ROOT / ".deps" / "install" / "bin"

SCRATCH_RE = re.compile(rb"cdin-untitled-[0-9]+-[0-9]+-[0-9]+\.cdin")
PAYLOAD = b"PTY_EDIT_7391"
RESTORE = (b"\x1b[?25h", b"\x1b[?2004l", b"\x1b[?1049l")
ENTER = (b"\x1b[?25l", b"\x1b[?2004h", b"\x1b[?1049h")


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_cdin_executable(raw: str) -> str:
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
    return str(executable)


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



def wait_for_title(master: int, process: subprocess.Popen[bytes], output: bytearray) -> None:
    read_until(master, process, output,
               lambda b: SCRATCH_RE.search(b) is not None, 10.0, "TUI title")

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


def public_status_flags(flags: int) -> int:
    """Ignore kernel-maintained F_GETFL bits such as Darwin FWASWRITTEN."""
    mask = os.O_ACCMODE | os.O_APPEND | os.O_NONBLOCK
    for name in ("O_ASYNC", "O_SYNC", "O_DSYNC"):
        mask |= getattr(os, name, 0)
    return flags & mask


def assert_restored(slave: int, before_termios, before_flags: int, output: bytearray) -> None:
    missing = [token for token in RESTORE if token not in output]
    if missing:
        raise AssertionError(f"terminal restore sequences missing: {missing!r}")
    if termios.tcgetattr(slave) != before_termios:
        raise AssertionError("terminal mode was not restored")
    after_flags = fcntl.fcntl(slave, fcntl.F_GETFL)
    if public_status_flags(after_flags) != public_status_flags(before_flags):
        raise AssertionError(
            "terminal descriptor status flags were not restored: "
            f"before=0x{public_status_flags(before_flags):x}, "
            f"after=0x{public_status_flags(after_flags):x}"
        )


def resolve_runtime_root(raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ValueError("Runtime root must be an absolute path")
    runtime_root = candidate.resolve(strict=True)
    expected_root = (ROOT / ".deps" / "src" / "runtime" / "lua").resolve(strict=True)
    if runtime_root != expected_root or not runtime_root.is_dir():
        raise ValueError("Runtime root must be the pinned Runtime Lua directory")
    return runtime_root


def run_live_edit(executable: str) -> None:
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    before_termios = termios.tcgetattr(slave)
    output = bytearray()
    process = None
    with tempfile.TemporaryDirectory(prefix="cdin-tui-pty-") as working:
        try:
            os.set_blocking(master, False)
            # Capture the slave's baseline only after the harness has made
            # its master nonblocking. Darwin PTYs may expose paired status
            # flags; this keeps the assertion focused on changes made by CDIN.
            before_flags = fcntl.fcntl(slave, fcntl.F_GETFL)
            env = os.environ.copy()
            env["CDIN_ENABLE_EXPERIMENTAL_TUI"] = "1"
            process = subprocess.Popen(
                [executable, "--frontend", "tui"],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=working, env=env, close_fds=True,
            )
            read_until(master, process, output,
                       lambda b: SCRATCH_RE.search(b) is not None, 10.0, "TUI title")
            if SCRATCH_RE.search(output) is None:
                raise AssertionError("TUI title did not contain the expected scratch document name")

            # Runtime assigns a constrained scratch name before the first
            # save; the file itself is created only by Ctrl+S. Accept exactly
            # one unique name matching the title grammar, then anchor it to
            # the private temporary directory without following output paths.
            working_root = Path(working).resolve(strict=True)
            scratch_names = set(SCRATCH_RE.findall(output))
            if len(scratch_names) != 1:
                raise AssertionError(
                    f"expected one unique scratch title in PTY output, found {len(scratch_names)}"
                )
            scratch_name = next(iter(scratch_names)).decode("ascii")
            scratch_path = (working_root / scratch_name).resolve(strict=False)
            if scratch_path.parent != working_root:
                raise AssertionError("scratch document path escaped the temporary directory")

            # Force a signal to interrupt the platform wait while the loop is
            # live; the self-pipe must turn it into a resize notification.
            os.kill(process.pid, signal.SIGWINCH)
            os.write(master, PAYLOAD)
            read_until(master, process, output,
                       lambda b: PAYLOAD in b, 10.0, "canonical text to render")

            # Save and quit in one input batch. This leaves a UI update pending
            # at teardown while the save itself must finish atomically.
            os.write(master, b"\x13\x11")
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


def run_signal_shutdown(executable: str) -> None:
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    before_termios = termios.tcgetattr(slave)
    output = bytearray()
    process = None
    with tempfile.TemporaryDirectory(prefix="cdin-tui-sigterm-") as working:
        try:
            os.set_blocking(master, False)
            before_flags = fcntl.fcntl(slave, fcntl.F_GETFL)
            env = os.environ.copy()
            env["CDIN_ENABLE_EXPERIMENTAL_TUI"] = "1"
            process = subprocess.Popen(
                [executable, "--frontend", "tui"],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=working, env=env, close_fds=True,
            )
            wait_for_title(master, process, output)
            os.kill(process.pid, signal.SIGTERM)
            code = wait_exit(master, process, output, 10.0)
            if code != 0:
                raise RuntimeError(f"SIGTERM shutdown exited with {code}; output={bytes(output)!r}")
            assert_restored(slave, before_termios, before_flags, output)
            print("CDIN TUI SIGTERM smoke passed: wake-pipe latch, orderly shutdown and terminal restoration")
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
    output = bytearray()
    process = None
    with tempfile.TemporaryDirectory(prefix="cdin-tui-startup-failure-") as working:
        try:
            os.set_blocking(master, False)
            before_flags = fcntl.fcntl(slave, fcntl.F_GETFL)
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
                after_flags = fcntl.fcntl(slave, fcntl.F_GETFL)
                if public_status_flags(after_flags) != public_status_flags(before_flags):
                    raise AssertionError("startup failure changed terminal status flags without restoring them")
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
    try:
        executable = resolve_cdin_executable(sys.argv[1])
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    runtime_value = os.environ.get("CDIN_RUNTIME_ROOT")
    if not runtime_value:
        print("CDIN_RUNTIME_ROOT must point at the pinned Runtime Lua tree", file=sys.stderr)
        return 2
    try:
        os.environ["CDIN_RUNTIME_ROOT"] = str(resolve_runtime_root(runtime_value))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    run_live_edit(executable)
    run_signal_shutdown(executable)
    run_startup_failure(executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
