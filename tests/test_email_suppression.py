from __future__ import annotations

import sqlite3
import smtplib
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from trade_review_agent.auth_system import (
    CN_TZ,
    create_ai_report_email_campaign,
    create_daily_top5_email_campaign,
    create_daily_top5_close_email_campaign,
    create_update_notice,
    init_auth_db,
    process_next_ai_report_email,
    process_next_daily_top5_email,
    process_next_daily_top5_close_email,
    publish_update_notice,
    retry_daily_top5_email_campaign,
)


class _CloseQuoteProvider:
    def stock_daily(self, code: str, _start, _end) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "trade_date": datetime(2026, 8, 14).date(),
                    "open": 10.0 + int(code[-1]),
                    "close": 10.5 + int(code[-1]),
                }
            ]
        )


def _top5_report(*, trade_date: str, report_id: str) -> dict:
    return {
        "id": report_id,
        "trade_date": trade_date,
        "analysis_time": f"{trade_date} 09:26:00",
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
            "one_sentence_for_930": "Manage risk",
        },
    }


def _market_report(*, report_date: str, run_id: str) -> dict:
    return {
        "run_id": run_id,
        "market_date": report_date,
        "report": {
            "marketDate": report_date,
            "oneLineConclusion": "Market conclusion",
            "marketMood": {"summary": "Neutral", "score": 5},
            "mainline": {"name": "Mainline", "reason": "Reason"},
            "strongestStocks": [{"name": "Stock 1", "code": "000001"}],
            "watchPoints": ["Watch"],
            "keyRisks": ["Risk"],
        },
    }


class EmailSuppressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        init_auth_db(self.db_path)
        now = datetime.now(CN_TZ).isoformat()
        future = (datetime.now(CN_TZ) + timedelta(days=30)).isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        phone, username, email, email_verified, update_emails_enabled,
                        password_hash, password_salt, role, status, invite_code, created_at,
                        membership_status, membership_expires_at
                    ) VALUES ('suppression-user', 'suppressed', ' Blocked@Example.Test ', 1, 1,
                              'hash', 'salt', 'user', 'active', 'SUPPRESSION1', ?, 'active', ?)
                    """,
                    (now, future),
                )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_update_campaign(self, *, request_id: str) -> dict:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                admin_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, update_emails_enabled,
                            password_hash, password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 1, 'hash', 'salt', 'admin', 'active', ?, ?)
                        """,
                        (
                            f"admin-{request_id}",
                            f"admin-{request_id}",
                            f"admin-{request_id}@example.test",
                            f"ADMIN{request_id}",
                            datetime.now(CN_TZ).isoformat(),
                        ),
                    ).lastrowid
                )
        notice = create_update_notice(
            self.db_path,
            title="Suppression regression",
            version="2026-08-12",
            items=["No blocked recipient may receive this"],
            admin_id=admin_id,
        )
        result = publish_update_notice(
            self.db_path,
            notice_id=int(notice["id"]),
            send_email=True,
            request_id=request_id,
            admin_id=admin_id,
        )
        return result["email_campaign"]

    def test_explicit_recipient_block_fails_current_delivery_and_skips_future_cross_campaign_types(self) -> None:
        first = create_daily_top5_email_campaign(
            self.db_path,
            report=_top5_report(trade_date="2026-08-11", report_id="top5-blocked"),
        )

        def blocked_sender(_delivery: dict) -> None:
            raise RuntimeError("550 5.7.1 blacklisted by the recipient")

        self.assertTrue(process_next_daily_top5_email(self.db_path, sender=blocked_sender))
        future_ai = create_ai_report_email_campaign(
            self.db_path,
            report_type="market_day",
            report=_market_report(report_date="2026-08-12", run_id="market-after-block"),
        )
        future_top5 = create_daily_top5_email_campaign(
            self.db_path,
            report=_top5_report(trade_date="2026-08-13", report_id="top5-after-block"),
        )
        future_update = self._create_update_campaign(request_id="suppression-update-001")

        self.assertEqual(first["pending"], 1)
        for campaign in (future_ai, future_top5, future_update):
            self.assertEqual(campaign["pending"], 0)
            self.assertEqual(campaign["skipped"], 1)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            failed = conn.execute(
                "SELECT status, last_error FROM daily_top5_email_deliveries WHERE campaign_id = ?",
                (first["id"],),
            ).fetchone()
            suppression = conn.execute("SELECT * FROM email_suppressions").fetchone()
            skipped = conn.execute(
                "SELECT status, last_error FROM ai_report_email_deliveries WHERE campaign_id = ?",
                (future_ai["id"],),
            ).fetchone()
        self.assertEqual(failed["status"], "failed")
        self.assertIn("blacklisted by the recipient", failed["last_error"])
        self.assertEqual(suppression["email"], "blocked@example.test")
        self.assertEqual(skipped["status"], "skipped")
        self.assertIn("全局不发送名单", skipped["last_error"])

    def test_already_enqueued_delivery_is_rechecked_before_send(self) -> None:
        first = create_daily_top5_email_campaign(
            self.db_path,
            report=_top5_report(trade_date="2026-08-11", report_id="top5-block-source"),
        )
        already_enqueued = create_ai_report_email_campaign(
            self.db_path,
            report_type="market_day",
            report=_market_report(report_date="2026-08-12", run_id="already-enqueued"),
        )

        self.assertTrue(
            process_next_daily_top5_email(
                self.db_path,
                sender=lambda _delivery: (_ for _ in ()).throw(
                    RuntimeError("550 5.7.1 blocked by recipient")
                ),
            )
        )
        retried = retry_daily_top5_email_campaign(self.db_path, campaign_id=int(first["id"]))
        self.assertEqual(retried["failed"], 1)
        self.assertEqual(retried["pending"], 0)
        sent: list[str] = []
        process_next_ai_report_email(
            self.db_path,
            sender=lambda delivery: sent.append(str(delivery["email"])),
        )

        self.assertEqual(sent, [])
        with closing(sqlite3.connect(self.db_path)) as conn:
            source_status = conn.execute(
                "SELECT status FROM daily_top5_email_deliveries WHERE campaign_id = ?",
                (first["id"],),
            ).fetchone()[0]
            queued_status, queued_error = conn.execute(
                "SELECT status, last_error FROM ai_report_email_deliveries WHERE campaign_id = ?",
                (already_enqueued["id"],),
            ).fetchone()
        self.assertEqual(source_status, "failed")
        self.assertEqual(queued_status, "skipped")
        self.assertIn("全局不发送名单", queued_error)

    def test_close_campaign_calculation_snapshots_suppressed_recipient_as_skipped(self) -> None:
        create_daily_top5_email_campaign(
            self.db_path,
            report=_top5_report(trade_date="2026-08-11", report_id="close-block-source"),
        )
        self.assertTrue(
            process_next_daily_top5_email(
                self.db_path,
                sender=lambda _delivery: (_ for _ in ()).throw(
                    RuntimeError("550 blacklisted by the recipient")
                ),
            )
        )
        close_campaign = create_daily_top5_close_email_campaign(
            self.db_path,
            report=_top5_report(trade_date="2026-08-14", report_id="close-after-block"),
            now_dt=datetime(2026, 8, 14, 9, 30, tzinfo=CN_TZ),
        )
        self.assertTrue(
            process_next_daily_top5_close_email(
                self.db_path,
                cache_db=self.db_path.parent / "cache.sqlite",
                provider=_CloseQuoteProvider(),
                now_dt=datetime(2026, 8, 14, 15, 10, tzinfo=CN_TZ),
            )
        )
        sent: list[str] = []
        process_next_daily_top5_close_email(
            self.db_path,
            sender=lambda delivery: sent.append(str(delivery["email"])),
            now_dt=datetime(2026, 8, 14, 15, 11, tzinfo=CN_TZ),
        )

        self.assertEqual(sent, [])
        with closing(sqlite3.connect(self.db_path)) as conn:
            status, error = conn.execute(
                "SELECT status, last_error FROM daily_top5_close_email_deliveries WHERE campaign_id = ?",
                (close_campaign["id"],),
            ).fetchone()
        self.assertEqual(status, "skipped")
        self.assertIn("全局不发送名单", error)

    def test_concurrent_duplicate_block_reports_create_one_suppression(self) -> None:
        create_daily_top5_email_campaign(
            self.db_path,
            report=_top5_report(trade_date="2026-08-11", report_id="concurrent-block-1"),
        )
        create_daily_top5_email_campaign(
            self.db_path,
            report=_top5_report(trade_date="2026-08-12", report_id="concurrent-block-2"),
        )
        barrier = threading.Barrier(2)

        def reject(_delivery: dict) -> None:
            barrier.wait(timeout=5)
            raise RuntimeError("550 recipient has blocked this sender")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _index: process_next_daily_top5_email(self.db_path, sender=reject),
                    range(2),
                )
            )

        self.assertEqual(results, [True, True])
        with closing(sqlite3.connect(self.db_path)) as conn:
            suppression_count = conn.execute("SELECT COUNT(*) FROM email_suppressions").fetchone()[0]
            statuses = [
                row[0]
                for row in conn.execute(
                    "SELECT status FROM daily_top5_email_deliveries ORDER BY id"
                ).fetchall()
            ]
        self.assertEqual(suppression_count, 1)
        self.assertEqual(statuses, ["failed", "failed"])

    def test_non_blocking_smtp_errors_never_add_suppression(self) -> None:
        errors = (
            RuntimeError("550 Too many attempts. Unable to send. Try again later"),
            RuntimeError("450 Requested mail action not taken: mailbox unavailable"),
            smtplib.SMTPAuthenticationError(535, b"authentication failed"),
            RuntimeError("550 5.1.1 user unknown"),
        )
        for index, error in enumerate(errors, start=1):
            with self.subTest(error=str(error)):
                campaign = create_daily_top5_email_campaign(
                    self.db_path,
                    report=_top5_report(
                        trade_date=f"2026-08-{20 + index:02d}",
                        report_id=f"non-blocking-{index}",
                    ),
                )
                self.assertTrue(
                    process_next_daily_top5_email(
                        self.db_path,
                        sender=lambda _delivery, failure=error: (_ for _ in ()).throw(failure),
                    )
                )
                with closing(sqlite3.connect(self.db_path)) as conn:
                    self.assertEqual(
                        conn.execute("SELECT COUNT(*) FROM email_suppressions").fetchone()[0],
                        0,
                    )
                    # Keep the next subtest focused on its newly-created delivery.
                    with conn:
                        conn.execute(
                            "UPDATE daily_top5_email_deliveries SET next_attempt_at = '2099-01-01' WHERE campaign_id = ?",
                            (campaign["id"],),
                        )


if __name__ == "__main__":
    unittest.main()
