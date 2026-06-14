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
                "manual_stock_name": "东材科技",
                "manual_trade_at": "2026-06-09T09:25:30",
                "manual_side": "buy",
            }
        )

        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual(trade["trade_date"], "2026-06-09")
        self.assertEqual(trade["trade_time"], "09:25:30")
        self.assertEqual(trade["code"], "601208")
        self.assertEqual(trade["name"], "东材科技")
        self.assertEqual(trade["side"], "buy")
        self.assertEqual(trade["quantity"], 1.0)
        self.assertIn("position=not provided", trade["source_text"])

        with tempfile.TemporaryDirectory() as temp_dir:
            output = _write_manual_trade_csv(trade, Path(temp_dir) / "ai_trades.csv")
            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trade_date"], "2026-06-09")
        self.assertEqual(rows[0]["trade_time"], "09:25:30")
        self.assertEqual(rows[0]["code"], "601208")
        self.assertEqual(rows[0]["source_text"], "manual input; position=not provided")


if __name__ == "__main__":
    unittest.main()
