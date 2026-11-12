#!/usr/bin/env python3
"""Acquire and safely stage the exact immutable SDL3 SDK release for CDIN."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "deps.lock"
CACHE = ROOT / ".deps" / "cache" / "sdl3-sdk"
REPOSITORY = "https://github.com/cdin-editor/cdin"
API = "https://api.github.com/repos/cdin-editor/cdin"
MAX_API_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 30_000
MAX_PATH_DEPTH = 32
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TARGETS: dict[str, tuple[str, str]] = {
    "linux-x86_64": ("linux", "gnu-glibc-2.39"),
    "linux-arm64": ("linux", "gnu-glibc-2.39"),
    "macos-x86_64": ("darwin", "macos-15"),
    "macos-arm64": ("darwin", "macos-15"),
    "windows-x86_64": ("windows", "windows-ucrt64"),
}


class SDL3ArtifactError(RuntimeError):
    """Raised when a pinned immutable SDL3 SDK cannot be safely installed."""


def strict_json(data: bytes, label: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SDL3ArtifactError(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SDL3ArtifactError(f"{label} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise SDL3ArtifactError(f"{label} JSON root must be an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_key(target: dict[str, Any]) -> str:
    if not isinstance(target, dict):
        raise SDL3ArtifactError("Registry Resolved Manifest target must be an object")
    os_name = target.get("os")
    architecture = target.get("architecture")
    abi = target.get("abi")
    if not all(isinstance(item, str) for item in (os_name, architecture, abi)):
        raise SDL3ArtifactError("Registry target must declare OS, architecture and ABI")
    normalized_os = "macos" if os_name == "darwin" else os_name
    if set(target) != {"os", "architecture", "abi"}:
        raise SDL3ArtifactError("Registry target must contain only OS, architecture and ABI")
    candidates = [
        key for key, (expected_os, expected_abi) in TARGETS.items()
        if normalized_os == ("macos" if expected_os == "darwin" else expected_os)
        and architecture == key.rsplit("-", 1)[1]
        and abi == expected_abi
    ]
    if len(candidates) != 1:
        raise SDL3ArtifactError(
            f"no published SDL3 SDK matches target OS/architecture/ABI: {target}"
        )
    return candidates[0]


def current_target_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    os_name = {"linux": "linux", "darwin": "macos", "windows": "windows"}.get(system)
    architecture = {
        "x86_64": "x86_64", "amd64": "x86_64",
        "aarch64": "arm64", "arm64": "arm64",
    }.get(machine)
    if os_name is None or architecture is None:
        raise SDL3ArtifactError(f"unsupported native SDL3 SDK target: {system}/{machine}")
    if os_name == "linux":
        libc, version = platform.libc_ver()
        abi = f"{libc.lower()}-{version}"
        if libc.lower() != "glibc" or version != "2.39":
            raise SDL3ArtifactError(
                f"published Linux SDL3 SDKs require glibc 2.39, found {abi}"
            )
    elif os_name == "macos":
        major = (platform.mac_ver()[0] or "").split(".", 1)[0]
        if major != "15":
            raise SDL3ArtifactError(
                f"published macOS SDL3 SDKs require macOS 15, found {platform.mac_ver()[0]!r}"
            )
        abi = "macos-15"
    else:
        if architecture != "x86_64" or os.environ.get("MSYSTEM") != "UCRT64":
            raise SDL3ArtifactError("published Windows SDL3 SDK requires x86_64 MSYS2 UCRT64")
        abi = "windows-ucrt64"
    key = f"{os_name}-{architecture}"
    expected_os, expected_abi = TARGETS.get(key, (None, None))
    if (
        (("macos" if expected_os == "darwin" else expected_os) != os_name)
        or expected_abi != abi
    ):
        raise SDL3ArtifactError(f"unsupported SDL3 SDK ABI for {key}: {abi}")
    return key


def validate_pin(lock: dict[str, Any], key: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Validate a complete five-target immutable SDK pin; never invent missing bytes."""
    pin = lock.get("dependencies", {}).get("sdl3_sdk")
    if not isinstance(pin, dict):
        raise SDL3ArtifactError(
            "deps.lock is missing dependencies.sdl3_sdk. Publish and verify "
            "sdl3-sdk-v3.4.16 first, then pin its tag commit and all five "
            "Release asset sizes/SHA-256 digests; source fallback is developer-only."
        )
    required = ("repository", "tag", "version", "revision", "assets")
    missing = [field for field in required if field not in pin]
    if missing:
        raise SDL3ArtifactError(
            "deps.lock dependencies.sdl3_sdk is incomplete: " + ", ".join(missing)
        )
    repository = pin.get("repository")
    version = pin.get("version")
    tag = pin.get("tag")
    revision = pin.get("revision")
    if repository != REPOSITORY:
        raise SDL3ArtifactError("SDL3 SDK repository pin is not the canonical CDIN repository")
    source = lock.get("tooling", {}).get("sdl3")
    if not isinstance(source, dict):
        raise SDL3ArtifactError("deps.lock tooling.sdl3 source provenance is missing")
    source_version = source.get("version")
    source_url = source.get("archive")
    source_digest = source.get("sha256")
    if (
        not isinstance(source_version, str)
        or version != source_version
        or tag != f"sdl3-sdk-v{version}"
        or not isinstance(revision, str)
        or GIT_SHA_RE.fullmatch(revision) is None
        or not isinstance(source_url, str)
        or not source_url.startswith("https://github.com/libsdl-org/SDL/releases/download/")
        or not isinstance(source_digest, str)
        or SHA_RE.fullmatch(source_digest) is None
    ):
        raise SDL3ArtifactError("SDL3 SDK version/tag/source provenance pin is malformed")
    assets = pin.get("assets")
    if not isinstance(assets, dict) or set(assets) != set(TARGETS):
        missing_targets = sorted(set(TARGETS) - set(assets or {})) if isinstance(assets, dict) else sorted(TARGETS)
        extra_targets = sorted(set(assets) - set(TARGETS)) if isinstance(assets, dict) else []
        raise SDL3ArtifactError(
            f"SDL3 SDK lock must pin exactly five targets; missing={missing_targets}, extra={extra_targets}"
        )
    for target_name in sorted(TARGETS):
        pinned_asset = assets.get(target_name)
        if not isinstance(pinned_asset, dict):
            raise SDL3ArtifactError(
                f"SDL3 SDK lock has no asset object for {target_name}"
            )
        expected_name = f"sdl3-sdk-{version}-{target_name}.tar.gz"
        filename = pinned_asset.get("file_name")
        size = pinned_asset.get("size_bytes")
        digest = pinned_asset.get("sha256")
        if (
            set(pinned_asset) != {"file_name", "format", "size_bytes", "sha256"}
            or filename != expected_name
            or pinned_asset.get("format") != "tar.gz"
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or size > MAX_ASSET_BYTES
            or not isinstance(digest, str)
            or SHA_RE.fullmatch(digest) is None
        ):
            raise SDL3ArtifactError(
                f"SDL3 SDK asset pin for {target_name} is malformed"
            )
    asset = assets[key]
    return pin, asset, {
        "version": version,
        "url": source_url,
        "sha256": source_digest,
    }


