from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from email.message import EmailMessage
from pathlib import Path
from unittest import mock

from trade_review_agent import auth_system


LEGACY_SKIN = ("#050505", "#111", "#262113", "#c9a64655", "#f5d77a", "#e3bd4f")


def _top5_report() -> dict:
    return {
        "trade_date": "2026-07-16",
        "analysis_time": "2026-07-16 09:26:00",
        "summary": {"one_sentence": "Market <script>alert('summary')</script> summary"},
        "top5_strong_stocks": [
            {
                "rank": index,
                "code": f"00000{index}",
                "name": f"Stock {index}",
                "theme": f"Theme {index}",
                "today_open_change": f"+{index}.00%",
                "reason": f"Reason {index}",
                "observe_after_930": f"Observe {index}",
            }
            for index in range(1, 6)
        ],
        "global_conclusion": {
            "strongest_stock_at_925": "Stock 1",
            "strongest_theme_cluster": "Theme 1",
            "most_over_expected_stock": "Stock 2",
            "best_capacity_confirmation": "Stock 3",
            "biggest_negative_feedback": "Stock X",
            "one_sentence_for_930": "Hold the main line & manage risk",
        },
    }


class EmailMimeContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.messages: list[EmailMessage] = []
        self.environment = mock.patch.dict(
            os.environ,
            {
                "SMTP_FROM": "no-reply@example.test",
                "SMTP_FROM_NAME": "Yinghang",
                "EMAIL_PROVIDER": "smtp",
                "PUBLIC_SITE_URL": "https://trade.example.test",
                "ADMIN_DASHBOARD_URL": "https://trade.example.test/admin",
                "ADMIN_PAYMENT_NOTIFY_EMAIL": "ops@example.test",
            },
            clear=False,
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()

    def _capture_mime(self, email: str, *, subject: str, text: str, html: str | None = None) -> None:
        self.messages.append(auth_system._smtp_message(email, subject=subject, text=text, html=html))

    def _assert_mime_and_light_html(self, message: EmailMessage) -> tuple[str, str]:
        self.assertTrue(message.is_multipart())
        parts = {part.get_content_type(): part.get_content() for part in message.walk() if not part.is_multipart()}
        self.assertEqual(set(parts), {"text/plain", "text/html"})
        text, html = parts["text/plain"], parts["text/html"]
        self.assertTrue(text.strip())
        compact = re.sub(r"\s+", "", html).lower()
        self.assertRegex(compact, r"background(?:-color)?:#(?:fff|ffffff)(?:[;\"'])")
        self.assertIn('name="color-scheme"content="light"', compact)
        self.assertIn('name="supported-color-schemes"content="light"', compact)
        self.assertIn("color:#1f2328", compact)
        for token in LEGACY_SKIN:
            self.assertNotIn(token, compact)
        for tag in re.findall(r"<(?:h[1-6]|p|li|td|th)\b[^>]*>", html, flags=re.I):
            self.assertRegex(tag, r"style=[\"'][^\"']*\bcolor\s*:", f"missing explicit text color: {tag}")
        return text, html

    def _assert_standard_link(self, html: str, url: str) -> None:
        anchor = re.search(rf'<a[^>]+href=["\']{re.escape(url)}["\'][^>]*>', html, flags=re.I)
        self.assertIsNotNone(anchor)
        opening_tag = anchor.group(0).lower()
        self.assertIn("color:#0969da", opening_tag)
        self.assertRegex(opening_tag, r"text-decoration:\s*underline")
        self.assertNotIn("background:", opening_tag)
        self.assertIn(url, html, "the complete URL must remain visible in the HTML body")

    def test_verification_credit_and_admin_payment_generate_safe_light_mime(self) -> None:
        with mock.patch("trade_review_agent.auth_system._send_smtp_message", side_effect=self._capture_mime):
            auth_system._send_smtp_email("reader@example.test", "12<img src=x onerror=alert(1)>")
            payment_result = auth_system.notify_admin_membership_payment(
                order={
                    "order_no": "ORDER<img src=x onerror=alert(1)>",
                    "plan_name": "年度会员<script>alert('plan')</script>",
                    "amount_cents": 39900,
                    "submitted_amount_cents": 39900,
                    "payment_method": "alipay",
                    "payer_note": "Note</p><script>alert('note')</script>",
                },
                user={"id": 7, "username": "User<b>unsafe</b>", "email": "member@example.test"},
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / "auth.sqlite"
                auth_system.init_auth_db(db_path)
                with closing(sqlite3.connect(db_path)) as conn:
                    with conn:
                        user_id = conn.execute(
                            """
                            INSERT INTO users (
                                phone, username, email, email_verified, password_hash, password_salt,
                                role, status, invite_code, created_at
                            ) VALUES ('mime-credit', ?, 'credit@example.test', 1, 'hash', 'salt',
                                      'user', 'active', 'MIMECREDIT', '2026-07-16T09:00:00+08:00')
                            """,
                            ("Reader<script>alert('user')</script>",),
                        ).lastrowid
                        conn.execute(
                            "INSERT INTO credit_ledger (user_id, delta, reason, created_at) VALUES (?, 10, 'seed', '2026-07-16T09:00:00+08:00')",
                            (user_id,),
                        )
                credit_result = auth_system.notify_credit_added(
                    db_path,
                    user_id=int(user_id),
                    credits=10,
                    reason="Reward<img src=x onerror=alert(1)>",
                )

        self.assertTrue(payment_result["sent"])
        self.assertTrue(credit_result["sent"])
        self.assertEqual(len(self.messages), 3)
        verification_text, verification_html = self._assert_mime_and_light_html(self.messages[0])
        self.assertIn("12<img src=x onerror=alert(1)>", verification_text)
        self.assertNotIn("<img src=x", verification_html)
        payment_text, payment_html = self._assert_mime_and_light_html(self.messages[1])
        self.assertIn("ORDER<img src=x onerror=alert(1)>", payment_text)
        self.assertNotRegex(payment_html, r"<(?:script|img)\b")
        self._assert_standard_link(payment_html, "https://trade.example.test/admin")
        credit_text, credit_html = self._assert_mime_and_light_html(self.messages[2])
        self.assertIn("Reward<img src=x onerror=alert(1)>", credit_text)
        self.assertNotRegex(credit_html, r"<(?:script|img)\b")

    def test_update_notice_generates_safe_light_mime_with_plain_standard_link(self) -> None:
        delivery = {
            "email": "reader@example.test",
            "title": "New <script>alert('title')</script>",
            "version": "2026-07-16<img src=x>",
            "items_json": json.dumps(["First <svg onload=alert(1)>", "Second & safe"]),
        }
        with mock.patch("trade_review_agent.auth_system._send_smtp_message", side_effect=self._capture_mime):
            auth_system._send_update_notice_email(delivery)

        text, html = self._assert_mime_and_light_html(self.messages.pop())
        self.assertIn("- First <svg onload=alert(1)>", text)
        self.assertNotRegex(html, r"<(?:script|svg|img)\b")
        self.assertIn("First &lt;svg onload=alert(1)&gt;", html)
        self._assert_standard_link(html, "https://trade.example.test")

    def test_update_notice_renders_safe_markdown_in_html_and_plain_text(self) -> None:
        markdown = """## 今日更新

- 支持 **Markdown** 排版
- 查看 [使用说明](https://docs.example.test/guide)

> 请先阅读风险提示

`<script>alert(1)</script>`
<img src=x onerror=alert(1)>
[危险链接](javascript:alert(1))
"""
        delivery = {
            "email": "reader@example.test",
            "title": "每日公告",
            "version": "2026-08-07",
            "summary": "今日重点",
            "content_markdown": markdown,
            "items_json": "[]",
        }
        with mock.patch("trade_review_agent.auth_system._send_smtp_message", side_effect=self._capture_mime):
            auth_system._send_update_notice_email(delivery)

        text, html = self._assert_mime_and_light_html(self.messages.pop())
        self.assertIn("## 今日更新", text)
        self.assertIn("<h3", html)
        self.assertIn("<strong>Markdown</strong>", html)
        self.assertIn('href="https://docs.example.test/guide"', html)
        self.assertNotIn('href="javascript:', html)
        self.assertNotRegex(html, r"<(?:script|img)\b")
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)

    def test_top5_full_and_teaser_generate_safe_light_mime_without_data_table_or_leak(self) -> None:
        report = _top5_report()
        report["top5_strong_stocks"][0]["reason"] = "Reason <script>alert('reason')</script>"
        report["global_conclusion"]["one_sentence_for_930"] = "Conclusion <img src=x onerror=alert(1)>"
        with mock.patch("trade_review_agent.auth_system._send_smtp_message", side_effect=self._capture_mime):
            for email, variant in (("member@example.test", "full"), ("reader@example.test", "teaser")):
                auth_system._send_daily_top5_email(
                    {
                        "email": email,
                        "trade_date": "2026-07-16",
                        "content_variant": variant,
                        "report_json": json.dumps(report),
                    }
                )

        full_text, full_html = self._assert_mime_and_light_html(self.messages[0])
        teaser_text, teaser_html = self._assert_mime_and_light_html(self.messages[1])
        self.assertNotRegex(full_html, r'<table\b(?![^>]*\brole=["\']presentation["\'])|<(?:thead|tbody|th)\b')
        positions = [full_html.index(f"Stock {index}") for index in range(1, 6)]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Reason &lt;script&gt;alert('reason')&lt;/script&gt;", full_html)
        self.assertIn("Conclusion &lt;img src=x onerror=alert(1)&gt;", full_html)
        self.assertIn("Stock 1", full_text)
        for protected in ("Stock 1", "000001", "Conclusion"):
            self.assertNotIn(protected, teaser_text)
            self.assertNotIn(protected, teaser_html)
        self.assertNotIn("<script>alert('summary')</script>", teaser_html)
        self._assert_standard_link(full_html, "https://trade.example.test/auction-strength?date=2026-07-16")
        self._assert_standard_link(teaser_html, "https://trade.example.test/auction-strength?date=2026-07-16")


if __name__ == "__main__":
    unittest.main()
