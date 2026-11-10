"""Safety and reproducibility tests for the SDL3 SDK package builder."""
from __future__ import annotations

from io import BytesIO
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


if __name__ == "__main__":
    unittest.main()
