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

from smoke_support import resolve_cdin_executable, resolve_runtime_root, scratch_file_from_output

ROOT = Path(__file__).resolve().parents[1]
BUILD_BIN = ROOT / "build" / "stack" / "cdin"
INSTALL_BIN = ROOT / ".deps" / "install" / "bin"

SCRATCH_RE = re.compile(rb"cdin-untitled-([0-9]{1,10})-([0-9]{1,10})-([0-9]{1,10})\.cdin")
PAYLOAD = b"PTY_EDIT_7391"
BURST_COUNT = 4
LIVE_PLUGIN_INIT = b"CDIN_TUI_EXTENSION_INIT_7391"
LIVE_PLUGIN_UNLOAD = b"CDIN_TUI_EXTENSION_UNLOAD_7391"
LIVE_PLUGIN_SOURCE = """\
local logger
return {
  init = function(core)
    logger = core
    core:log("info", "CDIN_TUI_EXTENSION_INIT_7391")
  end,
  unload = function()
    if logger ~= nil then
      logger:log("info", "CDIN_TUI_EXTENSION_UNLOAD_7391")
    end
  end,
}
"""
RESTORE = (b"\x1b[?25h", b"\x1b[?2004l", b"\x1b[?1049l")
ENTER = (b"\x1b[?25l", b"\x1b[?2004h", b"\x1b[?1049h")


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


def prepare_live_extension(working: Path) -> Path:
    extension_root = working / "extensions"
    extension_dir = extension_root / "smoke"
    extension_dir.mkdir(parents=True)
    (extension_dir / "init.lua").write_text(LIVE_PLUGIN_SOURCE, encoding="utf-8")
    return extension_root

def run_live_edit(executable: str) -> None:
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    before_termios = termios.tcgetattr(slave)
    output = bytearray()
    process = None
    with tempfile.TemporaryDirectory(prefix="cdin-tui-pty-") as working:
        try:
            extension_root = prepare_live_extension(Path(working))
            os.set_blocking(master, False)
            # Capture the slave's baseline only after the harness has made
            # its master nonblocking. Darwin PTYs may expose paired status
            # flags; this keeps the assertion focused on changes made by CDIN.
            before_flags = fcntl.fcntl(slave, fcntl.F_GETFL)
            env = os.environ.copy()
            env["CDIN_ENABLE_EXPERIMENTAL_TUI"] = "1"
            process = subprocess.Popen(
                [executable, "--frontend", "tui", "--extension-root", str(extension_root),
                 "--load-extension", "smoke"],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=working, env=env, close_fds=True,
            )
            read_until(master, process, output,
                       lambda b: SCRATCH_RE.search(b) is not None, 10.0, "TUI title")
            if SCRATCH_RE.search(output) is None:
                raise AssertionError("TUI title did not contain the expected scratch document name")

            if len(set(SCRATCH_RE.findall(output))) != 1:
                raise AssertionError("expected one unique scratch title in PTY output")

            # Force a signal to interrupt the platform wait while the loop is
            # live; the self-pipe must turn it into a resize notification.
            expected_payload = PAYLOAD * BURST_COUNT
            for index in range(BURST_COUNT):
                os.write(master, PAYLOAD)
                # Interleave resize notifications with repeated Backend work
                # while the owner loop is servicing terminal input.
                if index % 2 == 0:
                    os.kill(process.pid, signal.SIGWINCH)
            read_until(master, process, output,
                       lambda b: expected_payload in b, 10.0,
                       "all burst text rendered without a lost wakeup")

            # Save and quit in one input batch. This leaves a UI update pending
            # at teardown while the save itself must finish atomically.
            os.write(master, b"\x13\x11")
            code = wait_exit(master, process, output, 10.0)
            if code != 0:
                raise RuntimeError(f"cdin exited with {code}; output={bytes(output)!r}")
            scratch_path = scratch_file_from_output(output, Path(working), SCRATCH_RE)
            if scratch_path.read_bytes() != expected_payload:
                raise AssertionError("shutdown lost the completed Ctrl+S save")
            assert_restored(slave, before_termios, before_flags, output)
            if LIVE_PLUGIN_INIT not in output or LIVE_PLUGIN_UNLOAD not in output:
                raise AssertionError("live TUI extension init/unload lifecycle was not observed")
            print("CDIN TUI PTY smoke passed: render, SIGWINCH, edit/save/quit, live extension init/unload and terminal restore")
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
            extension_root = prepare_live_extension(Path(working))
            os.set_blocking(master, False)
            before_flags = fcntl.fcntl(slave, fcntl.F_GETFL)
            env = os.environ.copy()
            env["CDIN_ENABLE_EXPERIMENTAL_TUI"] = "1"
            process = subprocess.Popen(
                [executable, "--frontend", "tui", "--extension-root", str(extension_root),
                 "--load-extension", "smoke"],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=working, env=env, close_fds=True,
            )
            wait_for_title(master, process, output)
            os.kill(process.pid, signal.SIGTERM)
            code = wait_exit(master, process, output, 10.0)
            if code != 0:
                raise RuntimeError(f"SIGTERM shutdown exited with {code}; output={bytes(output)!r}")
            assert_restored(slave, before_termios, before_flags, output)
            if LIVE_PLUGIN_INIT not in output or LIVE_PLUGIN_UNLOAD not in output:
                raise AssertionError("SIGTERM TUI extension init/unload lifecycle was not observed")
            print("CDIN TUI SIGTERM smoke passed: wake-pipe latch, live extension unload and terminal restoration")
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
    if len(sys.argv) != 1:
        print("usage: tui_pty_smoke.py", file=sys.stderr)
        return 2
    try:
        executable = str(resolve_cdin_executable())
        os.environ["CDIN_RUNTIME_ROOT"] = str(resolve_runtime_root())
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    run_live_edit(executable)
    run_signal_shutdown(executable)
    run_startup_failure(executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
