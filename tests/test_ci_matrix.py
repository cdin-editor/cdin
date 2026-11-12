#!/usr/bin/env python3
"""Guard CDIN's native product matrix against architecture coverage regressions."""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

EXPECTED_TARGETS = {
    "linux-x86_64": "ubuntu-latest",
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

    def test_each_matrix_job_verifies_its_actual_host_and_windows_abi(self) -> None:
        self.assertIn("CDIN_EXPECTED_TARGET: ${{ matrix.target }}", self.workflow)
        self.assertIn("Verify native runner target identity", self.workflow)
        self.assertIn("platform.machine().lower()", self.workflow)
        self.assertIn('os.environ.get("MSYSTEM") != "UCRT64"', self.workflow)

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
