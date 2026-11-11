#!/usr/bin/env python3
"""Build and verify the pinned CDIN component stack in dependency order."""
from __future__ import annotations
import argparse
import os
import re
import shutil
import subprocess
import sys
import hashlib
import json
import urllib.request
import tomllib
from pathlib import Path

try:
    from .package_sdl3_sdk import safe_extract as safe_extract_sdl3_source
except ImportError:  # Direct execution: scripts/ is sys.path[0].
    from package_sdl3_sdk import safe_extract as safe_extract_sdl3_source

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / ".deps" / "src"
PROFILE = "tui"
WORKSPACE = ROOT / ".deps" / "registry-workspace-tui"
PREFIX = ROOT / ".deps" / "install"
BUILD = ROOT / "build" / "stack"
LOCK = ROOT / "deps.lock"


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
    result["CMAKE_PREFIX_PATH"] = os.pathsep.join(
        [str(PREFIX), result.get("CMAKE_PREFIX_PATH", "")]
    ).rstrip(os.pathsep)
    if os.name == "nt":
        # Windows does not use the executable's RPATH. The Kernel package
        # installs cdin_kernel.dll into PREFIX/bin, while CTest launches the
        # CDIN build-tree executable from BUILD/cdin. Make installed component
        # runtime DLLs discoverable for both CTest and the installed smoke test.
        runtime_dirs = [str(PREFIX / "bin"), str(PREFIX / "lib")]
        current_path = result.get("PATH")
        if current_path:
            runtime_dirs.append(current_path)
        result["PATH"] = os.pathsep.join(runtime_dirs)
    return result


def cmake_component(name: str, source: Path, *, options: list[str], env: dict[str, str]) -> None:
    build = BUILD / name
    run(["cmake", "-S", str(source), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
         f"-DCMAKE_INSTALL_PREFIX={PREFIX}", *options], env=env)
    run(["cmake", "--build", str(build), "--parallel"], env=env)
    run(["ctest", "--test-dir", str(build), "--output-on-failure"], env=env)
    run(["cmake", "--install", str(build)], env=env)


