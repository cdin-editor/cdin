#!/usr/bin/env python3
"""Build and verify the pinned CDIN component stack in dependency order."""
from __future__ import annotations
import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
import hashlib
import json
import stat
import urllib.request
import tomllib
from pathlib import Path

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


def stage_cmake_prefix(package: Path, prefix: Path) -> None:
    """Merge a Registry-verified cmake-prefix-v1 package into the private prefix.

    Directories may be shared with previously staged environment providers,
    but file paths may never overwrite an existing package. All source entries
    and destination collisions are preflighted before any file is copied.
    """
    try:
        info = package.lstat()
    except OSError as error:
        raise RuntimeError(f"Backend Registry package is unavailable: {package}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("Backend Registry package root must be a real directory")

    required = (
        "include/cdin/backend.h",
        "lib/libcdin_backend.a",
        "lib/libcdin_backend_services.a",
        "lib/libcdin_protocol.a",
        "lib/cmake/cdinBackend/cdinBackendConfig.cmake",
        "lib/pkgconfig/cdin-backend.pc",
        "lib/pkgconfig/cdin-backend-services.pc",
        "lib/pkgconfig/cdin-protocol.pc",
    )
    for relative in required:
        path = package / relative
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"Backend package is missing a regular required file: {relative}")

    prefix = Path(os.path.abspath(prefix))
    ancestor = prefix
    while ancestor != ancestor.parent:
        if ancestor.is_symlink():
            raise RuntimeError(f"Backend package destination contains a symlink ancestor: {ancestor}")
        ancestor = ancestor.parent
    if prefix.exists() or prefix.is_symlink():
        prefix_info = prefix.lstat()
        if stat.S_ISLNK(prefix_info.st_mode) or not stat.S_ISDIR(prefix_info.st_mode):
            raise RuntimeError("Backend package destination must be a real directory")
    else:
        prefix.mkdir(parents=True, exist_ok=False)

    source_root = Path(os.path.abspath(package))
    ancestor = source_root
    while ancestor != ancestor.parent:
        if ancestor.is_symlink():
            raise RuntimeError(f"Backend Registry package contains a symlink ancestor: {ancestor}")
        ancestor = ancestor.parent
    package = source_root
    source_files: list[Path] = []
    for top in ("include", "lib", "bin", "share"):
        source_root = package / top
        if not source_root.exists():
            continue
        if source_root.is_symlink() or not source_root.is_dir():
            raise RuntimeError(f"Backend package contains an unsafe prefix entry: {top}")
        for current, directories, files in os.walk(source_root, topdown=True, followlinks=False):
            current_path = Path(current)
            for name in list(directories):
                source_dir = current_path / name
                if source_dir.is_symlink() or not source_dir.is_dir():
                    raise RuntimeError(
                        f"Backend package contains a symlink/special directory: "
                        f"{source_dir.relative_to(package)}"
                    )
            for name in files:
                source_file = current_path / name
                file_info = source_file.lstat()
                if stat.S_ISLNK(file_info.st_mode) or not stat.S_ISREG(file_info.st_mode):
                    raise RuntimeError(
                        f"Backend package contains a symlink/special file: "
                        f"{source_file.relative_to(package)}"
                    )
                source_files.append(source_file)

    # Preflight every destination before writing any file. A collision must
    # leave the existing private prefix unchanged.
    for source_file in source_files:
        relative = source_file.relative_to(package)
        destination = prefix / relative
        if destination.exists() or destination.is_symlink():
            raise RuntimeError(
                f"Backend package would overwrite an existing staged file: {relative}"
            )
        parent = destination.parent
        while parent != prefix and parent != parent.parent:
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise RuntimeError(f"Backend package has an unsafe destination parent: {parent}")
            parent = parent.parent

    for source_file in source_files:
        relative = source_file.relative_to(package)
        destination = prefix / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise RuntimeError(
                f"Backend package destination changed during staging: {relative}"
            )
        shutil.copy2(source_file, destination)

    print(f"Staged Backend artifact from Registry: {package}", flush=True)


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
        # The source archive is authenticated by the immutable SHA-256 above.
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(source_root)
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
    parser.add_argument(
        "--registry-source-build",
        action="store_true",
        help="developer/CI-only: verify the workspace using the pinned Registry source build",
    )
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
    registry_command = [
        sys.executable, "scripts/registry.py", "--profile", PROFILE, "--verify-workspace"
    ]
    if args.registry_source_build:
        registry_command.append("--source-build")
    run(registry_command)
    run([
        sys.executable,
        "tests/e2e/test_registry_workspace.py",
        "--workspace", str(WORKSPACE),
        "--profile", PROFILE,
    ])
    run([sys.executable, "scripts/deps.py", "--verify"])
    PREFIX.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    env = pkg_env()
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

    backend_package = (
        WORKSPACE / "components" / "backend" / "default" / "package"
    )
    stage_cmake_prefix(backend_package, PREFIX)

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
