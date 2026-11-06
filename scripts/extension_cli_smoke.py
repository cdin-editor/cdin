#!/usr/bin/env python3
"""Verify CDIN loads and unloads one explicitly selected Lua extension."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_BIN = ROOT / "build" / "stack" / "cdin"
INSTALL_BIN = ROOT / ".deps" / "install" / "bin"

PLUGIN_SOURCE = """\
local logger
return {
  init = function(core)
    logger = core
    core:log("info", "CDIN_EXTENSION_INIT_SENTINEL_8427")
  end,
  unload = function()
    if logger ~= nil then
      logger:log("info", "CDIN_EXTENSION_UNLOAD_SENTINEL_8427")
    end
  end,
}
"""


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_executable(raw: str) -> Path:
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


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: extension_cli_smoke.py CDIN_EXECUTABLE", file=sys.stderr)
        return 2
    runtime_root = os.environ.get("CDIN_RUNTIME_ROOT")
    if not runtime_root or not Path(runtime_root).is_dir():
        print("CDIN_RUNTIME_ROOT must identify the pinned Runtime Lua tree", file=sys.stderr)
        return 2
    try:
        executable = resolve_executable(sys.argv[1])
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="cdin-extension-cli-") as temporary:
        root = Path(temporary).resolve()
        extension_dir = root / "demo"
        extension_dir.mkdir()
        (extension_dir / "init.lua").write_text(PLUGIN_SOURCE, encoding="utf-8")
        working = root / "work"
        working.mkdir()
        environment = os.environ.copy()
        environment["CDIN_RUNTIME_ROOT"] = str(Path(runtime_root).resolve())

        completed = subprocess.run(
            [
                str(executable),
                "--check",
                "--extension-root",
                str(root),
                "--load-extension",
                "demo",
            ],
            cwd=working,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            shell=False,
        )
        combined = completed.stdout + "\n" + completed.stderr
        required = (
            "CDIN_EXTENSION_INIT_SENTINEL_8427",
            "CDIN_EXTENSION_UNLOAD_SENTINEL_8427",
        )
        failures = []
        if completed.returncode != 0:
            failures.append(f"CDIN exited with {completed.returncode}")
        for marker in required:
            if marker not in combined:
                failures.append(f"extension lifecycle marker missing: {marker}")
        if failures:
            print("\n".join(failures), file=sys.stderr)
            print("--- CDIN stdout ---", file=sys.stderr)
            print(completed.stdout, file=sys.stderr)
            print("--- CDIN stderr ---", file=sys.stderr)
            print(completed.stderr, file=sys.stderr)
            return 1
    print("PASS: trusted extension resolver, Runtime init hook, and unload hook")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
