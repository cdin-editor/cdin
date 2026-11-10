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
import shutil
import stat
import subprocess
import tarfile
import tempfile
import tomllib
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


def load_source_pin() -> dict[str, str]:
    with LOCK.open("rb") as stream:
        data = tomllib.load(stream)
    spec = data.get("tooling", {}).get("sdl3", {})
    required = ("version", "archive", "sha256")
    if any(not isinstance(spec.get(key), str) or not spec[key] for key in required):
        raise RuntimeError("deps.lock must pin SDL3 version, archive URL and SHA-256")
    digest = spec["sha256"].lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise RuntimeError("deps.lock contains an invalid SDL3 SHA-256")
    return {key: spec[key] for key in required}


def download_source(spec: dict[str, str], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if actual == spec["sha256"]:
            return destination
        destination.unlink()
    request = urllib.request.Request(
        spec["archive"], headers={"User-Agent": "cdin-sdl3-sdk-builder/1"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
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
    extracted_bytes = 0
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if not members or len(members) > 100_000:
            raise RuntimeError("SDL3 source archive has an invalid member count")
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or not name.parts or any(part in ("", ".", "..") for part in name.parts):
                raise RuntimeError(f"unsafe SDL3 source archive path: {member.name!r}")
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


def write_manifest(prefix: Path, version: str, os_name: str, arch: str,
                   source_sha256: str) -> None:
    metadata = {
        "schema": "cdin.sdl3-sdk.v1",
        "version": version,
        "target": {"os": os_name, "architecture": arch},
        "source": {
            "url": load_source_pin()["archive"],
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


def verify_prefix(prefix: Path) -> None:
    required = (
        prefix / "include" / "SDL3" / "SDL.h",
        prefix / "lib" / "cmake" / "SDL3" / "SDL3Config.cmake",
        prefix / "share" / "cdin" / "sdl3-sdk.json",
    )
    missing = [str(path.relative_to(prefix)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("SDL3 SDK install is incomplete; missing: " + ", ".join(missing))
    libraries = list((prefix / "lib").glob("*SDL3*"))
    if not libraries:
        raise RuntimeError("SDL3 SDK install contains no SDL3 library")


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
    spec = load_source_pin()
    source_archive = args.work_dir / "downloads" / f"SDL3-{spec['version']}.tar.gz"
    source_archive = download_source(spec, source_archive)
    source = safe_extract(source_archive, args.work_dir / "source")
    prefix = args.work_dir / "prefix"
    build = args.work_dir / "build"
    if prefix.exists():
        shutil.rmtree(prefix)
    if build.exists():
        shutil.rmtree(build)

    run([
        "cmake", "-S", str(source), "-B", str(build),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
        "-DBUILD_SHARED_LIBS=OFF",
        "-DSDL_SHARED=OFF",
        "-DSDL_STATIC=ON",
        "-DSDL_TESTS=OFF",
        "-DSDL_EXAMPLES=OFF",
        "-DSDL_TEST_LIBRARY=OFF",
    ])
    run(["cmake", "--build", str(build), "--config", "Release", "--parallel"])
    run(["cmake", "--install", str(build), "--config", "Release"])
    write_manifest(prefix, spec["version"], os_name, arch, spec["sha256"])
    verify_prefix(prefix)

    output = args.output_dir / f"sdl3-sdk-{spec['version']}-{os_name}-{arch}.tar.gz"
    digest = build_archive(prefix, output)
    print(f"Created {output}")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
