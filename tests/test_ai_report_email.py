from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from unittest import mock

from trade_review_agent import auth_system
from trade_review_agent.auth_system import (
    AuthError,
    CN_TZ,
    create_ai_report_email_campaign,
    init_auth_db,
    process_next_ai_report_email,
    recover_ai_report_email_queue,
    retry_ai_report_email_campaign,
)


def market_day_report(*, run_id: str = "market-run-1", report_date: str = "2026-07-16") -> dict:
    return {
        "run_id": run_id,
        "market_date": report_date,
        "received_at": f"{report_date} 19:00:00",
        "report": {
            "marketDate": report_date,
            "oneLineConclusion": "PROTECTED_MARKET_CONCLUSION <script>alert(1)</script>",
            "marketMood": {"summary": "PROTECTED_MARKET_MOOD", "score": 7},
            "mainline": {"name": "PROTECTED_MARKET_MAINLINE", "reason": "成交与涨停结构领先"},
            "strongestStocks": [{"name": "PROTECTED_MARKET_STOCK", "code": "000001"}],
            "watchPoints": ["PROTECTED_MARKET_WATCH"],
            "keyRisks": ["PROTECTED_MARKET_RISK"],
        },
    }


def research_report(*, run_id: str = "research-run-1", report_date: str = "2026-07-16") -> dict:
    return {
        "run_id": run_id,
        "research_date": report_date,
        "received_at": f"{report_date} 08:30:00",
        "title": "PROTECTED_RESEARCH_TITLE <script>alert(1)</script>",
        "summary": "PROTECTED_RESEARCH_SUMMARY",
        "markdown": "# PROTECTED_RESEARCH_MARKDOWN\n\nCPI and oil evidence",
        "decision_cards": [{"title": "PROTECTED_RESEARCH_CARD", "trigger": "09:35 confirmation"}],
        "watchlist": [{"name": "PROTECTED_RESEARCH_WATCH"}],
        "sources": [{"title": "PROTECTED_RESEARCH_SOURCE", "url": "https://example.test/source"}],
        # These ingestion-only fields must never be rendered into a full email.
        "headers": {"authorization": "PROTECTED_SECRET_HEADER"},
        "source_ip": "PROTECTED_SOURCE_IP",
        "payload": {"secret": "PROTECTED_RAW_PAYLOAD"},
    }


class AIReportEmailTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        init_auth_db(self.db_path)
        now = datetime.now(CN_TZ)
        future = (now + timedelta(days=20)).isoformat()
        past = (now - timedelta(days=1)).isoformat()
        users = [
            # username, role, verified, opted in, status, membership status, expiry
            ("admin", "admin", 1, 1, "active", "active", future),
            ("member", "user", 1, 1, "active", "active", future),
            ("ordinary", "user", 1, 1, "active", "", ""),
            ("inactive", "user", 1, 1, "disabled", "", ""),
            ("expired", "user", 1, 1, "active", "active", past),
            ("unverified", "user", 0, 1, "active", "", ""),
            ("optedout", "user", 1, 0, "active", "", ""),
        ]
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                for index, (username, role, verified, enabled, status, membership, expiry) in enumerate(users, 1):
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, update_emails_enabled,
                            password_hash, password_salt, role, status, invite_code, created_at,
                            membership_status, membership_expires_at
                        ) VALUES (?, ?, ?, ?, ?, 'hash', 'salt', ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"ai-report-email-{index}", username, f"{username}@example.test", verified,
                            enabled, role, status, f"AIREPORT{index}", now.isoformat(), membership, expiry,
                        ),
                    )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_recipient_and_membership_snapshot_matches_email_preference_contract(self) -> None:
        campaign = create_ai_report_email_campaign(
            self.db_path, report_type="market_day", report=market_day_report()
        )

        self.assertEqual(campaign["total"], 6, "admins must not appear even as skipped recipients")
        self.assertEqual(campaign["pending"], 4)
        self.assertEqual(campaign["skipped"], 2)
        self.assertEqual(campaign["full"], 1)
        self.assertEqual(campaign["teaser"], 3)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT u.username, d.email, d.status, d.content_variant, d.membership_active
                FROM ai_report_email_deliveries d
                JOIN users u ON u.id = d.user_id
                ORDER BY u.username
                """
            ).fetchall()
            by_name = {str(row["username"]): dict(row) for row in rows}
            self.assertNotIn("admin", by_name)
            self.assertEqual(by_name["member"]["content_variant"], "full")
            self.assertEqual(by_name["expired"]["content_variant"], "teaser")
            self.assertEqual(by_name["inactive"]["status"], "pending")
            self.assertEqual(by_name["unverified"]["status"], "skipped")
            self.assertEqual(by_name["optedout"]["status"], "skipped")
            self.assertEqual(by_name["ordinary"]["email"], "ordinary@example.test")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credit_ledger").fetchone()[0], 0)

    def test_idempotency_is_per_report_type_and_run_id_and_preserves_snapshot(self) -> None:
        first = create_ai_report_email_campaign(
            self.db_path, report_type="ai_research", report=research_report(run_id="shared-run")
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "UPDATE users SET update_emails_enabled = 0, membership_status = '', membership_expires_at = '' "
                    "WHERE username = 'member'"
                )
        corrected = research_report(run_id="shared-run")
        corrected["title"] = "REPLACEMENT_TITLE"
        duplicate = create_ai_report_email_campaign(
            self.db_path, report_type="ai_research", report=corrected
        )
        other_type = create_ai_report_email_campaign(
            self.db_path, report_type="market_day", report=market_day_report(run_id="shared-run")
        )
        same_date_new_run = create_ai_report_email_campaign(
            self.db_path, report_type="ai_research", report=research_report(run_id="new-run-same-date")
        )

        self.assertEqual(first["id"], duplicate["id"])
        self.assertEqual(duplicate["full"], 1, "membership snapshot must not change on replay")
        self.assertNotEqual(first["id"], other_type["id"])
        self.assertNotEqual(first["id"], same_date_new_run["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ai_report_email_campaigns").fetchone()[0], 3)
            stored = json.loads(conn.execute(
                "SELECT report_json FROM ai_report_email_campaigns WHERE id = ?", (first["id"],)
            ).fetchone()[0])
            self.assertEqual(stored["title"], "PROTECTED_RESEARCH_TITLE <script>alert(1)</script>")

    def test_incomplete_snapshot_creates_nothing_and_same_run_can_trigger_after_completion(self) -> None:
        incomplete_market = market_day_report(run_id="market-later-complete")
        incomplete_market["report"] = {"oneLineConclusion": "只有结论"}
        incomplete_research = research_report(run_id="research-later-complete")
        for key in ("markdown", "decision_cards", "watchlist", "sources"):
            incomplete_research.pop(key, None)

        for report_type, report in (
            ("market_day", incomplete_market),
            ("ai_research", incomplete_research),
        ):
            with self.subTest(report_type=report_type), self.assertRaises(AuthError) as raised:
                create_ai_report_email_campaign(self.db_path, report_type=report_type, report=report)
            self.assertEqual(raised.exception.status, 409)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ai_report_email_campaigns").fetchone()[0], 0)

        market_campaign = create_ai_report_email_campaign(
            self.db_path,
            report_type="market_day",
            report=market_day_report(run_id="market-later-complete"),
        )
        research_campaign = create_ai_report_email_campaign(
            self.db_path,
            report_type="ai_research",
            report=research_report(run_id="research-later-complete"),
        )
        self.assertNotEqual(market_campaign["id"], research_campaign["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ai_report_email_campaigns").fetchone()[0], 2)

    def test_concurrent_campaign_creation_and_delivery_claim_are_exactly_once(self) -> None:
        with ThreadPoolExecutor(max_workers=2) as pool:
            campaigns = list(pool.map(
                lambda _index: create_ai_report_email_campaign(
                    self.db_path, report_type="market_day", report=market_day_report()
                ),
                range(2),
            ))
        self.assertEqual(campaigns[0]["id"], campaigns[1]["id"])

        sent_ids: list[int] = []

        def sender(delivery: dict) -> None:
            sent_ids.append(int(delivery["id"]))
            time.sleep(0.03)

        with ThreadPoolExecutor(max_workers=4) as pool:
            processed = list(pool.map(
                lambda _index: process_next_ai_report_email(self.db_path, sender=sender), range(5)
            ))
        self.assertEqual(processed.count(True), campaigns[0]["pending"])
        self.assertEqual(Counter(sent_ids), Counter(set(sent_ids)))
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM ai_report_email_deliveries WHERE status = 'sent'"
            ).fetchone()[0], campaigns[0]["pending"])

    def test_full_and_teaser_are_isolated_escaped_and_use_light_multipart_inputs(self) -> None:
        for report_type, report, protected, route in (
            (
                "market_day", market_day_report(),
                ["PROTECTED_MARKET_CONCLUSION", "PROTECTED_MARKET_MAINLINE", "PROTECTED_MARKET_STOCK"],
                "/market-day?date=2026-07-16",
            ),
            (
                "ai_research", research_report(),
                ["PROTECTED_RESEARCH_TITLE", "PROTECTED_RESEARCH_SUMMARY", "PROTECTED_RESEARCH_MARKDOWN"],
                "/ai-research?date=2026-07-16",
            ),
        ):
            with self.subTest(report_type=report_type):
                create_ai_report_email_campaign(self.db_path, report_type=report_type, report=report)

        sent: dict[tuple[str, str], dict[str, str]] = {}

        def capture(email: str, *, subject: str, text: str, html: str, message_id: str = "") -> None:
            product = "research" if "研报" in subject else "market"
            sent[(email, product)] = {"subject": subject, "text": text, "html": html}

        with mock.patch.dict(os.environ, {"PUBLIC_SITE_URL": "https://trade.example.test/"}, clear=False), mock.patch(
            "trade_review_agent.auth_system._send_smtp_message", side_effect=capture
        ):
            while process_next_ai_report_email(self.db_path):
                pass

        for product, protected, route in (
            ("market", ["PROTECTED_MARKET_CONCLUSION", "PROTECTED_MARKET_MAINLINE", "PROTECTED_MARKET_STOCK"], "/market-day?date=2026-07-16"),
            ("research", ["PROTECTED_RESEARCH_TITLE", "PROTECTED_RESEARCH_SUMMARY", "PROTECTED_RESEARCH_MARKDOWN"], "/ai-research?date=2026-07-16"),
        ):
            full = sent[("member@example.test", product)]
            teaser = sent[("ordinary@example.test", product)]
            for token in protected:
                self.assertIn(token, full["text"])
                self.assertNotIn(token, teaser["text"])
                self.assertNotIn(token, teaser["html"])
            self.assertIn(f"https://trade.example.test{route}", full["text"])
            self.assertIn(f"https://trade.example.test{route}", full["html"])
            self.assertIn("background-color:#ffffff", full["html"])
            self.assertIn("color:#1f2328", full["html"])
            self.assertIn("color:#0969da", full["html"])
            self.assertNotIn("<script>alert(1)</script>", full["html"])
        research_full = sent[("member@example.test", "research")]
        for forbidden in ("PROTECTED_SECRET_HEADER", "PROTECTED_SOURCE_IP", "PROTECTED_RAW_PAYLOAD"):
            self.assertNotIn(forbidden, research_full["text"])
            self.assertNotIn(forbidden, research_full["html"])
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", research_full["html"])
        self.assertEqual(len(sent), 8)

    def test_both_report_types_build_text_plain_and_light_html_mime(self) -> None:
        messages: list[EmailMessage] = []

        def capture(email: str, *, subject: str, text: str, html: str, message_id: str = "") -> None:
            messages.append(auth_system._smtp_message(email, subject=subject, text=text, html=html, message_id=message_id))

        with mock.patch.dict(
            os.environ,
            {"PUBLIC_SITE_URL": "https://trade.example.test", "SMTP_FROM": "no-reply@example.test"},
            clear=False,
        ), mock.patch("trade_review_agent.auth_system._send_smtp_message", side_effect=capture):
            auth_system._send_ai_report_email({
                "email": "member@example.test",
                "report_type": "market_day",
                "report_date": "2026-07-16",
                "content_variant": "full",
                "report_json": json.dumps(market_day_report()),
            })
            auth_system._send_ai_report_email({
                "email": "ordinary@example.test",
                "report_type": "ai_research",
                "report_date": "2026-07-16",
                "content_variant": "teaser",
                "report_json": json.dumps(research_report()),
            })

        self.assertEqual(len(messages), 2)
        for message in messages:
            self.assertTrue(message.is_multipart())
            parts = {
                part.get_content_type(): part.get_content()
                for part in message.walk()
                if not part.is_multipart()
            }
            self.assertEqual(set(parts), {"text/plain", "text/html"})
            self.assertTrue(parts["text/plain"].strip())
            self.assertIn("background-color:#ffffff", parts["text/html"])
            self.assertIn('name="color-scheme" content="light"', parts["text/html"])
            self.assertIn("color:#0969da", parts["text/html"])

    def test_full_research_email_removes_nested_transport_metadata_but_keeps_siblings(self) -> None:
        report = research_report(run_id="research-nested-metadata")
        report["decision_cards"] = [{
            "title": "LEGITIMATE_DECISION_TITLE",
            "trigger": "LEGITIMATE_TRIGGER",
            "headers": {"authorization": "NESTED_SECRET_HEADER"},
            "payload": {"raw": "NESTED_SECRET_PAYLOAD"},
            "source_ip": "NESTED_SECRET_SOURCE_IP",
        }]
        report["sources"] = [{
            "title": "LEGITIMATE_SOURCE_TITLE",
            "url": "https://example.test/legitimate-source",
            "headers": {"cookie": "NESTED_SOURCE_COOKIE"},
            "payload": {"token": "NESTED_SOURCE_TOKEN"},
            "source_ip": "NESTED_SOURCE_IP",
        }]
        captured: dict[str, str] = {}

        def capture(_email: str, *, subject: str, text: str, html: str, message_id: str = "") -> None:
            captured.update(subject=subject, text=text, html=html)

        with mock.patch.dict(
            os.environ, {"PUBLIC_SITE_URL": "https://trade.example.test"}, clear=False
        ), mock.patch("trade_review_agent.auth_system._send_smtp_message", side_effect=capture):
            auth_system._send_ai_report_email({
                "email": "member@example.test",
                "report_type": "ai_research",
                "report_date": "2026-07-16",
                "content_variant": "full",
                "report_json": json.dumps(report),
            })

        for legitimate in (
            "LEGITIMATE_DECISION_TITLE",
            "LEGITIMATE_TRIGGER",
            "LEGITIMATE_SOURCE_TITLE",
            "https://example.test/legitimate-source",
        ):
            self.assertIn(legitimate, captured["text"])
            self.assertIn(legitimate, captured["html"])
        for secret in (
            "NESTED_SECRET_HEADER",
            "NESTED_SECRET_PAYLOAD",
            "NESTED_SECRET_SOURCE_IP",
            "NESTED_SOURCE_COOKIE",
            "NESTED_SOURCE_TOKEN",
            "NESTED_SOURCE_IP",
        ):
            self.assertNotIn(secret, captured["text"])
            self.assertNotIn(secret, captured["html"])

    def test_failure_recovery_three_attempt_limit_and_manual_retry(self) -> None:
        campaign = create_ai_report_email_campaign(
            self.db_path, report_type="market_day", report=market_day_report()
        )
        campaign_id = int(campaign["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "DELETE FROM ai_report_email_deliveries WHERE campaign_id = ? AND email != 'ordinary@example.test'",
                    (campaign_id,),
                )
                conn.execute(
                    "UPDATE ai_report_email_deliveries SET status = 'sending', updated_at = '2000-01-01' "
                    "WHERE campaign_id = ?", (campaign_id,),
                )
        self.assertEqual(recover_ai_report_email_queue(self.db_path), 1)

        def fail(_delivery: dict) -> None:
            raise RuntimeError("smtp down")

        for expected_attempt in range(1, 4):
            self.assertTrue(process_next_ai_report_email(self.db_path, sender=fail))
            with closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    conn.execute(
                        "UPDATE ai_report_email_deliveries SET next_attempt_at = '2000-01-01' WHERE campaign_id = ?",
                        (campaign_id,),
                    )
                status, attempts = conn.execute(
                    "SELECT status, attempt_count FROM ai_report_email_deliveries WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone()
            self.assertEqual(attempts, expected_attempt)
        self.assertEqual(status, "failed")
        self.assertFalse(process_next_ai_report_email(self.db_path, sender=lambda _delivery: None))

        retried = retry_ai_report_email_campaign(self.db_path, campaign_id=campaign_id)
        self.assertEqual((retried["pending"], retried["failed"]), (1, 0))
        delivered: list[int] = []
        self.assertTrue(process_next_ai_report_email(
            self.db_path, sender=lambda delivery: delivered.append(int(delivery["id"]))
        ))
        self.assertEqual(len(delivered), 1)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute(
                "SELECT status, attempt_count FROM ai_report_email_deliveries WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone(), ("sent", 1))

    def test_campaign_payload_exposes_earliest_pending_next_retry_at(self) -> None:
        campaign = create_ai_report_email_campaign(
            self.db_path, report_type="market_day", report=market_day_report()
        )
        campaign_id = int(campaign["id"])
        first_retry_at = "2026-07-16T19:35:00+08:00"
        second_retry_at = "2026-07-16T19:45:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE ai_report_email_deliveries
                    SET next_attempt_at = ?
                    WHERE campaign_id = ? AND email = 'member@example.test'
                    """,
                    (second_retry_at, campaign_id),
                )
                conn.execute(
                    """
                    UPDATE ai_report_email_deliveries
                    SET next_attempt_at = ?
                    WHERE campaign_id = ? AND email = 'ordinary@example.test'
                    """,
                    (first_retry_at, campaign_id),
                )

        refreshed = create_ai_report_email_campaign(
            self.db_path, report_type="market_day", report=market_day_report()
        )
        self.assertEqual(refreshed["id"], campaign_id)
        self.assertEqual(refreshed["next_retry_at"], first_retry_at)

    def test_manual_retry_only_resets_failed_rows(self) -> None:
        campaign = create_ai_report_email_campaign(
            self.db_path, report_type="market_day", report=market_day_report()
        )
        campaign_id = int(campaign["id"])
        pending_retry_at = "2026-07-16T19:55:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE ai_report_email_deliveries
                    SET status = 'failed', attempt_count = 3, next_attempt_at = '2000-01-01',
                        last_error = 'smtp down'
                    WHERE campaign_id = ? AND email = 'ordinary@example.test'
                    """,
                    (campaign_id,),
                )
                conn.execute(
                    """
                    UPDATE ai_report_email_deliveries
                    SET next_attempt_at = ?
                    WHERE campaign_id = ? AND email = 'member@example.test'
                    """,
                    (pending_retry_at, campaign_id),
                )
                conn.execute(
                    """
                    UPDATE ai_report_email_deliveries
                    SET status = 'sent', attempt_count = 2, sent_at = '2026-07-16T19:40:00+08:00',
                        next_attempt_at = NULL
                    WHERE campaign_id = ? AND email = 'inactive@example.test'
                    """,
                    (campaign_id,),
                )
                conn.execute(
                    """
                    UPDATE ai_report_email_deliveries
                    SET status = 'skipped', next_attempt_at = NULL, last_error = 'not eligible'
                    WHERE campaign_id = ? AND email = 'expired@example.test'
                    """,
                    (campaign_id,),
                )

        retried = retry_ai_report_email_campaign(self.db_path, campaign_id=campaign_id)
        self.assertEqual(retried["failed"], 0)
        self.assertEqual(retried["sent"], 1)
        self.assertEqual(retried["skipped"], 3)
        self.assertIsNotNone(retried["next_retry_at"])

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT email, status, attempt_count, next_attempt_at, last_error, sent_at
                FROM ai_report_email_deliveries
                WHERE campaign_id = ?
                ORDER BY email
                """,
                (campaign_id,),
            ).fetchall()
        by_email = {str(row["email"]): row for row in rows}
        self.assertEqual(str(by_email["inactive@example.test"]["status"]), "sent")
        self.assertEqual(int(by_email["inactive@example.test"]["attempt_count"]), 2)
        self.assertEqual(str(by_email["expired@example.test"]["status"]), "skipped")
        self.assertEqual(str(by_email["member@example.test"]["next_attempt_at"]), pending_retry_at)
        self.assertEqual(str(by_email["ordinary@example.test"]["status"]), "pending")
        self.assertEqual(int(by_email["ordinary@example.test"]["attempt_count"]), 0)
        self.assertIsNone(by_email["ordinary@example.test"]["last_error"])


if __name__ == "__main__":
    unittest.main()
