from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark import parse_linux_rss, percentile  # noqa: E402


class BenchmarkTests(unittest.TestCase):
    def test_percentile_interpolates_between_ordered_samples(self) -> None:
        self.assertEqual(percentile([9.0, 1.0, 5.0], 0.5), 5.0)
        self.assertAlmostEqual(percentile([1.0, 2.0, 3.0, 4.0], 0.95), 3.85)
        self.assertEqual(percentile([7.0], 0.99), 7.0)

    def test_percentile_rejects_empty_input(self) -> None:
        with self.assertRaises(ValueError):
            percentile([], 0.5)

    def test_percentile_rejects_invalid_quantile(self) -> None:
        with self.assertRaises(ValueError):
            percentile([1.0], 1.01)

    def test_linux_rss_parser_converts_kibibytes_to_bytes(self) -> None:
        status = "Name:\\tcdin\nVmPeak:\\t12345 kB\nVmRSS:\\t2048 kB\n"
        self.assertEqual(parse_linux_rss(status), 2 * 1024 * 1024)

    def test_linux_rss_parser_reports_missing_or_unknown_units(self) -> None:
        self.assertIsNone(parse_linux_rss("Name:\\tcdin\nVmSize:\\t10 kB\n"))
        self.assertIsNone(parse_linux_rss("VmRSS:\\t10 widgets\n"))


if __name__ == "__main__":
    unittest.main()