class _APIRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        parsed = urllib.parse.urlsplit(new_url)
        try:
            port = parsed.port
        except ValueError as error:
            raise SDL3ArtifactError("SDL3 GitHub API redirect has an invalid port") from error
        if (
            parsed.scheme != "https" or parsed.hostname != "api.github.com"
            or port not in (None, 443) or parsed.username or parsed.password
            or parsed.query or parsed.fragment
        ):
            raise SDL3ArtifactError("SDL3 GitHub API redirect left the trusted API origin")
        return super().redirect_request(request, fp, code, message, headers, new_url)


class _AssetRedirectHandler(urllib.request.HTTPRedirectHandler):
    allowed_hosts = {
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }

    def redirect_request(self, request, fp, code, message, headers, new_url):
        parsed = urllib.parse.urlsplit(new_url)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts:
            raise SDL3ArtifactError(f"SDL3 SDK asset redirect rejected: {new_url}")
        return super().redirect_request(request, fp, code, message, headers, new_url)


def fetch_github_json(path: str) -> dict[str, Any]:
    if not path.startswith("/repos/cdin-editor/cdin/") or "?" in path or "#" in path:
        raise SDL3ArtifactError("SDL3 GitHub API path is outside the canonical CDIN repository")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CDIN-SDL3-SDK-Bootstrap/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"https://api.github.com{path}", headers=headers)
    opener = urllib.request.build_opener(_APIRedirectHandler())
    try:
        with opener.open(request, timeout=30) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if response.status != 200 or final.scheme != "https" or final.hostname != "api.github.com":
                raise SDL3ArtifactError("SDL3 GitHub API response came from an untrusted origin")
            data = response.read(MAX_API_BYTES + 1)
    except (OSError, urllib.error.URLError) as error:
        raise SDL3ArtifactError(f"cannot inspect immutable SDL3 SDK Release identity: {error}") from error
    if len(data) > MAX_API_BYTES:
        raise SDL3ArtifactError("SDL3 GitHub API response exceeds the 2 MiB limit")
    return strict_json(data, "SDL3 GitHub API response")


