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
SDK_PREFIX = ROOT / ".deps" / "sdk"
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


def _stage_install_prefix(
    package: Path,
    prefix: Path,
    *,
    component: str,
    required_files: tuple[str, ...],
) -> None:
    """Merge one verified CMake install prefix without overwriting other SDKs."""
    try:
        info = package.lstat()
    except OSError as error:
        raise RuntimeError(f"{component} package is unavailable: {package}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"{component} package root must be a real directory")

    for relative in required_files:
        path = package / relative
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"{component} package is missing a regular required file: {relative}")

    prefix = Path(os.path.abspath(prefix))
    ancestor = prefix
    while ancestor != ancestor.parent:
        if ancestor.is_symlink():
            raise RuntimeError(f"{component} destination contains a symlink ancestor: {ancestor}")
        ancestor = ancestor.parent
    if prefix.exists() or prefix.is_symlink():
        prefix_info = prefix.lstat()
        if stat.S_ISLNK(prefix_info.st_mode) or not stat.S_ISDIR(prefix_info.st_mode):
            raise RuntimeError(f"{component} destination must be a real directory")
    else:
        prefix.mkdir(parents=True, exist_ok=False)

    package = Path(os.path.abspath(package))
    ancestor = package
    while ancestor != ancestor.parent:
        if ancestor.is_symlink():
            raise RuntimeError(f"{component} package contains a symlink ancestor: {ancestor}")
        ancestor = ancestor.parent

    source_files: list[Path] = []
    for top in ("include", "lib", "bin", "share"):
        source_root = package / top
        if not source_root.exists():
            continue
        if source_root.is_symlink() or not source_root.is_dir():
            raise RuntimeError(f"{component} package contains an unsafe prefix entry: {top}")
        for current, directories, files in os.walk(source_root, topdown=True, followlinks=False):
            current_path = Path(current)
            for name in list(directories):
                source_dir = current_path / name
                if source_dir.is_symlink() or not source_dir.is_dir():
                    raise RuntimeError(
                        f"{component} package contains a symlink/special directory: "
                        f"{source_dir.relative_to(package)}"
                    )
            for name in files:
                source_file = current_path / name
                file_info = source_file.lstat()
                if stat.S_ISLNK(file_info.st_mode) or not stat.S_ISREG(file_info.st_mode):
                    raise RuntimeError(
                        f"{component} package contains a symlink/special file: "
                        f"{source_file.relative_to(package)}"
                    )
                source_files.append(source_file)

    # Preflight the entire file set. Identical existing SDK files are reusable;
    # different bytes at the same path are never silently replaced.
    existing_identical: set[Path] = set()
    for source_file in source_files:
        relative = source_file.relative_to(package)
        destination = prefix / relative
        if destination.is_symlink():
            raise RuntimeError(f"{component} destination is a symlink: {relative}")
        if destination.exists():
            if not destination.is_file():
                raise RuntimeError(f"{component} destination is not a regular file: {relative}")
            if destination.read_bytes() != source_file.read_bytes():
                raise RuntimeError(f"{component} package would overwrite a different staged file: {relative}")
            existing_identical.add(relative)
        parent = destination.parent
        while parent != prefix and parent != parent.parent:
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise RuntimeError(f"{component} package has an unsafe destination parent: {parent}")
            parent = parent.parent

    for source_file in source_files:
        relative = source_file.relative_to(package)
        if relative in existing_identical:
            continue
        destination = prefix / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise RuntimeError(f"{component} destination changed during staging: {relative}")
        shutil.copy2(source_file, destination)

    print(f"Staged {component} install prefix from {package}", flush=True)


def stage_kernel_sdk_prefix(package: Path, prefix: Path) -> None:
    """Stage the pinned Kernel 1.2.1 + logger 0.1.0 SDK into CDIN's private prefix."""
    _stage_install_prefix(
        package,
        prefix,
        component="Kernel/logger SDK",
        required_files=(
            "include/cdin/kernel.h",
            "include/m-mdy-m/log.h",
            "lib/libcdin_kernel.a",
            "lib/libm-mdy-m-log.a",
            "lib/pkgconfig/cdin-kernel.pc",
            "lib/pkgconfig/m-mdy-m-log.pc",
            "lib/cmake/m-mdy-m-log/m-mdy-m-log-config.cmake",
            "lib/cmake/m-mdy-m-log/m-mdy-m-log-config-version.cmake",
            "lib/cmake/m-mdy-m-log/m-mdy-m-log-targets.cmake",
        ),
    )


def stage_cmake_prefix(package: Path, prefix: Path) -> None:
    """Stage a Registry-verified cmake-prefix-v1 component without collisions."""
    _stage_install_prefix(
        package,
        prefix,
        component="Backend",
        required_files=(
            "include/cdin/backend.h",
            "lib/libcdin_backend.a",
            "lib/libcdin_backend_services.a",
            "lib/libcdin_protocol.a",
            "lib/cmake/cdinBackend/cdinBackendConfig.cmake",
            "lib/pkgconfig/cdin-backend.pc",
            "lib/pkgconfig/cdin-backend-services.pc",
            "lib/pkgconfig/cdin-protocol.pc",
        ),
    )


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


def verify_environment_sdk_contract(manifest: dict, sdk_pin: dict) -> None:
    """Bind externally staged SDKs and Lua to the Product Definition environment providers."""
    declarations = manifest.get("environment_contracts", [])
    providers = {
        (item.get("contract_id"), item.get("version"))
        for item in declarations
    }
    expected = {
        ("org.cdin.kernel-abi", sdk_pin.get("kernel_abi")),
        ("org.m-mdy-m.log-c-api", sdk_pin.get("logger_version")),
        ("org.lua.puc-lua-c-api", "5.4.0"),
    }
    missing = sorted(expected - providers)
    unexpected = sorted(
        (contract_id, version)
        for contract_id, version in providers
        if contract_id in {
            "org.cdin.kernel-abi",
            "org.m-mdy-m.log-c-api",
            "org.lua.puc-lua-c-api",
        }
        and (contract_id, version) not in expected
    )
    if missing or unexpected:
        raise RuntimeError(
            f"SDK environment contracts do not match deps.lock; missing={missing}, unexpected={unexpected}"
        )




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
    manifest = json.loads((WORKSPACE / "registry-manifest.json").read_text(encoding="utf-8"))
    sdk_pin = tomllib.loads(LOCK.read_text(encoding="utf-8"))["dependencies"]["kernel_sdk"]
    verify_environment_sdk_contract(manifest, sdk_pin)
    PREFIX.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    stage_kernel_sdk_prefix(SDK_PREFIX, PREFIX)
    env = pkg_env()

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
