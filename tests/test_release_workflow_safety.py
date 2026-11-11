#!/usr/bin/env python3
"""Guard the legacy product release repair path against immutable-ref mutation."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "pre-release.yml"
EXPECTED_ALPHA_COMMIT = "e4c5fb26659f9a00cf11163ae132ebe40e7e0157"
EXPECTED_PIPELINE_REF = "4fc55439656a7b0e4b270ae05049c29b0ddc1d56"


class LegacyReleaseRecoverySafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        marker = "  inspect-legacy-alpha-release:"
        if marker not in cls.workflow:
            raise AssertionError("legacy alpha.1 inspection job is missing")
        cls.legacy_jobs = cls.workflow[self.workflow.index(marker):]

    def test_recovery_never_deletes_or_replaces_a_release(self) -> None:
        self.assertNotIn("--method DELETE", self.legacy_jobs)
        self.assertNotIn("DELETE /releases", self.legacy_jobs)
        self.assertIn("Refusing to delete, replace or rewrite it", self.legacy_jobs)

    def test_inspection_resolves_the_immutable_annotated_tag_commit(self) -> None:
        self.assertIn("git/ref/tags/$TAG_NAME", self.legacy_jobs)
        self.assertIn("git/tags/$tag_object", self.legacy_jobs)
        self.assertIn(
            f'expected_commit="{EXPECTED_ALPHA_COMMIT}"',
            self.legacy_jobs,
        )
        self.assertIn("contents: read", self.legacy_jobs)

    def test_repair_is_only_for_a_missing_release_and_uses_the_existing_tag(self) -> None:
        self.assertIn('if [[ -z "$release" ]]', self.legacy_jobs)
        self.assertIn('echo "repair_required=true" >> "$GITHUB_OUTPUT"', self.legacy_jobs)
        self.assertIn(
            "needs.inspect-legacy-alpha-release.outputs.repair_required == 'true'",
            self.legacy_jobs,
        )
        self.assertIn(
            f"uses: m-mdy-m/pipeline/.github/workflows/source-release.yml@{EXPECTED_PIPELINE_REF}",
            self.legacy_jobs,
        )
        self.assertIn("source-ref: refs/tags/v0.3.0-alpha.1", self.legacy_jobs)

    def test_existing_incomplete_release_fails_closed(self) -> None:
        self.assertIn('if [[ "$draft" == "true" ||', self.legacy_jobs)
        self.assertIn(
            "Existing immutable Release $release_url is incomplete or malformed",
            self.legacy_jobs,
        )
        self.assertIn('echo "repair_required=false" >> "$GITHUB_OUTPUT"', self.legacy_jobs)


if __name__ == "__main__":
    unittest.main()
