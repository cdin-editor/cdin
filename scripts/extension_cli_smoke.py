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

PLUGIN_SOURCE = """\\
local logger
return {
  init = function(core)
    logger = core

    -- The Runtime sandbox must not expose ambient process, filesystem, debug,
    -- package or dynamic-loading capabilities to an in-process extension.
    local denied = {
      "io", "os", "debug", "package", "dofile", "loadfile",
    }
    for _, name in ipairs(denied) do
      local ok = pcall(function() return _G[name] end)
      if ok then
        error("sandbox exposed forbidden global: " .. name)
      end
    end

    local write_ok = pcall(function() math.pi = 0 end)
    if write_ok then error("sandbox allowed mutation of read-only math library") end

    local require_ok = pcall(require, "unapproved.module")
    if require_ok then error("sandbox allowed module loading without Backend resolver") end

    local global_write_ok = pcall(function() _G.cdin_smoke_escape = true end)
    if global_write_ok then error("sandbox allowed undeclared global write") end

    core:log("info", "CDIN_EXTENSION_CAPABILITY_DENY_SENTINEL_8427")
    core:log("info", "CDIN_EXTENSION_INIT_SENTINEL_8427")
  end,
  unload = function()
    if logger ~= nil then
      logger:log("info", "CDIN_EXTENSION_UNLOAD_SENTINEL_8427")
    end
  end,
}
"""

BROKEN_PLUGIN_SOURCE = """\\
return {
  init = function(core)
    core:commands:register("cdin.smoke.rollback", function() return true end)
    core:log("info", "CDIN_EXTENSION_INIT_FAILURE_SENTINEL_8427")
    error("intentional extension init failure")
  end,
  unload = function()
    core:log("error", "CDIN_EXTENSION_FAILED_INIT_UNLOAD_SENTINEL_8427")
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


def resolve_runtime_root(raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ValueError("Runtime root must be an absolute path")
    runtime_root = candidate.resolve(strict=True)
    expected_root = (ROOT / ".deps" / "src" / "runtime" / "lua").resolve(strict=True)
    if runtime_root != expected_root or not runtime_root.is_dir():
        raise ValueError("Runtime root must be the pinned Runtime Lua directory")
    return runtime_root


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: extension_cli_smoke.py CDIN_EXECUTABLE", file=sys.stderr)
        return 2
    runtime_value = os.environ.get("CDIN_RUNTIME_ROOT")
    if not runtime_value:
        print("CDIN_RUNTIME_ROOT must identify the pinned Runtime Lua tree", file=sys.stderr)
        return 2
    try:
        executable = resolve_executable(sys.argv[1])
        runtime_root = resolve_runtime_root(runtime_value)
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
        environment["CDIN_RUNTIME_ROOT"] = str(runtime_root)

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
            "CDIN_EXTENSION_CAPABILITY_DENY_SENTINEL_8427",
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
    # A failed init must fail the CDIN startup check and must not invoke
    # the explicit-unload hook for an extension that never became active.
    broken_dir = root / "broken"
    broken_dir.mkdir()
    (broken_dir / "init.lua").write_text(BROKEN_PLUGIN_SOURCE, encoding="utf-8")
    failed = subprocess.run(
        [
            str(executable),
            "--check",
            "--extension-root",
            str(root),
            "--load-extension",
            "broken",
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
    failed_output = failed.stdout + "\\n" + failed.stderr
    if failed.returncode == 0:
        print("extension init failure unexpectedly succeeded", file=sys.stderr)
        return 1
    if "CDIN_EXTENSION_INIT_FAILURE_SENTINEL_8427" not in failed_output:
        print("extension init failure sentinel missing", file=sys.stderr)
        print(failed_output, file=sys.stderr)
        return 1
    if "CDIN_EXTENSION_FAILED_INIT_UNLOAD_SENTINEL_8427" in failed_output:
        print("Runtime incorrectly invoked unload after failed init", file=sys.stderr)
        return 1

    print("PASS: trusted extension lifecycle, capability denials, and failed-init semantics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
