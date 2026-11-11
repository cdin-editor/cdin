#!/usr/bin/env python3
"""Install and verify the immutable Kernel + logger SDK release package.

The Kernel 1.2.1 GitHub Release already contains both the Kernel C SDK and its
pinned m-mdy-m/log.c 0.1.0 static SDK. This consumer bootstrap downloads that
published archive; it never clones or compiles Kernel or logger source.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "deps.lock"
SDK_PREFIX = ROOT / ".deps" / "sdk"
CACHE = ROOT / "build" / "deps" / "kernel-sdk"
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_PATH_DEPTH = 32
ALLOWED_REDIRECT_HOSTS = {
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
}


class SDKBootstrapError(RuntimeError):
    """Raised when the pinned native SDK cannot be safely installed."""


class _ReleaseRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        parsed = urllib.parse.urlsplit(new_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_REDIRECT_HOSTS:
            raise SDKBootstrapError(f"SDK download redirect rejected: {new_url}")
        return super().redirect_request(request, fp, code, message, headers, new_url)


def load_pin() -> dict:
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    try:
        pin = lock["dependencies"]["kernel_sdk"]
    except (KeyError, TypeError) as error:
        raise SDKBootstrapError("deps.lock is missing dependencies.kernel_sdk") from error
    if pin.get("tag") != f"v{pin.get('version')}" or len(pin.get("revision", "")) not in (40, 64):
        raise SDKBootstrapError("Kernel SDK tag/version/source revision pin is invalid")
    if pin.get("kernel_abi") != "1.1.0" or pin.get("logger_version") != "0.1.0":
        raise SDKBootstrapError("Kernel SDK contract pins differ from the reviewed release baseline")
    return pin


def target_key(system: str | None = None, machine: str | None = None) -> str:
    system = system or platform.system()
    machine = machine or platform.machine()
    arch_aliases = {
        "x86_64": "x86_64",
        "AMD64": "x86_64",
        "amd64": "x86_64",
        "x64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    try:
        arch = arch_aliases[machine]
    except KeyError as error:
        raise SDKBootstrapError(f"unsupported SDK architecture: {machine}") from error

    if os.name == "nt" or system.lower().startswith(("mingw", "msys", "cygwin")):
        if arch != "x86_64":
            raise SDKBootstrapError("the published Windows SDK currently targets x86_64 UCRT64")
        return "windows-x86_64"
    normalized = system.lower()
    if normalized == "linux":
        return f"linux-{arch}"
    if normalized == "darwin":
        return f"macos-{arch}"
    raise SDKBootstrapError(f"unsupported SDK operating system: {system}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_asset(path: Path, asset: dict) -> None:
    expected_size = asset.get("size_bytes")
    expected_digest = asset.get("sha256")
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size <= 0
        or expected_size > MAX_ARCHIVE_BYTES
    ):
        raise SDKBootstrapError("locked Kernel SDK asset size is invalid")
    if (
        not isinstance(expected_digest, str)
        or len(expected_digest) != 64
        or any(character not in "0123456789abcdef" for character in expected_digest)
    ):
        raise SDKBootstrapError("locked Kernel SDK SHA-256 is invalid")
    actual_size = path.stat().st_size
    actual_digest = sha256_file(path)
    if actual_size != expected_size:
        raise SDKBootstrapError(
            f"Kernel SDK size mismatch: expected {expected_size}, found {actual_size}"
        )
    if actual_digest != expected_digest:
        raise SDKBootstrapError(
            f"Kernel SDK SHA-256 mismatch: expected {expected_digest}, found {actual_digest}"
        )


def download_asset(pin: dict, asset: dict) -> Path:
    filename = asset["file_name"]
    if Path(filename).name != filename or not filename.startswith("cdin-kernel-"):
        raise SDKBootstrapError("locked Kernel SDK filename is not a safe basename")
    CACHE.mkdir(parents=True, exist_ok=True)
    destination = CACHE / filename
    if destination.is_file():
        try:
            verify_asset(destination, asset)
            return destination
        except SDKBootstrapError:
            destination.unlink()

    url = f"{pin['repository'].rstrip('/')}/releases/download/{pin['tag']}/{filename}"
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise SDKBootstrapError("Kernel SDK source must be a canonical GitHub HTTPS URL")

    opener = urllib.request.build_opener(_ReleaseRedirectHandler())
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CDIN-SDK-Bootstrap/1",
            "Accept": "application/octet-stream",
        },
    )
    temporary = destination.with_name(destination.name + ".download")
    try:
        with opener.open(request, timeout=45) as response, temporary.open("wb") as output:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname not in ALLOWED_REDIRECT_HOSTS:
                raise SDKBootstrapError("Kernel SDK final download URL is not trusted")
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) != asset["size_bytes"]:
                raise SDKBootstrapError("Kernel SDK Content-Length differs from deps.lock")
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > asset["size_bytes"] or total > MAX_ARCHIVE_BYTES:
                    raise SDKBootstrapError("Kernel SDK download exceeded its pinned size")
                output.write(chunk)
        if total != asset["size_bytes"]:
            raise SDKBootstrapError(
                f"Kernel SDK download was truncated: expected {asset['size_bytes']}, found {total}"
            )
        verify_asset(temporary, asset)
        temporary.replace(destination)
        return destination
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as error:
        raise SDKBootstrapError(f"cannot download pinned Kernel SDK {filename}: {error}") from error
    finally:
        if temporary.exists():
            temporary.unlink()


def _safe_archive_path(raw: str) -> str:
    if (
        not raw
        or "\x00" in raw
        or "\\" in raw
        or raw.startswith("/")
        or (len(raw) >= 2 and raw[1] == ":")
        or any(ord(character) < 32 or ord(character) == 127 for character in raw)
    ):
        raise SDKBootstrapError(f"unsafe SDK archive path: {raw!r}")
    value = raw[:-1] if raw.endswith("/") else raw
    parts = value.split("/")
    if not value or any(part in ("", ".", "..") for part in parts):
        raise SDKBootstrapError(f"non-canonical SDK archive path: {raw!r}")
    if len(parts) > MAX_PATH_DEPTH:
        raise SDKBootstrapError(f"SDK archive path depth exceeded: {raw!r}")
    if unicodedata.normalize("NFC", value) != value:
        raise SDKBootstrapError(f"non-normalized Unicode SDK archive path: {raw!r}")
    for part in parts:
        if part.endswith((".", " ")) or ":" in part:
            raise SDKBootstrapError(f"non-portable SDK archive path: {raw!r}")
        stem = part.split(".", 1)[0].upper()
        reserved = {"CON", "PRN", "AUX", "NUL"}
        reserved.update(f"COM{i}" for i in range(1, 10))
        reserved.update(f"LPT{i}" for i in range(1, 10))
        if stem in reserved:
            raise SDKBootstrapError(f"reserved Windows SDK archive path: {raw!r}")
    return value


def _register_archive_paths(records: list[tuple[str, str]]) -> tuple[str, dict[str, str]]:
    kinds: dict[str, str] = {}
    folded: dict[str, str] = {}
    explicit: set[str] = set()
    root_names: set[str] = set()
    for name, kind in records:
        value = _safe_archive_path(name)
        key = value.casefold()
        if key in folded:
            raise SDKBootstrapError(f"duplicate or case-folding SDK archive path: {value}")
        folded[key] = value
        parts = value.split("/")
        root_names.add(parts[0])
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index])
            parent_key = parent.casefold()
            if kinds.get(parent_key) not in (None, "dir"):
                raise SDKBootstrapError(f"SDK archive file/directory collision: {value}")
            kinds[parent_key] = "dir"
        if key in kinds:
            raise SDKBootstrapError(f"SDK archive path collides with an implicit parent: {value}")
        kinds[key] = kind
        explicit.add(key)
    if len(root_names) != 1:
        raise SDKBootstrapError("Kernel SDK archive must contain exactly one top-level package directory")
    return next(iter(root_names)), folded


def _write_file(destination: Path, data: bytes, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    destination.chmod(0o755 if mode & 0o111 else 0o644)


def extract_tar_gz(archive_path: Path, destination: Path) -> Path:
    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = archive.getmembers()
        if not members or len(members) > MAX_ARCHIVE_ENTRIES:
            raise SDKBootstrapError("Kernel TAR.GZ entry count is empty or exceeds the limit")
        records: list[tuple[str, str]] = []
        member_by_name: dict[str, tarfile.TarInfo] = {}
        expanded = 0
        for member in members:
            if member.isdir():
                kind = "dir"
            elif member.isfile():
                kind = "file"
                if member.size < 0:
                    raise SDKBootstrapError("negative Kernel TAR entry size")
                expanded += member.size
            elif member.issym():
                kind = "symlink"
            else:
                raise SDKBootstrapError(f"Kernel TAR links/special entries are not allowed: {member.name}")
            if member.mode & 0o7000:
                raise SDKBootstrapError(f"privileged Kernel TAR mode rejected: {member.name}")
            if kind == "dir" and member.size != 0:
                raise SDKBootstrapError(f"Kernel TAR directory entry is not empty: {member.name}")
            records.append((member.name, kind))
            member_by_name[member.name.rstrip("/")] = member
        if expanded > MAX_EXPANDED_BYTES:
            raise SDKBootstrapError("Kernel TAR expanded-size limit exceeded")
        root_name, _ = _register_archive_paths(records)

        def read_member(name: str, visiting: set[str]) -> tuple[bytes, int]:
            if name in visiting:
                raise SDKBootstrapError(f"Kernel TAR symlink cycle detected: {name}")
            member = member_by_name.get(name)
            if member is None:
                raise SDKBootstrapError(f"Kernel TAR symlink target is missing: {name}")
            if member.isfile():
                stream = archive.extractfile(member)
                if stream is None:
                    raise SDKBootstrapError(f"cannot read Kernel TAR member: {name}")
                data = stream.read(member.size + 1)
                if len(data) != member.size:
                    raise SDKBootstrapError(f"Kernel TAR member size mismatch: {name}")
                return data, member.mode
            if member.issym():
                target = PurePosixPath(member.linkname)
                if target.is_absolute() or len(target.parts) != 1 or target.parts[0] in ("", ".", ".."):
                    raise SDKBootstrapError(f"Kernel TAR symlink target must be a sibling filename: {name}")
                parent = PurePosixPath(name).parent
                target_name = (parent / target).as_posix()
                return read_member(target_name, visiting | {name})
            raise SDKBootstrapError(f"Kernel TAR symlink does not target a regular file: {name}")

        destination.mkdir(parents=True, exist_ok=True)
        for name, kind in records:
            if kind == "dir":
                (destination / Path(*PurePosixPath(name).parts)).mkdir(parents=True, exist_ok=True)
        for name, kind in records:
            if kind not in ("file", "symlink"):
                continue
            data, mode = read_member(name.rstrip("/"), set())
            _write_file(destination / Path(*PurePosixPath(name).parts), data, mode)
    return destination / root_name


def extract_zip(archive_path: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if not members or len(members) > MAX_ARCHIVE_ENTRIES:
            raise SDKBootstrapError("Kernel ZIP entry count is empty or exceeds the limit")
        records: list[tuple[str, str]] = []
        total = 0
        for info in members:
            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if info.is_dir():
                kind = "dir"
            elif file_type in (0, stat.S_IFREG):
                kind = "file"
                total += info.file_size
            else:
                raise SDKBootstrapError(f"Kernel ZIP special/symlink entry rejected: {info.filename}")
            if mode & 0o7000:
                raise SDKBootstrapError(f"privileged Kernel ZIP mode rejected: {info.filename}")
            if info.flag_bits & 1:
                raise SDKBootstrapError("encrypted Kernel ZIP entries are not supported")
            records.append((info.filename, kind))
        if total > MAX_EXPANDED_BYTES:
            raise SDKBootstrapError("Kernel ZIP expanded-size limit exceeded")
        root_name, _ = _register_archive_paths(records)
        destination.mkdir(parents=True, exist_ok=True)
        for info, (_, kind) in zip(members, records):
            if kind == "dir":
                (destination / Path(*PurePosixPath(info.filename).parts)).mkdir(parents=True, exist_ok=True)
            else:
                data = archive.read(info)
                if len(data) != info.file_size:
                    raise SDKBootstrapError(f"Kernel ZIP member size mismatch: {info.filename}")
                mode = (info.external_attr >> 16) & 0o777
                _write_file(destination / Path(*PurePosixPath(info.filename).parts), data, mode)
    return destination / root_name


def parse_build_info(package_root: Path, pin: dict, target: str) -> None:
    build_info = package_root / "BUILD-INFO.txt"
    if not build_info.is_file():
        raise SDKBootstrapError("Kernel package is missing BUILD-INFO.txt")
    fields: dict[str, str] = {}
    for line in build_info.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            key = key.strip()
            if key in fields:
                raise SDKBootstrapError(f"duplicate Kernel BUILD-INFO field: {key}")
            fields[key] = value.strip()
    platform_name, architecture = target.split("-", 1)
    expected_platform = {"linux": "linux", "macos": "macos", "windows": "windows"}[platform_name]
    required = {
        "Package version": pin["version"],
        "C ABI version": pin["kernel_abi"],
        "Platform": expected_platform,
        "Architecture": architecture,
    }
    for key, expected in required.items():
        if fields.get(key) != expected:
            raise SDKBootstrapError(
                f"Kernel BUILD-INFO {key!r} is {fields.get(key)!r}, expected {expected!r}"
            )


def validate_package_tree(package_root: Path, pin: dict, target: str) -> None:
    parse_build_info(package_root, pin, target)
    required = (
        "include/cdin/kernel.h",
        "include/m-mdy-m/log.h",
        "lib/libcdin_kernel.a",
        "lib/libm-mdy-m-log.a",
        "lib/pkgconfig/cdin-kernel.pc",
        "lib/pkgconfig/m-mdy-m-log.pc",
        "lib/cmake/m-mdy-m-log/m-mdy-m-log-config.cmake",
        "lib/cmake/m-mdy-m-log/m-mdy-m-log-targets.cmake",
        "install.ps1" if target.startswith("windows-") else "install.sh",
    )
    missing = [name for name in required if not (package_root / name).is_file()]
    if missing:
        raise SDKBootstrapError("Kernel package is incomplete: " + ", ".join(missing))
    if target.startswith("windows-"):
        platform_files = ("lib/libcdin_kernel.dll.a", "bin/cdin_kernel.dll")
    elif target.startswith("macos-"):
        platform_files = (f"lib/libcdin_kernel.{pin['kernel_abi']}.dylib",)
    else:
        platform_files = (f"lib/libcdin_kernel.so.{pin['kernel_abi']}",)
    missing_platform = [name for name in platform_files if not (package_root / name).is_file()]
    if missing_platform:
        raise SDKBootstrapError("Kernel package is missing target libraries: " + ", ".join(missing_platform))


def _windows_path(path: Path) -> str:
    cygpath = shutil.which("cygpath")
    if cygpath is None:
        raise SDKBootstrapError("cygpath is required to install the UCRT64 Kernel SDK")
    return subprocess.check_output([cygpath, "-w", str(path)], text=True).strip()


def install_package(package_root: Path, prefix: Path) -> None:
    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
        if powershell is None:
            raise SDKBootstrapError("PowerShell is required to install the UCRT64 Kernel SDK")
        subprocess.run(
            [
                powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", _windows_path(package_root / "install.ps1"),
                "-Prefix", _windows_path(prefix),
            ],
            cwd=package_root,
            check=True,
        )
    else:
        subprocess.run(
            ["bash", str(package_root / "install.sh"), "--prefix", str(prefix)],
            cwd=package_root,
            check=True,
        )


def parse_kernel_abi(header_text: str) -> str:
    """Read the public three-part Kernel C ABI from kernel.h."""
    values: dict[str, str] = {}
    for name in ("MAJOR", "MINOR", "PATCH"):
        match = re.search(
            rf"^#define CDIN_KERNEL_ABI_{name}\s+([0-9]+)u?$",
            header_text,
            flags=re.MULTILINE,
        )
        if match is None:
            raise SDKBootstrapError(f"installed Kernel header is missing ABI {name}")
        values[name] = match.group(1)
    return ".".join(values[name] for name in ("MAJOR", "MINOR", "PATCH"))



def verify_installed(pin: dict, prefix: Path = SDK_PREFIX) -> None:
    required = (
        "include/cdin/kernel.h",
        "include/m-mdy-m/log.h",
        "lib/libcdin_kernel.a",
        "lib/libm-mdy-m-log.a",
        "lib/pkgconfig/cdin-kernel.pc",
        "lib/pkgconfig/m-mdy-m-log.pc",
        "lib/cmake/m-mdy-m-log/m-mdy-m-log-config.cmake",
        "lib/cmake/m-mdy-m-log/m-mdy-m-log-targets.cmake",
    )
    missing = [name for name in required if not (prefix / name).is_file()]
    if missing:
        raise SDKBootstrapError("pinned Kernel/logger SDK is not installed: " + ", ".join(missing))
    pc_versions: dict[str, str] = {}
    for package, filename in (
        ("kernel", "lib/pkgconfig/cdin-kernel.pc"),
        ("logger", "lib/pkgconfig/m-mdy-m-log.pc"),
    ):
        values: dict[str, str] = {}
        for line in (prefix / filename).read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator:
                values[key.strip()] = value.strip()
        if not values.get("Version"):
            raise SDKBootstrapError(f"{filename} does not declare a package Version")
        pc_versions[package] = values["Version"]
    if pc_versions["kernel"] != pin["version"]:
        raise SDKBootstrapError(
            f"installed Kernel pkg-config version is {pc_versions['kernel']}, expected {pin['version']}"
        )
    if pc_versions["logger"] != pin["logger_version"]:
        raise SDKBootstrapError(
            f"installed logger pkg-config version is {pc_versions['logger']}, expected {pin['logger_version']}"
        )
    header = (prefix / "include/cdin/kernel.h").read_text(encoding="utf-8")
    abi_version = parse_kernel_abi(header)
    if abi_version != pin["kernel_abi"]:
        raise SDKBootstrapError(
            f"installed Kernel ABI is {abi_version}, expected {pin['kernel_abi']}"
        )
    if os.name == "nt":
        for name in ("lib/libcdin_kernel.dll.a", "bin/cdin_kernel.dll"):
            if not (prefix / name).is_file():
                raise SDKBootstrapError(f"installed Windows Kernel SDK is missing {name}")



def install_sdk_atomically(
    package_root: Path,
    pin: dict,
    destination: Path = SDK_PREFIX,
) -> None:
    """Install to a sibling staging directory and swap only after full verification.

    A failed installer or verification leaves any previously working SDK prefix
    untouched. The staging directory is on the same filesystem as the target so
    the final directory replacement is an atomic rename.
    """
    destination = Path(os.path.abspath(destination))
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)

    current = destination
    while current != current.parent:
        if current.is_symlink():
            raise SDKBootstrapError(f"Kernel SDK destination contains a symlink ancestor: {current}")
        current = current.parent
    if destination.exists() and (destination.is_symlink() or not destination.is_dir()):
        raise SDKBootstrapError("Kernel SDK destination must be a real directory")

    backup = destination.with_name(destination.name + ".previous")
    if backup.is_symlink():
        raise SDKBootstrapError("Kernel SDK backup path must not be a symlink")
    if backup.exists():
        raise SDKBootstrapError("Kernel SDK backup path already exists; inspect it before retrying")

    with tempfile.TemporaryDirectory(prefix=destination.name + ".staging-", dir=parent) as temporary:
        staged_prefix = Path(temporary) / "prefix"
        install_package(package_root, staged_prefix)
        verify_installed(pin, staged_prefix)

        had_previous = destination.exists()
        if had_previous:
            os.replace(destination, backup)
        try:
            os.replace(staged_prefix, destination)
        except Exception:
            if had_previous and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="verify the installed SDK without network access")
    parser.add_argument("--force", action="store_true", help="replace the installed SDK from the pinned release asset")
    args = parser.parse_args()
    pin = load_pin()
    if args.verify:
        verify_installed(pin)
        print(f"OK Kernel SDK {pin['version']} (ABI {pin['kernel_abi']}) + logger {pin['logger_version']}")
        return 0

    try:
        verify_installed(pin)
        if not args.force:
            print(f"Kernel/logger SDK already installed at {SDK_PREFIX}")
            return 0
    except SDKBootstrapError:
        pass

    target = target_key()
    try:
        asset = pin["assets"][target]
    except KeyError as error:
        raise SDKBootstrapError(f"deps.lock has no Kernel SDK asset for target {target}") from error
    archive = download_asset(pin, asset)

    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="extract-", dir=CACHE) as temporary:
        stage = Path(temporary)
        root = extract_zip(archive, stage) if asset["format"] == "zip" else extract_tar_gz(archive, stage)
        expected_root = f"cdin-kernel-{pin['version']}"
        if root.name != expected_root:
            raise SDKBootstrapError(f"Kernel SDK package root is {root.name}, expected {expected_root}")
        validate_package_tree(root, pin, target)
        install_sdk_atomically(root, pin)
    verify_installed(pin)
    print(f"Installed Kernel SDK {pin['version']} (ABI {pin['kernel_abi']}) + logger {pin['logger_version']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SDKBootstrapError, OSError, subprocess.CalledProcessError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"deps: {error}", file=sys.stderr)
        raise SystemExit(1)
