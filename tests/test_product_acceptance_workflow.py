"""Protect the clean product acceptance workflow and its PR concurrency behavior."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "product-acceptance.yml"


class ProductAcceptanceWorkflowTests(unittest.TestCase):
    def test_artifact_first_changes_run_acceptance_on_pull_requests(self) -> None:
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  pull_request:\n", content)
        for path in (
            '"deps.lock"',
            '"registry/**"',
            '"scripts/registry.py"',
            '"scripts/registry_artifact.py"',
            '"tests/test_registry_artifact.py"',
        ):
            with self.subTest(path=path):
                self.assertIn(path, content)

    def test_new_pull_request_revision_replaces_only_stale_pr_acceptance(self) -> None:
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("group: product-acceptance-${{ github.ref }}", content)
        self.assertIn(
            "cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
            content,
        )
        self.assertIn("  push:\n    branches: [main]", content)
        self.assertIn("  workflow_dispatch:", content)


if __name__ == "__main__":
    unittest.main()
