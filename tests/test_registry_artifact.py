"""Tests for the pinned, artifact-first Registry executable bootstrap."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest

from scripts.registry_artifact import (
    REGISTRY_REPOSITORY_URI,
    RegistryBootstrapError,
    TARGETS,
    _public_release_asset_url,
    acquire_registry_artifact,
    detect_target,
    verify_binary_target,
    _validate_pin,
)


def elf64(machine: int = 62) -> bytes:
    data = bytearray(64)
    data[:4] = b"\x7fELF"
    data[4] = 2
    data[5] = 1
    data[6] = 1
    data[18:20] = machine.to_bytes(2, "little")
    return bytes(data)




class RegistryPublicReleaseURLTests(unittest.TestCase):
    def test_builds_canonical_public_release_asset_urls(self) -> None:
        self.assertEqual(
            _public_release_asset_url("v1.0.1", "registry-release-1.0.1.json"),
            "https://github.com/cdin-editor/registry/releases/download/"
            "v1.0.1/registry-release-1.0.1.json",
        )
        self.assertEqual(
            _public_release_asset_url("v1.0.1", "registry-linux-amd64"),
            "https://github.com/cdin-editor/registry/releases/download/"
            "v1.0.1/registry-linux-amd64",
        )

    def test_rejects_unknown_asset_names_and_invalid_tags(self) -> None:
        with self.assertRaisesRegex(RegistryBootstrapError, "untrusted Registry Release asset name"):
            _public_release_asset_url("v1.0.1", "../registry-linux-amd64")
        with self.assertRaisesRegex(RegistryBootstrapError, "invalid pinned Registry release tag"):
            _public_release_asset_url("latest", "registry-linux-amd64")

    def test_bootstrap_has_no_github_rest_api_or_api_token_dependency(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "scripts" / "registry_artifact.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("api.github.com", source)
        self.assertNotIn("REGISTRY_GITHUB_API_TOKEN", source)
        self.assertNotIn("CDIN_GITHUB_API_TOKEN", source)


class FakeGitHubClient:
    def __init__(
        self,
        *,
        binary: bytes | None = None,
        source_commit: str = "a" * 40,
    ):
        self.binary = binary or elf64()
        self.source_commit = source_commit
        self.downloads: dict[str, bytes] = {}
        self.calls: list[str] = []

        catalog = {
            "schema_version": "1.0.0",
            "catalog_id": "cdin-components",
            "entries": [{"component_id": "runtime", "variant": "default", "version": "1.0.0-rc.3"}],
        }
        self.catalog_bytes = json.dumps(catalog, sort_keys=True).encode("utf-8")
        binaries: dict[str, bytes] = {}
        for target_id, (asset_name, _target) in TARGETS.items():
            binaries[asset_name] = (
                self.binary if target_id == "linux-amd64" else f"fixture:{target_id}".encode()
            )
        executables = []
        for target_id, (asset_name, target) in TARGETS.items():
            payload = binaries[asset_name]
            executables.append({
                "asset_name": asset_name,
                "target_id": target_id,
                "target": target,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            })
        descriptor = {
            "schema_version": "1.0.0",
            "registry": {
                "repository_uri": REGISTRY_REPOSITORY_URI,
                "version": "0.2.0-dev.1",
                "tag": "v0.2.0-dev.1",
                "source_commit": self.source_commit,
            },
            "catalog": {
                "asset_name": "catalog-index.json",
                "catalog_id": "cdin-components",
                "schema_version": "1.0.0",
                "size": len(self.catalog_bytes),
                "sha256": hashlib.sha256(self.catalog_bytes).hexdigest(),
            },
            "executables": executables,
        }
        self.descriptor_bytes = json.dumps(descriptor, sort_keys=True).encode("utf-8")
        self.downloads[
            _public_release_asset_url("v0.2.0-dev.1", "registry-release-0.2.0-dev.1.json")
        ] = self.descriptor_bytes
        self.downloads[
            _public_release_asset_url("v0.2.0-dev.1", "catalog-index.json")
        ] = self.catalog_bytes
        for asset_name, payload in binaries.items():
            self.downloads[_public_release_asset_url("v0.2.0-dev.1", asset_name)] = payload

    def download(self, url: str, *, maximum: int) -> bytes:
        self.calls.append(url)
        payload = self.downloads[url]
        if len(payload) > maximum:
            raise AssertionError("fixture exceeds requested maximum")
        return payload


class RegistryArtifactBootstrapTests(unittest.TestCase):
    def test_committed_registry_pin_matches_the_published_immutable_release(self) -> None:
        lock_path = Path(__file__).resolve().parents[1] / "deps.lock"
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        pin = lock["tooling"]["registry"]
        revision, version, tag, descriptor_sha, descriptor_size = _validate_pin(pin)
        self.assertEqual(revision, "ed7c8fbe5513b6b0d6eb76d31191c696b98f8d27")
        self.assertEqual(version, "1.0.1")
        self.assertEqual(tag, "v1.0.1")
        self.assertEqual(
            descriptor_sha,
            "c37a1902afe6d41291b0f29d6970408d70dae239881307533673ceaf85634403",
        )
        self.assertEqual(descriptor_size, 1633)

    def _pin(self, client: FakeGitHubClient) -> dict:
        return {
            "repository": "https://github.com/cdin-editor/registry.git",
            "revision": "a" * 40,
            "version": "0.2.0-dev.1",
            "release_tag": "v0.2.0-dev.1",
            "release_descriptor_sha256": hashlib.sha256(client.descriptor_bytes).hexdigest(),
            "release_descriptor_size": len(client.descriptor_bytes),
        }

    def test_detects_supported_targets_and_requires_ucrt64(self) -> None:
        self.assertEqual(
            detect_target(system="Linux", machine="x86_64"),
            ("linux-amd64", "linux", "amd64"),
        )
        self.assertEqual(
            detect_target(system="Darwin", machine="arm64"),
            ("darwin-arm64", "darwin", "arm64"),
        )
        self.assertEqual(
            detect_target(system="Windows", machine="AMD64", msystem="UCRT64"),
            ("windows-amd64", "windows", "amd64"),
        )
        with self.assertRaisesRegex(RegistryBootstrapError, "UCRT64"):
            detect_target(system="Windows", machine="AMD64", msystem="MINGW64")

    def test_rejects_wrong_native_executable_architecture(self) -> None:
        with self.assertRaisesRegex(RegistryBootstrapError, "machine mismatch"):
            verify_binary_target(elf64(183), os_name="linux", architecture="amd64")

    def test_downloads_public_assets_after_descriptor_identity_verification(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as temporary:
            binary, catalog = acquire_registry_artifact(
                self._pin(client),
                cache_root=Path(temporary).resolve() / "cache",
                target=("linux", "amd64"),
                client=client,
            )
            self.assertEqual(binary.read_bytes(), client.binary)
            self.assertEqual(catalog.read_bytes(), client.catalog_bytes)
            self.assertEqual(
                client.calls,
                [
                    _public_release_asset_url("v0.2.0-dev.1", "registry-release-0.2.0-dev.1.json"),
                    _public_release_asset_url("v0.2.0-dev.1", "catalog-index.json"),
                    _public_release_asset_url("v0.2.0-dev.1", "registry-linux-amd64"),
                ],
            )
            if os.name != "nt":
                self.assertTrue(binary.stat().st_mode & 0o100)

    def test_uses_only_verified_exact_pin_cache_when_offline(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary).resolve() / "cache"
            first_binary, first_catalog = acquire_registry_artifact(
                self._pin(client), cache_root=cache, target=("linux", "amd64"), client=client
            )

            class NoNetwork:
                def download(self, _url: str, *, maximum: int) -> bytes:
                    raise AssertionError("offline cache lookup unexpectedly downloaded an asset")

            second_binary, second_catalog = acquire_registry_artifact(
                self._pin(client),
                cache_root=cache,
                target=("linux", "amd64"),
                client=NoNetwork(),
                offline=True,
            )
            self.assertEqual(first_binary, second_binary)
            self.assertEqual(first_catalog, second_catalog)

    def test_rejects_corrupt_cache_in_offline_mode(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary).resolve() / "cache"
            binary, _catalog = acquire_registry_artifact(
                self._pin(client), cache_root=cache, target=("linux", "amd64"), client=client
            )
            binary.write_bytes(b"corrupt")
            with self.assertRaisesRegex(RegistryBootstrapError, "cache is missing or corrupt"):
                acquire_registry_artifact(
                    self._pin(client),
                    cache_root=cache,
                    target=("linux", "amd64"),
                    client=client,
                    offline=True,
                )


    @unittest.skipIf(os.name == "nt", "POSIX cache symlinks require Unix filesystem semantics")
    def test_rejects_symlinked_cache_ancestor_before_network(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            real = root / "real-cache"
            real.mkdir()
            linked = root / "linked-cache"
            linked.symlink_to(real, target_is_directory=True)

            class NoNetwork:
                def download(self, _url: str, *, maximum: int) -> bytes:
                    raise AssertionError("unsafe cache path reached asset download")

            with self.assertRaisesRegex(RegistryBootstrapError, "symlink or non-directory ancestor"):
                acquire_registry_artifact(
                    self._pin(client),
                    cache_root=linked / "registry",
                    target=("linux", "amd64"),
                    client=NoNetwork(),
                )

    @unittest.skipIf(os.name == "nt", "POSIX executable mode bits are not portable to Windows")
    def test_rejects_cached_binary_without_executable_permission(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary).resolve() / "cache"
            binary, _catalog = acquire_registry_artifact(
                self._pin(client),
                cache_root=cache,
                target=("linux", "amd64"),
                client=client,
            )
            binary.chmod(0o644)

            class NoNetwork:
                def download(self, _url: str, *, maximum: int) -> bytes:
                    raise AssertionError("offline cache verification must not download assets")

            with self.assertRaisesRegex(
                RegistryBootstrapError, "offline Registry cache is missing or corrupt"
            ):
                acquire_registry_artifact(
                    self._pin(client),
                    cache_root=cache,
                    target=("linux", "amd64"),
                    client=NoNetwork(),
                    offline=True,
                )

    def test_rejects_descriptor_with_a_source_commit_outside_the_lock(self) -> None:
        client = FakeGitHubClient(source_commit="b" * 40)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                RegistryBootstrapError,
                "Registry release descriptor identity differs from deps.lock",
            ):
                acquire_registry_artifact(
                    self._pin(client),
                    cache_root=Path(temporary).resolve() / "cache",
                    target=("linux", "amd64"),
                    client=client,
                )
        self.assertEqual(
            client.calls,
            [_public_release_asset_url("v0.2.0-dev.1", "registry-release-0.2.0-dev.1.json")],
        )


if __name__ == "__main__":
    unittest.main()
