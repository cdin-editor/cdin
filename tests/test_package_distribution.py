#!/usr/bin/env python3
"""Tests for reproducible installed-prefix distributions and safe extraction."""
from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from package_distribution import (  # noqa: E402
    DistributionError,
    detect_host,
    package_distribution,
    safe_extract,
    sha256_file,
)


def host_target() -> dict[str, str]:
    os_name, architecture = detect_host()
    if os_name == "linux":
        libc, version = platform.libc_ver()
        if libc.lower() not in {"glibc", "gnu libc"} or not version:
            raise RuntimeError(f"tests require a glibc host, got {libc}/{version}")
        major, minor = version.split(".")[:2]
        abi = f"gnu-glibc-{major}.{minor}"
    elif os_name == "darwin":
        major = platform.mac_ver()[0].split(".")[0]
        abi = f"macos-{major}"
    else:
        abi = "windows-ucrt64"
    return {"os": os_name, "architecture": architecture, "abi": abi}


class InstalledDistributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_msystem = os.environ.get("MSYSTEM")
        self.temporary = tempfile.TemporaryDirectory(prefix="cdin-package-test-")
        self.root = Path(self.temporary.name)
        self.prefix = self.root / "prefix"
        self.workspace = self.root / "registry-workspace-tui"
        self.output = self.root / "out"
        self.executable = self.prefix / "bin" / ("cdin.exe" if os.name == "nt" else "cdin")
        self.runtime = self.prefix / "share" / "cdin" / "lua"
        self.executable.parent.mkdir(parents=True)
        self.runtime.mkdir(parents=True)
        self.runtime.joinpath("cdin").mkdir()
        self.runtime.joinpath("cdin/runtime.lua").write_text("return true\n", encoding="utf-8")
        if os.name == "nt":
            self.executable.write_bytes(b"not executed by this platform-neutral packaging test")
        else:
            self.executable.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  --version) echo 'cdin 0.2.0'; exit 0 ;;\n"
                "  --check) app_root=$(CDPATH= cd -- \"$(dirname \"$0\")/..\" && pwd); test -d \"$app_root/share/cdin/lua\"; exit $? ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            self.executable.chmod(0o755)
        self.workspace.mkdir()
        self.target = host_target()
        if self.target["os"] == "windows":
            os.environ["MSYSTEM"] = "UCRT64"
        self.write_manifest("tui")

    def tearDown(self) -> None:
        self.temporary.cleanup()
        if self.previous_msystem is None:
            os.environ.pop("MSYSTEM", None)
        else:
            os.environ["MSYSTEM"] = self.previous_msystem

    def write_manifest(self, profile: str) -> Path:
        components = [
            {"component_id": "backend", "variant": "default", "version": "1.2.1",
             "delivery": "artifact", "release_metadata_sha256": "9" * 64,
             "release_metadata_uri": "https://raw.githubusercontent.com/cdin-editor/backend/backend-1.2.1/metadata.json",
             "selected_artifact": {"artifact_id": "backend-native", "file_name": "backend.tar.gz",
             "uri": "https://github.com/cdin-editor/backend/releases/download/v1.2.1/backend.tar.gz",
             "size_bytes": 1024, "sha256": "a" * 64,
             "source_provenance": [{"repository_uri": "https://github.com/cdin-editor/backend",
             "revision": "b" * 40, "source_unit_id": "backend-source"}]}},
            {"component_id": "frontend", "variant": "core", "version": "1.1.1",
             "delivery": "artifact", "release_metadata_sha256": "8" * 64,
             "release_metadata_uri": "https://raw.githubusercontent.com/cdin-editor/frontend/frontend-1.1.1/metadata.json",
             "selected_artifact": {"artifact_id": "frontend-core", "file_name": "frontend-core.tar.gz",
             "uri": "https://github.com/cdin-editor/frontend/releases/download/v1.1.1/frontend-core.tar.gz",
             "size_bytes": 1024, "sha256": "c" * 64,
             "source_provenance": [{"repository_uri": "https://github.com/cdin-editor/frontend",
             "revision": "d" * 40, "source_unit_id": "frontend-source"}]}},
            {"component_id": "frontend", "variant": "tui", "version": "1.1.1",
             "delivery": "artifact", "release_metadata_sha256": "7" * 64,
             "release_metadata_uri": "https://raw.githubusercontent.com/cdin-editor/frontend/frontend-1.1.1/metadata.json",
             "selected_artifact": {"artifact_id": "frontend-tui", "file_name": "frontend-tui.tar.gz",
             "uri": "https://github.com/cdin-editor/frontend/releases/download/v1.1.1/frontend-tui.tar.gz",
             "size_bytes": 1024, "sha256": "e" * 64,
             "source_provenance": [{"repository_uri": "https://github.com/cdin-editor/frontend",
             "revision": "f" * 40, "source_unit_id": "frontend-source"}]}},
            {"component_id": "runtime", "variant": "default", "version": "1.0.0-rc.3",
             "delivery": "artifact", "release_metadata_sha256": "6" * 64,
             "release_metadata_uri": "https://raw.githubusercontent.com/cdin-editor/runtime/runtime-1.0.0-rc.3/metadata.json",
             "selected_artifact": {"artifact_id": "runtime-modules", "file_name": "runtime.tar.gz",
             "uri": "https://github.com/cdin-editor/runtime/releases/download/v1.0.0-rc.3/runtime.tar.gz",
             "size_bytes": 1024, "sha256": "1" * 64,
             "source_provenance": [{"repository_uri": "https://github.com/cdin-editor/runtime",
             "revision": "2" * 40, "source_unit_id": "runtime-source"}]}},
        ]
        if profile == "gui-sdl":
            components.append({
                "component_id": "frontend", "variant": "gui-sdl", "version": "1.1.1",
                "delivery": "artifact", "release_metadata_sha256": "5" * 64,
                "release_metadata_uri": "https://raw.githubusercontent.com/cdin-editor/frontend/frontend-1.1.1/metadata.json",
                "selected_artifact": {"artifact_id": "frontend-gui-sdl", "file_name": "frontend-gui-sdl.tar.gz",
                "uri": "https://github.com/cdin-editor/frontend/releases/download/v1.1.1/frontend-gui-sdl.tar.gz",
                "size_bytes": 1024, "sha256": "3" * 64,
                "source_provenance": [{"repository_uri": "https://github.com/cdin-editor/frontend",
                "revision": "4" * 40, "source_unit_id": "frontend-source"}]},
            })
        manifest = {
            "schema_version": "1.1.0",
            "registry_version": "0.2.0-dev.1",
            "resolution": {"target": self.target, "delivery_mode": "artifact"},
            "catalogs": [{"catalog_id": "cdin-components", "metadata_sha256": "5" * 64,
                          "metadata_uri": "file:///registry/catalog-index.json"}],
            "environment_contracts": [
                {"contract_id": "org.cdin.kernel-abi", "version": "1.1.0"},
                {"contract_id": "org.lua.puc-lua-c-api", "version": "5.4.0"},
                {"contract_id": "org.m-mdy-m.log-c-api", "version": "0.1.0"},
            ],
            "components": components,
        }
        path = self.workspace / "registry-manifest.json"
        path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def package(self, *, profile: str = "tui", run_smoke: bool | None = None) -> dict:
        if run_smoke is None:
            run_smoke = os.name != "nt"
        return package_distribution(
            prefix=self.prefix,
            workspace=self.workspace,
            output_directory=self.output,
            profile=profile,
            source_revision="a" * 40,
            run_smoke=run_smoke,
        )

    def test_packages_installed_prefix_and_verifies_manifest_checksums(self) -> None:
        result = self.package()
        archive = Path(result["archive"])
        checksum = Path(result["checksum"])
        manifest_path = Path(result["manifest"])
        expected = sha256_file(archive)
        self.assertEqual(result["archive_sha256"], expected)
        self.assertEqual(checksum.read_text(encoding="ascii"),
                         f"{expected}  {archive.name}\n")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_commit"], "a" * 40)
        self.assertEqual(manifest["profile"], "tui")
        self.assertEqual(manifest["archive"]["size_bytes"], archive.stat().st_size)
        self.assertEqual(archive.suffix == ".zip", self.target["os"] == "windows")

        with tempfile.TemporaryDirectory(prefix="cdin-package-unpack-test-") as temporary:
            extracted = safe_extract(archive, Path(temporary))
            build_info = json.loads((extracted / "BUILD-INFO.json").read_text(encoding="utf-8"))
            copied_manifest = extracted / "share" / "cdin" / "registry-manifest.json"
            self.assertEqual(build_info["registry_manifest_sha256"], sha256_file(copied_manifest))
            self.assertEqual(build_info["source_commit"], "a" * 40)
            self.assertTrue((extracted / "LICENSE").is_file())
            self.assertTrue((extracted / "NOTICE").is_file())

    def test_tui_distribution_rejects_sdl3(self) -> None:
        library = self.prefix / "lib" / "libSDL3.a"
        library.parent.mkdir(parents=True)
        library.write_bytes(b"must not be in TUI")
        with self.assertRaisesRegex(DistributionError, "TUI distribution contains SDL3"):
            self.package(run_smoke=False)

    def test_gui_sdl_distribution_requires_pinned_sdk_files(self) -> None:
        self.write_manifest("gui-sdl")
        with self.assertRaisesRegex(DistributionError, "does not contain its pinned SDL3 SDK"):
            self.package(profile="gui-sdl", run_smoke=False)

    def test_refuses_to_overwrite_an_existing_immutable_distribution(self) -> None:
        self.package(run_smoke=False)
        with self.assertRaisesRegex(DistributionError, "refusing to overwrite"):
            self.package(run_smoke=False)

    def test_rejects_a_registry_target_for_another_architecture(self) -> None:
        manifest = json.loads((self.workspace / "registry-manifest.json").read_text(encoding="utf-8"))
        manifest["resolution"]["target"]["architecture"] = (
            "arm64" if self.target["architecture"] == "x86_64" else "x86_64"
        )
        (self.workspace / "registry-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "does not match runner"):
            self.package(run_smoke=False)

    def test_rejects_symlinks_inside_the_installed_prefix(self) -> None:
        if os.name == "nt":
            self.skipTest("creating symlinks may require elevated Windows privileges")
        link = self.prefix / "share" / "cdin" / "lua" / "linked"
        link.symlink_to(self.runtime / "cdin", target_is_directory=True)
        with self.assertRaisesRegex(DistributionError, "symlink"):
            self.package(run_smoke=False)


    def test_build_info_records_pinned_kernel_logger_and_environment_contracts(self) -> None:
        result = self.package(run_smoke=False)
        with tempfile.TemporaryDirectory(prefix="cdin-package-info-") as temporary:
            extracted = safe_extract(Path(result["archive"]), Path(temporary))
            build_info = json.loads((extracted / "BUILD-INFO.json").read_text(encoding="utf-8"))
        kernel = build_info["build_dependencies"]["kernel_sdk"]
        self.assertEqual(kernel["version"], "1.2.3")
        self.assertEqual(kernel["logger_version"], "0.1.0")
        self.assertEqual(kernel["source_revision"], "2fb09f52dc1a9963cf358ec54d584c520e174e67")
        self.assertEqual(len(kernel["asset"]["sha256"]), 64)
        self.assertEqual(
            {item["contract_id"] for item in build_info["environment_contracts"]},
            {"org.cdin.kernel-abi", "org.lua.puc-lua-c-api", "org.m-mdy-m.log-c-api"},
        )

    def test_gui_sdl_build_info_records_pinned_sdl3_source_identity(self) -> None:
        self.write_manifest("gui-sdl")
        library = self.prefix / "lib" / "libSDL3.a"
        library.parent.mkdir(parents=True)
        library.write_bytes(b"pinned SDL3 SDK fixture")
        result = self.package(profile="gui-sdl", run_smoke=False)
        with tempfile.TemporaryDirectory(prefix="cdin-package-sdl-info-") as temporary:
            extracted = safe_extract(Path(result["archive"]), Path(temporary))
            build_info = json.loads((extracted / "BUILD-INFO.json").read_text(encoding="utf-8"))
        sdl = build_info["build_dependencies"]["sdl3"]
        self.assertEqual(sdl["version"], "3.4.16")
        self.assertEqual(sdl["delivery"], "pinned-source-build")
        self.assertEqual(len(sdl["source_archive_sha256"]), 64)

    def test_rejects_missing_immutable_artifact_provenance(self) -> None:
        manifest = json.loads((self.workspace / "registry-manifest.json").read_text(encoding="utf-8"))
        manifest["components"][0]["selected_artifact"]["source_provenance"] = []
        (self.workspace / "registry-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "immutable source provenance"):
            self.package(run_smoke=False)

    def test_rejects_missing_release_metadata_digest(self) -> None:
        manifest = json.loads((self.workspace / "registry-manifest.json").read_text(encoding="utf-8"))
        del manifest["components"][0]["release_metadata_sha256"]
        (self.workspace / "registry-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "immutable release metadata identity"):
            self.package(run_smoke=False)

    def test_smoke_failure_does_not_publish_partial_distribution(self) -> None:
        if os.name == "nt":
            self.skipTest("the fixture executable is not a Windows PE binary")
        self.executable.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  --version) echo 'cdin 0.2.0'; exit 0 ;;\n"
            "  --check) exit 9 ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        self.executable.chmod(0o755)
        with self.assertRaisesRegex(DistributionError, "lifecycle check failed"):
            self.package(run_smoke=True)
        self.assertEqual(list(self.output.iterdir()) if self.output.exists() else [], [])

    def test_safe_extractor_requires_an_empty_destination(self) -> None:
        archive = self.root / "simple.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("cdin-test/README", "ok")
        destination = self.root / "existing"
        destination.mkdir()
        (destination / "unexpected").write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "empty directory"):
            safe_extract(archive, destination)
        self.assertEqual((destination / "unexpected").read_text(encoding="utf-8"), "preserve")

    def test_safe_extractor_rejects_windows_drive_paths(self) -> None:
        archive = self.root / "drive.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("C:/outside.txt", "outside")
        with self.assertRaisesRegex(DistributionError, "unsafe archive member"):
            safe_extract(archive, self.root / "drive-extract")

    def test_safe_extractor_rejects_multiple_roots_and_case_collisions(self) -> None:
        multiple = self.root / "multiple.zip"
        with zipfile.ZipFile(multiple, "w") as output:
            output.writestr("one/file", "1")
            output.writestr("two/file", "2")
        with self.assertRaisesRegex(DistributionError, "exactly one application root"):
            safe_extract(multiple, self.root / "multiple-extract")

        collision = self.root / "collision.zip"
        with zipfile.ZipFile(collision, "w") as output:
            output.writestr("root/Name", "1")
            output.writestr("root/name", "2")
        with self.assertRaisesRegex(DistributionError, "duplicate normalized paths"):
            safe_extract(collision, self.root / "collision-extract")

    def test_safe_extractor_rejects_path_traversal(self) -> None:
        malicious = self.root / "malicious.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("../escaped.txt", "outside")
        destination = self.root / "extract"
        with self.assertRaisesRegex(DistributionError, "unsafe archive member"):
            safe_extract(malicious, destination)
        self.assertFalse((self.root / "escaped.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