def install_sdl3(env: dict[str, str]) -> None:
    """Build the checksum-pinned SDL3 needed by the optional GUI peer."""
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    spec = lock["tooling"]["sdl3"]
    version = spec["version"]
    archive = ROOT / ".deps" / "archives" / f"SDL3-{version}.tar.gz"
    source_root = DEPS / "sdl3"
    archive.parent.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    if not archive.is_file():
        print(f"Downloading SDL3 {version}", flush=True)
        urllib.request.urlretrieve(spec["archive"], archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != spec["sha256"]:
        raise RuntimeError(
            f"SDL3 SHA-256 mismatch: expected {spec['sha256']}, found {digest}"
        )

    source = source_root / f"SDL3-{version}"
    if not (source / "CMakeLists.txt").is_file():
        # SHA-256 authenticates the downloaded bytes; safe_extract separately
        # enforces path, entry-type, collision and expansion limits before any
        # source file is written.
        safe_extract_sdl3_source(archive, source_root)
    if not (source / "CMakeLists.txt").is_file():
        raise RuntimeError(f"SDL3 source tree is missing: {source}")

    options = [
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={PREFIX}",
        "-DSDL_SHARED=OFF", "-DSDL_STATIC=ON",
        "-DSDL_TEST_LIBRARY=OFF", "-DSDL_TESTS=OFF",
        "-DSDL_EXAMPLES=OFF", "-DSDL_AUDIO=OFF",
        "-DSDL_CAMERA=OFF", "-DSDL_JOYSTICK=OFF",
        "-DSDL_HAPTIC=OFF", "-DSDL_HIDAPI=OFF",
        "-DSDL_POWER=OFF", "-DSDL_SENSOR=OFF",
        "-DSDL_VIDEO=ON", "-DSDL_RENDER=ON",
        "-DSDL_DUMMYVIDEO=ON",
    ]
    if sys.platform.startswith("linux"):
        options.extend([
            "-DSDL_UNIX_CONSOLE_BUILD=ON", "-DSDL_X11=OFF",
            "-DSDL_WAYLAND=OFF", "-DSDL_KMSDRM=OFF",
            "-DSDL_OPENGL=OFF", "-DSDL_OPENGLES=OFF",
            "-DSDL_VULKAN=OFF",
        ])
    build_dir = BUILD / "sdl3"
    run(["cmake", "-S", str(source), "-B", str(build_dir), *options], env=env)
    run(["cmake", "--build", str(build_dir), "--parallel"], env=env)
    run(["cmake", "--install", str(build_dir)], env=env)


def pinned_package_version(name: str, variant: str = "default") -> str:
    manifest_path = WORKSPACE / "registry-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Registry manifest is missing at {manifest_path}; run make registry"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    matches = [
        item["version"] for item in manifest["components"]
        if item["component_id"] == name and item["variant"] == variant
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Registry manifest must select exactly one {name} release; found {matches}"
        )
    return matches[0]


def verify_runtime_version(executable: Path, env: dict[str, str]) -> None:
    expected = pinned_package_version("runtime")
    print("+", str(executable), "--check", flush=True)
    result = subprocess.run(
        [str(executable), "--check"], cwd=ROOT, env=env,
        text=True, errors="replace", capture_output=True, check=False
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, [str(executable), "--check"])
    output = result.stdout + result.stderr
    marker = re.compile(r"runtime started[^\r\n]*\bversion=" + re.escape(expected) + r"(?:\s|$)")
    if marker.search(output) is None:
        raise RuntimeError(
            f"Backend did not report the pinned Runtime version {expected!r} "
            "during the lifecycle smoke test"
        )


def main() -> int:
    global PROFILE, WORKSPACE
    requested_default = os.environ.get("CDIN_FRONTEND_VARIANT", "tui")
    if requested_default == "gui-sdl":
        default_profile = "gui-sdl"
    elif requested_default == "tui":
        default_profile = "tui"
    else:
        print("CDIN_FRONTEND_VARIANT must be exactly 'tui' or 'gui-sdl'", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("tui", "gui-sdl"), default=default_profile)
    args = parser.parse_args()
    if args.profile == "gui-sdl":
        PROFILE = "gui-sdl"
        WORKSPACE = ROOT / ".deps" / "registry-workspace-gui-sdl"
    else:
        PROFILE = "tui"
        WORKSPACE = ROOT / ".deps" / "registry-workspace-tui"

    for tool in ("git", "cmake", "make", "pkg-config"):
        if shutil.which(tool) is None:
            print(f"missing required build tool: {tool}", file=sys.stderr)
            return 2

    # Registry owns component discovery and immutable source collection.
    # The manifest, not deps.lock, is the authoritative component selection.
    run([sys.executable, "scripts/registry.py", "--profile", PROFILE, "--verify-workspace"])
    run([sys.executable, "scripts/deps.py", "--verify"])
    PREFIX.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    env = pkg_env()
    lua_options: list[str] = []
    if os.name == "nt":
        lua_include = os.environ.get("CDIN_LUA_INCLUDE_DIR")
        lua_library = os.environ.get("CDIN_LUA_LIBRARY")
        if not lua_include or not lua_library:
            print("Windows builds require the explicit Lua 5.4 UCRT64 include and library paths", file=sys.stderr)
            return 2
        lua_options = [f"-DLUA_INCLUDE_DIR={lua_include}", f"-DLUA_LIBRARY={lua_library}"]

    logger = DEPS / "logger"
    logger_build = BUILD / "logger"
    run(["cmake", "-S", str(logger), "-B", str(logger_build),
         "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_INSTALL_PREFIX={PREFIX}",
         "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DBUILD_SHARED_LIBS=OFF",
         "-DBUILD_TESTING=OFF", "-DM_MDY_M_LOG_BUILD_TESTS=OFF",
         "-DM_MDY_M_LOG_BUILD_EXAMPLES=OFF"], env=env)
    run(["cmake", "--build", str(logger_build), "--parallel"], env=env)
    run(["cmake", "--install", str(logger_build)], env=env)

    kernel = DEPS / "kernel"
    kernel_package_version = pinned_package_version("kernel")
    logger_args = [f"DEPS_PREFIX={PREFIX}", f"LOG_SOURCE_DIR={logger}",
                   f"LOG_BUILD_DIR={logger_build}"]
    run(["make", "all", "shared", *logger_args], cwd=kernel, env=env)
    run(["make", "check", *logger_args], cwd=kernel, env=env)
    # Kernel distinguishes the published package version from its C ABI version.
    # Its release workflow supplies PACKAGE_VERSION when installing the .pc file;
    # use the same rule so Backend's pkg-config >=1.2.1 check validates the
    # package release, while ABI 1.1.0 remains recorded in kernel.h.
    run(["make", "install", f"PREFIX={PREFIX}",
         f"PACKAGE_VERSION={kernel_package_version}", *logger_args], cwd=kernel, env=env)

    backend = DEPS / "backend"
    cmake_component("backend", backend, options=["-DCDIN_WITH_LUA=ON",
        "-DCDIN_BUILD_BACKEND=ON", "-DCDIN_BUILD_INTEGRATION_TESTS=ON",
        "-DCDIN_BUILD_EXAMPLES=OFF", "-DBUILD_TESTING=ON", *lua_options], env=env)

    gui_enabled = PROFILE == "gui-sdl"
    if gui_enabled:
        install_sdl3(env)
    frontend = DEPS / "frontend"
    frontend_options = [
        "-DCDIN_FRONTEND_USE_LOG_STUB=OFF",
        "-DCDIN_FRONTEND_BUILD_UI_TUI=ON",
        f"-DCDIN_FRONTEND_BUILD_UI_SDL={'ON' if gui_enabled else 'OFF'}",
        "-DCDIN_FRONTEND_BUILD_UI_HEADLESS=ON",
        "-DCDIN_FRONTEND_BUILD_APPS=OFF",
        "-DCDIN_FRONTEND_BUILD_EXAMPLES=OFF",
    ]
    cmake_component("frontend", frontend, options=frontend_options, env=env)

    root_build = BUILD / "cdin"
    run(["cmake", "-S", str(ROOT), "-B", str(root_build),
         "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_INSTALL_PREFIX={PREFIX}",
         f"-DCDIN_RUNTIME_SOURCE_DIR={DEPS / 'runtime'}",
         f"-DCDIN_REGISTRY_PROFILE={PROFILE}",
         f"-DCDIN_BACKEND_PACKAGE_VERSION={pinned_package_version('backend')}",
         f"-DCDIN_FRONTEND_PACKAGE_VERSION={pinned_package_version('frontend', PROFILE)}",
         "-DCDIN_INSTALL_RUNTIME=ON",
         f"-DCDIN_ENABLE_GUI_SDL={'ON' if gui_enabled else 'OFF'}",
         "-DBUILD_TESTING=ON",
         "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"], env=env)
    run(["cmake", "--build", str(root_build), "--parallel"], env=env)
    run(["ctest", "--test-dir", str(root_build), "--output-on-failure"], env=env)
    run(["cmake", "--install", str(root_build)], env=env)
    executable = PREFIX / "bin" / ("cdin.exe" if os.name == "nt" else "cdin")
    verify_runtime_version(executable, env)
    print("\nCDIN pinned stack: BUILD + COMPONENT TESTS + CLI E2E + LIFECYCLE SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
