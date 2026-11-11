#!/usr/bin/env python3
"""Build a target-native, relocatable SDL3 SDK package for CDIN consumers."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import tomllib
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "deps.lock"
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def target_identity() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    os_name = {"linux": "linux", "darwin": "macos", "windows": "windows"}.get(system)
    arch = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine)
    if os_name is None or arch is None:
        raise RuntimeError(f"unsupported SDL3 SDK build target: {system}/{machine}")
    if os_name == "windows" and arch != "x86_64":
        raise RuntimeError(f"unsupported Windows SDL3 SDK architecture: {arch}")
    return os_name, arch


def target_abi(os_name: str) -> str:
    """Return the exact ABI baseline required by the CDIN target matrix."""
    if os_name == "linux":
        libc, version = platform.libc_ver()
        if libc.lower() != "glibc" or version != "2.39":
            raise RuntimeError(
                f"SDL3 Linux SDKs require glibc 2.39; found {libc or 'unknown'} "
                f"{version or 'unknown'}"
            )
        return "gnu-glibc-2.39"
    if os_name == "macos":
        version = platform.mac_ver()[0]
        major = version.split(".", 1)[0] if version else ""
        if major != "15":
            raise RuntimeError(
                f"SDL3 macOS SDKs require macOS 15; found {version or 'unknown'}"
            )
        return "macos-15"
    if os_name == "windows":
        msystem = os.environ.get("MSYSTEM", "")
        if msystem != "UCRT64":
            raise RuntimeError(
                f"SDL3 Windows SDKs require MSYS2 UCRT64; found {msystem or 'unknown'}"
            )
        return "windows-ucrt64"
    raise RuntimeError(f"unsupported SDL3 SDK ABI target: {os_name}")


def load_source_pin() -> dict[str, str]:
    with LOCK.open("rb") as stream:
        data = tomllib.load(stream)
    spec = data.get("tooling", {}).get("sdl3", {})
    required = ("version", "archive", "sha256")
    if any(not isinstance(spec.get(key), str) or not spec[key] for key in required):
        raise RuntimeError("deps.lock must pin SDL3 version, archive URL and SHA-256")
    if re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", spec["version"]) is None:
        raise RuntimeError("deps.lock contains an invalid SDL3 SemVer version")
    digest = spec["sha256"].lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise RuntimeError("deps.lock contains an invalid SDL3 SHA-256")
    return {key: spec[key] for key in required}


class TrustedSDLRedirectHandler(urllib.request.HTTPRedirectHandler):
    allowed_hosts = {"github.com", "release-assets.githubusercontent.com"}

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        parsed = urllib.parse.urlparse(new_url)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts:
            raise RuntimeError(f"untrusted SDL3 source redirect: {new_url!r}")
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def download_source(spec: dict[str, str], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if actual == spec["sha256"]:
            return destination
        destination.unlink()
    source_url = urllib.parse.urlparse(spec["archive"])
    if (source_url.scheme != "https" or source_url.hostname != "github.com" or
            not source_url.path.startswith("/libsdl-org/SDL/releases/download/") or
            source_url.username is not None or source_url.password is not None):
        raise RuntimeError("SDL3 source URL must be a trusted HTTPS SDL GitHub release URL")
    request = urllib.request.Request(
        spec["archive"], headers={"User-Agent": "cdin-sdl3-sdk-builder/1"}
    )
    opener = urllib.request.build_opener(TrustedSDLRedirectHandler())
    with opener.open(request, timeout=60) as response:
        final_url = urllib.parse.urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname not in TrustedSDLRedirectHandler.allowed_hosts:
            raise RuntimeError("SDL3 source download ended at an untrusted host")
        if response.status != 200:
            raise RuntimeError(f"SDL3 source download returned HTTP {response.status}")
        total = 0
        digest = hashlib.sha256()
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            with temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_SOURCE_BYTES:
                        raise RuntimeError("SDL3 source archive exceeds the 128 MiB limit")
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != spec["sha256"]:
                raise RuntimeError("SDL3 source archive SHA-256 mismatch")
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    return destination


def safe_extract(archive_path: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    top_levels: set[str] = set()
    seen_paths: set[str] = set()
    extracted_bytes = 0
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if not members or len(members) > 100_000:
            raise RuntimeError("SDL3 source archive has an invalid member count")
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or not name.parts or
                    any(part in ("", ".", "..") for part in name.parts) or
                    "\\" in member.name or ":" in name.parts[0]):
                raise RuntimeError(f"unsafe SDL3 source archive path: {member.name!r}")
            normalized_name = name.as_posix().rstrip("/").casefold()
            if normalized_name in seen_paths:
                raise RuntimeError(f"duplicate SDL3 source archive path: {member.name!r}")
            seen_paths.add(normalized_name)
            if not (member.isdir() or member.isfile()):
                raise RuntimeError(f"unsupported SDL3 source archive entry: {member.name!r}")
            if member.size < 0 or member.size > MAX_SOURCE_BYTES:
                raise RuntimeError(f"invalid SDL3 source member size: {member.name!r}")
            extracted_bytes += member.size
            if extracted_bytes > MAX_EXTRACTED_BYTES:
                raise RuntimeError("SDL3 source archive expands beyond the 512 MiB limit")
            top_levels.add(name.parts[0])
            target = (destination / Path(*name.parts)).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"SDL3 source archive path escapes extraction root: {member.name!r}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"cannot read SDL3 source member: {member.name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    if len(top_levels) != 1:
        raise RuntimeError("SDL3 source archive must contain exactly one top-level directory")
    source_root = destination / next(iter(top_levels))
    if not (source_root / "CMakeLists.txt").is_file():
        raise RuntimeError("SDL3 source archive does not contain its root CMakeLists.txt")
    return source_root


def install_license(source: Path, prefix: Path) -> None:
    """Retain the upstream zlib license in every redistributable SDK archive."""
    license_source = source / "LICENSE.txt"
    if not license_source.is_file():
        raise RuntimeError("SDL3 source tree is missing its LICENSE.txt")
    destination = prefix / "share" / "licenses" / "SDL3" / "LICENSE.txt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(license_source, destination)


def write_manifest(
    prefix: Path,
    version: str,
    os_name: str,
    arch: str,
    abi: str,
    source_sha256: str,
) -> None:
    source = load_source_pin()
    metadata = {
        "schema": "cdin.sdl3-sdk.v1",
        "version": version,
        "target": {"os": os_name, "architecture": arch, "abi": abi},
        "source": {
            "url": source["archive"],
            "sha256": source_sha256,
        },
        "linkage": "static",
        "cmake_package": "SDL3",
    }
    directory = prefix / "share" / "cdin"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sdl3-sdk.json").write_text(
        json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def verify_prefix(
    prefix: Path,
    *,
    version: str,
    os_name: str,
    arch: str,
    abi: str,
    source: dict[str, str],
) -> None:
    required = (
        prefix / "include" / "SDL3" / "SDL.h",
        prefix / "include" / "SDL3" / "SDL_version.h",
        prefix / "lib" / "cmake" / "SDL3" / "SDL3Config.cmake",
        prefix / "share" / "cdin" / "sdl3-sdk.json",
        prefix / "share" / "licenses" / "SDL3" / "LICENSE.txt",
    )
    missing = [str(path.relative_to(prefix)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("SDL3 SDK install is incomplete; missing: " + ", ".join(missing))

    manifest_path = prefix / "share" / "cdin" / "sdl3-sdk.json"
    try:
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"SDL3 SDK manifest is invalid: {error}") from error
    expected = {
        "schema": "cdin.sdl3-sdk.v1",
        "version": version,
        "target": {"os": os_name, "architecture": arch, "abi": abi},
        "source": {"url": source["archive"], "sha256": source["sha256"]},
        "linkage": "static",
        "cmake_package": "SDL3",
    }
    if metadata != expected:
        raise RuntimeError(
            "SDL3 SDK manifest does not match the pinned version, target ABI, "
            "source digest and static CMake package"
        )

    library_dir = prefix / "lib"
    static_libraries = {"libSDL3.a", "SDL3-static.lib"}
    if not any((library_dir / name).is_file() for name in static_libraries):
        raise RuntimeError(
            "SDL3 SDK install is missing a supported static SDL3 library "
            "(libSDL3.a or SDL3-static.lib)"
        )
    shared_libraries = ("SDL3.dll", "libSDL3.so", "libSDL3.dylib")
    if any((library_dir / name).exists() for name in shared_libraries):
        raise RuntimeError("SDL3 SDK must not contain a shared SDL3 library")


def verify_consumer(prefix: Path, work_dir: Path, version: str) -> None:
    consumer = work_dir / "consumer"
    build = work_dir / "consumer-build"
    consumer.mkdir(parents=True, exist_ok=True)
    version_parts = tuple(int(part) for part in version.split("."))
    if len(version_parts) != 3:
        raise RuntimeError(f"invalid SDL3 version for consumer verification: {version!r}")
    major, minor, patch = version_parts
    cmake_lines = [
        "cmake_minimum_required(VERSION 3.22)",
        "project(cdin_sdl3_sdk_consumer LANGUAGES C)",
        "include(CTest)",
        f"find_package(SDL3 {version} EXACT CONFIG REQUIRED COMPONENTS SDL3-static)",
        "get_target_property(SDL3_LINKAGE SDL3::SDL3-static TYPE)",
        'if(NOT SDL3_LINKAGE STREQUAL "STATIC_LIBRARY")',
        '  message(FATAL_ERROR "The pinned SDL3 SDK did not export a static target")',
        "endif()",
        "add_executable(cdin_sdl3_sdk_consumer main.c)",
        "target_link_libraries(cdin_sdl3_sdk_consumer PRIVATE SDL3::SDL3-static)",
        "add_test(NAME cdin_sdl3_sdk_exact_linked_version COMMAND cdin_sdl3_sdk_consumer)",
    ]
    (consumer / "CMakeLists.txt").write_text("\n".join(cmake_lines) + "\n", encoding="utf-8")
    main_lines = [
        "#include <SDL3/SDL_version.h>",
        "int main(void)",
        "{",
        f"    return SDL_GetVersion() == SDL_VERSIONNUM({major}, {minor}, {patch}) ? 0 : 1;",
        "}",
    ]
    (consumer / "main.c").write_text("\n".join(main_lines) + "\n", encoding="utf-8")
    run([
        "cmake", "-S", str(consumer), "-B", str(build),
        f"-DCMAKE_PREFIX_PATH={prefix}",
        "-DCMAKE_BUILD_TYPE=Release",
    ])
    run(["cmake", "--build", str(build), "--config", "Release", "--parallel"])
    run(["ctest", "--test-dir", str(build), "--output-on-failure"])


def build_archive(prefix: Path, output: Path) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0, compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for path in sorted(prefix.rglob("*"), key=lambda item: item.relative_to(prefix).as_posix()):
                mode = path.lstat().st_mode
                relative = PurePosixPath("sdl3-sdk") / PurePosixPath(path.relative_to(prefix).as_posix())
                info = tarfile.TarInfo(relative.as_posix())
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = 0
                info.pax_headers = {}
                if stat.S_ISDIR(mode):
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    info.size = 0
                    archive.addfile(info)
                elif stat.S_ISREG(mode):
                    info.type = tarfile.REGTYPE
                    info.mode = 0o755 if mode & 0o111 else 0o644
                    info.size = path.stat().st_size
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
                else:
                    raise RuntimeError(f"unsupported installed SDK file type: {path}")
    payload = raw.getvalue()
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(output)
    digest = hashlib.sha256(payload).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii"
    )
    return digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".deps" / "sdl3-sdk-build")
    args = parser.parse_args()

    os_name, arch = target_identity()
    abi = target_abi(os_name)
    spec = load_source_pin()
    release_tag = os.environ.get("GITHUB_REF_NAME", "")
    if release_tag.startswith("sdl3-sdk-v") and release_tag != f"sdl3-sdk-v{spec['version']}":
        raise RuntimeError(
            f"release tag {release_tag} does not match pinned SDL3 version {spec['version']}"
        )
    source_archive = args.work_dir / "downloads" / f"SDL3-{spec['version']}.tar.gz"
    source_archive = download_source(spec, source_archive)
    source = safe_extract(source_archive, args.work_dir / "source")
    prefix = args.work_dir / "prefix"
    build = args.work_dir / "build"
    if prefix.exists():
        shutil.rmtree(prefix)
    if build.exists():
        shutil.rmtree(build)

    cmake_args = [
        "cmake", "-S", str(source), "-B", str(build),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
        "-DBUILD_SHARED_LIBS=OFF",
        "-DSDL_SHARED=OFF",
        "-DSDL_STATIC=ON",
        "-DSDL_TESTS=OFF",
        "-DSDL_EXAMPLES=OFF",
        "-DSDL_TEST_LIBRARY=OFF",
    ]
    if os_name == "macos":
        cmake_args.extend([
            "-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0",
            f"-DCMAKE_OSX_ARCHITECTURES={arch}",
        ])
    run(cmake_args)
    run(["cmake", "--build", str(build), "--config", "Release", "--parallel"])
    run(["cmake", "--install", str(build), "--config", "Release"])
    install_license(source, prefix)
    write_manifest(prefix, spec["version"], os_name, arch, abi, spec["sha256"])
    verify_prefix(
        prefix,
        version=spec["version"],
        os_name=os_name,
        arch=arch,
        abi=abi,
        source=spec,
    )
    verify_consumer(prefix, args.work_dir, spec["version"])

    output = args.output_dir / f"sdl3-sdk-{spec['version']}-{os_name}-{arch}.tar.gz"
    digest = build_archive(prefix, output)
    print(f"Created {output}")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
