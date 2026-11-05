#!/usr/bin/env python3
"""Build and verify the pinned CDIN component stack in dependency order."""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / ".deps" / "src"
PREFIX = ROOT / ".deps" / "install"
BUILD = ROOT / "build" / "stack"


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def pkg_env() -> dict[str, str]:
    result = os.environ.copy()
    entries = [str(PREFIX / "lib" / "pkgconfig"), str(PREFIX / "lib64" / "pkgconfig")]
    current = result.get("PKG_CONFIG_PATH")
    if current:
        entries.append(current)
    result["PKG_CONFIG_PATH"] = os.pathsep.join(entries)
    result["CMAKE_PREFIX_PATH"] = os.pathsep.join([str(PREFIX), result.get("CMAKE_PREFIX_PATH", "")]).rstrip(os.pathsep)
    return result


def cmake_component(name: str, source: Path, *, options: list[str], env: dict[str, str]) -> None:
    build = BUILD / name
    run(["cmake", "-S", str(source), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
         f"-DCMAKE_INSTALL_PREFIX={PREFIX}", *options], env=env)
    run(["cmake", "--build", str(build), "--parallel"], env=env)
    run(["ctest", "--test-dir", str(build), "--output-on-failure"], env=env)
    run(["cmake", "--install", str(build)], env=env)


def main() -> int:
    for tool in ("git", "cmake", "make", "pkg-config"):
        if shutil.which(tool) is None:
            print(f"missing required build tool: {tool}", file=sys.stderr)
            return 2
    run([sys.executable, "scripts/deps.py"])
    PREFIX.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    env = pkg_env()

    # The logger is built once from the top-level immutable pin and installed
    # into the prefix consumed by Kernel, Backend, Frontend and cdin.
    logger = DEPS / "logger"
    logger_build = BUILD / "logger"
    run(["cmake", "-S", str(logger), "-B", str(logger_build),
         "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_INSTALL_PREFIX={PREFIX}",
         "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DBUILD_SHARED_LIBS=OFF",
         "-DBUILD_TESTING=OFF", "-DM_MDY_M_LOG_BUILD_TESTS=OFF",
         "-DM_MDY_M_LOG_BUILD_EXAMPLES=OFF"], env=env)
    run(["cmake", "--build", str(logger_build), "--parallel"], env=env)
    run(["cmake", "--install", str(logger_build)], env=env)

    # Kernel is Make-based. Point its logger build variables at the pinned
    # source/build just installed above; its pkg-config lookup still uses the
    # shared prefix, and it never fetches a floating logger branch.
    kernel = DEPS / "kernel"
    logger_args = [f"DEPS_PREFIX={PREFIX}", f"LOG_SOURCE_DIR={logger}",
                   f"LOG_BUILD_DIR={logger_build}"]
    run(["make", "all", "shared", *logger_args], cwd=kernel, env=env)
    run(["make", "check", *logger_args], cwd=kernel, env=env)
    run(["make", "install", f"PREFIX={PREFIX}", *logger_args], cwd=kernel, env=env)

    backend = DEPS / "backend"
    cmake_component("backend", backend, options=["-DCDIN_WITH_LUA=ON",
        "-DCDIN_BUILD_BACKEND=ON", "-DCDIN_BUILD_INTEGRATION_TESTS=ON",
        "-DCDIN_BUILD_EXAMPLES=OFF", "-DBUILD_TESTING=ON"], env=env)

    frontend = DEPS / "frontend"
    cmake_component("frontend", frontend, options=["-DCDIN_FRONTEND_USE_LOG_STUB=OFF",
        "-DCDIN_FRONTEND_BUILD_UI_TUI=ON", "-DCDIN_FRONTEND_BUILD_UI_SDL=OFF",
        "-DCDIN_FRONTEND_BUILD_UI_HEADLESS=ON", "-DCDIN_FRONTEND_BUILD_APPS=OFF", "-DCDIN_FRONTEND_BUILD_EXAMPLES=OFF"], env=env)

    root_build = BUILD / "cdin"
    run(["cmake", "-S", str(ROOT), "-B", str(root_build),
         "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_INSTALL_PREFIX={PREFIX}",
         f"-DCDIN_RUNTIME_SOURCE_DIR={DEPS / 'runtime'}",
         "-DCDIN_INSTALL_RUNTIME=ON", "-DBUILD_TESTING=ON"], env=env)
    run(["cmake", "--build", str(root_build), "--parallel"], env=env)
    run(["ctest", "--test-dir", str(root_build), "--output-on-failure"], env=env)
    run(["cmake", "--install", str(root_build)], env=env)
    executable = PREFIX / "bin" / ("cdin.exe" if os.name == "nt" else "cdin")
    run([str(executable), "--check"], env=env)
    print("\nCDIN pinned stack: BUILD + COMPONENT TESTS + CLI E2E + LIFECYCLE SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
