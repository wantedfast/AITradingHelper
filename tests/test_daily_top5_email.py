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
from pathlib import Path
from unittest import mock

from trade_review_agent.auth_system import (
    AuthError,
    CN_TZ,
    DAILY_TOP5_EMAIL_MAX_ATTEMPTS,
    create_daily_top5_email_campaign,
    init_auth_db,
    process_next_daily_top5_email,
    recover_daily_top5_email_queue,
    retry_daily_top5_email_campaign,
)


def complete_report(*, trade_date: str = "2026-07-16", report_id: str = "top5-run-1") -> dict:
    return {
        "id": report_id,
        "request_id": report_id,
        "trade_date": trade_date,
        "analysis_time": "2026-07-16 09:26:00",
        "summary": {"one_sentence": "Market <script>alert(1)</script> summary"},
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


class DailyTop5EmailTest(unittest.TestCase):
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
                for index, (username, role, verified, enabled, status, member_status, expiry) in enumerate(users, 1):
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, update_emails_enabled,
                            password_hash, password_salt, role, status, invite_code, created_at,
                            membership_status, membership_expires_at
                        ) VALUES (?, ?, ?, ?, ?, 'hash', 'salt', ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"top5-email-{index}", username, f"{username}@example.test", verified,
                            enabled, role, status, f"TOP5EMAIL{index}", now.isoformat(), member_status, expiry,
                        ),
                    )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_campaign_snapshots_only_ordinary_verified_opted_in_users_and_membership(self) -> None:
        campaign = create_daily_top5_email_campaign(self.db_path, report=complete_report())

        self.assertEqual(campaign["total"], 6, "admin users must not receive or appear as skipped deliveries")
        self.assertEqual(campaign["pending"], 4)
        self.assertEqual(campaign["skipped"], 2)
        self.assertEqual(campaign["full"], 1)
        self.assertEqual(campaign["teaser"], 3)

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT u.username, d.email, d.status, d.content_variant, d.membership_active
                FROM daily_top5_email_deliveries d
                JOIN users u ON u.id = d.user_id
                ORDER BY u.username
                """
            ).fetchall()
            self.assertNotIn("admin", {row["username"] for row in rows})
            by_name = {row["username"]: dict(row) for row in rows}
            self.assertEqual(by_name["member"]["content_variant"], "full")
            self.assertEqual(by_name["expired"]["content_variant"], "teaser")
            self.assertEqual(by_name["inactive"]["status"], "pending")
            self.assertEqual(by_name["unverified"]["status"], "skipped")
            self.assertEqual(by_name["optedout"]["status"], "skipped")
            self.assertEqual(by_name["ordinary"]["email"], "ordinary@example.test")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credit_ledger").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0], 0)

    def test_trade_date_is_idempotent_and_preserves_first_report_and_recipient_snapshot(self) -> None:
        first = create_daily_top5_email_campaign(self.db_path, report=complete_report(report_id="first"))
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "UPDATE users SET update_emails_enabled = 0, membership_status = '', membership_expires_at = '' WHERE username = 'member'"
                )
        corrected = complete_report(report_id="corrected")
        corrected["top5_strong_stocks"][0]["name"] = "Replacement Stock"
        second = create_daily_top5_email_campaign(self.db_path, report=corrected)

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["report_id"], "first")
        self.assertEqual(second["full"], 1)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_top5_email_campaigns").fetchone()[0], 1)
            report = json.loads(conn.execute("SELECT report_json FROM daily_top5_email_campaigns").fetchone()[0])
            self.assertEqual(report["top5_strong_stocks"][0]["name"], "Stock 1")

    def test_concurrent_campaign_creation_is_idempotent(self) -> None:
        with ThreadPoolExecutor(max_workers=2) as pool:
            campaigns = list(pool.map(
                lambda _index: create_daily_top5_email_campaign(self.db_path, report=complete_report()), range(2)
            ))

        self.assertEqual(campaigns[0]["id"], campaigns[1]["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_top5_email_campaigns").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_top5_email_deliveries").fetchone()[0], 6)

    def test_incomplete_report_creates_nothing_and_later_complete_report_can_trigger(self) -> None:
        report = complete_report()
        report["top5_strong_stocks"] = report["top5_strong_stocks"][:4]
        with self.assertRaises(AuthError) as missing_stock:
            create_daily_top5_email_campaign(self.db_path, report=report)
        self.assertEqual(missing_stock.exception.status, 409)

        report = complete_report()
        report["global_conclusion"] = {}
        with self.assertRaises(AuthError) as missing_conclusion:
            create_daily_top5_email_campaign(self.db_path, report=report)
        self.assertEqual(missing_conclusion.exception.status, 409)

        report = complete_report()
        report["top5_strong_stocks"] = [{"rank": index} for index in range(1, 6)]
        with self.assertRaises(AuthError) as empty_stock_fields:
            create_daily_top5_email_campaign(self.db_path, report=report)
        self.assertEqual(empty_stock_fields.exception.status, 409)

        report = complete_report()
        report["global_conclusion"]["one_sentence_for_930"] = ""
        with self.assertRaises(AuthError) as partial_conclusion:
            create_daily_top5_email_campaign(self.db_path, report=report)
        self.assertEqual(partial_conclusion.exception.status, 409)

        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_top5_email_campaigns").fetchone()[0], 0)

        campaign = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        self.assertEqual(campaign["pending"], 4)

    def test_full_and_teaser_email_content_is_isolated_escaped_and_links_to_date(self) -> None:
        create_daily_top5_email_campaign(self.db_path, report=complete_report())
        sent: dict[str, dict[str, str]] = {}

        def capture(email: str, *, subject: str, text: str, html: str, message_id: str = "") -> None:
            sent[email] = {"subject": subject, "text": text, "html": html, "message_id": message_id}

        with mock.patch.dict(os.environ, {"PUBLIC_SITE_URL": "https://trade.example.test/"}, clear=False), mock.patch(
            "trade_review_agent.auth_system._send_smtp_message", side_effect=capture
        ):
            while process_next_daily_top5_email(self.db_path):
                pass

        full = sent["member@example.test"]
        teaser = sent["ordinary@example.test"]
        self.assertIn("Stock 1", full["text"])
        self.assertIn("Hold the main line", full["text"])
        self.assertNotIn("Stock 1", teaser["text"])
        self.assertNotIn("Hold the main line", teaser["text"])
        self.assertIn("Market <script>alert(1)</script> summary", teaser["text"])
        self.assertNotIn("<script>alert(1)</script>", teaser["html"])
        self.assertIn("Market &lt;script&gt;alert(1)&lt;/script&gt; summary", teaser["html"])
        for message in (full, teaser):
            self.assertIn("https://trade.example.test/auction-strength?date=2026-07-16", message["html"])
            self.assertIn("AI", message["text"])
            self.assertIn("TOP5", message["subject"])
            self.assertRegex(message["message_id"], r"^daily-top5-c\d+-d\d+$")
        self.assertEqual(len(sent), 4)

    def test_teaser_does_not_leak_a_stock_name_or_code_from_the_summary(self) -> None:
        report = complete_report()
        report["summary"]["one_sentence"] = "Stock 1 (000001) is the strongest candidate today"
        create_daily_top5_email_campaign(self.db_path, report=report)
        sent: dict[str, str] = {}

        def capture(email: str, *, subject: str, text: str, html: str, message_id: str = "") -> None:
            sent[email] = text

        with mock.patch.dict(os.environ, {"PUBLIC_SITE_URL": "https://trade.example.test"}, clear=False), mock.patch(
            "trade_review_agent.auth_system._send_smtp_message", side_effect=capture
        ):
            while process_next_daily_top5_email(self.db_path):
                pass

        teaser = sent["ordinary@example.test"]
        self.assertNotIn("Stock 1", teaser)
        self.assertNotIn("000001", teaser)

    def test_concurrent_workers_claim_each_delivery_once(self) -> None:
        campaign = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        sent_ids: list[int] = []

        def sender(delivery: dict) -> None:
            sent_ids.append(int(delivery["id"]))
            time.sleep(0.04)

        with ThreadPoolExecutor(max_workers=4) as pool:
            processed = list(pool.map(
                lambda _index: process_next_daily_top5_email(self.db_path, sender=sender), range(5)
            ))

        self.assertEqual(processed.count(True), campaign["pending"])
        self.assertEqual(Counter(sent_ids), Counter(set(sent_ids)), "a delivery was claimed more than once")
        with closing(sqlite3.connect(self.db_path)) as conn:
            sent_count = conn.execute(
                "SELECT COUNT(*) FROM daily_top5_email_deliveries WHERE campaign_id = ? AND status = 'sent'",
                (campaign["id"],),
            ).fetchone()[0]
        self.assertEqual(sent_count, campaign["pending"])

    def test_failure_retries_automatically_until_daily_limit(self) -> None:
        campaign = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        campaign_id = int(campaign["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "DELETE FROM daily_top5_email_deliveries WHERE campaign_id = ? AND email != 'ordinary@example.test'",
                    (campaign_id,),
                )
                conn.execute(
                    "UPDATE daily_top5_email_deliveries SET status = 'sending', updated_at = '2000-01-01' WHERE campaign_id = ?",
                    (campaign_id,),
                )
        self.assertEqual(recover_daily_top5_email_queue(self.db_path), 1)

        for attempt in range(DAILY_TOP5_EMAIL_MAX_ATTEMPTS):
            self.assertTrue(process_next_daily_top5_email(self.db_path, sender=lambda _delivery: (_ for _ in ()).throw(RuntimeError("smtp down"))))
            with closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    conn.execute(
                        "UPDATE daily_top5_email_deliveries SET next_attempt_at = '2000-01-01' WHERE campaign_id = ?",
                        (campaign_id,),
                    )
                status, attempts = conn.execute(
                    "SELECT status, attempt_count FROM daily_top5_email_deliveries WHERE campaign_id = ?", (campaign_id,)
                ).fetchone()
            self.assertEqual(attempts, attempt + 1)
        self.assertEqual(status, "failed")
        self.assertFalse(process_next_daily_top5_email(self.db_path, sender=lambda _delivery: None))

    def test_recipient_blacklist_is_a_permanent_failure_and_is_not_retried(self) -> None:
        campaign = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        campaign_id = int(campaign["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "DELETE FROM daily_top5_email_deliveries WHERE campaign_id = ? AND email != 'ordinary@example.test'",
                    (campaign_id,),
                )

        def rejected(_delivery: dict) -> None:
            raise RuntimeError("(550, b'The sender is blacklisted by the recipient, please contact the recipient.')")

        self.assertTrue(process_next_daily_top5_email(self.db_path, sender=rejected))
        self.assertFalse(process_next_daily_top5_email(self.db_path, sender=lambda _delivery: None))
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                """
                SELECT status, attempt_count, next_attempt_at, last_error
                FROM daily_top5_email_deliveries WHERE campaign_id = ?
                """,
                (campaign_id,),
            ).fetchone()
        self.assertEqual(row[0], "failed")
        self.assertEqual(row[1], 1)
        self.assertIsNone(row[2])
        self.assertTrue(str(row[3]).startswith("[permanent] "))

        refreshed = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        self.assertEqual(refreshed["permanent_failed"], 1)
        self.assertEqual(refreshed["retryable_failed"], 0)
        retried = retry_daily_top5_email_campaign(self.db_path, campaign_id=campaign_id)
        self.assertEqual(retried["failed"], 1)
        self.assertEqual(retried["pending"], 0)

    def test_qq_rate_limit_remains_pending_for_automatic_retry(self) -> None:
        campaign = create_daily_top5_email_campaign(
            self.db_path,
            report=complete_report(trade_date="2026-07-17", report_id="top5-run-rate-limit"),
        )
        campaign_id = int(campaign["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "DELETE FROM daily_top5_email_deliveries WHERE campaign_id = ? AND email != 'ordinary@example.test'",
                    (campaign_id,),
                )

        def rate_limited(_delivery: dict) -> None:
            raise RuntimeError("(550, b'Too many attempts. Unable to send. Try again later')")

        self.assertTrue(process_next_daily_top5_email(self.db_path, sender=rate_limited))
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                """
                SELECT status, attempt_count, next_attempt_at, last_error
                FROM daily_top5_email_deliveries WHERE campaign_id = ?
                """,
                (campaign_id,),
            ).fetchone()
        self.assertEqual(row[0], "pending")
        self.assertEqual(row[1], 1)
        self.assertIsNotNone(row[2])
        self.assertFalse(str(row[3]).startswith("[permanent] "))

    def test_temporary_mailbox_unavailable_remains_pending_for_retry(self) -> None:
        campaign = create_daily_top5_email_campaign(
            self.db_path,
            report=complete_report(trade_date="2026-07-18", report_id="top5-run-mailbox-temporary"),
        )
        campaign_id = int(campaign["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "DELETE FROM daily_top5_email_deliveries WHERE campaign_id = ? AND email != 'ordinary@example.test'",
                    (campaign_id,),
                )

        def temporarily_unavailable(_delivery: dict) -> None:
            raise RuntimeError("(450, b'Requested mail action not taken: mailbox unavailable')")

        self.assertTrue(process_next_daily_top5_email(self.db_path, sender=temporarily_unavailable))
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                """
                SELECT status, next_attempt_at, last_error
                FROM daily_top5_email_deliveries WHERE campaign_id = ?
                """,
                (campaign_id,),
            ).fetchone()
        self.assertEqual(row[0], "pending")
        self.assertIsNotNone(row[1])
        self.assertFalse(str(row[2]).startswith("[permanent] "))

    def test_queue_recovery_normalizes_existing_blacklist_retry(self) -> None:
        campaign = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        campaign_id = int(campaign["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "DELETE FROM daily_top5_email_deliveries WHERE campaign_id = ? AND email != 'ordinary@example.test'",
                    (campaign_id,),
                )
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET status = 'pending', attempt_count = 6, next_attempt_at = '2099-01-01',
                        last_error = '(550, blacklisted by the recipient)'
                    WHERE campaign_id = ?
                    """,
                    (campaign_id,),
                )

        self.assertEqual(recover_daily_top5_email_queue(self.db_path), 1)
        with closing(sqlite3.connect(self.db_path)) as conn:
            delivery = conn.execute(
                "SELECT status, next_attempt_at, last_error FROM daily_top5_email_deliveries WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            status = conn.execute(
                "SELECT status FROM daily_top5_email_campaigns WHERE id = ?", (campaign_id,)
            ).fetchone()[0]
        self.assertEqual(delivery[0], "failed")
        self.assertIsNone(delivery[1])
        self.assertTrue(str(delivery[2]).startswith("[permanent] "))
        self.assertEqual(status, "failed")

    def test_delivery_failed_under_old_limit_is_automatically_requeued(self) -> None:
        campaign = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        campaign_id = int(campaign["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "DELETE FROM daily_top5_email_deliveries WHERE campaign_id = ? AND email != 'ordinary@example.test'",
                    (campaign_id,),
                )
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET status = 'failed', attempt_count = 3, next_attempt_at = '2000-01-01'
                    WHERE campaign_id = ?
                    """,
                    (campaign_id,),
                )

        delivered: list[int] = []
        self.assertTrue(
            process_next_daily_top5_email(
                self.db_path, sender=lambda delivery: delivered.append(int(delivery["id"]))
            )
        )
        self.assertEqual(len(delivered), 1)
        with closing(sqlite3.connect(self.db_path)) as conn:
            status, attempts = conn.execute(
                "SELECT status, attempt_count FROM daily_top5_email_deliveries WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
        self.assertEqual((status, attempts), ("sent", 4))

    def test_manual_retry_resets_a_terminal_failure(self) -> None:
        campaign = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        campaign_id = int(campaign["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "DELETE FROM daily_top5_email_deliveries WHERE campaign_id = ? AND email != 'ordinary@example.test'",
                    (campaign_id,),
                )
                conn.execute(
                    "UPDATE daily_top5_email_deliveries SET status = 'failed', attempt_count = ? WHERE campaign_id = ?",
                    (DAILY_TOP5_EMAIL_MAX_ATTEMPTS, campaign_id),
                )

        retried = retry_daily_top5_email_campaign(self.db_path, campaign_id=campaign_id)
        self.assertEqual(retried["pending"], 1)
        self.assertEqual(retried["failed"], 0)
        delivered: list[int] = []
        self.assertTrue(process_next_daily_top5_email(self.db_path, sender=lambda delivery: delivered.append(int(delivery["id"]))))
        self.assertEqual(len(delivered), 1)
        with closing(sqlite3.connect(self.db_path)) as conn:
            status, attempts = conn.execute(
                "SELECT status, attempt_count FROM daily_top5_email_deliveries WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
        self.assertEqual((status, attempts), ("sent", 1))

    def test_campaign_payload_exposes_earliest_pending_next_retry_at(self) -> None:
        campaign = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        campaign_id = int(campaign["id"])
        first_retry_at = "2026-07-16T09:35:00+08:00"
        second_retry_at = "2026-07-16T09:45:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET next_attempt_at = ?
                    WHERE campaign_id = ? AND email = 'member@example.test'
                    """,
                    (second_retry_at, campaign_id),
                )
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET next_attempt_at = ?
                    WHERE campaign_id = ? AND email = 'ordinary@example.test'
                    """,
                    (first_retry_at, campaign_id),
                )

        refreshed = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        self.assertEqual(refreshed["id"], campaign_id)
        self.assertEqual(refreshed["next_retry_at"], first_retry_at)

    def test_manual_retry_only_resets_failed_rows(self) -> None:
        campaign = create_daily_top5_email_campaign(self.db_path, report=complete_report())
        campaign_id = int(campaign["id"])
        pending_retry_at = "2026-07-16T09:55:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET status = 'failed', attempt_count = ?, next_attempt_at = '2000-01-01',
                        last_error = 'smtp down'
                    WHERE campaign_id = ? AND email = 'ordinary@example.test'
                    """,
                    (DAILY_TOP5_EMAIL_MAX_ATTEMPTS, campaign_id),
                )
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET next_attempt_at = ?
                    WHERE campaign_id = ? AND email = 'member@example.test'
                    """,
                    (pending_retry_at, campaign_id),
                )
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET status = 'sent', attempt_count = 2, sent_at = '2026-07-16T09:40:00+08:00',
                        next_attempt_at = NULL
                    WHERE campaign_id = ? AND email = 'inactive@example.test'
                    """,
                    (campaign_id,),
                )
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET status = 'skipped', next_attempt_at = NULL, last_error = 'not eligible'
                    WHERE campaign_id = ? AND email = 'expired@example.test'
                    """,
                    (campaign_id,),
                )

        retried = retry_daily_top5_email_campaign(self.db_path, campaign_id=campaign_id)
        self.assertEqual(retried["failed"], 0)
        self.assertEqual(retried["sent"], 1)
        self.assertEqual(retried["skipped"], 3)
        self.assertIsNotNone(retried["next_retry_at"])

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT email, status, attempt_count, next_attempt_at, last_error, sent_at
                FROM daily_top5_email_deliveries
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
