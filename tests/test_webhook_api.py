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

    def test_ai_research_payload_maps_to_report(self):
        report = simple_api._ai_research_report_from_payload(
            payload={
                "research_date": "2026-07-13",
                "title": "A股盘前消息简报：2026-07-13",
                "summary": "外围风险偏好中性，关注半导体映射。",
                "markdown": "# A股盘前消息简报：2026-07-13\n\n## 1. 盘前结论\n- 主看：半导体。",
                "sources": [{"title": "Reuters market wrap", "url": "https://example.com"}],
                "tags": ["盘前", "半导体"],
            },
            headers={"x-ai-research-secret": "secret", "user-agent": "unit-test"},
            source_ip="127.0.0.1",
            request_id="req-ai",
        )

        self.assertEqual(report["research_date"], "2026-07-13")
        self.assertEqual(report["title"], "A股盘前消息简报：2026-07-13")
        self.assertEqual(report["event_type"], "ai_research.report")
        self.assertIn("盘前结论", report["markdown"])
        self.assertEqual(report["sources"][0]["title"], "Reuters market wrap")
        self.assertIn("盘前", report["tags"])
        self.assertNotIn("x-ai-research-secret", report["headers"])

    def test_ai_research_payload_rejects_suspected_encoding_damage(self):
        with self.assertRaisesRegex(ValueError, "character encoding damage"):
            simple_api._ai_research_report_from_payload(
                payload={
                    "research_date": "2026-07-13",
                    "title": "A???????:2026-07-13",
                    "markdown": "# ??????",
                },
                headers={},
                source_ip="127.0.0.1",
                request_id="req-ai-corrupt",
            )

    def test_ai_research_payload_keeps_decision_product_fields(self):
        report = simple_api._ai_research_report_from_payload(
            payload={
                "research_date": "2026-07-10",
                "title": "A股盘前消息简报：2026-07-10",
                "summary": "主线、验证点、失效点。",
                "markdown": "# A股盘前消息简报：2026-07-10",
                "decision_cards": [{"title": "科技成长", "trigger": "09:35成交确认"}],
                "evidence_table": [{"event": "隔夜美股科技反弹", "confidence": "中"}],
                "watchlist": [{"name": "科创50", "check_time": "09:35"}],
                "scenario_plan": [{"scenario": "高开回落", "action": "降低追高"}],
                "risk_calendar": [{"time": "盘前", "event": "A50"}],
                "data_gaps": ["缺少板块广度数据"],
                "institutional_research": [{"institution": "Goldman Sachs", "industry": "semiconductors", "title": "AI hardware outlook"}],
            },
            headers={"user-agent": "unit-test"},
            source_ip="127.0.0.1",
            request_id="req-ai-product",
        )

        public = simple_api._ai_research_public_report(report)

        self.assertEqual(public["decision_cards"][0]["title"], "科技成长")
        self.assertEqual(public["evidence_table"][0]["event"], "隔夜美股科技反弹")
        self.assertEqual(public["watchlist"][0]["name"], "科创50")
        self.assertEqual(public["scenario_plan"][0]["scenario"], "高开回落")
        self.assertEqual(public["risk_calendar"][0]["event"], "A50")
        self.assertEqual(public["data_gaps"], ["缺少板块广度数据"])
        self.assertEqual(public["institutional_research"][0]["institution"], "Goldman Sachs")

    def test_recent_ai_research_summaries_read_newest_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_dir = root / "first"
            second_dir = root / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            (first_dir / simple_api.AI_RESEARCH_REPORT_NAME).write_text(
                '{"run_id":"first","title":"first report","summary":"old","research_date":"2026-07-12","received_at":"2026-07-12 08:30:00"}',
                encoding="utf-8",
            )
            (second_dir / simple_api.AI_RESEARCH_REPORT_NAME).write_text(
                '{"run_id":"second","title":"second report","summary":"new","research_date":"2026-07-13","received_at":"2026-07-13 08:30:00"}',
                encoding="utf-8",
            )
            with patch.object(simple_api, "AI_RESEARCH_REPORT_DIR", root):
                reports = simple_api._recent_ai_research_report_summaries(limit=2)

        self.assertEqual([item["run_id"] for item in reports], ["second", "first"])
        self.assertEqual(reports[0]["report_route"], "/ai-research/report/second")

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

    def test_auction_strength_billing_only_treats_current_date_as_paid_view(self):
        today = simple_api.datetime.now(simple_api.CN_TZ).date().isoformat()

        self.assertTrue(simple_api._is_today_trade_date(today))
        self.assertFalse(simple_api._is_today_trade_date("2000-01-01"))
        self.assertFalse(simple_api._is_today_trade_date(""))

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
