import tempfile
import unittest
from pathlib import Path

import pandas as pd

from trade_review_agent.auction_strength.top1_performance import (
    auction_top1_performance_payload,
    refresh_top1_performance,
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


class EventuallyReadyProvider:
    def __init__(self):
        self.calls = 0

    def stock_daily(self, code, start, end):
        self.calls += 1
        if self.calls == 1:
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
                ]
            )
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
        self.assertEqual(payload["best_trade"]["code"], "600353")
        self.assertEqual(payload["best_trade"]["return_text"], "+11.35%")

    def test_auction_report_extracts_top5_first_and_calculates_next_trade_day_high_return(self):
        top1 = top1_from_auction_report(
            {
                "trade_date": "2026-06-26",
                "global_conclusion": {"strongest_stock_at_925": "000002 vanke"},
                "top5_strong_stocks": [
                    {"rank": 1, "code": "000001", "name": "pingan"},
                    {"rank": 2, "code": "000002", "name": "vanke"},
                ],
            }
        )
        record = resolve_top1_performance(top1, provider=FakeProvider())

        self.assertEqual(top1["code"], "000001")
        self.assertEqual(record["trade_date"], "2026-06-26")
        self.assertEqual(record["code"], "000001")
        self.assertEqual(record["buy_price"], 10.0)
        self.assertEqual(record["sell_date"], "2026-06-29")
        self.assertEqual(record["sell_price"], 11.5)
        self.assertEqual(record["return_pct"], 15.0)
        self.assertEqual(record["result"], "win")

    def test_pending_top1_record_is_retried_until_completed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            auction_path = root / "auction.jsonl"
            performance_path = root / "performance.jsonl"
            auction_path.write_text(
                '{"trade_date":"2026-06-26","top5_strong_stocks":[{"code":"000001","name":"pingan"}]}\n',
                encoding="utf-8",
            )
            provider = EventuallyReadyProvider()

            first = refresh_top1_performance(
                auction_reports_path=auction_path,
                performance_path=performance_path,
                cache_db=root / "cache.sqlite",
                provider=provider,
            )
            second = refresh_top1_performance(
                auction_reports_path=auction_path,
                performance_path=performance_path,
                cache_db=root / "cache.sqlite",
                provider=provider,
            )
            payload = auction_top1_performance_payload(
                performance_path=performance_path,
                auction_reports_path=auction_path,
                cache_db=root / "cache.sqlite",
                refresh=False,
            )

        self.assertEqual(first[0]["status"], "pending")
        self.assertEqual(second[0]["status"], "completed")
        self.assertEqual(second[0]["return_pct"], 15.0)
        self.assertEqual(payload["rows"][-1]["trade_date"], "2026-06-26")
        self.assertEqual(payload["rows"][-1]["return_text"], "+15.00%")

    def test_payload_filters_stale_webhook_records_that_no_longer_match_top1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            auction_path = root / "auction.jsonl"
            performance_path = root / "performance.jsonl"
            auction_path.write_text(
                '{"trade_date":"2026-06-30","top5_strong_stocks":[{"code":"000001","name":"pingan"},{"code":"000002","name":"vanke"}]}\n',
                encoding="utf-8",
            )
            performance_path.write_text(
                "\n".join(
                    [
                        '{"trade_date":"2026-06-30","code":"000001","name":"pingan","buy_price":10,"sell_date":"2026-07-01","sell_price":11,"return_pct":10,"result":"win","source":"auction_strength_webhook","status":"completed"}',
                        '{"trade_date":"2026-06-30","code":"000002","name":"vanke","buy_price":10,"sell_date":"2026-07-01","sell_price":12,"return_pct":20,"result":"win","source":"auction_strength_webhook","status":"completed"}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = auction_top1_performance_payload(
                performance_path=performance_path,
                auction_reports_path=auction_path,
                cache_db=root / "cache.sqlite",
                refresh=False,
            )

        webhook_rows = [row for row in payload["rows"] if row["source"] == "auction_strength_webhook"]
        self.assertEqual(len(webhook_rows), 1)
        self.assertEqual(webhook_rows[0]["code"], "000001")
        self.assertEqual(webhook_rows[0]["return_text"], "+10.00%")


if __name__ == "__main__":
    unittest.main()
