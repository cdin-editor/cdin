"""Unit tests for the Registry toolchain bootstrap environment."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
