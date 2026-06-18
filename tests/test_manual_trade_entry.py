from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from trade_review_agent.api.simple_api import _manual_trade_from_fields, _write_manual_trade_csv


class ManualTradeEntryTest(unittest.TestCase):
    def test_manual_trade_fields_map_to_trade_csv(self) -> None:
        trade = _manual_trade_from_fields(
            {
                "manual_trade": "1",
                "manual_stock_name": "\u4e1c\u6750\u79d1\u6280",
                "manual_trade_at": "2026-06-09T09:25:30",
                "manual_price": "58.71",
                "manual_side": "buy",
            }
        )

        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual(trade["trade_date"], "2026-06-09")
        self.assertEqual(trade["trade_time"], "09:25:30")
        self.assertEqual(trade["code"], "601208")
        self.assertEqual(trade["name"], "\u4e1c\u6750\u79d1\u6280")
        self.assertEqual(trade["side"], "buy")
        self.assertEqual(trade["price"], 58.71)
        self.assertIn("price=58.71", trade["source_text"])

        with tempfile.TemporaryDirectory() as temp_dir:
            output = _write_manual_trade_csv(trade, Path(temp_dir) / "ai_trades.csv")
            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trade_date"], "2026-06-09")
        self.assertEqual(rows[0]["trade_time"], "09:25:30")
        self.assertEqual(rows[0]["code"], "601208")
        self.assertEqual(rows[0]["price"], "58.71")
        self.assertNotIn("quantity", rows[0])
        self.assertNotIn("amount", rows[0])
        self.assertEqual(rows[0]["source_text"], "manual input; name=东材科技; code=601208; price=58.71")

    def test_manual_trade_allows_unresolved_stock_code(self) -> None:
        trade = _manual_trade_from_fields(
            {
                "manual_trade": "1",
                "manual_stock_name": "\u4e0d\u5b58\u5728\u6d4b\u8bd5\u80a1",
                "manual_trade_at": "2026-06-09T09:25:00",
                "manual_price": "12.34",
                "manual_side": "buy",
            }
        )

        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual(trade["name"], "\u4e0d\u5b58\u5728\u6d4b\u8bd5\u80a1")
        self.assertEqual(trade["code"], "")
        self.assertEqual(trade["price"], 12.34)
        self.assertIn("code=not resolved", trade["source_text"])


if __name__ == "__main__":
    unittest.main()
