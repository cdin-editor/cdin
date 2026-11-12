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
from hashlib import sha256
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

    def write_manifest(self, profile: str) -> Path:
        components = [
            {"component_id": "backend", "variant": "default", "version": "1.2.1",
             "delivery": "artifact", "selected_artifact": {"artifact_id": "backend-native",
             "sha256": "a" * 64, "source_provenance": [{"revision": "b" * 40}]}},
            {"component_id": "frontend", "variant": "core", "version": "1.1.1",
             "delivery": "artifact", "selected_artifact": {"artifact_id": "frontend-core",
             "sha256": "c" * 64, "source_provenance": [{"revision": "d" * 40}]}},
            {"component_id": "frontend", "variant": "tui", "version": "1.1.1",
             "delivery": "artifact", "selected_artifact": {"artifact_id": "frontend-tui",
             "sha256": "e" * 64, "source_provenance": [{"revision": "f" * 40}]}},
            {"component_id": "runtime", "variant": "default", "version": "1.0.0-rc.3",
             "delivery": "artifact", "selected_artifact": {"artifact_id": "runtime-modules",
             "sha256": "1" * 64, "source_provenance": [{"revision": "2" * 40}]}},
        ]
        if profile == "gui-sdl":
            components.append({
                "component_id": "frontend", "variant": "gui-sdl", "version": "1.1.1",
                "delivery": "artifact", "selected_artifact": {"artifact_id": "frontend-gui-sdl",
                "sha256": "3" * 64, "source_provenance": [{"revision": "4" * 40}]},
            })
        manifest = {
            "schema_version": "1.1.0",
            "registry_version": "0.2.0-dev.1",
            "resolution": {"target": self.target, "delivery_mode": "artifact"},
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
