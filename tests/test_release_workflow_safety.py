#!/usr/bin/env python3
"""Guard the legacy product release repair path against immutable-ref mutation."""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "pre-release.yml"
EXPECTED_ALPHA_COMMIT = "e4c5fb26659f9a00cf11163ae132ebe40e7e0157"
EXPECTED_PIPELINE_REF = "0f8c5a460932030b95d6f04b089eaf968df8c064"


class LegacyReleaseRecoverySafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        marker = "  inspect-legacy-alpha-release:"
        if marker not in cls.workflow:
            raise AssertionError("legacy alpha.1 inspection job is missing")
        cls.legacy_jobs = cls.workflow[cls.workflow.index(marker):]

    def test_legacy_alpha_recovery_runs_after_successful_main_ci_not_product_acceptance(self) -> None:
        inspection = self.legacy_jobs.split("  repair-legacy-alpha-release:", 1)[0]
        self.assertIn("workflow_run.name == 'CI'", inspection)
        self.assertIn("head_branch == 'main'", inspection)
        self.assertNotIn("workflow_run.name == 'Product Acceptance'", inspection)

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


class VersionedReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    def test_development_tags_are_excluded_from_the_immutable_semver_release_path(self) -> None:
        tags = self.workflow.split("    tags:", 1)[1].split("\n\n", 1)[0]
        self.assertIn('"v*"', tags)
        self.assertIn('"!v0.0.0-dev.*"', tags)

    def test_versioned_tag_must_be_reachable_from_main_before_ci_and_publication(self) -> None:
        self.assertIn("verify-tag-on-main:", self.workflow)
        self.assertIn('git merge-base --is-ancestor "$tag_commit" refs/remotes/origin/main', self.workflow)
        verify = self.workflow.split("  verify:", 1)[1].split("  publish:", 1)[0]
        publish = self.workflow.split("  publish:", 1)[1]
        self.assertIn("needs: [verify-tag-on-main]", verify)
        self.assertIn("needs: [verify, verify-tag-on-main]", publish)

    def test_versioned_release_uses_the_same_immutable_pipeline_workflow_and_helper_pin(self) -> None:
        publish = self.workflow.split("  publish:", 1)[1]
        workflow_ref = next(
            line.strip()
            for line in publish.splitlines()
            if line.strip().startswith("uses: m-mdy-m/pipeline/.github/workflows/source-release.yml@")
        ).rsplit("@", 1)[1]
        helper_ref = next(
            line.strip()
            for line in publish.splitlines()
            if line.strip().startswith("pipeline-ref:")
        ).split(":", 1)[1].strip()
        self.assertEqual(workflow_ref, helper_ref)
        self.assertEqual(workflow_ref, "0f8c5a460932030b95d6f04b089eaf968df8c064")
        self.assertIn("contents: write", publish)
        self.assertNotIn("CDIN_RELEASE_TOKEN", self.workflow)
        self.assertNotIn("secrets:", publish)

class RollingProductReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (ROOT / ".github" / "workflows" / "pre-release.yml").read_text(encoding="utf-8")
        cls.source_tag = cls.workflow.split("  create-development-tag:", 1)[1].split(
            "  publish-development-prerelease:", 1
        )[0]
        cls.rolling = cls.workflow.split("  publish-rolling-product-release:", 1)[1].split(
            "  inspect-legacy-alpha-release:", 1
        )[0]

    def test_channel_workflow_listens_to_ci_for_source_snapshots_and_product_acceptance_for_latest(self) -> None:
        self.assertIn('workflows: ["CI", "Product Acceptance"]', self.workflow)

    def test_release_jobs_use_job_scoped_github_token_without_manual_secrets(self) -> None:
        self.assertNotIn("CDIN_RELEASE_TOKEN", self.workflow)
        self.assertNotIn("secrets:", self.workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}", self.source_tag)
        self.assertIn("contents: write", self.source_tag)
        self.assertIn("contents: write", self.rolling)
        self.assertIn("actions: read", self.rolling)

    def test_development_tag_creation_shell_has_valid_bash_syntax(self) -> None:
        # The Windows matrix uses a native UCRT64 Python process. Spawning the
        # MSYS2/Git Bash compatibility executable from native Python returns
        # exit code 1 without a parser diagnostic, even for valid -n input.
        # The Linux and macOS matrix jobs run this exact syntax check.
        if os.name == "nt":
            self.skipTest("Bash syntax is validated by the Linux/macOS CI jobs")
        if shutil.which("bash") is None:
            self.skipTest("bash is not installed")
        script = textwrap.dedent(self.source_tag.split("        run: |\n", 1)[1])
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_tag_lookup_fails_closed_and_resolves_annotated_tags(self) -> None:
        self.assertIn('status="$(curl', self.source_tag)
        self.assertIn("404)", self.source_tag)
        self.assertIn("Could not inspect development tag", self.source_tag)
        self.assertIn("resolve_tag_commit()", self.source_tag)
        self.assertIn('while [[ "$object_type" == "tag" ]]', self.source_tag)
        self.assertIn('current_sha="$(resolve_tag_commit)"', self.source_tag)
        self.assertNotIn("2>/dev/null", self.source_tag)

    def test_source_release_uses_the_exact_tag_created_for_the_successful_ci_run(self) -> None:
        self.assertIn("source-ref: ${{ needs.create-development-tag.outputs.source_ref }}", self.workflow)
        self.assertIn("SOURCE_SHA: ${{ github.event.workflow_run.head_sha }}", self.source_tag)

    def test_every_successful_ci_push_gets_a_unique_source_only_development_tag(self) -> None:
        self.assertIn("workflow_run.name == 'CI'", self.source_tag)
        self.assertNotIn("head_branch != 'main'", self.source_tag)
        self.assertIn("v0.0.0-dev.$SOURCE_RUN_NUMBER", self.source_tag)
        self.assertIn("changelog-missing-policy: warn", self.workflow)
        self.assertIn("release-notes-mode: section", self.workflow)

    def test_main_uses_the_reusable_rolling_product_workflow_only_after_product_acceptance(self) -> None:
        self.assertIn("workflow_run.name == 'Product Acceptance'", self.rolling)
        self.assertIn("head_branch == 'main'", self.rolling)
        self.assertIn("m-mdy-m/pipeline/.github/workflows/rolling-release.yml@", self.rolling)
        self.assertIn("source-run-id: ${{ github.event.workflow_run.id }}", self.rolling)
        self.assertIn("source-sha: ${{ github.event.workflow_run.head_sha }}", self.rolling)
        self.assertIn("artifact-pattern: \"cdin-installed-product-*\"", self.rolling)
        self.assertNotIn("release-token:", self.rolling)
        self.assertIn("contents: write", self.rolling)
        self.assertIn("actions: read", self.rolling)


    def test_normal_ci_on_main_cannot_publish_the_product_rolling_channel(self) -> None:
        self.assertNotIn("workflow_run.name == 'CI'", self.rolling)
        self.assertIn("workflow_run.name == 'Product Acceptance'", self.rolling)

    def test_rolling_channel_requires_all_five_targets_and_both_profiles(self) -> None:
        for target in (
            "linux-x86_64",
            "linux-arm64",
            "macos-x86_64",
            "macos-arm64",
            "windows-x86_64",
        ):
            for profile in ("tui", "gui-sdl"):
                with self.subTest(target=target, profile=profile):
                    self.assertIn(
                        f'{{"target":"{target}","profile":"{profile}"}}',
                        self.rolling,
                    )

    def test_rolling_workflow_and_pipeline_helper_use_the_same_immutable_commit(self) -> None:
        workflow_line = next(
            line.strip()
            for line in self.rolling.splitlines()
            if line.strip().startswith(
                "uses: m-mdy-m/pipeline/.github/workflows/rolling-release.yml@"
            )
        )
        helper_line = next(
            line.strip()
            for line in self.rolling.splitlines()
            if line.strip().startswith("pipeline-ref:")
        )
        workflow_ref = workflow_line.rsplit("@", 1)[1]
        helper_ref = helper_line.split(":", 1)[1].strip()
        self.assertEqual(workflow_ref, helper_ref)
        self.assertEqual(workflow_ref, "0f8c5a460932030b95d6f04b089eaf968df8c064")

    def test_rolling_channel_uses_the_explicit_product_acceptance_workflow_path(self) -> None:
        self.assertIn(
            "source-workflow-path: .github/workflows/product-acceptance.yml",
            self.rolling,
        )
        self.assertIn(
            'workflows: ["CI", "Product Acceptance"]',
            self.workflow,
        )

    def test_rolling_release_keeps_fixed_latest_separate_from_semver_tags(self) -> None:
        self.assertIn("rolling-release.yml@", self.rolling)
        self.assertNotIn("v0.0.0-dev", self.rolling)


if __name__ == "__main__":
    unittest.main()
