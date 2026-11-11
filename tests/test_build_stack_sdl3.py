"""Integration tests for safe SDL3 source acquisition in the developer build path."""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_stack


def write_archive(path: Path, member_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"cmake_minimum_required(VERSION 3.22)\nproject(SDL3)\n"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo(member_name)
        member.size = len(payload)
        archive.addfile(member, BytesIO(payload))


class SDL3SourceExtractionTests(unittest.TestCase):
    def _write_lock(self, root: Path, digest: str) -> Path:
        lock = root / "deps.lock"
        lock.write_text(
            "[tooling.sdl3]\n"
            'version = "3.4.16"\n'
            'archive = "https://github.com/libsdl-org/SDL/releases/download/release-3.4.16/SDL3-3.4.16.tar.gz"\n'
            f'sha256 = "{digest}"\n',
            encoding="utf-8",
        )
        return lock

    def test_uses_bounded_extractor_before_configuring_sdl3(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / ".deps" / "archives" / "SDL3-3.4.16.tar.gz"
            write_archive(archive, "SDL3-3.4.16/CMakeLists.txt")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            lock = self._write_lock(root, digest)

            with patch.multiple(
                build_stack,
                ROOT=root,
                DEPS=root / ".deps" / "src",
                PREFIX=root / ".deps" / "install",
                BUILD=root / "build" / "stack",
                LOCK=lock,
            ), patch.object(build_stack, "run") as run_mock:
                build_stack.install_sdl3({})

            source = root / ".deps" / "src" / "sdl3" / "SDL3-3.4.16"
            self.assertTrue((source / "CMakeLists.txt").is_file())
            self.assertIn(b"project(SDL3)", (source / "CMakeLists.txt").read_bytes())
            self.assertTrue(run_mock.called)
            configure = run_mock.call_args_list[0].args[0]
            self.assertEqual(configure[:3], ["cmake", "-S", str(source)])

    def test_rejects_traversal_even_when_archive_digest_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / ".deps" / "archives" / "SDL3-3.4.16.tar.gz"
            write_archive(archive, "SDL3-3.4.16/../../outside.txt")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            lock = self._write_lock(root, digest)

            with patch.multiple(
                build_stack,
                ROOT=root,
                DEPS=root / ".deps" / "src",
                PREFIX=root / ".deps" / "install",
                BUILD=root / "build" / "stack",
                LOCK=lock,
            ), patch.object(build_stack, "run") as run_mock:
                with self.assertRaisesRegex(
                    RuntimeError, "unsafe SDL3 source archive path"
                ):
                    build_stack.install_sdl3({})

            run_mock.assert_not_called()
            self.assertFalse((root / ".deps" / "src" / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
