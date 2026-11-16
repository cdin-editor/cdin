"""Tests for the public Kernel SDK Release bootstrap contract."""
from __future__ import annotations

import unittest

from scripts.deps import (
    SDKBootstrapError,
    release_asset_download_url,
    verify_locked_asset_identity,
)


class PublicKernelReleaseURLTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pin = {
            "repository": "https://github.com/cdin-editor/kernel",
            "tag": "v1.2.3",
            "version": "1.2.3",
            "revision": "2fb09f52dc1a9963cf358ec54d584c520e174e67",
        }
        self.asset = {
            "file_name": "cdin-kernel-1.2.3-linux-x86_64.tar.gz",
            "format": "tar.gz",
            "size_bytes": 381038,
            "sha256": "48a82eb7f4c1fac57c7661f070c1338eb17c10d709eff0d87bb0229b87e46013",
        }

    def test_uses_the_public_release_download_endpoint(self) -> None:
        self.assertEqual(
            release_asset_download_url(self.pin, self.asset),
            "https://github.com/cdin-editor/kernel/releases/download/"
            "v1.2.3/cdin-kernel-1.2.3-linux-x86_64.tar.gz",
        )

    def test_refuses_a_release_from_another_repository(self) -> None:
        pin = dict(self.pin, repository="https://example.invalid/kernel")
        with self.assertRaisesRegex(SDKBootstrapError, "repository pin is invalid"):
            verify_locked_asset_identity(pin, self.asset)

    def test_refuses_a_tag_or_commit_that_does_not_match_the_versioned_pin(self) -> None:
        pin = dict(self.pin, tag="v1.2.2")
        with self.assertRaisesRegex(SDKBootstrapError, "tag/version/source revision pin is invalid"):
            verify_locked_asset_identity(pin, self.asset)

    def test_refuses_path_traversal_and_bad_digests(self) -> None:
        bad_path = dict(self.asset, file_name="../archive.tar.gz")
        with self.assertRaisesRegex(SDKBootstrapError, "locked asset identity is malformed"):
            verify_locked_asset_identity(self.pin, bad_path)
        bad_digest = dict(self.asset, sha256="not-a-sha256")
        with self.assertRaisesRegex(SDKBootstrapError, "locked asset identity is malformed"):
            verify_locked_asset_identity(self.pin, bad_digest)


if __name__ == "__main__":
    unittest.main()