def resolve_tag_commit(tag: str) -> str:
    reference = fetch_github_json(
        f"/repos/cdin-editor/cdin/git/ref/tags/{urllib.parse.quote(tag, safe='')}"
    )
    obj = reference.get("object")
    visited: set[str] = set()
    for _ in range(8):
        if not isinstance(obj, dict):
            raise SDL3ArtifactError("SDL3 SDK Git tag has no Git object")
        kind, sha = obj.get("type"), obj.get("sha")
        if not isinstance(sha, str) or GIT_SHA_RE.fullmatch(sha) is None or sha in visited:
            raise SDL3ArtifactError("SDL3 SDK Git tag contains an invalid/cyclic object SHA")
        visited.add(sha)
        if kind == "commit":
            return sha
        if kind != "tag":
            raise SDL3ArtifactError("SDL3 SDK tag resolves to an unsupported Git object")
        tag_object = fetch_github_json(f"/repos/cdin-editor/cdin/git/tags/{sha}")
        if tag_object.get("sha") != sha:
            raise SDL3ArtifactError("SDL3 SDK annotated tag object identity mismatch")
        obj = tag_object.get("object")
    raise SDL3ArtifactError("SDL3 SDK annotated tag nesting exceeds 8 objects")


def verify_release(pin: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    release = fetch_github_json(
        f"/repos/cdin-editor/cdin/releases/tags/{urllib.parse.quote(pin['tag'], safe='')}"
    )
    if (
        release.get("tag_name") != pin["tag"]
        or release.get("draft") is not False
        or release.get("prerelease") is not True
    ):
        raise SDL3ArtifactError("SDL3 SDK Release must be the exact published prerelease for its pin")
    actual_revision = resolve_tag_commit(pin["tag"])
    if actual_revision != pin["revision"]:
        raise SDL3ArtifactError(
            f"SDL3 SDK tag target mismatch: expected {pin['revision']}, found {actual_revision}"
        )
    api_assets = release.get("assets")
    if not isinstance(api_assets, list):
        raise SDL3ArtifactError("SDL3 SDK Release has no asset inventory")
    expected_names: set[str] = set()
    indexed: dict[str, dict[str, Any]] = {}
    for key, pinned_asset in pin["assets"].items():
        filename = pinned_asset["file_name"]
        sidecar = filename + ".sha256"
        expected_names.update((filename, sidecar))
    for item in api_assets:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise SDL3ArtifactError("SDL3 SDK Release contains a malformed asset record")
        name = item["name"]
        if name in indexed:
            raise SDL3ArtifactError(f"SDL3 SDK Release contains duplicate asset {name}")
        indexed[name] = item
    if set(indexed) != expected_names:
        missing = sorted(expected_names - set(indexed))
        unexpected = sorted(set(indexed) - expected_names)
        raise SDL3ArtifactError(
            f"SDL3 SDK Release inventory must contain exactly five archive/checksum pairs; "
            f"missing={missing}, unexpected={unexpected}"
        )
    for key, pinned_asset in pin["assets"].items():
        filename = pinned_asset["file_name"]
        item = indexed[filename]
        if (
            item.get("size") != pinned_asset["size_bytes"]
            or item.get("digest") != f"sha256:{pinned_asset['sha256']}"
        ):
            raise SDL3ArtifactError(
                f"SDL3 SDK Release Asset size/digest differs from deps.lock for {key}"
            )
        if indexed[filename + ".sha256"].get("size", 0) <= 0:
            raise SDL3ArtifactError(f"SDL3 SDK Release checksum sidecar is empty for {key}")
    return release


def _ensure_real_directory(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    chain = [absolute, *absolute.parents]
    for item in reversed(chain):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise SDL3ArtifactError(f"SDL3 SDK path has a symlink/non-directory ancestor: {item}")
    absolute.mkdir(parents=True, exist_ok=True)


def _download(url: str, destination: Path, *, expected_size: int, max_size: int) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise SDL3ArtifactError("SDL3 SDK download URL must use the canonical GitHub HTTPS host")
    opener = urllib.request.build_opener(_AssetRedirectHandler())
    request = urllib.request.Request(url, headers={
        "User-Agent": "CDIN-SDL3-SDK-Bootstrap/1",
        "Accept": "application/octet-stream",
    })
    fd, temporary_name = tempfile.mkstemp(prefix=destination.name + ".tmp-", dir=destination.parent)
    temporary = Path(temporary_name)
    total = 0
    try:
        with os.fdopen(fd, "wb") as output:
            with opener.open(request, timeout=45) as response:
                final = urllib.parse.urlsplit(response.geturl())
                if response.status != 200 or final.scheme != "https" or final.hostname not in _AssetRedirectHandler.allowed_hosts:
                    raise SDL3ArtifactError("SDL3 SDK final download URL is not trusted")
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) != expected_size:
                    raise SDL3ArtifactError("SDL3 SDK Content-Length differs from deps.lock")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > expected_size or total > max_size:
                        raise SDL3ArtifactError("SDL3 SDK download exceeded its pinned size")
                    output.write(chunk)
        if total != expected_size:
            raise SDL3ArtifactError(f"SDL3 SDK download truncated: expected {expected_size}, found {total}")
        temporary.replace(destination)
    except SDL3ArtifactError:
        raise
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as error:
        raise SDL3ArtifactError(f"SDL3 SDK download failed: {error}") from error
    finally:
        temporary.unlink(missing_ok=True)


def download_asset(pin: dict[str, Any], asset: dict[str, Any],
                   source: dict[str, str], *, cache: Path = CACHE, offline: bool = False) -> Path:
    filename = asset["file_name"]
    cache_name = f"{Path(filename).stem}-{asset['sha256']}.tar.gz"
    _ensure_real_directory(cache)
    destination = cache / cache_name
    if destination.exists() or destination.is_symlink():
        info = destination.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise SDL3ArtifactError("SDL3 SDK cache archive must be a regular file")
        if info.st_size != asset["size_bytes"] or sha256_file(destination) != asset["sha256"]:
            if offline:
                raise SDL3ArtifactError("offline SDL3 SDK cache entry is corrupt for the exact pin")
            destination.unlink()
    if offline:
        if not destination.is_file():
            raise SDL3ArtifactError("offline GUI-SDL install requires the exact pinned SDL3 SDK archive in cache")
        return destination
    # Online requests revalidate the tag, commit and GitHub asset digest even
    # when the local archive cache is already populated.
    release = verify_release(pin, asset)
    if destination.is_file():
        return destination
    url = f"{REPOSITORY}/releases/download/{pin['tag']}/{filename}"
    _download(url, destination, expected_size=asset["size_bytes"], max_size=MAX_ASSET_BYTES)
    if sha256_file(destination) != asset["sha256"]:
        destination.unlink(missing_ok=True)
        raise SDL3ArtifactError("downloaded SDL3 SDK archive SHA-256 mismatch")
    sidecar_url = f"{REPOSITORY}/releases/download/{pin['tag']}/{filename}.sha256"
    sidecar = cache / (cache_name + ".sha256")
    _download(sidecar_url, sidecar, expected_size=67 + len(filename), max_size=256)
    expected_line = f"{asset['sha256']}  {filename}\n"
    if sidecar.read_text(encoding="ascii") != expected_line:
        raise SDL3ArtifactError("SDL3 SDK SHA-256 sidecar does not match the locked archive digest")
    return destination


def safe_extract(archive_path: Path, destination: Path) -> Path:
    _ensure_real_directory(destination)
    root = destination.resolve()
    seen: set[str] = set()
    top_level: set[str] = set()
    expanded = 0
    try:
        archive = tarfile.open(archive_path, "r:gz")
    except (OSError, tarfile.TarError) as error:
        raise SDL3ArtifactError(f"SDL3 SDK archive is not a valid gzip TAR: {error}") from error
    with archive:
        members = archive.getmembers()
        if not members or len(members) > MAX_ARCHIVE_ENTRIES:
            raise SDL3ArtifactError("SDL3 SDK archive has an invalid entry count")
        for member in members:
            name = PurePosixPath(member.name)
            if (
                name.is_absolute() or not name.parts
                or any(part in ("", ".", "..") for part in name.parts)
                or "\\" in member.name or (len(member.name) >= 2 and member.name[1] == ":")
            ):
                raise SDL3ArtifactError(f"unsafe SDL3 SDK archive path: {member.name!r}")
            normalized = name.as_posix().rstrip("/").casefold()
            if normalized in seen:
                raise SDL3ArtifactError(f"duplicate/case-colliding SDL3 SDK path: {member.name!r}")
            seen.add(normalized)
            if len(name.parts) > MAX_PATH_DEPTH:
                raise SDL3ArtifactError(f"SDL3 SDK archive path depth exceeded: {member.name!r}")
            if not (member.isdir() or member.isfile()):
                raise SDL3ArtifactError(f"unsupported SDL3 SDK archive entry: {member.name!r}")
            if member.size < 0 or member.size > MAX_ASSET_BYTES:
                raise SDL3ArtifactError(f"invalid SDL3 SDK archive member size: {member.name!r}")
            expanded += member.size
            if expanded > MAX_EXPANDED_BYTES:
                raise SDL3ArtifactError("SDL3 SDK archive expands beyond the safety limit")
            top_level.add(name.parts[0])
            target = (destination / Path(*name.parts)).resolve()
            if target != root and root not in target.parents:
                raise SDL3ArtifactError(f"SDL3 SDK archive path escapes extraction root: {member.name!r}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = archive.extractfile(member)
            if source is None:
                raise SDL3ArtifactError(f"cannot read SDL3 SDK archive entry {member.name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    if top_level != {"sdl3-sdk"}:
        raise SDL3ArtifactError(f"SDL3 SDK archive root must be exactly 'sdl3-sdk', found {sorted(top_level)}")
    return destination / "sdl3-sdk"


def _safe_regular_file(root: Path, relative: str) -> Path:
    """Resolve a required package file while rejecting symlinked path components."""
    root = Path(os.path.abspath(root))
    current = root
    try:
        root_info = current.lstat()
    except FileNotFoundError as error:
        raise SDL3ArtifactError(f"SDL3 SDK package root does not exist: {root}") from error
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise SDL3ArtifactError("SDL3 SDK package root is not a real directory")
    parts = PurePosixPath(relative).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise SDL3ArtifactError(f"invalid SDL3 SDK package path: {relative!r}")
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError as error:
            raise SDL3ArtifactError(f"SDL3 SDK package is missing: {relative}") from error
        is_final = index == len(parts) - 1
        if stat.S_ISLNK(info.st_mode):
            raise SDL3ArtifactError(f"SDL3 SDK package path contains a symlink: {relative}")
        if is_final:
            if not stat.S_ISREG(info.st_mode):
                raise SDL3ArtifactError(f"SDL3 SDK package entry is not a regular file: {relative}")
        elif not stat.S_ISDIR(info.st_mode):
            raise SDL3ArtifactError(f"SDL3 SDK package parent is not a directory: {relative}")
    return current


def verify_package_prefix(prefix: Path, version: str, target: dict[str, str],
                          source: dict[str, str]) -> None:
    expected_files = (
        "include/SDL3/SDL.h",
        "include/SDL3/SDL_version.h",
        "lib/cmake/SDL3/SDL3Config.cmake",
        "share/cdin/sdl3-sdk.json",
        "share/licenses/SDL3/LICENSE.txt",
    )
    required_paths = {
        relative: _safe_regular_file(prefix, relative)
        for relative in expected_files
    }
    target_os = "macos" if target["os"] == "darwin" else target["os"]
    expected_manifest = {
        "schema": "cdin.sdl3-sdk.v1",
        "version": version,
        "target": {
            "os": target_os,
            "architecture": target["architecture"],
            "abi": target["abi"],
        },
        "source": {"url": source["url"], "sha256": source["sha256"]},
        "linkage": "static",
        "cmake_package": "SDL3",
    }
    metadata = strict_json(required_paths["share/cdin/sdl3-sdk.json"].read_bytes(), "SDL3 SDK manifest")
    if metadata != expected_manifest:
        raise SDL3ArtifactError("SDL3 SDK manifest differs from the exact lock version/source/target/ABI")
    library_present = False
    for relative in ("lib/libSDL3.a", "lib/SDL3-static.lib"):
        try:
            _safe_regular_file(prefix, relative)
            library_present = True
        except SDL3ArtifactError as error:
            if "package is missing" not in str(error):
                raise
    if not library_present:
        raise SDL3ArtifactError("SDL3 SDK package has no target-native static library")
    for name in ("SDL3.dll", "libSDL3.so", "libSDL3.dylib"):
        relative = f"lib/{name}"
        candidate = prefix / relative
        if candidate.exists() or candidate.is_symlink():
            _safe_regular_file(prefix, relative)
            raise SDL3ArtifactError("SDL3 SDK package must not contain a shared SDL3 library")


def _stage_package(package: Path, prefix: Path) -> None:
    """Merge the verified SDK into a prefix without replacing different bytes."""
    _ensure_real_directory(prefix)
    files: list[Path] = []
    for top in ("include", "lib", "bin", "share"):
        root = package / top
        if not root.exists():
            continue
        if root.is_symlink() or not root.is_dir():
            raise SDL3ArtifactError(f"SDL3 package has an unsafe prefix entry: {top}")
        for current, directories, names in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            for name in directories:
                directory = current_path / name
                if directory.is_symlink() or not directory.is_dir():
                    raise SDL3ArtifactError("SDL3 package contains a symlink/special directory")
            for name in names:
                item = current_path / name
                info = item.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    raise SDL3ArtifactError("SDL3 package contains a symlink/special file")
                files.append(item)
    for source in files:
        relative = source.relative_to(package)
        destination = prefix / relative
        parent = destination.parent
        while parent != prefix:
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise SDL3ArtifactError(f"SDL3 SDK destination has an unsafe parent: {relative}")
            parent = parent.parent
        if destination.is_symlink():
            raise SDL3ArtifactError(f"SDL3 SDK destination is a symlink: {relative}")
        if destination.exists():
            if not destination.is_file() or destination.read_bytes() != source.read_bytes():
                raise SDL3ArtifactError(f"SDL3 SDK would overwrite different staged bytes: {relative}")
    for source in files:
        relative = source.relative_to(package)
        destination = prefix / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def install_sdl3_sdk(prefix: Path, target: dict[str, str], *, lock_path: Path = LOCK,
                     cache: Path = CACHE, offline: bool | None = None) -> Path:
    """Download, verify, safely extract and stage the exact immutable SDK."""
    key = target_key(target)
    try:
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise SDL3ArtifactError(f"cannot read SDL3 SDK lock: {error}") from error
    pin, asset, source = validate_pin(lock, key)
    if offline is None:
        offline = os.environ.get("CDIN_OFFLINE", "").strip().lower() in {"1", "true", "yes"}
    archive = download_asset(pin, asset, source, cache=cache, offline=offline)
    extraction_parent = cache / "packages"
    _ensure_real_directory(extraction_parent)
    install_id = f"{pin['version']}-{key}-{asset['sha256']}"
    package = extraction_parent / install_id
    if package.exists():
        info = package.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise SDL3ArtifactError("SDL3 SDK extracted cache entry is not a real directory")
        try:
            verify_package_prefix(package, pin["version"], target, source)
        except SDL3ArtifactError:
            if offline:
                raise SDL3ArtifactError("offline SDL3 SDK extracted cache is corrupt for the exact pin")
            shutil.rmtree(package)
    if not package.exists():
        with tempfile.TemporaryDirectory(prefix=".sdl3-extract-", dir=extraction_parent) as temporary:
            stage = Path(temporary)
            extracted = safe_extract(archive, stage)
            verify_package_prefix(extracted, pin["version"], target, source)
            os.replace(extracted, package)
    _stage_package(package, prefix)
    verify_package_prefix(prefix, pin["version"], target, source)
    return prefix


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=ROOT / ".deps" / "install")
    parser.add_argument("--target", choices=tuple(TARGETS))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        target_name = args.target or current_target_key()
        target_os, abi = TARGETS[target_name]
        architecture = target_name.rsplit("-", 1)[1]
        target = {"os": target_os, "architecture": architecture, "abi": abi}
        package = install_sdl3_sdk(args.prefix, target, offline=True if args.offline else None)
        print(f"Verified SDL3 SDK {target_name}: {package}", flush=True)
        return 0
    except SDL3ArtifactError as error:
        print(f"CDIN SDL3 SDK bootstrap failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
