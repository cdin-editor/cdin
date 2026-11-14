from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scripts.deps import github_api_token_from_environment


class GitHubAPITokenSelectionTests(unittest.TestCase):
    def test_explicit_cdin_token_has_priority(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GITHUB_ACTIONS": "true",
                "CDIN_GITHUB_API_TOKEN": "cdin-read-token",
                "GH_TOKEN": "generic-read-token",
                "GITHUB_TOKEN": "repo-scoped-token",
            },
            clear=True,
        ):
            self.assertEqual(github_api_token_from_environment(), "cdin-read-token")

    def test_gh_token_is_used_in_actions(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GITHUB_ACTIONS": "true",
                "GH_TOKEN": "cross-repository-read-token",
                "GITHUB_TOKEN": "repo-scoped-token",
            },
            clear=True,
        ):
            self.assertEqual(
                github_api_token_from_environment(),
                "cross-repository-read-token",
            )

    def test_automatic_actions_token_is_not_used_for_kernel_api(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GITHUB_ACTIONS": "true",
                "GITHUB_TOKEN": "cdin-repository-token",
            },
            clear=True,
        ):
            self.assertEqual(github_api_token_from_environment(), "")

    def test_local_github_token_fallback_is_preserved(self) -> None:
        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": " local-personal-token "},
            clear=True,
        ):
            self.assertEqual(
                github_api_token_from_environment(),
                "local-personal-token",
            )

    def test_gh_token_precedes_local_github_token(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GH_TOKEN": "gh-cli-token",
                "GITHUB_TOKEN": "local-github-token",
            },
            clear=True,
        ):
            self.assertEqual(github_api_token_from_environment(), "gh-cli-token")


if __name__ == "__main__":
    unittest.main()
