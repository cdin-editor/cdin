"""Tests for immutable SDL3 SDK pinning, verification and offline installation."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import sdl3_artifact as sdk


SOURCE_URL = (
    "https://github.com/libsdl-org/SDL/releases/download/"
    "release-3.4.16/SDL3-3.4.16.tar.gz"
)
SOURCE_SHA = "a" * 64
REVISION = "b" * 40
TARGET = {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.39"}


def package_files(target: dict[str, str] = TARGET) -> dict[str, bytes]:
    manifest = {
        "schema": "cdin.sdl3-sdk.v1",
        "version": "3.4.16",
        "target": target,
        "source": {"url": SOURCE_URL, "sha256": SOURCE_SHA},
        "linkage": "static",
        "cmake_package": "SDL3",
    }
    return {
        "include/SDL3/SDL.h": b"/* SDL3 fixture */\n",
        "include/SDL3/SDL_version.h": b"#define SDL3_VERSION 30416\n",
        "lib/libSDL3.a": b"static SDL3 fixture\n",
        "lib/cmake/SDL3/SDL3Config.cmake": b"# SDL3 CMake package\n",
        "share/cdin/sdl3-sdk.json": (
            json.dumps(manifest, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8"),
        "share/licenses/SDL3/LICENSE.txt": b"zlib license fixture\n",
    }


def make_archive(path: Path, files: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as archive:
        root = tarfile.TarInfo("sdl3-sdk/")
        root.type = tarfile.DIRTYPE
        archive.addfile(root)
        directories: set[str] = set()
        for relative, payload in sorted(files.items()):
            parts = relative.split("/")[:-1]
            for index in range(1, len(parts) + 1):
                directory = "sdl3-sdk/" + "/".join(parts[:index]) + "/"
                if directory not in directories:
                    directories.add(directory)
                    entry = tarfile.TarInfo(directory)
                    entry.type = tarfile.DIRTYPE
                    archive.addfile(entry)
            member = tarfile.TarInfo("sdl3-sdk/" + relative)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))


def make_lock(archive: Path | None = None) -> dict:
    assets = {}
    for key in sdk.TARGETS:
        asset = {
            "file_name": f"sdl3-sdk-3.4.16-{key}.tar.gz",
            "format": "tar.gz",
            "size_bytes": 123,
            "sha256": "c" * 64,
        }
        if archive is not None and key == "linux-x86_64":
            asset["size_bytes"] = archive.stat().st_size
            asset["sha256"] = sdk.sha256_file(archive)
        assets[key] = asset
    return {
        "dependencies": {
            "sdl3_sdk": {
                "repository": sdk.REPOSITORY,
                "tag": "sdl3-sdk-v3.4.16",
                "version": "3.4.16",
                "revision": REVISION,
                "assets": assets,
            }
        },
        "tooling": {
            "sdl3": {
                "version": "3.4.16",
                "archive": SOURCE_URL,
                "sha256": SOURCE_SHA,
            }
        },
    }


def write_lock(path: Path, lock: dict) -> None:
    pin = lock["dependencies"]["sdl3_sdk"]
    lines = [
        "[dependencies.sdl3_sdk]",
        'repository = "{}"'.format(pin["repository"]),
        'tag = "{}"'.format(pin["tag"]),
        'version = "{}"'.format(pin["version"]),
        'revision = "{}"'.format(pin["revision"]),
        "",
    ]
    for key, asset in pin["assets"].items():
        lines.extend([
            '[dependencies.sdl3_sdk.assets."{}"]'.format(key),
            'file_name = "{}"'.format(asset["file_name"]),
            'format = "{}"'.format(asset["format"]),
            "size_bytes = {}".format(asset["size_bytes"]),
            'sha256 = "{}"'.format(asset["sha256"]),
            "",
        ])
    source = lock["tooling"]["sdl3"]
    lines.extend([
        "[tooling.sdl3]",
        'version = "{}"'.format(source["version"]),
        'archive = "{}"'.format(source["archive"]),
        'sha256 = "{}"'.format(source["sha256"]),
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


class TargetAndPinTests(unittest.TestCase):
    def test_maps_all_five_exact_target_identities(self) -> None:
        for key, (os_name, abi) in sdk.TARGETS.items():
            architecture = key.rsplit("-", 1)[1]
            target_os = os_name
            self.assertEqual(
                sdk.target_key({"os": target_os, "architecture": architecture, "abi": abi}),
                key,
            )

    def test_rejects_target_with_wrong_abi(self) -> None:
        with self.assertRaisesRegex(sdk.SDL3ArtifactError, "no published SDL3 SDK"):
            sdk.target_key({"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.40"})

    def test_missing_release_pin_fails_closed_without_source_fallback(self) -> None:
        with self.assertRaisesRegex(sdk.SDL3ArtifactError, "Publish and verify"):
            sdk.validate_pin({"tooling": {"sdl3": {
                "version": "3.4.16", "archive": SOURCE_URL, "sha256": SOURCE_SHA
            }}}, "linux-x86_64")

    def test_requires_all_five_target_asset_identities(self) -> None:
        lock = make_lock()
        del lock["dependencies"]["sdl3_sdk"]["assets"]["windows-x86_64"]
        with self.assertRaisesRegex(sdk.SDL3ArtifactError, "exactly five targets"):
            sdk.validate_pin(lock, "linux-x86_64")

    def test_rejects_mutated_tag_revision_and_asset_filename(self) -> None:
        lock = make_lock()
        pin = lock["dependencies"]["sdl3_sdk"]
        pin["revision"] = "not-a-commit"
        with self.assertRaisesRegex(sdk.SDL3ArtifactError, "version/tag/source provenance"):
            sdk.validate_pin(lock, "linux-x86_64")
        pin["revision"] = REVISION
        pin["assets"]["linux-x86_64"]["file_name"] = "other.tar.gz"
        with self.assertRaisesRegex(sdk.SDL3ArtifactError, "asset pin"):
            sdk.validate_pin(lock, "linux-x86_64")


class ReleaseIdentityTests(unittest.TestCase):
    def test_requires_exact_prerelease_tag_commit_digest_and_size(self) -> None:
        lock = make_lock()
        pin, asset, _source = sdk.validate_pin(lock, "linux-x86_64")
        release = {
            "tag_name": pin["tag"],
            "draft": False,
            "prerelease": True,
            "assets": [
                {
                    "name": asset["file_name"],
                    "size": asset["size_bytes"],
                    "digest": "sha256:" + asset["sha256"],
                },
                {"name": asset["file_name"] + ".sha256"},
            ],
        }
        tag_ref = {"object": {"type": "commit", "sha": REVISION}}
        with patch.object(sdk, "fetch_github_json", side_effect=[release, tag_ref]):
            self.assertEqual(sdk.verify_release(pin, asset), release)

    def test_rejects_a_release_with_a_moved_tag(self) -> None:
        lock = make_lock()
        pin, asset, _source = sdk.validate_pin(lock, "linux-x86_64")
        release = {
            "tag_name": pin["tag"], "draft": False, "prerelease": True,
            "assets": [
                {"name": asset["file_name"], "size": asset["size_bytes"],
                 "digest": "sha256:" + asset["sha256"]},
                {"name": asset["file_name"] + ".sha256"},
            ],
        }
        moved = {"object": {"type": "commit", "sha": "d" * 40}}
        with patch.object(sdk, "fetch_github_json", side_effect=[release, moved]):
            with self.assertRaisesRegex(sdk.SDL3ArtifactError, "tag target mismatch"):
                sdk.verify_release(pin, asset)

    def test_rejects_missing_release_digest_or_sidecar(self) -> None:
        lock = make_lock()
        pin, asset, _source = sdk.validate_pin(lock, "linux-x86_64")
        release = {
            "tag_name": pin["tag"], "draft": False, "prerelease": True,
            "assets": [{"name": asset["file_name"], "size": asset["size_bytes"]}],
        }
        with patch.object(sdk, "fetch_github_json", return_value=release):
            with self.assertRaisesRegex(sdk.SDL3ArtifactError, "asset size/digest"):
                sdk.verify_release(pin, asset)


class ArchiveAndPackageTests(unittest.TestCase):
    def test_extracts_and_verifies_exact_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "sdk.tar.gz"
            make_archive(archive, package_files())
            extracted = sdk.safe_extract(archive, root / "extract")
            sdk.verify_package_prefix(extracted, "3.4.16", TARGET, {
                "url": SOURCE_URL, "sha256": SOURCE_SHA
            })

    def test_rejects_path_traversal_and_symlink_members(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            traversal = root / "traversal.tar.gz"
            with tarfile.open(traversal, "w:gz") as archive:
                member = tarfile.TarInfo("sdl3-sdk/../../outside")
                member.size = 1
                archive.addfile(member, io.BytesIO(b"x"))
            with self.assertRaisesRegex(sdk.SDL3ArtifactError, "unsafe"):
                sdk.safe_extract(traversal, root / "traversal-out")
            link = root / "link.tar.gz"
            with tarfile.open(link, "w:gz") as archive:
                member = tarfile.TarInfo("sdl3-sdk/link")
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                archive.addfile(member)
            with self.assertRaisesRegex(sdk.SDL3ArtifactError, "unsupported"):
                sdk.safe_extract(link, root / "link-out")

    def test_rejects_wrong_manifest_target_and_shared_library(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = package_files()
            metadata = json.loads(files["share/cdin/sdl3-sdk.json"])
            metadata["target"]["abi"] = "gnu-glibc-2.40"
            files["share/cdin/sdl3-sdk.json"] = (
                json.dumps(metadata, sort_keys=True, indent=2) + "\\n"
            ).encode()
            for relative, payload in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            with self.assertRaisesRegex(sdk.SDL3ArtifactError, "manifest differs"):
                sdk.verify_package_prefix(root, "3.4.16", TARGET, {
                    "url": SOURCE_URL, "sha256": SOURCE_SHA
                })

        with tempfile.TemporaryDirectory() as nested:
            prefix = Path(nested)
            files = package_files()
            files["lib/libSDL3.so"] = b"shared library"
            for relative, payload in files.items():
                path = prefix / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            with self.assertRaisesRegex(sdk.SDL3ArtifactError, "shared SDL3"):
                sdk.verify_package_prefix(prefix, "3.4.16", TARGET, {
                    "url": SOURCE_URL, "sha256": SOURCE_SHA
                })

    def test_offline_install_stages_only_the_exact_cached_target_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_files = package_files()
            archive = root / "source.tar.gz"
            make_archive(archive, source_files)
            lock = make_lock(archive)
            lock_path = root / "deps.lock"
            write_lock(lock_path, lock)
            pin, asset, _source = sdk.validate_pin(lock, "linux-x86_64")
            cache = root / "cache"
            cache.mkdir()
            cache_name = f"{Path(asset['file_name']).stem}-{asset['sha256']}.tar.gz"
            (cache / cache_name).write_bytes(archive.read_bytes())
            prefix = root / "install"
            sdk.install_sdl3_sdk(prefix, TARGET, lock_path=lock_path, cache=cache, offline=True)
            sdk.verify_package_prefix(prefix, "3.4.16", TARGET, {
                "url": SOURCE_URL, "sha256": SOURCE_SHA
            })
            self.assertEqual((prefix / "lib" / "libSDL3.a").read_bytes(), b"static SDL3 fixture\n")


if __name__ == "__main__":
    unittest.main()
