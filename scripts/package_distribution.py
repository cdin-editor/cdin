#!/usr/bin/env python3
"""Package the installed CDIN product prefix and verify the extracted application."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREFIX = ROOT / ".deps" / "install"
DEFAULT_OUTPUT = ROOT / "dist" / "distributions"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
VERSION = re.compile(r"^project\(cdin\s+VERSION\s+([0-9]+\.[0-9]+\.[0-9]+)\s+LANGUAGES\s+C\)", re.MULTILINE)
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 100000
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DistributionError(RuntimeError):
    """Raised when an installed product cannot be packaged or verified safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, payload: bytes) -> None:
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        if path.exists() or path.is_symlink():
            raise DistributionError(f"refusing to overwrite an existing output: {path.name}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise DistributionError(f"{label} is missing or unsafe: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DistributionError(f"{label} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise DistributionError(f"{label} root must be a JSON object")
    return value


def detect_host() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    os_name = {
        "linux": "linux",
        "darwin": "darwin",
        "windows": "windows",
    }.get(system)
    arch = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "x64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine)
    if os_name is None or arch is None:
        raise DistributionError(f"unsupported native distribution host: {system}/{machine}")
    return os_name, arch


def validate_target(target: Any) -> dict[str, str]:
    if not isinstance(target, dict):
        raise DistributionError("Registry Manifest has no target identity")
    values = {key: target.get(key) for key in ("os", "architecture", "abi")}
    if any(not isinstance(value, str) or not value for value in values.values()):
        raise DistributionError("Registry Manifest target must identify OS, architecture and ABI")
    host_os, host_arch = detect_host()
    if values["os"] != host_os or values["architecture"] != host_arch:
        raise DistributionError(
            f"installed package target {values['os']}/{values['architecture']} "
            f"does not match runner {host_os}/{host_arch}"
        )
    abi = values["abi"]
    if host_os == "linux":
        libc, version = platform.libc_ver()
        match = re.match(r"^gnu-glibc-(\d+)\.(\d+)$", abi)
        actual = re.match(r"^(\d+)\.(\d+)", version)
        if not match or libc.lower() not in {"glibc", "gnu libc"} or not actual:
            raise DistributionError(f"unsupported Linux ABI for distribution: {libc}/{version}/{abi}")
        if tuple(map(int, actual.groups())) < tuple(map(int, match.groups())):
            raise DistributionError(f"runner glibc {version} is older than package baseline {abi}")
    elif host_os == "darwin":
        match = re.match(r"^macos-(\d+)$", abi)
        actual = re.match(r"^(\d+)", platform.mac_ver()[0])
        if not match or not actual or int(actual.group(1)) < int(match.group(1)):
            raise DistributionError(f"runner macOS version does not satisfy package ABI {abi}")
    elif host_os == "windows":
        if host_arch != "x86_64" or abi != "windows-ucrt64" or os.environ.get("MSYSTEM") != "UCRT64":
            raise DistributionError("Windows application distributions require x86_64 MSYS2 UCRT64")
    return values


def _validated_provenance(records: Any, label: str) -> list[dict[str, str]]:
    if not isinstance(records, list) or not records:
        raise DistributionError(f"{label} must contain immutable source provenance")
    result: list[dict[str, str]] = []
    for source in records:
        if not isinstance(source, dict):
            raise DistributionError(f"{label} contains a malformed source record")
        repository_uri = source.get("repository_uri")
        revision = source.get("revision")
        source_unit_id = source.get("source_unit_id")
        if (
            not isinstance(repository_uri, str)
            or not repository_uri.startswith("https://")
            or not isinstance(revision, str)
            or not FULL_SHA.fullmatch(revision)
            or not isinstance(source_unit_id, str)
            or not source_unit_id
        ):
            raise DistributionError(f"{label} contains incomplete or mutable source provenance")
        result.append({
            "repository_uri": repository_uri,
            "revision": revision,
            "source_unit_id": source_unit_id,
        })
    return sorted(
        result,
        key=lambda item: (item["repository_uri"], item["source_unit_id"], item["revision"]),
    )


def component_summary(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        raise DistributionError("Registry Manifest must contain selected component records")
    result: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for item in components:
        if not isinstance(item, dict):
            raise DistributionError("Registry Manifest contains a malformed component record")
        component_id = item.get("component_id")
        variant = item.get("variant", "default")
        version = item.get("version")
        delivery = item.get("delivery")
        if not all(
            isinstance(value, str) and value
            for value in (component_id, variant, version)
        ) or delivery not in {"artifact", "source"}:
            raise DistributionError("Registry Manifest component identity is incomplete")
        identity = (component_id, variant)
        if identity in identities:
            raise DistributionError(f"duplicate Registry component identity: {identity}")
        identities.add(identity)

        metadata_digest = item.get("release_metadata_sha256")
        metadata_uri = item.get("release_metadata_uri")
        if (
            not isinstance(metadata_digest, str)
            or not HEX_SHA256.fullmatch(metadata_digest)
            or not isinstance(metadata_uri, str)
            or not metadata_uri.startswith("https://")
        ):
            raise DistributionError(f"component {component_id}/{variant} has no immutable release metadata identity")

        row: dict[str, Any] = {
            "component_id": component_id,
            "variant": variant,
            "version": version,
            "delivery": delivery,
            "release_metadata_sha256": metadata_digest,
            "release_metadata_uri": metadata_uri,
        }
        if delivery == "artifact":
            artifact = item.get("selected_artifact")
            if not isinstance(artifact, dict):
                raise DistributionError(f"artifact component {component_id}/{variant} has no selected artifact")
            artifact_id = artifact.get("artifact_id")
            artifact_digest = artifact.get("sha256")
            file_name = artifact.get("file_name")
            artifact_uri = artifact.get("uri")
            size_bytes = artifact.get("size_bytes")
            if (
                not isinstance(artifact_id, str) or not artifact_id
                or not isinstance(artifact_digest, str) or not HEX_SHA256.fullmatch(artifact_digest)
                or not isinstance(file_name, str) or not file_name
                or not isinstance(artifact_uri, str) or not artifact_uri.startswith("https://")
                or not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes <= 0
            ):
                raise DistributionError(f"artifact component {component_id}/{variant} has incomplete immutable artifact identity")
            provenance = _validated_provenance(
                artifact.get("source_provenance"),
                f"artifact {component_id}/{variant}",
            )
            row["artifact"] = {
                "artifact_id": artifact_id,
                "file_name": file_name,
                "uri": artifact_uri,
                "size_bytes": size_bytes,
                "sha256": artifact_digest,
            }
        else:
            provenance = _validated_provenance(
                item.get("source_units"),
                f"source component {component_id}/{variant}",
            )
        row["source_provenance"] = provenance
        row["source_revisions"] = sorted({source["revision"] for source in provenance})
        result.append(row)
    return sorted(result, key=lambda row: (row["component_id"], row["variant"]))


def manifest_environment_contracts(manifest: dict[str, Any]) -> list[dict[str, str]]:
    contracts = manifest.get("environment_contracts", [])
    if not isinstance(contracts, list):
        raise DistributionError("Registry Manifest environment_contracts must be an array")
    result: list[dict[str, str]] = []
    identities: set[str] = set()
    for contract in contracts:
        if not isinstance(contract, dict):
            raise DistributionError("Registry Manifest contains a malformed environment contract")
        contract_id = contract.get("contract_id")
        version = contract.get("version")
        if (
            not isinstance(contract_id, str) or not contract_id
            or not isinstance(version, str) or not version
            or contract_id in identities
        ):
            raise DistributionError("Registry Manifest environment contract identity is incomplete or duplicated")
        identities.add(contract_id)
        result.append({"contract_id": contract_id, "version": version})
    return sorted(result, key=lambda item: item["contract_id"])


def build_dependency_summary(target: dict[str, str], profile: str) -> dict[str, Any]:
    lock_path = ROOT / "deps.lock"
    try:
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise DistributionError(f"cannot read pinned build dependencies from deps.lock: {error}") from error

    dependencies = lock.get("dependencies")
    kernel = dependencies.get("kernel_sdk") if isinstance(dependencies, dict) else None
    if not isinstance(kernel, dict):
        raise DistributionError("deps.lock has no pinned Kernel SDK package")
    target_os = "macos" if target["os"] == "darwin" else target["os"]
    asset_key = f"{target_os}-{target['architecture']}"
    assets = kernel.get("assets")
    asset = assets.get(asset_key) if isinstance(assets, dict) else None
    revision = kernel.get("revision")
    if (
        not isinstance(revision, str) or not FULL_SHA.fullmatch(revision)
        or not isinstance(kernel.get("repository"), str)
        or not isinstance(kernel.get("tag"), str)
        or not isinstance(kernel.get("version"), str)
        or not isinstance(kernel.get("kernel_abi"), str)
        or not isinstance(kernel.get("logger_version"), str)
        or not isinstance(asset, dict)
        or not isinstance(asset.get("file_name"), str)
        or not isinstance(asset.get("format"), str)
        or not isinstance(asset.get("size_bytes"), int)
        or isinstance(asset.get("size_bytes"), bool)
        or asset["size_bytes"] <= 0
        or not isinstance(asset.get("sha256"), str)
        or not HEX_SHA256.fullmatch(asset["sha256"])
    ):
        raise DistributionError(f"deps.lock has no complete immutable Kernel SDK asset for {asset_key}")

    result: dict[str, Any] = {
        "kernel_sdk": {
            "repository": kernel["repository"],
            "tag": kernel["tag"],
            "version": kernel["version"],
            "source_revision": revision,
            "kernel_abi": kernel["kernel_abi"],
            "logger_version": kernel["logger_version"],
            "asset": {
                "file_name": asset["file_name"],
                "format": asset["format"],
                "size_bytes": asset["size_bytes"],
                "sha256": asset["sha256"],
            },
        }
    }
    if profile == "gui-sdl":
        tooling = lock.get("tooling")
        sdl = tooling.get("sdl3") if isinstance(tooling, dict) else None
        if (
            not isinstance(sdl, dict)
            or not isinstance(sdl.get("version"), str)
            or not isinstance(sdl.get("archive"), str)
            or not sdl["archive"].startswith("https://")
            or not isinstance(sdl.get("sha256"), str)
            or not HEX_SHA256.fullmatch(sdl["sha256"])
        ):
            raise DistributionError("deps.lock has no complete immutable SDL3 source SDK pin for GUI-SDL")
        result["sdl3"] = {
            "version": sdl["version"],
            "delivery": "pinned-source-build",
            "source_archive_uri": sdl["archive"],
            "source_archive_sha256": sdl["sha256"],
        }
    return result


def safe_copy_prefix(prefix: Path, destination: Path) -> None:
    if prefix.is_symlink() or not prefix.is_dir():
        raise DistributionError(f"installed product prefix is missing or unsafe: {prefix}")
    prefix = prefix.resolve()
    for source in sorted(prefix.rglob("*"), key=lambda path: path.relative_to(prefix).as_posix()):
        relative = source.relative_to(prefix)
        if any(part in {"..", ".git", ".deps", "build"} for part in relative.parts):
            raise DistributionError(f"unsafe installed prefix path: {relative}")
        mode = source.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise DistributionError(f"installed prefix contains a symlink: {relative}")
        target = destination / relative
        if stat.S_ISDIR(mode):
            target.mkdir(parents=True, exist_ok=True)
        elif stat.S_ISREG(mode):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            os.chmod(target, stat.S_IMODE(mode))
        else:
            raise DistributionError(f"installed prefix contains a special file: {relative}")


def _regular_members(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise DistributionError(f"staged distribution contains a symlink: {path.relative_to(root)}")
        if path.is_file():
            yield path


def write_tar_gz(root: Path, archive: Path, arc_root: str) -> None:
    import gzip

    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for path in _regular_members(root):
                    relative = path.relative_to(root).as_posix()
                    info = tarfile.TarInfo(f"{arc_root}/{relative}")
                    info.size = path.stat().st_size
                    info.mode = stat.S_IMODE(path.stat().st_mode)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    with path.open("rb") as stream:
                        tar.addfile(info, stream)


def write_zip(root: Path, archive: Path, arc_root: str) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in _regular_members(root):
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(f"{arc_root}/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | stat.S_IMODE(path.stat().st_mode)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as stream, output.open(info, "w", force_zip64=True) as writer:
                shutil.copyfileobj(stream, writer, length=1024 * 1024)


def _member_path(root: Path, name: str) -> Path:
    if (
        not isinstance(name, str)
        or not name
        or "\x00" in name
        or "\\" in name
        or name.startswith("/")
        or re.match(r"^[A-Za-z]:", name) is not None
    ):
        raise DistributionError(f"unsafe archive member name: {name!r}")
    normalized = name[:-1] if name.endswith("/") else name
    parts = normalized.split("/")
    if not normalized or any(part in {"", ".", ".."} for part in parts):
        raise DistributionError(f"unsafe archive member path: {name!r}")
    target = root.joinpath(*parts)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise DistributionError(f"archive member escapes extraction root: {name!r}") from error
    return target


def safe_extract(archive: Path, destination: Path) -> Path:
    if destination.is_symlink():
        raise DistributionError("extraction destination must not be a symlink")
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir() or any(destination.iterdir()):
        raise DistributionError("extraction destination must be an empty directory")
    destination = destination.resolve()

    if archive.stat().st_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise DistributionError("distribution archive exceeds the compressed-size limit")

    total_size = 0
    member_count = 0
    normalized_names: set[str] = set()
    root_name: str | None = None

    def register_member(name: str, *, is_directory: bool, size: int) -> Path:
        nonlocal total_size, member_count, root_name
        member_count += 1
        if member_count > MAX_ARCHIVE_MEMBERS:
            raise DistributionError("distribution archive contains too many members")
        path = _member_path(destination, name)
        parts = path.relative_to(destination).parts
        if not parts:
            raise DistributionError("distribution archive has an empty root path")
        if root_name is None:
            root_name = parts[0]
        elif parts[0] != root_name:
            raise DistributionError("distribution archive must contain exactly one application root directory")
        if len(parts) == 1 and not is_directory:
            raise DistributionError("distribution archive must not contain files outside its application root")
        normalized = "/".join(parts).casefold()
        if normalized in normalized_names:
            raise DistributionError(f"distribution archive contains duplicate normalized paths: {name}")
        normalized_names.add(normalized)
        if not is_directory:
            if size < 0 or size > MAX_MEMBER_BYTES:
                raise DistributionError(f"distribution archive contains an oversized member: {name}")
            total_size += size
            if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise DistributionError("distribution archive exceeds the total uncompressed-size limit")
        return path

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            infos = source.infolist()
            if not infos:
                raise DistributionError("ZIP archive is empty")
            for info in infos:
                is_directory = info.is_dir()
                target = register_member(info.filename, is_directory=is_directory, size=info.file_size)
                mode = (info.external_attr >> 16) & 0xFFFF
                kind = stat.S_IFMT(mode)
                if is_directory:
                    if kind not in (0, stat.S_IFDIR):
                        raise DistributionError(f"ZIP archive contains a special directory entry: {info.filename}")
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if kind not in (0, stat.S_IFREG) or info.flag_bits & 0x1:
                    raise DistributionError(f"ZIP archive contains a special or encrypted member: {info.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(info) as reader, target.open("xb") as writer:
                    shutil.copyfileobj(reader, writer, length=1024 * 1024)
                os.chmod(target, stat.S_IMODE(mode) or 0o644)
    else:
        try:
            source = tarfile.open(archive, "r:gz")
        except (OSError, tarfile.TarError) as error:
            raise DistributionError(f"unsupported distribution archive: {error}") from error
        with source:
            members = source.getmembers()
            if not members:
                raise DistributionError("TAR archive is empty")
            for member in members:
                is_directory = member.isdir()
                target = register_member(member.name, is_directory=is_directory, size=member.size)
                if is_directory:
                    if not member.isdir():
                        raise DistributionError(f"TAR archive contains an invalid directory entry: {member.name}")
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise DistributionError(f"TAR archive contains a special member: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                reader = source.extractfile(member)
                if reader is None:
                    raise DistributionError(f"could not read TAR member: {member.name}")
                with reader, target.open("xb") as writer:
                    shutil.copyfileobj(reader, writer, length=1024 * 1024)
                os.chmod(target, member.mode & 0o777)

    if root_name is None:
        raise DistributionError("distribution archive has no application root directory")
    roots = [path for path in destination.iterdir()]
    if len(roots) != 1 or roots[0].name != root_name or not roots[0].is_dir():
        raise DistributionError("distribution archive must contain exactly one application root directory")
    return destination / root_name


def verify_extracted(extracted: Path, expected_version: str, *, timeout: int = 120) -> None:
    executable = extracted / "bin" / ("cdin.exe" if os.name == "nt" else "cdin")
    runtime_root = extracted / "share" / "cdin" / "lua"
    if not executable.is_file() or not runtime_root.is_dir():
        raise DistributionError("extracted distribution is missing cdin executable or Runtime modules")
    environment = os.environ.copy()
    environment.pop("CDIN_RUNTIME_ROOT", None)
    environment["PATH"] = os.pathsep.join(
        [str(executable.parent), str(extracted / "lib"), environment.get("PATH", "")]
    ).rstrip(os.pathsep)
    version = subprocess.run(
        [str(executable), "--version"],
        cwd=extracted,
        env=environment,
        text=True,
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    expected_line = f"cdin {expected_version}"
    if version.returncode != 0 or expected_line not in version.stdout:
        raise DistributionError(
            f"extracted application version check failed: exit={version.returncode}, "
            f"stdout={version.stdout[-1000:]!r}, stderr={version.stderr[-1000:]!r}"
        )
    check = subprocess.run(
        [str(executable), "--check"],
        cwd=extracted,
        env=environment,
        text=True,
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check.returncode != 0:
        raise DistributionError(
            f"extracted application lifecycle check failed: exit={check.returncode}, "
            f"stdout={check.stdout[-2000:]!r}, stderr={check.stderr[-2000:]!r}"
        )


def package_distribution(
    *,
    prefix: Path,
    workspace: Path,
    output_directory: Path,
    profile: str,
    source_revision: str,
    run_smoke: bool = True,
) -> dict[str, Any]:
    if profile not in {"tui", "gui-sdl"}:
        raise DistributionError(f"unsupported product profile: {profile}")
    if not FULL_SHA.fullmatch(source_revision):
        raise DistributionError("source revision must be a full 40-character commit SHA")
    if prefix.is_symlink() or not prefix.is_dir():
        raise DistributionError(f"installed product prefix is missing or unsafe: {prefix}")
    prefix = prefix.resolve()
    if output_directory.is_symlink():
        raise DistributionError("distribution output directory must not be a symlink")
    if workspace.is_symlink() or not workspace.is_dir():
        raise DistributionError(f"Registry workspace is missing or unsafe: {workspace}")
    registry_manifest_path = workspace / "registry-manifest.json"
    registry_manifest = read_json(registry_manifest_path, "Registry Resolved Manifest")
    resolution = registry_manifest.get("resolution")
    if not isinstance(resolution, dict):
        raise DistributionError("Registry Manifest has no valid resolution object")
    target = validate_target(resolution.get("target"))
    components = component_summary(registry_manifest)
    environment_contracts = manifest_environment_contracts(registry_manifest)
    build_dependencies = build_dependency_summary(target, profile)
    frontend_variants = {
        item["variant"] for item in components if item["component_id"] == "frontend"
    }
    if "tui" not in frontend_variants or (profile == "tui" and "gui-sdl" in frontend_variants):
        raise DistributionError(f"Registry Manifest Frontend variants do not match the {profile} profile")
    if profile == "gui-sdl" and "gui-sdl" not in frontend_variants:
        raise DistributionError("GUI-SDL Registry Manifest does not select the GUI-SDL Frontend variant")

    project_text = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    version_match = VERSION.search(project_text)
    if version_match is None:
        raise DistributionError("could not read CDIN project version from CMakeLists.txt")
    version = version_match.group(1)
    executable = prefix / "bin" / ("cdin.exe" if os.name == "nt" else "cdin")
    runtime = prefix / "share" / "cdin" / "lua"
    if not executable.is_file() or not runtime.is_dir():
        raise DistributionError("installed prefix is missing cdin executable or Runtime modules")

    prefix_files = list(_regular_members(prefix))
    if not prefix_files:
        raise DistributionError("installed prefix is empty")
    sdl_files = [
        path.relative_to(prefix).as_posix()
        for path in prefix_files
        if "sdl3" in path.name.lower() or "sdl3" in path.as_posix().lower()
    ]
    if profile == "tui" and sdl_files:
        raise DistributionError("TUI distribution contains SDL3 files")
    if profile == "gui-sdl" and not sdl_files:
        raise DistributionError("GUI-SDL distribution does not contain its pinned SDL3 SDK")

    output_directory.mkdir(parents=True, exist_ok=True)
    slug = f"{target['os']}-{target['architecture']}-{profile}"
    archive_root = f"cdin-{version}-{slug}"
    suffix = ".zip" if target["os"] == "windows" else ".tar.gz"
    archive_name = f"{archive_root}{suffix}"
    archive_path = output_directory / archive_name
    checksum_path = archive_path.with_name(archive_path.name + ".sha256")
    manifest_path = archive_path.with_name(archive_root + ".manifest.json")
    if any(path.exists() or path.is_symlink() for path in (archive_path, checksum_path, manifest_path)):
        raise DistributionError(f"refusing to overwrite an existing distribution identity: {archive_name}")

    catalogs = registry_manifest.get("catalogs", [])
    if not isinstance(catalogs, list):
        raise DistributionError("Registry Manifest catalogs must be an array")
    catalog_summary: list[dict[str, str]] = []
    for catalog in catalogs:
        if not isinstance(catalog, dict):
            raise DistributionError("Registry Manifest contains a malformed Catalog identity")
        catalog_id = catalog.get("catalog_id")
        metadata_digest = catalog.get("metadata_sha256")
        metadata_uri = catalog.get("metadata_uri")
        if (
            not isinstance(catalog_id, str) or not catalog_id
            or not isinstance(metadata_digest, str) or not HEX_SHA256.fullmatch(metadata_digest)
            or not isinstance(metadata_uri, str) or not metadata_uri.startswith(("https://", "file://"))
        ):
            raise DistributionError("Registry Manifest contains an incomplete Catalog identity")
        catalog_summary.append({
            "catalog_id": catalog_id,
            "metadata_sha256": metadata_digest,
            "metadata_uri": metadata_uri,
        })

    build_info: dict[str, Any] = {
        "schema_version": 1,
        "product": "com.cdin.editor",
        "product_version": version,
        "source_commit": source_revision,
        "target": target,
        "profile": profile,
        "registry_version": registry_manifest.get("registry_version"),
        "registry_manifest_sha256": sha256_file(registry_manifest_path),
        "catalogs": catalog_summary,
        "components": components,
        "environment_contracts": environment_contracts,
        "build_dependencies": build_dependencies,
        "workflow": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        },
        "distribution_status": "development-build; not a stable product release",
    }

    reserved = [
        prefix / "BUILD-INFO.json",
        prefix / "LICENSE",
        prefix / "NOTICE",
        prefix / "share" / "cdin" / "registry-manifest.json",
    ]
    if any(path.exists() or path.is_symlink() for path in reserved):
        raise DistributionError("installed prefix already contains a reserved distribution metadata path")

    with tempfile.TemporaryDirectory(prefix=".cdin-distribution-publish-", dir=output_directory) as publish_dir:
        candidate_root = Path(publish_dir)
        candidate_archive = candidate_root / archive_name
        candidate_checksum = candidate_root / checksum_path.name
        candidate_manifest = candidate_root / manifest_path.name

        with tempfile.TemporaryDirectory(prefix="cdin-distribution-stage-") as stage_dir:
            stage_root = Path(stage_dir) / archive_root
            stage_root.mkdir(parents=True)
            safe_copy_prefix(prefix, stage_root)
            shutil.copyfile(ROOT / "LICENSE", stage_root / "LICENSE")
            shutil.copyfile(ROOT / "NOTICE", stage_root / "NOTICE")
            registry_destination = stage_root / "share" / "cdin" / "registry-manifest.json"
            registry_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(registry_manifest_path, registry_destination)
            (stage_root / "BUILD-INFO.json").write_text(
                json.dumps(build_info, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if target["os"] == "windows":
                write_zip(stage_root, candidate_archive, archive_root)
            else:
                write_tar_gz(stage_root, candidate_archive, archive_root)

        digest = sha256_file(candidate_archive)
        archive_size = candidate_archive.stat().st_size
        atomic_write(
            candidate_checksum,
            f"{digest}  {archive_name}\n".encode("ascii"),
        )
        release_manifest = {
            "schema_version": 1,
            "product": "com.cdin.editor",
            "version": version,
            "source_commit": source_revision,
            "target": target,
            "profile": profile,
            "registry_version": build_info["registry_version"],
            "registry_manifest_sha256": build_info["registry_manifest_sha256"],
            "catalogs": catalog_summary,
            "components": components,
            "environment_contracts": environment_contracts,
            "build_dependencies": build_dependencies,
            "archive": {
                "name": archive_name,
                "size_bytes": archive_size,
                "sha256": digest,
            },
            "workflow": build_info["workflow"],
        }
        atomic_write(
            candidate_manifest,
            (json.dumps(release_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

        if run_smoke:
            with tempfile.TemporaryDirectory(
                prefix="cdin-distribution-extract-", dir=ROOT.parent
            ) as extract_dir:
                extracted = safe_extract(candidate_archive, Path(extract_dir))
                verify_extracted(extracted, version)

        published: list[Path] = []
        try:
            for candidate, final in (
                (candidate_archive, archive_path),
                (candidate_checksum, checksum_path),
                (candidate_manifest, manifest_path),
            ):
                if final.exists() or final.is_symlink():
                    raise DistributionError(f"refusing to overwrite an existing distribution identity: {final.name}")
                os.replace(candidate, final)
                published.append(final)
        except BaseException:
            for path in published:
                path.unlink(missing_ok=True)
            raise

    return {
        "archive": str(archive_path),
        "archive_sha256": digest,
        "archive_size_bytes": archive_path.stat().st_size,
        "checksum": str(checksum_path),
        "manifest": str(manifest_path),
        "target": target,
        "profile": profile,
        "version": version,
        "source_commit": source_revision,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("tui", "gui-sdl"), default=os.environ.get("CDIN_FRONTEND_VARIANT", "tui"))
    parser.add_argument("--prefix", type=Path, default=DEFAULT_PREFIX)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-revision", default=os.environ.get("CDIN_SOURCE_REVISION", ""))
    args = parser.parse_args()
    workspace = args.workspace or ROOT / ".deps" / f"registry-workspace-{args.profile}"
    source_revision = args.source_revision
    if not source_revision:
        try:
            source_revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip()
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"cannot determine source revision: {error}", file=sys.stderr)
            return 2
    try:
        result = package_distribution(
            prefix=args.prefix.absolute(),
            workspace=workspace.resolve(),
            output_directory=args.output_directory.absolute(),
            profile=args.profile,
            source_revision=source_revision,
            run_smoke=True,
        )
    except (OSError, DistributionError, subprocess.SubprocessError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"distribution packaging failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
