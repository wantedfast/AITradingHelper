import tempfile
import unittest
from pathlib import Path

from trade_review_agent.auth_system import AuthError
from trade_review_agent.api import simple_api


class WebhookApiTest(unittest.TestCase):
    def test_webhook_payload_is_normalized_for_frontend(self):
        event = simple_api._webhook_event_from_request(
            payload={
                "source": "tradingview",
                "event_type": "alert.created",
                "title": "突破观察位",
                "summary": "600584 已触发 webhook。",
            },
            headers={"user-agent": "unit-test", "authorization": "Bearer secret"},
            source_ip="127.0.0.1",
            request_id="req-1",
        )

        self.assertEqual(event["source"], "tradingview")
        self.assertEqual(event["event_type"], "alert.created")
        self.assertEqual(event["title"], "突破观察位")
        self.assertEqual(event["summary"], "600584 已触发 webhook。")
        self.assertEqual(event["source_ip"], "127.0.0.1")
        self.assertNotIn("authorization", event["headers"])

    def test_webhook_secret_accepts_header_or_query_token(self):
        simple_api._assert_webhook_secret(expected="abc", header_value="abc", query="")
        simple_api._assert_webhook_secret(expected="abc", header_value="", query="token=abc")

        with self.assertRaises(AuthError):
            simple_api._assert_webhook_secret(expected="abc", header_value="wrong", query="")

    def test_recent_webhook_events_reads_newest_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "webhooks.jsonl"
            first = simple_api._webhook_event_from_request(
                payload={"title": "first"},
                headers={},
                source_ip="127.0.0.1",
                request_id="req-1",
            )
            second = simple_api._webhook_event_from_request(
                payload={"title": "second"},
                headers={},
                source_ip="127.0.0.1",
                request_id="req-2",
            )
            simple_api._append_webhook_event(path, first)
            simple_api._append_webhook_event(path, second)

            events = simple_api._recent_webhook_events(path, limit=1)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "second")
        self.assertEqual(events[0]["request_id"], "req-2")

    def test_auction_strength_payload_maps_to_frontend_report(self):
        report = simple_api._auction_strength_report_from_payload(
            payload={
                "trade_date": "2026-06-17",
                "analysis_time": "09:25集合竞价后",
                "summary": {
                    "one_sentence": "强题材核心高开。",
                    "selection_logic": "先看题材，再看竞价姿态。",
                    "data_limit": "缺失封单。",
                },
                "top5_strong_stocks": [
                    {
                        "rank": 1,
                        "code": "001257",
                        "name": "盛龙股份",
                        "theme": "有色金属/小金属",
                        "today_open_change": "4.29",
                        "label": "昨日龙头延续",
                        "theme_level": "竞价超预期主线",
                        "reason": "确定性最强。",
                        "observe_after_930": "看承接。",
                    }
                ],
                "top5_avoid_stocks": [
                    {
                        "rank": 1,
                        "code": "603045",
                        "name": "福达合金",
                        "theme": "算力/数据中心",
                        "today_open_change": "-5.86",
                        "label": "龙头负反馈",
                        "theme_level": "竞价超预期主线",
                        "reason": "后排出逃。",
                        "risk_after_930": "警惕杀跌。",
                    }
                ],
                "global_conclusion": {
                    "strongest_stock_at_925": "盛龙股份",
                    "strongest_theme_cluster": "有色金属/小金属",
                    "most_over_expected_stock": "常铝股份",
                    "best_capacity_confirmation": "厦门钨业",
                    "biggest_negative_feedback": "福达合金",
                    "one_sentence_for_930": "紧盯承接。",
                },
            },
            source_ip="127.0.0.1",
            request_id="req-auction",
        )

        public = simple_api._auction_strength_public_report(report)

        self.assertEqual(public["trade_date"], "2026-06-17")
        self.assertEqual(public["summary"]["one_sentence"], "强题材核心高开。")
        self.assertEqual(public["top5_strong_stocks"][0]["name"], "盛龙股份")
        self.assertEqual(public["top5_strong_stocks"][0]["observe_after_930"], "看承接。")
        self.assertEqual(public["top5_avoid_stocks"][0]["name"], "福达合金")
        self.assertEqual(public["top5_avoid_stocks"][0]["risk_after_930"], "警惕杀跌。")
        self.assertEqual(public["global_conclusion"]["strongest_theme_cluster"], "有色金属/小金属")

    def test_recent_auction_strength_reports_reads_newest_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "auction.jsonl"
            first = simple_api._auction_strength_report_from_payload(
                payload={"trade_date": "2026-06-16", "global_conclusion": {"strongest_stock_at_925": "first"}},
                source_ip="127.0.0.1",
                request_id="req-1",
            )
            second = simple_api._auction_strength_report_from_payload(
                payload={"trade_date": "2026-06-17", "global_conclusion": {"strongest_stock_at_925": "second"}},
                source_ip="127.0.0.1",
                request_id="req-2",
            )
            simple_api._append_webhook_event(path, first)
            simple_api._append_webhook_event(path, second)

            reports = simple_api._recent_auction_strength_reports(path, limit=1)

        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["trade_date"], "2026-06-17")
        self.assertEqual(reports[0]["global_conclusion"]["strongest_stock_at_925"], "second")

    def test_recent_auction_strength_reports_filters_by_trade_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "auction.jsonl"
            first = simple_api._auction_strength_report_from_payload(
                payload={"trade_date": "2026-06-16", "global_conclusion": {"strongest_stock_at_925": "first"}},
                source_ip="127.0.0.1",
                request_id="req-1",
            )
            second = simple_api._auction_strength_report_from_payload(
                payload={"trade_date": "2026-06-17", "global_conclusion": {"strongest_stock_at_925": "second"}},
                source_ip="127.0.0.1",
                request_id="req-2",
            )
            third = simple_api._auction_strength_report_from_payload(
                payload={"trade_date": "2026-06-17", "global_conclusion": {"strongest_stock_at_925": "third"}},
                source_ip="127.0.0.1",
                request_id="req-3",
            )
            simple_api._append_webhook_event(path, first)
            simple_api._append_webhook_event(path, second)
            simple_api._append_webhook_event(path, third)

            reports = simple_api._recent_auction_strength_reports(path, limit=20, trade_date="2026-06-17")
            filtered_total = simple_api._auction_strength_report_count(path, trade_date="2026-06-17")
            overall_total = simple_api._auction_strength_report_count(path)

        self.assertEqual([report["request_id"] for report in reports], ["req-3", "req-2"])
        self.assertEqual(filtered_total, 2)
        self.assertEqual(overall_total, 3)


if __name__ == "__main__":
    unittest.main()
