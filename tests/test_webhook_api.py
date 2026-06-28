import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from trade_review_agent.auth_system import AuthError, create_order, init_auth_db
from trade_review_agent.api import simple_api


class WebhookApiTest(unittest.TestCase):
    def _create_payment_user(self, db_path: Path) -> int:
        init_auth_db(db_path)
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO users (
                        phone, username, email, email_verified, password_hash,
                        password_salt, role, status, invite_code, created_at
                    )
                    VALUES (?, ?, ?, 1, 'hash', 'salt', 'user', 'active', ?, ?)
                    """,
                    ("test@example.com", "payuser", "test@example.com", "PAYUSER1", "2026-06-27T10:00:00+08:00"),
                )
                return int(cursor.lastrowid)

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

    def test_jinshuju_webhook_marks_order_paid_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            user_id = self._create_payment_user(db_path)
            order = create_order(db_path, user_id=user_id, package_id="pack_10")
            old_db = simple_api.AUTH_DB
            simple_api.AUTH_DB = db_path
            payload = {
                "form": "form-token-1",
                "entry": {
                    "serial_number": "JSJ-1001",
                    "field_1": order["order_no"],
                    "field_2": "test@example.com",
                    "field_3": "pack_10",
                    "total_price": "9.90",
                },
            }
            try:
                with patch.dict(
                    "os.environ",
                    {
                        "JINSHUJU_FORM_TOKEN": "form-token-1",
                        "JINSHUJU_ORDER_FIELD": "field_1",
                        "JINSHUJU_EMAIL_FIELD": "field_2",
                        "JINSHUJU_PACKAGE_FIELD": "field_3",
                    },
                    clear=False,
                ):
                    first = simple_api._process_jinshuju_payment_webhook(payload)
                    second = simple_api._process_jinshuju_payment_webhook(payload)
            finally:
                simple_api.AUTH_DB = old_db

            with closing(sqlite3.connect(db_path)) as conn:
                paid_order = conn.execute("SELECT * FROM orders WHERE id = ?", (order["id"],)).fetchone()
                balance = conn.execute("SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE user_id = ?", (user_id,)).fetchone()[0]

        self.assertEqual(first["order"]["status"], "paid")
        self.assertEqual(second["order"]["status"], "paid")
        self.assertEqual(paid_order[6], "paid")
        self.assertEqual(balance, 10)

    def test_jinshuju_webhook_rejects_mismatched_amount(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            user_id = self._create_payment_user(db_path)
            order = create_order(db_path, user_id=user_id, package_id="pack_10")
            old_db = simple_api.AUTH_DB
            simple_api.AUTH_DB = db_path
            payload = {
                "form": "form-token-1",
                "entry": {
                    "serial_number": "JSJ-1002",
                    "field_1": order["order_no"],
                    "field_2": "test@example.com",
                    "total_price": "8.80",
                },
            }
            try:
                with patch.dict("os.environ", {"JINSHUJU_FORM_TOKEN": "form-token-1"}, clear=False):
                    with self.assertRaises(AuthError):
                        simple_api._process_jinshuju_payment_webhook(payload)
            finally:
                simple_api.AUTH_DB = old_db

            with closing(sqlite3.connect(db_path)) as conn:
                balance = conn.execute("SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE user_id = ?", (user_id,)).fetchone()[0]

        self.assertEqual(balance, 0)


if __name__ == "__main__":
    unittest.main()
