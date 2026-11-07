from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RegistryOwnershipBoundaryTests(unittest.TestCase):
    def test_cdin_does_not_own_a_catalog_index(self) -> None:
        self.assertFalse(
            (ROOT / "registry" / "catalog-index.json").exists(),
            "Catalog Index data belongs to the pinned Registry checkout, not CDIN",
        )

    def test_registry_wrapper_uses_catalog_from_its_exact_checkout(self) -> None:
        source = (ROOT / "scripts" / "registry.py").read_text(encoding="utf-8")
        self.assertIn(
            'REGISTRY_CATALOG = REGISTRY_SOURCE / "catalogs" / "cdin-components" / "catalog-index.json"',
            source,
        )
        self.assertIn("catalog = REGISTRY_CATALOG", source)
        self.assertNotIn('ROOT / "registry" / "catalog-index.json"', source)

    def test_product_definitions_do_not_contain_repository_or_metadata_locations(self) -> None:
        product_definitions = sorted((ROOT / "registry").glob("product-definition.*.yaml"))
        self.assertTrue(product_definitions, "expected the CDIN Product Definitions")
        for path in product_definitions:
            content = path.read_text(encoding="utf-8")
            for field in ("metadata_uri", "metadata_sha256", "repository_uri", "raw.githubusercontent.com"):
                with self.subTest(path=path.name, field=field):
                    self.assertNotIn(field, content)


if __name__ == "__main__":
    unittest.main()
