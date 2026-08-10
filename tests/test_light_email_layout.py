from __future__ import annotations

import gc
import json
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from trade_review_agent import auth_system


FORBIDDEN_EMAIL_SKIN_TOKENS = (
    "#050505",
    "#f4f0e8",
    "#c9a646",
    "#f5d77a",
    "#262113",
    "#e3bd4f",
    "border-radius",
)


def assert_light_email(test_case: unittest.TestCase, html: str) -> None:
    normalized = html.lower()
    test_case.assertIn('name="color-scheme" content="light"', normalized)
    test_case.assertIn('name="supported-color-schemes" content="light"', normalized)
    test_case.assertIn('bgcolor="#ffffff"', normalized)
    test_case.assertIn("background-color:#ffffff", normalized)
    test_case.assertIn("color:#1f2328", normalized)
    for token in FORBIDDEN_EMAIL_SKIN_TOKENS:
        test_case.assertNotIn(token, normalized)


def cleanup_temp_directory(temp_dir: tempfile.TemporaryDirectory[str]) -> None:
    """Let Windows release short-lived SQLite handles before removing fixtures."""
    for attempt in range(5):
        gc.collect()
        try:
            temp_dir.cleanup()
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


class LightEmailLayoutTest(unittest.TestCase):
    def test_verification_email_is_light_and_escapes_code(self) -> None:
        with mock.patch("trade_review_agent.auth_system._send_smtp_message") as send:
            auth_system._send_smtp_email("reader@example.test", "12<345")

        message = send.call_args.kwargs
        assert_light_email(self, message["html"])
        self.assertIn("12&lt;345", message["html"])
        self.assertNotIn("12<345", message["html"])
        self.assertIn("12<345", message["text"])

    def test_credit_added_email_is_light_and_escapes_user_content(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            db_path = Path(temp_dir.name) / "auth.sqlite"
            auth_system.init_auth_db(db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    user_id = int(
                        conn.execute(
                            """
                            INSERT INTO users (
                                phone, username, email, email_verified, password_hash,
                                password_salt, role, status, invite_code, created_at
                            ) VALUES ('light-user', '<User>', 'light@example.test', 1,
                                      'hash', 'salt', 'user', 'active', 'LIGHTMAIL', ?)
                            """,
                            (auth_system._now(),),
                        ).lastrowid
                    )
            with mock.patch("trade_review_agent.auth_system._send_smtp_message") as send:
                result = auth_system.notify_credit_added(
                    db_path, user_id=user_id, credits=10, reason="奖励 <script>alert(1)</script>"
                )
        finally:
            cleanup_temp_directory(temp_dir)

        self.assertTrue(result["sent"])
        message = send.call_args.kwargs
        assert_light_email(self, message["html"])
        self.assertIn("&lt;User&gt;", message["html"])
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", message["html"])
        self.assertNotIn("<script>", message["html"])
        self.assertIn("奖励 <script>alert(1)</script>", message["text"])

    def test_admin_payment_email_is_light_linked_and_escaped(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "ADMIN_PAYMENT_NOTIFY_EMAIL": "admin@example.test",
                "ADMIN_DASHBOARD_URL": "https://trade.example.test/admin?tab=<orders>",
                "EMAIL_PROVIDER": "smtp",
            },
            clear=False,
        ), mock.patch("trade_review_agent.auth_system._send_smtp_message") as send:
            result = auth_system.notify_admin_membership_payment(
                order={
                    "order_no": "ORDER<script>",
                    "plan_name": "年度会员",
                    "amount_cents": 39900,
                    "submitted_amount_cents": 39900,
                    "payment_method": "alipay",
                    "payer_note": "<b>note</b>",
                },
                user={"id": 7, "username": "<member>", "email": "member@example.test"},
            )

        self.assertTrue(result["sent"])
        message = send.call_args.kwargs
        assert_light_email(self, message["html"])
        self.assertIn("color:#0969da", message["html"])
        self.assertIn("text-decoration:underline", message["html"])
        self.assertIn("ORDER&lt;script&gt;", message["html"])
        self.assertIn("&lt;b&gt;note&lt;/b&gt;", message["html"])
        self.assertIn("https://trade.example.test/admin?tab=<orders>", message["text"])

    def test_update_notice_email_is_light_with_plain_url_and_escaped_items(self) -> None:
        delivery = {
            "email": "reader@example.test",
            "title": "产品 <更新>",
            "version": "2026-07-16",
            "items_json": json.dumps(["新增 <script>alert(1)</script>"]),
        }
        with mock.patch.dict(
            os.environ, {"PUBLIC_SITE_URL": "https://trade.example.test"}, clear=False
        ), mock.patch("trade_review_agent.auth_system._send_smtp_message") as send:
            auth_system._send_update_notice_email(delivery)

        message = send.call_args.kwargs
        assert_light_email(self, message["html"])
        self.assertIn("color:#0969da", message["html"])
        self.assertIn("text-decoration:underline", message["html"])
        self.assertIn("产品 &lt;更新&gt;", message["html"])
        self.assertIn("新增 &lt;script&gt;alert(1)&lt;/script&gt;", message["html"])
        self.assertNotIn("<script>alert(1)</script>", message["html"])
        self.assertIn("https://trade.example.test", message["text"])

    def test_daily_top5_full_and_teaser_emails_are_light_and_stacked(self) -> None:
        report = {
            "trade_date": "2026-07-16",
            "analysis_time": "2026-07-16 09:26:00",
            "summary": {"one_sentence": "市场 <script>alert(1)</script> 摘要"},
            "top5_strong_stocks": [
                {
                    "rank": index,
                    "code": f"00000{index}",
                    "name": f"股票 {index}",
                    "theme": f"题材 {index}",
                    "today_open_change": f"+{index}%",
                    "reason": f"理由 {index}",
                    "observe_after_930": f"观察 {index}",
                }
                for index in range(1, 6)
            ],
            "global_conclusion": {"one_sentence_for_930": "保持谨慎"},
        }

        messages: list[dict[str, str]] = []

        def capture(_email: str, *, subject: str, text: str, html: str, message_id: str = "") -> None:
            messages.append({"subject": subject, "text": text, "html": html})

        with mock.patch.dict(
            os.environ, {"PUBLIC_SITE_URL": "https://trade.example.test"}, clear=False
        ), mock.patch("trade_review_agent.auth_system._send_smtp_message", side_effect=capture):
            auth_system._send_daily_top5_email(
                {"email": "member@example.test", "content_variant": "full", "report_json": json.dumps(report)}
            )
            auth_system._send_daily_top5_email(
                {"email": "reader@example.test", "content_variant": "teaser", "report_json": json.dumps(report)}
            )

        full, teaser = messages
        for message in messages:
            assert_light_email(self, message["html"])
            self.assertIn("color:#0969da", message["html"])
            self.assertIn("text-decoration:underline", message["html"])
            self.assertIn("https://trade.example.test/auction-strength?date=2026-07-16", message["text"])
            self.assertNotIn("<script>alert(1)</script>", message["html"])
        self.assertNotIn("<thead", full["html"].lower())
        self.assertNotIn("<tbody", full["html"].lower())
        self.assertIn("1. 股票 1（000001）", full["html"])
        self.assertNotIn("股票 1", teaser["html"])
        self.assertNotIn("000001", teaser["html"])


if __name__ == "__main__":
    unittest.main()
