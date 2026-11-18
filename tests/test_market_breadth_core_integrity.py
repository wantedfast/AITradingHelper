from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA256 = {
    "breadth.mjs": "b64891f2c39d2707bb5ee36fc6ec77416fe636ddb5aeaca8ff1668222bb3b235",
    "backtest.mjs": "9d0e7f16e45cce06d2f435bd52574396381fb49e551d758cfa8cd6e7779ff28b",
}


class MarketBreadthCoreIntegrityTest(unittest.TestCase):
    def test_handoff_core_files_are_byte_for_byte_unchanged(self) -> None:
        for name, expected in EXPECTED_SHA256.items():
            with self.subTest(name=name):
                # Git commits these source files with LF. Windows checkouts may use
                # CRLF, so hash the bytes exactly as they will be committed.
                committed_bytes = (ROOT / "market_breadth" / name).read_bytes().replace(
                    b"\r\n", b"\n"
                )
                actual = hashlib.sha256(committed_bytes).hexdigest()
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
