"""Unit tests for the Registry toolchain bootstrap environment."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scripts.configure import selected_package_version\nfrom scripts.registry import registry_go_environment


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


if __name__ == "__main__":
    unittest.main()
