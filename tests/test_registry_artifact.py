"""Tests for the pinned, artifact-first Registry executable bootstrap."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.registry_artifact import (
    REGISTRY_REPOSITORY_URI,
    RegistryBootstrapError,
    TARGETS,
    acquire_registry_artifact,
    detect_target,
    verify_binary_target,
)


def elf64(machine: int = 62) -> bytes:
    data = bytearray(64)
    data[:4] = b"\x7fELF"
    data[4] = 2
    data[5] = 1
    data[6] = 1
    data[18:20] = machine.to_bytes(2, "little")
    return bytes(data)


class FakeGitHubClient:
    def __init__(self, *, tag_commit: str | None = None, binary: bytes | None = None):
        self.tag_commit = tag_commit or "a" * 40
        self.binary = binary or elf64()
        self.downloads: dict[str, bytes] = {}
        self.release: dict = {}
        self.release_url = (
            "https://api.github.com/repos/cdin-editor/registry/releases/tags/v0.2.0-dev.1"
        )

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
                "source_commit": "a" * 40,
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
        self.downloads["https://github.com/cdin-editor/registry/releases/download/v0.2.0-dev.1/registry-release-0.2.0-dev.1.json"] = self.descriptor_bytes
        self.downloads["https://github.com/cdin-editor/registry/releases/download/v0.2.0-dev.1/catalog-index.json"] = self.catalog_bytes
        for asset_name, payload in binaries.items():
            self.downloads[
                f"https://github.com/cdin-editor/registry/releases/download/v0.2.0-dev.1/{asset_name}"
            ] = payload

        assets = []
        for name, payload in [
            ("registry-release-0.2.0-dev.1.json", self.descriptor_bytes),
            ("catalog-index.json", self.catalog_bytes),
            *binaries.items(),
        ]:
            assets.append({
                "id": len(assets) + 1,
                "name": name,
                "size": len(payload),
                "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
                "browser_download_url": (
                    "https://github.com/cdin-editor/registry/releases/download/v0.2.0-dev.1/"
                    + name
                ),
            })
        self.release = {
            "tag_name": "v0.2.0-dev.1",
            "draft": False,
            "prerelease": True,
            "assets": assets,
        }

    def get_json(self, url: str) -> dict:
        if url == self.release_url:
            return self.release
        if url.endswith("/git/ref/tags/v0.2.0-dev.1"):
            return {"object": {"type": "commit", "sha": self.tag_commit}}
        raise AssertionError(f"unexpected API request: {url}")

    def download(self, url: str, *, maximum: int) -> bytes:
        payload = self.downloads[url]
        if len(payload) > maximum:
            raise AssertionError("fixture exceeds requested maximum")
        return payload


class RegistryArtifactBootstrapTests(unittest.TestCase):
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

    def test_downloads_only_after_tag_and_descriptor_identity_verification(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as temporary:
            binary, catalog = acquire_registry_artifact(
                self._pin(client),
                cache_root=Path(temporary) / "cache",
                target=("linux", "amd64"),
                client=client,
            )
            self.assertEqual(binary.read_bytes(), client.binary)
            self.assertEqual(catalog.read_bytes(), client.catalog_bytes)
            if os.name != "nt":
                self.assertTrue(binary.stat().st_mode & 0o100)

    def test_uses_only_verified_exact_pin_cache_when_offline(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache"
            first_binary, first_catalog = acquire_registry_artifact(
                self._pin(client), cache_root=cache, target=("linux", "amd64"), client=client
            )

            class NoNetwork:
                def get_json(self, _url: str) -> dict:
                    raise AssertionError("offline cache lookup unexpectedly used the network")

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
            cache = Path(temporary) / "cache"
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
            root = Path(temporary)
            real = root / "real-cache"
            real.mkdir()
            linked = root / "linked-cache"
            linked.symlink_to(real, target_is_directory=True)

            class NoNetwork:
                def get_json(self, _url: str) -> dict:
                    raise AssertionError("unsafe cache path reached network")

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
            cache = Path(temporary) / "cache"
            binary, _catalog = acquire_registry_artifact(
                self._pin(client),
                cache_root=cache,
                target=("linux", "amd64"),
                client=client,
            )
            binary.chmod(0o644)

            class NoNetwork:
                def get_json(self, _url: str) -> dict:
                    raise AssertionError("offline cache verification must not fetch release metadata")

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

    def test_rejects_moved_tag_before_downloading_assets(self) -> None:
        client = FakeGitHubClient(tag_commit="b" * 40)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RegistryBootstrapError, "tag moved or mismatched"):
                acquire_registry_artifact(
                    self._pin(client),
                    cache_root=Path(temporary) / "cache",
                    target=("linux", "amd64"),
                    client=client,
                )

    def test_resolves_annotated_tag_objects(self) -> None:
        client = FakeGitHubClient()

        class AnnotatedTagClient(FakeGitHubClient):
            def get_json(self, url: str) -> dict:
                if url.endswith("/git/ref/tags/v0.2.0-dev.1"):
                    return {"object": {"type": "tag", "sha": "b" * 40}}
                if url.endswith("/git/tags/" + "b" * 40):
                    return {
                        "sha": "b" * 40,
                        "object": {"type": "commit", "sha": "a" * 40},
                    }
                return super().get_json(url)

        with tempfile.TemporaryDirectory() as temporary:
            binary, catalog = acquire_registry_artifact(
                self._pin(client),
                cache_root=Path(temporary) / "cache",
                target=("linux", "amd64"),
                client=AnnotatedTagClient(),
            )
            self.assertTrue(binary.is_file())
            self.assertTrue(catalog.is_file())


if __name__ == "__main__":
    unittest.main()
