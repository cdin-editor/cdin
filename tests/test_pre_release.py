#!/usr/bin/env python3
"""Tests for the Registry-backed CDIN source pre-release report."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import pre_release


class PreReleaseManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.dist = self.root / "dist"
        self.dist.mkdir()
        self.archive = self.dist / "cdin-composition-root-source.zip"
        self.archive.write_bytes(b"reproducible source snapshot")
        self.checksum = self.dist / "cdin-composition-root-source.zip.sha256"
        self.checksum.write_text(
            sha256(self.archive.read_bytes()).hexdigest() + "  cdin-composition-root-source.zip\n",
            encoding="ascii",
        )
        self.workspace = self.root / ".deps/registry-workspace-tui"
        self.workspace.mkdir(parents=True)
        self.manifest_path = self.workspace / "registry-manifest.json"
        self.manifest = self.valid_manifest()
        self.write_manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def valid_manifest() -> dict:
        return {
            "schema_version": "1.1.0",
            "registry_version": "0.2.0-dev.1",
            "resolution": {
                "delivery_mode": "artifact-or-source",
                "target": {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.39"},
            },
            "environment_contracts": [
                {"contract_id": "org.cdin.kernel-abi", "version": "1.1.0"},
                {"contract_id": "org.m-mdy-m.log-c-api", "version": "0.1.0"},
                {"contract_id": "org.lua.puc-lua-c-api", "version": "5.4.0"},
            ],
            "components": [
                {
                    "component_id": "backend", "variant": "default", "version": "1.2.1",
                    "delivery": "artifact",
                    "selected_artifact": {
                        "artifact_id": "backend-linux-x86_64",
                        "kind": "native-development-package",
                        "target": {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.39"},
                        "file_name": "backend.tar.gz", "sha256": "a" * 64, "size_bytes": 123,
                        "source_provenance": [{"source_unit_id": "backend-source", "revision": "a" * 40}],
                    },
                },
                {
                    "component_id": "runtime", "variant": "default", "version": "1.0.0-rc.2",
                    "delivery": "source",
                    "source_units": [{
                        "source_unit_id": "runtime-source", "revision": "b" * 64,
                        "workspace_path": "components/runtime/default/source",
                    }],
                },
                {
                    "component_id": "frontend", "variant": "tui", "version": "1.0.2",
                    "delivery": "source",
                    "source_units": [{
                        "source_unit_id": "frontend-source", "revision": "c" * 40,
                        "workspace_path": "components/frontend/tui/source",
                    }],
                },
            ],
        }

    def write_manifest(self) -> None:
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def run_report(self, profile: str = "tui") -> dict:
        workspace = self.root / ".deps" / f"registry-workspace-{profile}"
        workspace.mkdir(parents=True, exist_ok=True)
        manifest_path = workspace / "registry-manifest.json"
        manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        with (
            patch.object(pre_release, "ROOT", self.root),
            patch.object(pre_release, "DIST", self.dist),
            patch.object(pre_release, "ARCHIVE", self.archive),
            patch.object(pre_release, "CHECKSUM", self.checksum),
            patch.dict("os.environ", {
                "CDIN_FRONTEND_VARIANT": profile,
                "CDIN_PRERELEASE_VERSION": "0.0.0-dev.test",
                "GITHUB_REF_NAME": "",
            }),
            patch.object(pre_release.subprocess, "check_output", return_value="d" * 40 + "\n"),
        ):
            self.assertEqual(pre_release.main(), 0)
        return json.loads((self.dist / "cdin-pre-release.json").read_text(encoding="utf-8"))

    def test_artifact_provenance_and_environment_providers_are_reported(self) -> None:
        report = self.run_report()
        self.assertEqual(
            {(item["contract_id"], item["version"]) for item in report["environment_contracts"]},
            {
                ("org.cdin.kernel-abi", "1.1.0"),
                ("org.m-mdy-m.log-c-api", "0.1.0"),
                ("org.lua.puc-lua-c-api", "5.4.0"),
            },
        )
        backend = next(item for item in report["components"] if item["component_id"] == "backend")
        self.assertEqual(backend["delivery"], "artifact")
        self.assertEqual(backend["selected_artifact"]["artifact_id"], "backend-linux-x86_64")
        self.assertEqual(backend["source_revisions"], ["a" * 40])
        runtime = next(item for item in report["components"] if item["component_id"] == "runtime")
        self.assertEqual(runtime["source_revisions"], ["b" * 64])
        self.assertNotIn("kernel", {item["component_id"] for item in report["components"]})

    def test_gui_profile_requires_both_frontend_adapters(self) -> None:
        self.manifest["components"].append({
            "component_id": "frontend", "variant": "gui-sdl", "version": "1.0.2",
            "delivery": "source",
            "source_units": [{
                "source_unit_id": "frontend-source", "revision": "c" * 40,
                "workspace_path": "components/frontend/gui-sdl/source",
            }],
        })
        self.write_manifest()
        report = self.run_report("gui-sdl")
        variants = {item["variant"] for item in report["components"] if item["component_id"] == "frontend"}
        self.assertEqual(variants, {"tui", "gui-sdl"})

    def test_missing_kernel_environment_contract_fails_closed(self) -> None:
        self.manifest["environment_contracts"] = [
            item for item in self.manifest["environment_contracts"]
            if item["contract_id"] != "org.cdin.kernel-abi"
        ]
        self.write_manifest()
        with self.assertRaisesRegex(SystemExit, "pinned environment contracts"):
            with (
                patch.object(pre_release, "ROOT", self.root),
                patch.object(pre_release, "DIST", self.dist),
                patch.object(pre_release, "ARCHIVE", self.archive),
                patch.object(pre_release, "CHECKSUM", self.checksum),
                patch.dict("os.environ", {"CDIN_FRONTEND_VARIANT": "tui"}),
            ):
                pre_release.main()

    def test_artifact_without_immutable_source_provenance_fails_closed(self) -> None:
        backend = next(item for item in self.manifest["components"] if item["component_id"] == "backend")
        backend["selected_artifact"]["source_provenance"] = []
        self.write_manifest()
        with self.assertRaisesRegex(SystemExit, "immutable source provenance"):
            with (
                patch.object(pre_release, "ROOT", self.root),
                patch.object(pre_release, "DIST", self.dist),
                patch.object(pre_release, "ARCHIVE", self.archive),
                patch.object(pre_release, "CHECKSUM", self.checksum),
                patch.dict("os.environ", {"CDIN_FRONTEND_VARIANT": "tui"}),
            ):
                pre_release.main()


if __name__ == "__main__":
    unittest.main()
