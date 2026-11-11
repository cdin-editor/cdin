"""Unit tests for the Registry toolchain bootstrap environment."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.configure import selected_package_version
from scripts.registry import registry_go_environment


class RegistryGoEnvironmentTests(unittest.TestCase):
    def test_uses_canonical_proxy_and_auto_toolchain_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            environment = registry_go_environment()
        self.assertEqual(
            environment["GOPROXY"], "https://proxy.golang.org,direct"
        )
        self.assertEqual(environment["GOTOOLCHAIN"], "auto")

    def test_allows_explicit_proxy_override(self) -> None:
        with patch.dict(
            os.environ,
            {"CDIN_GOPROXY": "https://proxy.example.invalid"},
            clear=True,
        ):
            environment = registry_go_environment()
        self.assertEqual(environment["GOPROXY"], "https://proxy.example.invalid")

    def test_preserves_other_environment_variables(self) -> None:
        with patch.dict(
            os.environ,
            {"CI": "true", "CDIN_GOPROXY": "direct"},
            clear=True,
        ):
            environment = registry_go_environment()
        self.assertEqual(environment["CI"], "true")
        self.assertEqual(environment["GOPROXY"], "direct")


class ConfigureManifestTests(unittest.TestCase):
    def test_reads_the_exact_selected_component_variant(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        payload = {
            "components": [
                {"component_id": "frontend", "variant": "tui", "version": "1.0.2"},
                {"component_id": "frontend", "variant": "gui-sdl", "version": "1.0.2"},
                {"component_id": "backend", "variant": "default", "version": "1.2.0"},
            ]
        }
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "registry-manifest.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(
                selected_package_version(manifest, "frontend", "gui-sdl"),
                "1.0.2",
            )

    def test_rejects_missing_or_ambiguous_component_variants(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "registry-manifest.json"
            manifest.write_text(
                json.dumps({
                    "components": [
                        {"component_id": "backend", "variant": "default", "version": "1.2.0"},
                        {"component_id": "backend", "variant": "default", "version": "1.2.1"},
                    ]
                }),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                selected_package_version(manifest, "backend", "default")

    def test_rejects_a_missing_manifest(self) -> None:
        from pathlib import Path

        with self.assertRaises(FileNotFoundError):
            selected_package_version(
                Path("missing-registry-manifest.json"), "backend", "default"
            )


class RegistryMakeTargetTests(unittest.TestCase):
    def test_normal_stack_uses_pinned_registry_binary(self) -> None:
        makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(makefile, r"(?m)^stack: deps registry$")
        self.assertRegex(makefile, r"(?m)^stack-gui: deps registry-gui$")
        self.assertNotRegex(makefile, r"(?m)^stack:.*registry-dev")
        self.assertNotRegex(makefile, r"(?m)^stack-gui:.*registry-gui-dev")

    def test_source_build_is_explicit_for_developer_stack_targets(self) -> None:
        root = Path(__file__).resolve().parents[1]
        makefile = (root / "Makefile").read_text(encoding="utf-8")
        stack_script = (root / "scripts" / "build_stack.py").read_text(encoding="utf-8")
        pipeline = (root / "pipeline.toml").read_text(encoding="utf-8")

        self.assertRegex(makefile, r"(?m)^stack-dev: registry-dev$")
        self.assertRegex(makefile, r"(?m)^stack-gui-dev: registry-gui-dev$")
        self.assertIn("--registry-source-build", makefile)
        self.assertIn('parser.add_argument(\n        "--registry-source-build"', stack_script)
        self.assertIn('if args.registry_source_build:', stack_script)
        # CI is allowed to test the explicit source build; normal Make targets are not.
        self.assertIn('"scripts/build_stack.py", "--registry-source-build"', pipeline)


if __name__ == "__main__":
    unittest.main()
