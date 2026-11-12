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
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREFIX = ROOT / ".deps" / "install"
DEFAULT_OUTPUT = ROOT / "dist" / "distributions"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
VERSION = re.compile(r"^project\(cdin\s+VERSION\s+([0-9]+\.[0-9]+\.[0-9]+)\s+LANGUAGES\s+C\)", re.MULTILINE)
MAX_MEMBER_BYTES = 1024 * 1024 * 1024


class DistributionError(RuntimeError):
    """Raised when an installed product cannot be packaged or verified safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
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
        actual = re.match(r"^(\\d+)", platform.mac_ver()[0])
        if not match or not actual or int(actual.group(1)) < int(match.group(1)):
            raise DistributionError(f"runner macOS version does not satisfy package ABI {abi}")
    elif host_os == "windows":
        if host_arch != "x86_64" or abi != "windows-ucrt64" or os.environ.get("MSYSTEM") != "UCRT64":
            raise DistributionError("Windows application distributions require x86_64 MSYS2 UCRT64")
    return values


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
        delivery = item.get("delivery", "source")
        if not all(isinstance(value, str) and value for value in (component_id, variant, version, delivery)):
            raise DistributionError("Registry Manifest component identity is incomplete")
        identity = (component_id, variant)
        if identity in identities:
            raise DistributionError(f"duplicate Registry component identity: {identity}")
        identities.add(identity)
        row: dict[str, Any] = {
            "component_id": component_id,
            "variant": variant,
            "version": version,
            "delivery": delivery,
        }
        provenance: list[str] = []
        if delivery == "artifact":
            artifact = item.get("selected_artifact")
            if isinstance(artifact, dict):
                provenance = [
                    source["revision"]
                    for source in artifact.get("source_provenance", [])
                    if isinstance(source, dict) and isinstance(source.get("revision"), str)
                ]
                row["artifact_id"] = artifact.get("artifact_id")
                row["artifact_sha256"] = artifact.get("sha256")
        else:
            provenance = [
                source["revision"]
                for source in item.get("source_units", [])
                if isinstance(source, dict) and isinstance(source.get("revision"), str)
            ]
        row["source_revisions"] = sorted(set(provenance))
        result.append(row)
    return sorted(result, key=lambda row: (row["component_id"], row["variant"]))


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
            with path.open("rb") as stream:
                output.writestr(info, stream.read())


def _member_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or "\\" in name:
        raise DistributionError(f"unsafe archive member name: {name!r}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise DistributionError(f"unsafe archive member path: {name!r}")
    target = root.joinpath(*pure.parts)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise DistributionError(f"archive member escapes extraction root: {name!r}") from error
    return target


def safe_extract(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            names = source.namelist()
            if not names or len(names) != len(set(names)):
                raise DistributionError("ZIP archive is empty or contains duplicate paths")
            for info in source.infolist():
                target = _member_path(destination, info.filename.rstrip("/"))
                mode = (info.external_attr >> 16) & 0xFFFF
                kind = stat.S_IFMT(mode)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if kind not in (0, stat.S_IFREG) or info.file_size > MAX_MEMBER_BYTES:
                    raise DistributionError(f"ZIP archive contains a special or oversized member: {info.filename}")
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
            names = [member.name for member in members]
            if not names or len(names) != len(set(names)):
                raise DistributionError("TAR archive is empty or contains duplicate paths")
            for member in members:
                target = _member_path(destination, member.name.rstrip("/"))
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile() or member.size > MAX_MEMBER_BYTES:
                    raise DistributionError(f"TAR archive contains a special or oversized member: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                reader = source.extractfile(member)
                if reader is None:
                    raise DistributionError(f"could not read TAR member: {member.name}")
                with reader, target.open("xb") as writer:
                    shutil.copyfileobj(reader, writer, length=1024 * 1024)
                os.chmod(target, member.mode & 0o777)
    roots = {path.name for path in destination.iterdir() if path.is_dir()}
    if len(roots) != 1:
        raise DistributionError("distribution archive must contain exactly one application root directory")
    return destination / next(iter(roots))


def verify_extracted(extracted: Path, expected_version: str, *, timeout: int = 120) -> None:
    executable = extracted / "bin" / ("cdin.exe" if os.name == "nt" else "cdin")
    runtime_root = extracted / "share" / "cdin" / "lua"
    if not executable.is_file() or not runtime_root.is_dir():
        raise DistributionError("extracted distribution is missing cdin executable or Runtime modules")
    environment = os.environ.copy()
    environment["CDIN_RUNTIME_ROOT"] = str(runtime_root)
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
    if not workspace.is_dir():
        raise DistributionError(f"Registry workspace is missing: {workspace}")
    registry_manifest_path = workspace / "registry-manifest.json"
    registry_manifest = read_json(registry_manifest_path, "Registry Resolved Manifest")
    target = validate_target(registry_manifest.get("resolution", {}).get("target"))
    components = component_summary(registry_manifest)
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
    if archive_path.exists():
        raise DistributionError(f"refusing to overwrite an existing distribution: {archive_name}")

    build_info: dict[str, Any] = {
        "schema_version": 1,
        "product": "com.cdin.editor",
        "product_version": version,
        "source_commit": source_revision,
        "target": target,
        "profile": profile,
        "registry_manifest_sha256": sha256_file(registry_manifest_path),
        "components": components,
        "workflow": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        },
        "distribution_status": "development-build; not a stable product release",
    }

    with tempfile.TemporaryDirectory(prefix="cdin-distribution-stage-") as stage_dir:
        stage_root = Path(stage_dir) / archive_root
        stage_root.mkdir(parents=True)
        safe_copy_prefix(prefix, stage_root)
        shutil.copyfile(ROOT / "LICENSE", stage_root / "LICENSE")
        shutil.copyfile(ROOT / "NOTICE", stage_root / "NOTICE")
        shutil.copyfile(registry_manifest_path, stage_root / "share" / "cdin" / "registry-manifest.json")
        (stage_root / "BUILD-INFO.json").write_text(
            json.dumps(build_info, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if target["os"] == "windows":
            write_zip(stage_root, archive_path, archive_root)
        else:
            write_tar_gz(stage_root, archive_path, archive_root)

    digest = sha256_file(archive_path)
    checksum_path = archive_path.with_name(archive_path.name + ".sha256")
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="ascii")
    release_manifest = {
        "schema_version": 1,
        "product": "com.cdin.editor",
        "version": version,
        "source_commit": source_revision,
        "target": target,
        "profile": profile,
        "registry_manifest_sha256": build_info["registry_manifest_sha256"],
        "archive": {
            "name": archive_path.name,
            "size_bytes": archive_path.stat().st_size,
            "sha256": digest,
        },
    }
    manifest_path = archive_path.with_name(archive_root + ".manifest.json")
    manifest_path.write_text(json.dumps(release_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if run_smoke:
        with tempfile.TemporaryDirectory(prefix="cdin-distribution-extract-") as extract_dir:
            extracted = safe_extract(archive_path, Path(extract_dir))
            verify_extracted(extracted, version)

    return {
        "archive": str(archive_path),
        "archive_sha256": digest,
        "archive_size_bytes": archive_path.stat().st_size,
        "checksum": str(checksum_path),
        "manifest": str(manifest_path),
        "target": target,
        "profile": profile,
        "version": version,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("tui", "gui-sdl"), default=os.environ.get("CDIN_FRONTEND_VARIANT", "tui"))
    parser.add_argument("--prefix", type=Path, default=DEFAULT_PREFIX)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-revision", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--skip-extracted-smoke", action="store_true", help="test-only; never use in release CI")
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
            run_smoke=not args.skip_extracted_smoke,
        )
    except (OSError, DistributionError, subprocess.SubprocessError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"distribution packaging failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
