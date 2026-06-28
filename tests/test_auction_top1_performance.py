import tempfile
import unittest
from pathlib import Path

import pandas as pd

from trade_review_agent.auction_strength.top1_performance import (
    auction_top1_performance_payload,
    resolve_top1_performance,
    top1_from_auction_report,
)


class FakeProvider:
    def stock_daily(self, code, start, end):
        return pd.DataFrame(
            [
                {
                    "symbol": code,
                    "trade_date": pd.Timestamp("2026-06-26").date(),
                    "open": 10.0,
                    "close": 10.5,
                    "high": 10.8,
                    "low": 9.8,
                },
                {
                    "symbol": code,
                    "trade_date": pd.Timestamp("2026-06-29").date(),
                    "open": 10.7,
                    "close": 11.0,
                    "high": 11.5,
                    "low": 10.6,
                },
            ]
        )


class AuctionTop1PerformanceTest(unittest.TestCase):
    def test_seed_payload_uses_all_samples_for_win_rate_and_recent_five_for_average(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = auction_top1_performance_payload(
                performance_path=root / "performance.jsonl",
                auction_reports_path=root / "auction.jsonl",
                cache_db=root / "cache.sqlite",
                refresh=False,
            )

        self.assertEqual(payload["sample_count"], 7)
        self.assertEqual(payload["win_count"], 7)
        self.assertEqual(payload["win_rate_text"], "100.0%")
        self.assertEqual(payload["recent_5_avg_return_text"], "+7.92%")
        self.assertEqual(payload["best_trade"]["name"], "旭光电子")
        self.assertEqual(payload["best_trade"]["return_text"], "+11.35%")

    def test_auction_report_extracts_top1_and_calculates_next_trade_day_high_return(self):
        top1 = top1_from_auction_report(
            {
                "trade_date": "2026-06-26",
                "top5_strong_stocks": [
                    {"rank": 1, "code": "000001", "name": "平安银行"},
                    {"rank": 2, "code": "000002", "name": "万科A"},
                ],
            }
        )
        record = resolve_top1_performance(top1, provider=FakeProvider())

        self.assertEqual(record["trade_date"], "2026-06-26")
        self.assertEqual(record["code"], "000001")
        self.assertEqual(record["buy_price"], 10.0)
        self.assertEqual(record["sell_date"], "2026-06-29")
        self.assertEqual(record["sell_price"], 11.5)
        self.assertEqual(record["return_pct"], 15.0)
        self.assertEqual(record["result"], "win")


if __name__ == "__main__":
    unittest.main()
