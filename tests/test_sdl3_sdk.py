"""Safety and reproducibility tests for the SDL3 SDK package builder."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import package_sdl3_sdk as sdk


class TargetIdentityTests(unittest.TestCase):
    def test_supported_native_targets(self) -> None:
        with patch.object(sdk.platform, "system", return_value="Linux"), patch.object(
            sdk.platform, "machine", return_value="aarch64"
        ):
            self.assertEqual(sdk.target_identity(), ("linux", "arm64"))

        with patch.object(sdk.platform, "system", return_value="Darwin"), patch.object(
            sdk.platform, "machine", return_value="x86_64"
        ):
            self.assertEqual(sdk.target_identity(), ("macos", "x86_64"))

        with patch.object(sdk.platform, "system", return_value="Windows"), patch.object(
            sdk.platform, "machine", return_value="AMD64"
        ):
            self.assertEqual(sdk.target_identity(), ("windows", "x86_64"))

    def test_unknown_target_fails_closed(self) -> None:
        with patch.object(sdk.platform, "system", return_value="Plan9"), patch.object(
            sdk.platform, "machine", return_value="mips"
        ):
            with self.assertRaises(RuntimeError):
                sdk.target_identity()


class TargetAbiTests(unittest.TestCase):
    def test_linux_requires_exact_glibc_baseline(self) -> None:
        with patch.object(sdk.platform, "libc_ver", return_value=("glibc", "2.39")):
            self.assertEqual(sdk.target_abi("linux"), "gnu-glibc-2.39")
        with patch.object(sdk.platform, "libc_ver", return_value=("glibc", "2.40")):
            with self.assertRaisesRegex(RuntimeError, "glibc 2.39"):
                sdk.target_abi("linux")

    def test_macos_requires_supported_major_version(self) -> None:
        with patch.object(sdk.platform, "mac_ver", return_value=("15.6", ("", "", ""), "")):
            self.assertEqual(sdk.target_abi("macos"), "macos-15")
        with patch.object(sdk.platform, "mac_ver", return_value=("14.7", ("", "", ""), "")):
            with self.assertRaisesRegex(RuntimeError, "macOS 15"):
                sdk.target_abi("macos")

    def test_windows_requires_ucrt64_environment(self) -> None:
        with patch.dict(sdk.os.environ, {"MSYSTEM": "UCRT64"}):
            self.assertEqual(sdk.target_abi("windows"), "windows-ucrt64")
        with patch.dict(sdk.os.environ, {"MSYSTEM": "MINGW64"}):
            with self.assertRaisesRegex(RuntimeError, "UCRT64"):
                sdk.target_abi("windows")

    def test_unknown_abi_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unsupported SDL3 SDK ABI"):
            sdk.target_abi("freebsd")


class InstalledPrefixTests(unittest.TestCase):
    def _prefix(self, root: Path) -> Path:
        (root / "include" / "SDL3").mkdir(parents=True)
        (root / "lib" / "cmake" / "SDL3").mkdir(parents=True)
        (root / "share" / "cdin").mkdir(parents=True)
        (root / "share" / "licenses" / "SDL3").mkdir(parents=True)
        (root / "lib" / "libSDL3.a").write_bytes(b"static archive fixture")
        (root / "include" / "SDL3" / "SDL.h").write_text("/* fixture */\n", encoding="utf-8")
        (root / "include" / "SDL3" / "SDL_version.h").write_text("/* fixture */\n", encoding="utf-8")
        (root / "lib" / "cmake" / "SDL3" / "SDL3Config.cmake").write_text(
            "# fixture\n", encoding="utf-8"
        )
        (root / "share" / "licenses" / "SDL3" / "LICENSE.txt").write_text(
            "zlib license fixture\n", encoding="utf-8"
        )
        source = sdk.load_source_pin()
        manifest = {
            "schema": "cdin.sdl3-sdk.v1",
            "version": source["version"],
            "target": {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.39"},
            "source": {"url": source["archive"], "sha256": source["sha256"]},
            "linkage": "static",
            "cmake_package": "SDL3",
        }
        (root / "share" / "cdin" / "sdl3-sdk.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        return root

    def test_accepts_exact_static_prefix_with_license_and_abi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prefix = self._prefix(Path(temporary) / "prefix")
            sdk.verify_prefix(
                prefix,
                version="3.4.16",
                os_name="linux",
                arch="x86_64",
                abi="gnu-glibc-2.39",
                source=sdk.load_source_pin(),
            )

    def test_rejects_manifest_for_different_abi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prefix = self._prefix(Path(temporary) / "prefix")
            manifest_path = prefix / "share" / "cdin" / "sdl3-sdk.json"
            metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
            metadata["target"]["abi"] = "windows-ucrt64"
            manifest_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "manifest"):
                sdk.verify_prefix(
                    prefix,
                    version="3.4.16",
                    os_name="linux",
                    arch="x86_64",
                    abi="gnu-glibc-2.39",
                    source=sdk.load_source_pin(),
                )

    def test_rejects_missing_upstream_license(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prefix = self._prefix(Path(temporary) / "prefix")
            (prefix / "share" / "licenses" / "SDL3" / "LICENSE.txt").unlink()
            with self.assertRaisesRegex(RuntimeError, "LICENSE.txt"):
                sdk.verify_prefix(
                    prefix,
                    version="3.4.16",
                    os_name="linux",
                    arch="x86_64",
                    abi="gnu-glibc-2.39",
                    source=sdk.load_source_pin(),
                )

    def test_rejects_shared_only_library(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prefix = self._prefix(Path(temporary) / "prefix")
            (prefix / "lib" / "libSDL3.a").unlink()
            (prefix / "lib" / "libSDL3.so").write_bytes(b"shared fixture")
            with self.assertRaisesRegex(RuntimeError, "static SDL3 library"):
                sdk.verify_prefix(
                    prefix,
                    version="3.4.16",
                    os_name="linux",
                    arch="x86_64",
                    abi="gnu-glibc-2.39",
                    source=sdk.load_source_pin(),
                )

    def test_consumer_requires_exact_version_and_runs_linked_version_test(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(sdk, "run") as run_mock:
                sdk.verify_consumer(root / "prefix", root / "work", "3.4.16")
            cmake = (root / "work" / "consumer" / "CMakeLists.txt").read_text(encoding="utf-8")
            source = (root / "work" / "consumer" / "main.c").read_text(encoding="utf-8")
            self.assertIn("find_package(SDL3 3.4.16 EXACT CONFIG REQUIRED COMPONENTS SDL3-static)", cmake)
            self.assertIn("SDL3::SDL3-static", cmake)
            self.assertIn("SDL_VERSIONNUM(3, 4, 16)", source)
            self.assertTrue(any(command.args[0][0] == "ctest" for command in run_mock.call_args_list))


class SafeSourceExtractionTests(unittest.TestCase):
    def _archive(self, name: str, *, kind: str = "file") -> Path:
        temporary = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        temporary.close()
        path = Path(temporary.name)
        with tarfile.open(path, "w:gz") as archive:
            member = tarfile.TarInfo(name)
            if kind == "directory":
                member.type = tarfile.DIRTYPE
                archive.addfile(member)
            elif kind == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                archive.addfile(member)
            else:
                payload = b"fixture"
                member.size = len(payload)
                archive.addfile(member, BytesIO(payload))
        return path

    def test_extracts_single_root_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = self._archive("SDL3-3.4.16/CMakeLists.txt")
            try:
                source = sdk.safe_extract(archive, Path(temporary) / "source")
                self.assertTrue((source / "CMakeLists.txt").is_file())
                self.assertEqual((source / "CMakeLists.txt").read_bytes(), b"fixture")
            finally:
                archive.unlink(missing_ok=True)

    def test_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = self._archive("../outside.txt")
            try:
                with self.assertRaises(RuntimeError):
                    sdk.safe_extract(archive, Path(temporary) / "source")
            finally:
                archive.unlink(missing_ok=True)

    def test_rejects_case_insensitive_path_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "collision.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                for name in ("SDL3-3.4.16/Readme", "SDL3-3.4.16/README"):
                    member = tarfile.TarInfo(name)
                    member.size = 1
                    archive.addfile(member, BytesIO(b"x"))
            with self.assertRaises(RuntimeError):
                sdk.safe_extract(archive_path, Path(temporary) / "source")

    def test_rejects_symlink_members(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = self._archive("SDL3-3.4.16/link", kind="symlink")
            try:
                with self.assertRaises(RuntimeError):
                    sdk.safe_extract(archive, Path(temporary) / "source")
            finally:
                archive.unlink(missing_ok=True)


class ReproducibleArchiveTests(unittest.TestCase):
    def test_repeated_archives_have_identical_bytes_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "prefix"
            root.mkdir()
            (root / "include").mkdir()
            (root / "include" / "SDL.h").write_text("fixture\n", encoding="utf-8")
            first = Path(temporary) / "first.tar.gz"
            second = Path(temporary) / "second.tar.gz"
            digest_a = sdk.build_archive(root, first)
            digest_b = sdk.build_archive(root, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(digest_a, digest_b)
            self.assertEqual(len(digest_a), 64)

    def test_source_pin_is_immutable_sha256(self) -> None:
        spec = sdk.load_source_pin()
        self.assertEqual(len(spec["sha256"]), 64)
        self.assertTrue(spec["archive"].startswith("https://"))



class ReleaseWorkflowPermissionTests(unittest.TestCase):
    def test_sdk_publisher_can_read_its_own_workflow_artifacts(self) -> None:
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "sdl3-sdk.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("  publish:\n", workflow)
        publish = workflow.split("  publish:\n", 1)[1]
        permissions = publish.split("    steps:\n", 1)[0]
        self.assertIn("actions: read", permissions)
        self.assertIn("contents: write", permissions)
        self.assertIn('gh run download "${GITHUB_RUN_ID}"', publish)
        self.assertIn('gh release create "$TAG_NAME"', publish)
        self.assertIn('TAG_NAME: ${{ startsWith(github.ref, \'refs/tags/sdl3-sdk-v\')', publish)
        self.assertIn('SOURCE_SHA: ${{ github.event.workflow_run.head_sha }}', publish)
        self.assertIn('tag_commit" != "$SOURCE_SHA"', publish)


if __name__ == "__main__":
    unittest.main()
