#!/usr/bin/env python3
"""Guard CDIN's native product matrix against architecture coverage regressions."""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PRODUCT_ACCEPTANCE_WORKFLOW = ROOT / ".github" / "workflows" / "product-acceptance.yml"

EXPECTED_TARGETS = {
    "linux-x86_64": "ubuntu-24.04",
    "linux-arm64": "ubuntu-24.04-arm",
    "macos-arm64": "macos-latest",
    "macos-x86_64": "macos-15-intel",
    "windows-x86_64": "windows-latest",
}
EXPECTED_PROFILES = {"tui", "gui-sdl"}


class NativeProductMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(
            r"(?ms)^        include:\n(?P<entries>(?:          - target: [^\n]+\n"
            r"(?:            [^\n]*\n)*)+)",
            cls.workflow,
        )
        if match is None:
            raise AssertionError("full-stack native target matrix is missing")
        entries = re.findall(
            r"(?ms)^          - target: ([^\n]+)\n((?:            [^\n]*\n)*)",
            match.group("entries"),
        )
        cls.matrix = []
        for target, body in entries:
            os_match = re.search(r"^            os: ([^\n]+)$", body, re.MULTILINE)
            profile_match = re.search(
                r"^            profile: (tui|gui-sdl)$", body, re.MULTILINE
            )
            if os_match is None or profile_match is None:
                raise AssertionError(f"incomplete matrix entry for {target}")
            cls.matrix.append((target, os_match.group(1), profile_match.group(1)))

    def test_each_supported_native_target_runs_both_profiles(self) -> None:
        actual = {(target, profile) for target, _, profile in self.matrix}
        expected = {
            (target, profile)
            for target in EXPECTED_TARGETS
            for profile in EXPECTED_PROFILES
        }
        self.assertEqual(actual, expected)
        self.assertEqual(len(self.matrix), 10)

    def test_runner_labels_match_the_declared_architecture(self) -> None:
        for target, runner, _ in self.matrix:
            self.assertEqual(runner, EXPECTED_TARGETS[target], target)

    def test_linux_distribution_builds_use_the_glibc_239_baseline(self) -> None:
        linux_x86 = {
            runner for target, runner, _ in self.matrix if target == "linux-x86_64"
        }
        self.assertEqual(linux_x86, {"ubuntu-24.04"})

        acceptance = PRODUCT_ACCEPTANCE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("target: linux-x86_64\n            os: ubuntu-24.04", acceptance)
        self.assertIn("target: linux-arm64\n            os: ubuntu-24.04-arm", acceptance)

    def test_each_matrix_job_verifies_its_actual_host_and_windows_abi(self) -> None:
        self.assertIn("CDIN_EXPECTED_TARGET: ${{ matrix.target }}", self.workflow)
        self.assertIn("Verify native runner target identity", self.workflow)
        self.assertIn("platform.machine().lower()", self.workflow)
        self.assertIn('os.environ.get("MSYSTEM") != "UCRT64"', self.workflow)

    def test_hosted_cross_repository_api_access_requires_the_read_only_secret(self) -> None:
        for path in (WORKFLOW, PRODUCT_ACCEPTANCE_WORKFLOW):
            with self.subTest(workflow=path.name):
                content = path.read_text(encoding="utf-8")
                self.assertIn(
                    "CDIN_GITHUB_API_TOKEN: ${{ secrets.CDIN_GITHUB_READ_TOKEN }}",
                    content,
                )
                self.assertIn(
                    "REGISTRY_GITHUB_API_TOKEN: ${{ secrets.CDIN_GITHUB_READ_TOKEN }}",
                    content,
                )
                self.assertIn("GH_TOKEN: ${{ github.token }}", content)
                self.assertIn(
                    "::error::CDIN_GITHUB_READ_TOKEN is required for the parallel cross-repository Release/tag matrix.",
                    content,
                )
                self.assertIn("exit 1", content)
                self.assertNotIn(
                    "GH_TOKEN: ${{ secrets.CDIN_GITHUB_READ_TOKEN }}",
                    content,
                )
                preflight = content.index("Verify cross-repository GitHub read token")
                checkout = content.index("actions/checkout@")
                self.assertGreater(preflight, checkout, path.name)
                if path == WORKFLOW:
                    first_build_setup = content.index("Install native build dependencies (Linux)")
                    sanitizer_setup = content.index("Install native dependencies")
                    self.assertLess(preflight, first_build_setup)
                    sanitizer_preflight = content.index(
                        "Verify cross-repository GitHub read token", preflight + 1
                    )
                    sanitizer_checkout = content.index(
                        "actions/checkout@", checkout + 1
                    )
                    self.assertGreater(sanitizer_preflight, sanitizer_checkout)
                    self.assertLess(sanitizer_preflight, sanitizer_setup)
                else:
                    self.assertLess(preflight, content.index("Set up MSYS2 UCRT64"))
                    self.assertLess(preflight, content.index("Install Linux build dependencies"))
                    self.assertLess(preflight, content.index("Install macOS build dependencies"))

        # The source-build/sanitizer job has its own runner and must be guarded too.
        self.assertEqual(
            self.workflow.count(
                "::error::CDIN_GITHUB_READ_TOKEN is required for the parallel cross-repository Release/tag matrix."
            ),
            2,
        )

    def test_matrix_artifacts_are_unique_per_target_and_profile(self) -> None:
        for artifact in (
            "cdin-headless-benchmark",
            "cdin-source-snapshot",
            "cdin-installed-product",
        ):
            self.assertIn(
                f"name: {artifact}-${{{{ matrix.target }}}}-${{{{ matrix.profile }}}}",
                self.workflow,
            )
            self.assertNotIn(
                f"name: {artifact}-${{{{ runner.os }}}}-${{{{ matrix.profile }}}}",
                self.workflow,
            )


if __name__ == "__main__":
    unittest.main()
