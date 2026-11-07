#!/usr/bin/env python3
"""Exercise the live CDIN TUI through a native Windows Pseudo Console (ConPTY)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes

wintypes = ctypes.wintypes
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_BIN = ROOT / "build" / "stack" / "cdin"
INSTALL_BIN = ROOT / ".deps" / "install" / "bin"

SCRATCH_RE = re.compile(rb"cdin-untitled-[0-9]+-[0-9]+-[0-9]+\.cdin")
PAYLOAD = b"WIN_CONPTY_EDIT_8427"
BURST_COUNT = 4
LIVE_PLUGIN_INIT = b"CDIN_TUI_EXTENSION_INIT_8427"
LIVE_PLUGIN_UNLOAD = b"CDIN_TUI_EXTENSION_UNLOAD_8427"
LIVE_PLUGIN_SOURCE = """\
local logger
return {
  init = function(core)
    logger = core
    core:log("info", "CDIN_TUI_EXTENSION_INIT_8427")
  end,
  unload = function()
    if logger ~= nil then
      logger:log("info", "CDIN_TUI_EXTENSION_UNLOAD_8427")
    end
  end,
}
"""
RESTORE = (b"\x1b[?25h", b"\x1b[?2004l", b"\x1b[?1049l")
CREATE_UNICODE_ENVIRONMENT = 0x00000400
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
STILL_ACTIVE = 259
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", STARTUPINFOW),
        ("lpAttributeList", ctypes.c_void_p),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

kernel32.CreatePipe.argtypes = [
    ctypes.POINTER(wintypes.HANDLE),
    ctypes.POINTER(wintypes.HANDLE),
    ctypes.c_void_p,
    wintypes.DWORD,
]
kernel32.CreatePipe.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CreatePseudoConsole.argtypes = [
    COORD,
    wintypes.HANDLE,
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
]
kernel32.CreatePseudoConsole.restype = ctypes.c_long
kernel32.ResizePseudoConsole.argtypes = [wintypes.HANDLE, COORD]
kernel32.ResizePseudoConsole.restype = ctypes.c_long
kernel32.ClosePseudoConsole.argtypes = [wintypes.HANDLE]
kernel32.ClosePseudoConsole.restype = None
kernel32.InitializeProcThreadAttributeList.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
kernel32.UpdateProcThreadAttribute.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
kernel32.DeleteProcThreadAttributeList.restype = None
kernel32.CreateProcessW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.BOOL,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    ctypes.POINTER(STARTUPINFOW),
    ctypes.POINTER(PROCESS_INFORMATION),
]
kernel32.CreateProcessW.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetExitCodeProcess.restype = wintypes.BOOL
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateProcess.restype = wintypes.BOOL
kernel32.PeekNamedPipe.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.PeekNamedPipe.restype = wintypes.BOOL
kernel32.ReadFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.ReadFile.restype = wintypes.BOOL
kernel32.WriteFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.WriteFile.restype = wintypes.BOOL


def win_error(operation: str) -> OSError:
    return ctypes.WinError(ctypes.get_last_error(), operation)


def close_handle(handle: int | None) -> None:
    if handle and handle != INVALID_HANDLE_VALUE:
        kernel32.CloseHandle(handle)


class PseudoConsole:
    def __init__(
        self, executable: Path, working_directory: Path, environment: dict[str, str],
        extension_root: Path | None = None,
    ) -> None:
        self.hpc = wintypes.HANDLE()
        self.input_write = wintypes.HANDLE()
        self.output_read = wintypes.HANDLE()
        self.process = wintypes.HANDLE()
        self.thread = wintypes.HANDLE()
        self.attribute_list = None
        self.attribute_list_initialized = False
        self.attribute_buffer = None
        self.output = bytearray()
        input_read = wintypes.HANDLE()
        output_write = wintypes.HANDLE()

        if not kernel32.CreatePipe(
            ctypes.byref(input_read), ctypes.byref(self.input_write), None, 0
        ):
            raise win_error("CreatePipe(input)")
        if not kernel32.CreatePipe(
            ctypes.byref(self.output_read), ctypes.byref(output_write), None, 0
        ):
            close_handle(input_read)
            close_handle(self.input_write)
            raise win_error("CreatePipe(output)")

        hr = kernel32.CreatePseudoConsole(
            COORD(80, 24), input_read, output_write, 0, ctypes.byref(self.hpc)
        )
        close_handle(input_read)
        close_handle(output_write)
        if hr < 0:
            close_handle(self.input_write)
            close_handle(self.output_read)
            raise OSError(f"CreatePseudoConsole failed: HRESULT 0x{hr & 0xffffffff:08x}")

        try:
            required = ctypes.c_size_t(0)
            kernel32.InitializeProcThreadAttributeList(
                None, 1, 0, ctypes.byref(required)
            )
            if required.value == 0:
                raise win_error("InitializeProcThreadAttributeList(size)")
            self.attribute_buffer = ctypes.create_string_buffer(required.value)
            self.attribute_list = ctypes.cast(self.attribute_buffer, ctypes.c_void_p)
            if not kernel32.InitializeProcThreadAttributeList(
                self.attribute_list, 1, 0, ctypes.byref(required)
            ):
                raise win_error("InitializeProcThreadAttributeList")
            self.attribute_list_initialized = True
            if not kernel32.UpdateProcThreadAttribute(
                self.attribute_list,
                0,
                PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                self.hpc,
                ctypes.sizeof(self.hpc),
                None,
                None,
            ):
                raise win_error("UpdateProcThreadAttribute(PSEUDOCONSOLE)")

            startup = STARTUPINFOEXW()
            startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
            startup.lpAttributeList = self.attribute_list
            info = PROCESS_INFORMATION()
            arguments = [str(executable), "--frontend", "tui"]
            if extension_root is not None:
                arguments.extend([
                    "--extension-root", str(extension_root),
                    "--load-extension", "smoke",
                ])
            command_line = ctypes.create_unicode_buffer(
                subprocess.list2cmdline(arguments)
            )
            env_items = [
                f"{key}={value}" for key, value in sorted(
                    environment.items(), key=lambda item: item[0].upper()
                )
            ]
            env_buffer = ctypes.create_unicode_buffer("\0".join(env_items) + "\0\0")
            flags = EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT
            if not kernel32.CreateProcessW(
                str(executable),
                command_line,
                None,
                None,
                False,
                flags,
                ctypes.cast(env_buffer, ctypes.c_void_p),
                str(working_directory),
                ctypes.byref(startup.StartupInfo),
                ctypes.byref(info),
            ):
                raise win_error("CreateProcessW(ConPTY)")
            self.process = info.hProcess
            self.thread = info.hThread
        except Exception:
            self.close()
            raise
        finally:
            if self.attribute_list:
                if self.attribute_list_initialized:
                    kernel32.DeleteProcThreadAttributeList(self.attribute_list)
                self.attribute_list = None
                self.attribute_list_initialized = False
            close_handle(self.thread)
            self.thread = None

    def resize(self, columns: int, rows: int) -> None:
        hr = kernel32.ResizePseudoConsole(self.hpc, COORD(columns, rows))
        if hr < 0:
            raise OSError(f"ResizePseudoConsole failed: HRESULT 0x{hr & 0xffffffff:08x}")

    def drain(self) -> None:
        while True:
            available = wintypes.DWORD(0)
            if not kernel32.PeekNamedPipe(
                self.output_read, None, 0, None, ctypes.byref(available), None
            ):
                return
            if available.value == 0:
                return
            amount = min(available.value, 65536)
            buffer = ctypes.create_string_buffer(amount)
            received = wintypes.DWORD(0)
            if not kernel32.ReadFile(
                self.output_read, buffer, amount, ctypes.byref(received), None
            ):
                return
            if received.value == 0:
                return
            self.output.extend(buffer.raw[: received.value])

    def read_until(self, predicate, timeout: float, description: str) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.drain()
            if predicate(self.output):
                return
            if self.poll_exit() is not None:
                raise RuntimeError(
                    f"CDIN exited before {description}; output={bytes(self.output)!r}"
                )
            time.sleep(0.01)
        raise TimeoutError(
            f"{description} not observed; output={bytes(self.output)!r}"
        )

    def write(self, payload: bytes) -> None:
        offset = 0
        while offset < len(payload):
            buffer = ctypes.create_string_buffer(payload[offset:])
            written = wintypes.DWORD(0)
            if not kernel32.WriteFile(
                self.input_write,
                buffer,
                len(payload) - offset,
                ctypes.byref(written),
                None,
            ):
                raise win_error("WriteFile(ConPTY input)")
            if written.value == 0:
                raise RuntimeError("ConPTY input pipe accepted zero bytes")
            offset += written.value

    def poll_exit(self) -> int | None:
        if not self.process:
            return None
        result = kernel32.WaitForSingleObject(self.process, 0)
        if result == WAIT_TIMEOUT:
            return None
        if result != WAIT_OBJECT_0:
            raise win_error("WaitForSingleObject(process)")
        code = wintypes.DWORD(0)
        if not kernel32.GetExitCodeProcess(self.process, ctypes.byref(code)):
            raise win_error("GetExitCodeProcess")
        return int(code.value)

    def wait_exit(self, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.drain()
            code = self.poll_exit()
            if code is not None:
                for _ in range(5):
                    time.sleep(0.02)
                    self.drain()
                return code
            time.sleep(0.01)
        if self.process:
            kernel32.TerminateProcess(self.process, 124)
            kernel32.WaitForSingleObject(self.process, 5000)
        raise TimeoutError("CDIN TUI did not exit before timeout")

    def close(self) -> None:
        if self.process:
            if self.poll_exit() is None:
                kernel32.TerminateProcess(self.process, 125)
                kernel32.WaitForSingleObject(self.process, 5000)
            self.drain()
        if self.hpc:
            kernel32.ClosePseudoConsole(self.hpc)
            self.hpc = wintypes.HANDLE()
        close_handle(self.input_write)
        close_handle(self.output_read)
        close_handle(self.process)
        self.input_write = wintypes.HANDLE()
        self.output_read = wintypes.HANDLE()
        self.process = wintypes.HANDLE()


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
    executable = candidate.resolve(strict=True)
    allowed_roots = (
        BUILD_BIN.resolve(strict=False),
        INSTALL_BIN.resolve(strict=False),
    )
    if not any(is_within(executable, root) for root in allowed_roots):
        raise ValueError("CDIN executable must be inside the repository build/install bin directory")
    if executable.name.lower() not in {"cdin", "cdin.exe"} or not executable.is_file():
        raise ValueError("target must be the built CDIN executable")
    return executable


def resolve_runtime_root(raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ValueError("Runtime root must be an absolute path")
    runtime_root = candidate.resolve(strict=True)
    expected_root = (ROOT / ".deps" / "src" / "runtime" / "lua").resolve(strict=True)
    if runtime_root != expected_root or not runtime_root.is_dir():
        raise ValueError("Runtime root must be the pinned Runtime Lua directory")
    return runtime_root


def make_environment(runtime_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["CDIN_ENABLE_EXPERIMENTAL_TUI"] = "1"
    environment["CDIN_RUNTIME_ROOT"] = str(runtime_root)
    return environment


def run_editor(executable: Path, runtime_root: Path, working: Path) -> None:
    extension_root = working / "extensions"
    extension_dir = extension_root / "smoke"
    extension_dir.mkdir(parents=True)
    (extension_dir / "init.lua").write_text(LIVE_PLUGIN_SOURCE, encoding="utf-8")
    session = PseudoConsole(
        executable, working, make_environment(runtime_root), extension_root
    )
    try:
        session.read_until(
            lambda output: SCRATCH_RE.search(output) is not None,
            12.0,
            "initial TUI render and scratch title",
        )
        names = set(SCRATCH_RE.findall(session.output))
        if len(names) != 1:
            raise AssertionError(f"expected one scratch title, found {len(names)}")
        scratch_path = (working / next(iter(names)).decode("ascii")).resolve()
        if scratch_path.parent != working.resolve():
            raise AssertionError("scratch title path escaped the private working directory")

        session.drain()
        output_mark = len(session.output)
        session.resize(100, 32)
        session.read_until(
            lambda output: len(output) > output_mark,
            5.0,
            "TUI redraw after ConPTY resize",
        )

        # ConPTY redraws may insert ANSI cursor/control sequences between
        # successive text bursts, so the raw terminal byte stream is not a
        # contiguous representation of the document. Require a fresh render
        # turn after every burst, then use the saved file below as the
        # authoritative byte-exact assertion for all input.
        for burst in range(BURST_COUNT):
            output_mark = len(session.output)
            session.write(PAYLOAD)
            session.read_until(
                lambda output, mark=output_mark: len(output) > mark,
                3.0,
                f"TUI redraw after input burst {burst + 1}",
            )
        expected_payload = PAYLOAD * BURST_COUNT
        session.write(b"\x13\x11")  # Ctrl+S followed by Ctrl+Q.
        code = session.wait_exit(12.0)
        if code != 0:
            raise RuntimeError(
                f"CDIN TUI exited with {code}; output={bytes(session.output)!r}"
            )
        if not scratch_path.is_file() or scratch_path.read_bytes() != expected_payload:
            raise AssertionError("ConPTY TUI did not persist the exact edited bytes")
        missing = [token for token in RESTORE if token not in session.output]
        if missing:
            raise AssertionError(f"Windows terminal restoration sequences missing: {missing!r}")
        if LIVE_PLUGIN_INIT not in session.output or LIVE_PLUGIN_UNLOAD not in session.output:
            raise AssertionError("live ConPTY extension init/unload lifecycle was not observed")
        print(
            "CDIN Windows ConPTY smoke passed: render, resize, edit/save/quit, "
            "live extension init/unload and terminal restoration"
        )
    finally:
        session.close()


def run_startup_failure(executable: Path, working: Path) -> None:
    missing_runtime = working / "missing-runtime-root"
    session = PseudoConsole(
        executable, working, make_environment(missing_runtime)
    )
    try:
        code = session.wait_exit(12.0)
        if code == 0:
            raise AssertionError("CDIN unexpectedly started with a missing Runtime root")
        entered_terminal = any(
            token in session.output
            for token in (b"\x1b[?25l", b"\x1b[?2004h", b"\x1b[?1049h")
        )
        if entered_terminal:
            missing = [token for token in RESTORE if token not in session.output]
            if missing:
                raise AssertionError(
                    f"Windows terminal was not restored after startup failure: {missing!r}"
                )
        print(
            "CDIN Windows ConPTY startup-failure smoke passed: terminal state "
            "was unchanged or restored"
        )
    finally:
        session.close()


def main() -> int:
    if os.name != "nt":
        print("tui_conpty_smoke.py requires Windows", file=sys.stderr)
        return 2
    if len(sys.argv) != 2:
        print("usage: tui_conpty_smoke.py CDIN_EXECUTABLE", file=sys.stderr)
        return 2
    runtime_value = os.environ.get("CDIN_RUNTIME_ROOT")
    if not runtime_value:
        print("CDIN_RUNTIME_ROOT must point at the pinned Runtime Lua tree", file=sys.stderr)
        return 2
    try:
        executable = resolve_cdin_executable(sys.argv[1])
        runtime_root = resolve_runtime_root(runtime_value)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="cdin-tui-conpty-") as directory:
        working = Path(directory).resolve()
        try:
            run_editor(executable, runtime_root, working)
            run_startup_failure(executable, working)
        except (OSError, RuntimeError, TimeoutError, AssertionError) as error:
            print(f"Windows ConPTY smoke failed: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
