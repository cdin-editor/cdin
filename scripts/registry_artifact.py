#!/usr/bin/env python3
"""Acquire the immutable, target-specific Registry executable and Catalog release."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import tempfile
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

REGISTRY_REPOSITORY_URI = "https://github.com/cdin-editor/registry"
REGISTRY_API = "https://api.github.com/repos/cdin-editor/registry"
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_BINARY_BYTES = 128 * 1024 * 1024
MAX_TAG_DEPTH = 8
VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

TARGETS: dict[str, tuple[str, str]] = {
    "linux-amd64": ("registry-linux-amd64", "linux/amd64"),
    "linux-arm64": ("registry-linux-arm64", "linux/arm64"),
    "darwin-amd64": ("registry-darwin-amd64", "darwin/amd64"),
    "darwin-arm64": ("registry-darwin-arm64", "darwin/arm64"),
    "windows-amd64": ("registry-windows-amd64.exe", "windows/amd64"),
}


class RegistryBootstrapError(RuntimeError):
    """Raised when an immutable Registry release cannot be safely acquired."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryBootstrapError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _strict_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryBootstrapError(f"{label} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise RegistryBootstrapError(f"{label} root must be a JSON object")
    return value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise RegistryBootstrapError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_size(value: Any, label: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > maximum:
        raise RegistryBootstrapError(f"{label} must be a positive size no greater than {maximum}")
    return value


class _TrustedAssetRedirectHandler(urllib.request.HTTPRedirectHandler):
    allowed_hosts = {"github.com", "release-assets.githubusercontent.com"}

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        parsed = urllib.parse.urlparse(new_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self.allowed_hosts
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise RegistryBootstrapError(f"untrusted Registry asset redirect: {new_url!r}")
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


class GitHubReleaseClient:
    """Small bounded GitHub client; no shell, Git executable or Go toolchain is used."""

    def get_json(self, url: str) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.github.com"
            or not parsed.path.startswith("/repos/cdin-editor/registry/")
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise RegistryBootstrapError(f"untrusted Registry API URL: {url!r}")
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "cdin-registry-bootstrap/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 200:
                    raise RegistryBootstrapError(
                        f"GitHub Registry API returned HTTP {response.status}"
                    )
                data = response.read(MAX_JSON_BYTES + 1)
        except (OSError, urllib.error.URLError) as error:
            raise RegistryBootstrapError(f"cannot read Registry release API: {error}") from error
        if len(data) > MAX_JSON_BYTES:
            raise RegistryBootstrapError("Registry API JSON exceeds the 8 MiB limit")
        return _strict_json(data, "Registry API response")

    def download(self, url: str, *, maximum: int) -> bytes:
        parsed = urllib.parse.urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise RegistryBootstrapError(f"untrusted Registry asset URL: {url!r}")
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": "cdin-registry-bootstrap/1",
            },
        )
        opener = urllib.request.build_opener(_TrustedAssetRedirectHandler())
        try:
            with opener.open(request, timeout=60) as response:
                final_url = urllib.parse.urlparse(response.geturl())
                if (
                    response.status != 200
                    or final_url.scheme != "https"
                    or final_url.hostname not in _TrustedAssetRedirectHandler.allowed_hosts
                ):
                    raise RegistryBootstrapError("Registry asset download ended at an untrusted URL")
                length = response.headers.get("Content-Length")
                if length is not None:
                    try:
                        declared_length = int(length)
                    except ValueError as error:
                        raise RegistryBootstrapError("Registry asset has an invalid Content-Length") from error
                    if declared_length < 0 or declared_length > maximum:
                        raise RegistryBootstrapError("Registry asset exceeds its size limit")
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(min(1024 * 1024, maximum + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > maximum:
                        raise RegistryBootstrapError("Registry asset exceeds its size limit")
                    chunks.append(chunk)
        except (OSError, urllib.error.URLError) as error:
            raise RegistryBootstrapError(f"cannot download Registry asset: {error}") from error
        return b"".join(chunks)


def detect_target(
    *,
    system: str | None = None,
    machine: str | None = None,
    msystem: str | None = None,
) -> tuple[str, str, str]:
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    os_name = {"linux": "linux", "darwin": "darwin", "windows": "windows"}.get(system)
    architecture = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine)
    if os_name is None or architecture is None:
        raise RegistryBootstrapError(f"unsupported Registry target: {system}/{machine}")
    if os_name == "windows" and (architecture != "amd64" or (msystem or os.environ.get("MSYSTEM")) != "UCRT64"):
        raise RegistryBootstrapError("Registry Windows executable requires x86_64 MSYS2 UCRT64")
    if os_name == "darwin":
        os_name = "darwin"
    target_id = f"{os_name}-{architecture}"
    if target_id not in TARGETS:
        raise RegistryBootstrapError(f"unsupported Registry target: {target_id}")
    return target_id, os_name, architecture


def verify_binary_target(data: bytes, *, os_name: str, architecture: str) -> None:
    """Inspect the executable header; never trust the uploaded asset's filename."""
    if os_name == "linux":
        if len(data) < 20 or data[:4] != b"\x7fELF":
            raise RegistryBootstrapError("Registry Linux asset is not an ELF executable")
        if data[4] != 2 or data[5] not in (1, 2):
            raise RegistryBootstrapError("Registry Linux executable is not a supported 64-bit ELF")
        endian = "little" if data[5] == 1 else "big"
        machine = int.from_bytes(data[18:20], endian)
        expected = {"amd64": 62, "arm64": 183}.get(architecture)
        if expected is None or machine != expected:
            raise RegistryBootstrapError(
                f"Registry ELF machine mismatch: expected {architecture}, found e_machine={machine}"
            )
        return

    if os_name == "darwin":
        if len(data) < 8:
            raise RegistryBootstrapError("Registry macOS asset is too short to contain a Mach-O header")
        if data[:4] == b"\xcf\xfa\xed\xfe":
            endian = "little"
        elif data[:4] == b"\xfe\xed\xfa\xcf":
            endian = "big"
        else:
            raise RegistryBootstrapError("Registry macOS asset is not a 64-bit Mach-O executable")
        cpu_type = int.from_bytes(data[4:8], endian)
        expected = {"amd64": 0x01000007, "arm64": 0x0100000C}.get(architecture)
        if expected is None or cpu_type != expected:
            raise RegistryBootstrapError(
                f"Registry Mach-O CPU mismatch: expected {architecture}, found cpu_type={cpu_type:#x}"
            )
        return

    if os_name == "windows":
        if len(data) < 64 or data[:2] != b"MZ":
            raise RegistryBootstrapError("Registry Windows asset is not a PE executable")
        pe_offset = int.from_bytes(data[0x3C:0x40], "little")
        if pe_offset < 64 or pe_offset + 6 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\x00\x00":
            raise RegistryBootstrapError("Registry Windows executable has an invalid PE header")
        machine = int.from_bytes(data[pe_offset + 4:pe_offset + 6], "little")
        if architecture != "amd64" or machine != 0x8664:
            raise RegistryBootstrapError(
                f"Registry PE machine mismatch: expected x86_64, found machine={machine:#x}"
            )
        return

    raise RegistryBootstrapError(f"unsupported Registry binary format for {os_name}/{architecture}")


def _validate_pin(pin: dict[str, Any]) -> tuple[str, str, str, str, int]:
    repository = pin.get("repository")
    revision = pin.get("revision")
    version = pin.get("version")
    tag = pin.get("release_tag")
    descriptor_sha = _require_sha(
        pin.get("release_descriptor_sha256"), "Registry release descriptor digest"
    )
    descriptor_size = _require_size(
        pin.get("release_descriptor_size"),
        "Registry release descriptor size",
        maximum=MAX_JSON_BYTES,
    )
    if not isinstance(repository, str):
        raise RegistryBootstrapError("deps.lock is missing tooling.registry.repository")
    normalized_repository = repository.removesuffix(".git").rstrip("/")
    if normalized_repository != REGISTRY_REPOSITORY_URI:
        raise RegistryBootstrapError("deps.lock Registry repository does not match the expected owner")
    if not isinstance(revision, str) or GIT_SHA_RE.fullmatch(revision) is None:
        raise RegistryBootstrapError("deps.lock Registry revision must be a full lowercase commit SHA")
    if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
        raise RegistryBootstrapError("deps.lock Registry version is not valid SemVer")
    if not isinstance(tag, str) or tag != f"v{version}":
        raise RegistryBootstrapError("deps.lock Registry release_tag must equal v plus the pinned version")
    return revision, version, tag, descriptor_sha, descriptor_size


def _resolve_tag_commit(client: Any, tag: str) -> str:
    encoded_tag = urllib.parse.quote(tag, safe="")
    url = f"{REGISTRY_API}/git/ref/tags/{encoded_tag}"
    reference = client.get_json(url)
    obj = reference.get("object")
    visited: set[str] = set()
    for _ in range(MAX_TAG_DEPTH):
        if not isinstance(obj, dict):
            raise RegistryBootstrapError("Registry tag reference has no Git object")
        object_type = obj.get("type")
        object_sha = obj.get("sha")
        if not isinstance(object_sha, str) or GIT_SHA_RE.fullmatch(object_sha) is None:
            raise RegistryBootstrapError("Registry tag reference has an invalid Git object SHA")
        if object_sha in visited:
            raise RegistryBootstrapError("Registry tag object contains a cycle")
        visited.add(object_sha)
        if object_type == "commit":
            return object_sha
        if object_type != "tag":
            raise RegistryBootstrapError(f"Registry tag resolves to unsupported Git object type: {object_type!r}")
        tag_object = client.get_json(f"{REGISTRY_API}/git/tags/{object_sha}")
        if tag_object.get("sha") != object_sha:
            raise RegistryBootstrapError("Registry annotated tag object SHA mismatch")
        obj = tag_object.get("object")
    raise RegistryBootstrapError("Registry annotated tag nesting exceeds the safety limit")


def _asset_index(release: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_assets = release.get("assets")
    if not isinstance(raw_assets, list):
        raise RegistryBootstrapError("Registry release has no asset inventory")
    result: dict[str, dict[str, Any]] = {}
    for asset in raw_assets:
        if not isinstance(asset, dict):
            raise RegistryBootstrapError("Registry release contains a malformed asset record")
        name = asset.get("name")
        if not isinstance(name, str) or not name:
            raise RegistryBootstrapError("Registry release contains an asset with no name")
        if name in result:
            raise RegistryBootstrapError(f"Registry release contains duplicate asset {name!r}")
        result[name] = asset
    return result


def _api_asset_identity(asset: dict[str, Any], *, name: str, sha256: str, size: int) -> str:
    if asset.get("name") != name:
        raise RegistryBootstrapError(f"Registry release is missing asset {name!r}")
    api_digest = asset.get("digest")
    if not isinstance(api_digest, str) or not api_digest.startswith("sha256:"):
        raise RegistryBootstrapError(f"Registry release asset {name!r} has no GitHub SHA-256 digest")
    if api_digest.removeprefix("sha256:") != sha256:
        raise RegistryBootstrapError(f"Registry GitHub asset digest does not match the release descriptor: {name}")
    if asset.get("size") != size:
        raise RegistryBootstrapError(f"Registry GitHub asset size does not match the release descriptor: {name}")
    url = asset.get("browser_download_url")
    parsed = urllib.parse.urlparse(url) if isinstance(url, str) else None
    if (
        parsed is None
        or parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise RegistryBootstrapError(f"Registry release asset {name!r} has an untrusted download URL")
    return url


def _validate_descriptor(
    descriptor: dict[str, Any],
    *,
    revision: str,
    version: str,
    tag: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if descriptor.get("schema_version") != "1.0.0":
        raise RegistryBootstrapError("unsupported Registry release descriptor schema version")
    registry = descriptor.get("registry")
    if not isinstance(registry, dict) or registry != {
        "repository_uri": REGISTRY_REPOSITORY_URI,
        "version": version,
        "tag": tag,
        "source_commit": revision,
    }:
        raise RegistryBootstrapError("Registry release descriptor identity differs from deps.lock")
    catalog = descriptor.get("catalog")
    if not isinstance(catalog, dict) or catalog.get("asset_name") != "catalog-index.json":
        raise RegistryBootstrapError("Registry release descriptor has an invalid Catalog identity")
    catalog_sha = _require_sha(catalog.get("sha256"), "Registry Catalog digest")
    catalog_size = _require_size(
        catalog.get("size"), "Registry Catalog size", maximum=MAX_JSON_BYTES
    )
    catalog_id = catalog.get("catalog_id")
    catalog_schema = catalog.get("schema_version")
    if not isinstance(catalog_id, str) or not catalog_id:
        raise RegistryBootstrapError("Registry release descriptor has no Catalog ID")
    if not isinstance(catalog_schema, str) or not catalog_schema:
        raise RegistryBootstrapError("Registry release descriptor has no Catalog schema version")

    raw_executables = descriptor.get("executables")
    if not isinstance(raw_executables, list) or len(raw_executables) != len(TARGETS):
        raise RegistryBootstrapError("Registry release descriptor must contain exactly five target executables")
    executables: dict[str, dict[str, Any]] = {}
    for item in raw_executables:
        if not isinstance(item, dict):
            raise RegistryBootstrapError("Registry release descriptor contains a malformed executable record")
        target_id = item.get("target_id")
        if not isinstance(target_id, str) or target_id not in TARGETS or target_id in executables:
            raise RegistryBootstrapError(f"Registry release descriptor has an unknown/duplicate target: {target_id!r}")
        expected_name, expected_target = TARGETS[target_id]
        if item.get("asset_name") != expected_name or item.get("target") != expected_target:
            raise RegistryBootstrapError(f"Registry executable target/filename mismatch: {target_id}")
        digest = _require_sha(item.get("sha256"), f"Registry executable {target_id} digest")
        size = _require_size(
            item.get("size"), f"Registry executable {target_id} size", maximum=MAX_BINARY_BYTES
        )
        executables[target_id] = {
            "asset_name": expected_name,
            "target": expected_target,
            "sha256": digest,
            "size": size,
        }
    if set(executables) != set(TARGETS):
        raise RegistryBootstrapError("Registry release descriptor does not cover all five supported targets")
    catalog_record = {
        "asset_name": "catalog-index.json",
        "catalog_id": catalog_id,
        "schema_version": catalog_schema,
        "sha256": catalog_sha,
        "size": catalog_size,
    }
    return catalog_record, executables


def _validate_catalog(data: bytes, record: dict[str, Any]) -> None:
    catalog = _strict_json(data, "Registry Catalog Index")
    if (
        catalog.get("catalog_id") != record["catalog_id"]
        or catalog.get("schema_version") != record["schema_version"]
    ):
        raise RegistryBootstrapError("Registry Catalog does not match the release descriptor")
    has_entries = "entries" in catalog
    has_sources = "release_sources" in catalog
    if has_entries == has_sources:
        raise RegistryBootstrapError("Registry Catalog must use exactly one model: entries or release_sources")
    collection = catalog.get("entries") if has_entries else catalog.get("release_sources")
    if not isinstance(collection, list) or not collection:
        raise RegistryBootstrapError("Registry Catalog selected model must be a non-empty array")


def _verify_bytes(data: bytes, *, name: str, sha256: str, size: int) -> None:
    if len(data) != size:
        raise RegistryBootstrapError(
            f"Registry asset size mismatch for {name}: expected {size}, got {len(data)}"
        )
    actual = _sha256(data)
    if actual != sha256:
        raise RegistryBootstrapError(
            f"Registry asset SHA-256 mismatch for {name}: expected {sha256}, got {actual}"
        )


def _cache_paths(
    root: Path,
    *,
    version: str,
    target_id: str,
    descriptor_sha: str,
    executable_name: str,
) -> tuple[Path, Path, Path, Path]:
    destination = root / version / target_id / descriptor_sha
    return (
        destination,
        destination / "registry-release.json",
        destination / "catalog-index.json",
        destination / executable_name,
    )


def _verify_cached(
    paths: tuple[Path, Path, Path, Path],
    *,
    pin: tuple[str, str, str, str, int],
    target_id: str,
    executable_name: str,
    os_name: str,
    architecture: str,
) -> tuple[Path, Path]:
    destination, descriptor_path, catalog_path, binary_path = paths
    revision, version, tag, descriptor_sha, descriptor_size = pin
    if not all(path.is_file() and not path.is_symlink() for path in (descriptor_path, catalog_path, binary_path)):
        raise RegistryBootstrapError("Registry cache is incomplete")
    descriptor_bytes = descriptor_path.read_bytes()
    _verify_bytes(
        descriptor_bytes,
        name=descriptor_path.name,
        sha256=descriptor_sha,
        size=descriptor_size,
    )
    descriptor = _strict_json(descriptor_bytes, "cached Registry release descriptor")
    catalog_record, executables = _validate_descriptor(
        descriptor,
        revision=revision,
        version=version,
        tag=tag,
    )
    catalog_bytes = catalog_path.read_bytes()
    _verify_bytes(
        catalog_bytes,
        name=catalog_path.name,
        sha256=catalog_record["sha256"],
        size=catalog_record["size"],
    )
    _validate_catalog(catalog_bytes, catalog_record)
    executable = executables[target_id]
    binary_bytes = binary_path.read_bytes()
    _verify_bytes(
        binary_bytes,
        name=executable_name,
        sha256=executable["sha256"],
        size=executable["size"],
    )
    verify_binary_target(binary_bytes, os_name=os_name, architecture=architecture)
    return binary_path, catalog_path


def acquire_registry_artifact(
    pin: dict[str, Any],
    *,
    cache_root: Path,
    target: tuple[str, str] | None = None,
    client: Any | None = None,
    offline: bool = False,
) -> tuple[Path, Path]:
    """Return a verified Registry executable and its Catalog from one immutable release."""
    revision, version, tag, descriptor_sha, descriptor_size = _validate_pin(pin)
    if target is None:
        target_id, os_name, architecture = detect_target()
    else:
        if len(target) != 2:
            raise RegistryBootstrapError("explicit Registry target must contain OS and architecture")
        os_name, architecture = target
        target_id = f"{os_name}-{architecture}"
        if target_id not in TARGETS:
            raise RegistryBootstrapError(f"unsupported explicit Registry target: {target_id}")
    executable_name = TARGETS[target_id][0]
    cache_paths = _cache_paths(
        cache_root,
        version=version,
        target_id=target_id,
        descriptor_sha=descriptor_sha,
        executable_name=executable_name,
    )
    destination = cache_paths[0]
    if destination.exists():
        try:
            return _verify_cached(
                cache_paths,
                pin=(revision, version, tag, descriptor_sha, descriptor_size),
                target_id=target_id,
                executable_name=executable_name,
                os_name=os_name,
                architecture=architecture,
            )
        except (OSError, RegistryBootstrapError):
            if offline:
                raise RegistryBootstrapError(
                    "offline Registry cache is missing or corrupt for this exact release identity"
                )
            if destination.is_symlink():
                raise RegistryBootstrapError("Registry cache destination must not be a symlink")
            shutil.rmtree(destination)

    if offline:
        raise RegistryBootstrapError(
            "offline Registry installation requires a previously verified cache for this exact pin and target"
        )
    client = client or GitHubReleaseClient()
    release = client.get_json(f"{REGISTRY_API}/releases/tags/{urllib.parse.quote(tag, safe='')}")
    if release.get("tag_name") != tag or release.get("draft") is True:
        raise RegistryBootstrapError("GitHub Registry Release tag is missing, draft or mismatched")
    if release.get("prerelease") is not ("-" in version):
        raise RegistryBootstrapError("GitHub Registry Release prerelease flag differs from its SemVer")
    resolved_commit = _resolve_tag_commit(client, tag)
    if resolved_commit != revision:
        raise RegistryBootstrapError(
            f"Registry release tag moved or mismatched: expected {revision}, found {resolved_commit}"
        )

    assets = _asset_index(release)
    descriptor_name = f"registry-release-{version}.json"
    descriptor_asset = assets.get(descriptor_name)
    if descriptor_asset is None:
        raise RegistryBootstrapError(f"Registry release is missing {descriptor_name}")
    descriptor_url = _api_asset_identity(
        descriptor_asset,
        name=descriptor_name,
        sha256=descriptor_sha,
        size=descriptor_size,
    )
    descriptor_bytes = client.download(descriptor_url, maximum=MAX_JSON_BYTES)
    _verify_bytes(
        descriptor_bytes,
        name=descriptor_name,
        sha256=descriptor_sha,
        size=descriptor_size,
    )
    descriptor = _strict_json(descriptor_bytes, "Registry release descriptor")
    catalog_record, executables = _validate_descriptor(
        descriptor,
        revision=revision,
        version=version,
        tag=tag,
    )

    expected_assets = {
        "catalog-index.json": (catalog_record["sha256"], catalog_record["size"]),
    }
    expected_assets.update({
        item["asset_name"]: (item["sha256"], item["size"])
        for item in executables.values()
    })
    asset_urls: dict[str, str] = {}
    for name, (digest, size) in expected_assets.items():
        asset = assets.get(name)
        if asset is None:
            raise RegistryBootstrapError(f"Registry release is missing required asset {name!r}")
        asset_urls[name] = _api_asset_identity(
            asset,
            name=name,
            sha256=digest,
            size=size,
        )

    catalog_bytes = client.download(asset_urls["catalog-index.json"], maximum=MAX_JSON_BYTES)
    _verify_bytes(
        catalog_bytes,
        name="catalog-index.json",
        sha256=catalog_record["sha256"],
        size=catalog_record["size"],
    )
    _validate_catalog(catalog_bytes, catalog_record)

    executable = executables[target_id]
    binary_bytes = client.download(
        asset_urls[executable_name],
        maximum=MAX_BINARY_BYTES,
    )
    _verify_bytes(
        binary_bytes,
        name=executable_name,
        sha256=executable["sha256"],
        size=executable["size"],
    )
    verify_binary_target(binary_bytes, os_name=os_name, architecture=architecture)

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or cache_root.is_symlink():
        raise RegistryBootstrapError("Registry cache root must not contain a symlink at its root")
    staging = Path(tempfile.mkdtemp(prefix=".registry-stage-", dir=parent))
    try:
        descriptor_path = staging / "registry-release.json"
        catalog_path = staging / "catalog-index.json"
        binary_path = staging / executable_name
        descriptor_path.write_bytes(descriptor_bytes)
        catalog_path.write_bytes(catalog_bytes)
        binary_path.write_bytes(binary_bytes)
        if os_name != "windows":
            binary_path.chmod(0o755)
        staged_paths = (staging, descriptor_path, catalog_path, binary_path)
        _verify_cached(
            staged_paths,
            pin=(revision, version, tag, descriptor_sha, descriptor_size),
            target_id=target_id,
            executable_name=executable_name,
            os_name=os_name,
            architecture=architecture,
        )
        if destination.exists():
            if destination.is_symlink():
                raise RegistryBootstrapError("Registry cache destination must not be a symlink")
            shutil.rmtree(destination)
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return (
        destination / executable_name,
        destination / "catalog-index.json",
    )
