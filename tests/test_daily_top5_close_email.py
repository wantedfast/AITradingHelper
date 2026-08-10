from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest import mock

import pandas as pd

from trade_review_agent.auction_strength.close_email import collect_close_email_snapshot
from trade_review_agent.auth_system import (
    CN_TZ,
    create_daily_top5_close_email_campaign,
    init_auth_db,
    process_next_daily_top5_close_email,
    recover_daily_top5_close_email_queue,
    retry_daily_top5_close_email_campaign,
)
from trade_review_agent.auction_strength.close_email import collect_close_email_snapshot


def complete_report(*, trade_date: str = "2026-08-10", report_id: str = "top5-close-run-1") -> dict:
    return {
        "id": report_id,
        "request_id": report_id,
        "trade_date": trade_date,
        "analysis_time": "2026-08-10 09:26:00",
        "summary": {"one_sentence": "收盘表现测试"},
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


def complete_report_for_stocks(
    stocks: list[tuple[int, str, str]], *, trade_date: str = "2026-08-10", report_id: str = "top5-close-run-1"
) -> dict:
    report = complete_report(trade_date=trade_date, report_id=report_id)
    report["top5_strong_stocks"] = [
        {
            "rank": rank,
            "code": code,
            "name": name,
            "theme": f"Theme {rank}",
            "today_open_change": f"+{rank}.00%",
            "reason": f"Reason {rank}",
            "observe_after_930": f"Observe {rank}",
        }
        for rank, code, name in stocks
    ]
    return report


class StubProvider:
    def __init__(self, rows_by_code: dict[str, list[dict[str, object]]]) -> None:
        self.rows_by_code = rows_by_code

    def stock_daily(self, code: str, _start, _end) -> pd.DataFrame:
        rows = self.rows_by_code.get(code, [])
        frame = pd.DataFrame(rows)
        if not frame.empty:
            frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
        return frame


class DailyTop5CloseEmailTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        init_auth_db(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                for role, username, verified, enabled in (
                    ("admin", "admin", 1, 1),
                    ("user", "member", 1, 1),
                    ("user", "ordinary", 1, 1),
                    ("user", "unverified", 0, 1),
                    ("user", "optedout", 1, 0),
                ):
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, update_emails_enabled,
                            password_hash, password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, ?, ?, 'hash', 'salt', ?, 'active', ?, ?)
                        """,
                        (
                            f"close-{username}",
                            username,
                            f"{username}@example.test",
                            verified,
                            enabled,
                            role,
                            f"CLOSE{username.upper()}",
                            "2026-08-10T09:00:00+08:00",
                        ),
                    )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_snapshot_marks_limit_up_using_previous_close_and_board_rules(self) -> None:
        report = complete_report_for_stocks(
            [
                (1, "000001", "Main Board Limit"),
                (2, "000003", "ST Limit"),
                (3, "300001", "*ST ChiNext Limit"),
                (4, "920001", "Beijing Limit"),
                (5, "600009", "Above Derived Limit"),
            ]
        )
        provider = StubProvider(
            {
                "000001": [
                    {"trade_date": "2026-08-09", "open": 9.95, "close": 10.00},
                    {"trade_date": "2026-08-10", "open": 10.80, "close": 11.00},
                ],
                "000003": [
                    {"trade_date": "2026-08-09", "open": 10.00, "close": 10.00},
                    {"trade_date": "2026-08-10", "open": 10.20, "close": 10.50},
                ],
                "300001": [
                    {"trade_date": "2026-08-09", "open": 10.00, "close": 10.00},
                    {"trade_date": "2026-08-10", "open": 11.70, "close": 12.00},
                ],
                "920001": [
                    {"trade_date": "2026-08-09", "open": 10.00, "close": 10.00},
                    {"trade_date": "2026-08-10", "open": 12.80, "close": 13.00},
                ],
                "600009": [
                    {"trade_date": "2026-08-09", "open": 10.00, "close": 10.00},
                    {"trade_date": "2026-08-10", "open": 10.90, "close": 11.01},
                ],
            }
        )

        snapshot, issues = collect_close_email_snapshot(
            report,
            cache_db=self.db_path.parent / "cache.sqlite",
            provider=provider,
            quote_time=datetime(2026, 8, 10, 15, 10, tzinfo=CN_TZ),
        )

        self.assertEqual(issues, [])
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        by_code = {
            str(item["code"]): item
            for item in snapshot["top5_close_performance"]
            if isinstance(item, dict)
        }
        self.assertTrue(bool(by_code["000001"]["is_limit_up"]))
        self.assertTrue(bool(by_code["000003"]["is_limit_up"]))
        self.assertTrue(bool(by_code["300001"]["is_limit_up"]))
        self.assertTrue(bool(by_code["920001"]["is_limit_up"]))
        self.assertFalse(bool(by_code["600009"]["is_limit_up"]))
        self.assertAlmostEqual(float(by_code["000001"]["change_pct"]), 1.85, places=2)

    def test_snapshot_rounds_limit_threshold_and_missing_previous_close_is_conservative(self) -> None:
        report = complete_report_for_stocks(
            [
                (1, "600010", "Rounded Main Board"),
                (2, "600011", "Missing Prior Close"),
                (3, "688001", "STAR Limit"),
                (4, "600012", "Below Limit"),
                (5, "000005", "Another Below Limit"),
            ]
        )
        provider = StubProvider(
            {
                "600010": [
                    {"trade_date": "2026-08-09", "open": 7.10, "close": 7.27},
                    {"trade_date": "2026-08-10", "open": 7.60, "close": 7.997},
                ],
                "600011": [
                    {"trade_date": "2026-08-10", "open": 10.80, "close": 11.00},
                ],
                "688001": [
                    {"trade_date": "2026-08-09", "open": 20.00, "close": 20.00},
                    {"trade_date": "2026-08-10", "open": 23.00, "close": 24.00},
                ],
                "600012": [
                    {"trade_date": "2026-08-09", "open": 10.00, "close": 10.00},
                    {"trade_date": "2026-08-10", "open": 10.20, "close": 10.98},
                ],
                "000005": [
                    {"trade_date": "2026-08-09", "open": 5.00, "close": 5.00},
                    {"trade_date": "2026-08-10", "open": 5.10, "close": 5.24},
                ],
            }
        )

        snapshot, issues = collect_close_email_snapshot(
            report,
            cache_db=self.db_path.parent / "cache.sqlite",
            provider=provider,
            quote_time=datetime(2026, 8, 10, 15, 10, tzinfo=CN_TZ),
        )

        self.assertEqual(issues, [])
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        by_code = {
            str(item["code"]): item
            for item in snapshot["top5_close_performance"]
            if isinstance(item, dict)
        }
        self.assertTrue(bool(by_code["600010"]["is_limit_up"]), "7.27 * 1.10 should round to 8.00")
        self.assertFalse(bool(by_code["600011"]["is_limit_up"]), "missing prior close must stay conservative")
        self.assertTrue(bool(by_code["688001"]["is_limit_up"]))
        self.assertFalse(bool(by_code["600012"]["is_limit_up"]))
        self.assertFalse(bool(by_code["000005"]["is_limit_up"]))
        self.assertAlmostEqual(float(by_code["600010"]["close_price"]), 8.00, places=2)

    def test_waits_for_all_quotes_then_snapshots_recipients_and_sends_full_content(self) -> None:
        report = complete_report()
        campaign = create_daily_top5_close_email_campaign(
            self.db_path,
            report=report,
            now_dt=datetime(2026, 8, 10, 9, 30, tzinfo=CN_TZ),
        )
        self.assertEqual(campaign["status"], "pending")
        self.assertEqual(campaign["total"], 0)

        missing_provider = StubProvider(
            {
                f"00000{index}": [
                    {"trade_date": "2026-08-09", "open": 9 + index, "close": 10 + index},
                    {"trade_date": "2026-08-10", "open": 10 + index, "close": 10.5 + index},
                ]
                for index in range(1, 5)
            }
        )
        self.assertTrue(
            process_next_daily_top5_close_email(
                self.db_path,
                cache_db=self.db_path.parent / "cache.sqlite",
                provider=missing_provider,
                now_dt=datetime(2026, 8, 10, 15, 10, tzinfo=CN_TZ),
            )
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                """
                SELECT status, calculation_status, next_calculation_at, calculation_last_error
                FROM daily_top5_close_email_campaigns
                """
            ).fetchone()
        self.assertEqual(row[0], "pending")
        self.assertEqual(row[1], "pending")
        self.assertTrue(str(row[2]).startswith("2026-08-10T15:15:00"))
        self.assertIn("quote_missing", str(row[3]))

        full_provider = StubProvider(
            {
                "000001": [
                    {"trade_date": "2026-08-09", "open": 10.0, "close": 11.0},
                    {"trade_date": "2026-08-10", "open": 11.0, "close": 12.10},
                ],
                **{
                    f"00000{index}": [
                        {"trade_date": "2026-08-09", "open": 9 + index, "close": 10 + index},
                        {"trade_date": "2026-08-10", "open": 10 + index, "close": 10.55 + index},
                    ]
                    for index in range(2, 6)
                },
            }
        )
        self.assertTrue(
            process_next_daily_top5_close_email(
                self.db_path,
                cache_db=self.db_path.parent / "cache.sqlite",
                provider=full_provider,
                now_dt=datetime(2026, 8, 10, 15, 15, tzinfo=CN_TZ),
            )
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            campaign_row = conn.execute(
                """
                SELECT status, calculation_status, close_report_json
                FROM daily_top5_close_email_campaigns
                """
            ).fetchone()
            rows = conn.execute(
                """
                SELECT email, status, content_variant
                FROM daily_top5_close_email_deliveries
                ORDER BY email
                """
            ).fetchall()
        self.assertEqual(str(campaign_row["status"]), "pending")
        self.assertEqual(str(campaign_row["calculation_status"]), "ready")
        self.assertIn("top5_close_performance", str(campaign_row["close_report_json"]))
        self.assertIn('"is_limit_up":true', str(campaign_row["close_report_json"]).lower())
        self.assertIn('"is_limit_up":false', str(campaign_row["close_report_json"]).lower())
        by_email = {str(row["email"]): row for row in rows}
        self.assertEqual(str(by_email["member@example.test"]["status"]), "pending")
        self.assertEqual(str(by_email["ordinary@example.test"]["content_variant"]), "full")
        self.assertEqual(str(by_email["optedout@example.test"]["status"]), "skipped")
        self.assertNotIn("admin@example.test", by_email)

        sent: dict[str, dict[str, str]] = {}

        def capture(email: str, *, subject: str, text: str, html: str, message_id: str = "") -> None:
            sent[email] = {"subject": subject, "text": text, "html": html, "message_id": message_id}

        with mock.patch.dict("os.environ", {"PUBLIC_SITE_URL": "https://trade.example.test"}, clear=False), mock.patch(
            "trade_review_agent.auth_system._send_smtp_message",
            side_effect=capture,
        ):
            while process_next_daily_top5_close_email(
                self.db_path,
                cache_db=self.db_path.parent / "cache.sqlite",
                now_dt=datetime(2026, 8, 10, 15, 16, tzinfo=CN_TZ),
            ):
                pass

        self.assertEqual(set(sent), {"member@example.test", "ordinary@example.test"})
        self.assertIn("开盘 11.00", sent["member@example.test"]["text"])
        self.assertIn("收盘表现", sent["ordinary@example.test"]["subject"])
        self.assertIn("是否涨停 涨停", sent["member@example.test"]["text"])
        self.assertIn("未涨停", sent["member@example.test"]["text"])
        self.assertIn("是否涨停", sent["member@example.test"]["html"])
        self.assertRegex(sent["member@example.test"]["message_id"], r"^daily-top5-close-c\d+-d\d+$")

    def test_cutoff_failure_requires_manual_retry_before_sending(self) -> None:
        create_daily_top5_close_email_campaign(
            self.db_path,
            report=complete_report(),
            now_dt=datetime(2026, 8, 10, 9, 30, tzinfo=CN_TZ),
        )
        empty_provider = StubProvider({})
        self.assertTrue(
            process_next_daily_top5_close_email(
                self.db_path,
                cache_db=self.db_path.parent / "cache.sqlite",
                provider=empty_provider,
                now_dt=datetime(2026, 8, 10, 16, 0, tzinfo=CN_TZ),
            )
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            status, calc_status = conn.execute(
                "SELECT status, calculation_status FROM daily_top5_close_email_campaigns"
            ).fetchone()
            delivery_count = conn.execute(
                "SELECT COUNT(*) FROM daily_top5_close_email_deliveries"
            ).fetchone()[0]
        self.assertEqual((status, calc_status), ("failed", "failed"))
        self.assertEqual(delivery_count, 0)

        retried = retry_daily_top5_close_email_campaign(
            self.db_path,
            campaign_id=1,
            now_dt=datetime(2026, 8, 10, 16, 5, tzinfo=CN_TZ),
        )
        self.assertEqual(retried["status"], "pending")
        full_provider = StubProvider(
            {
                f"00000{index}": [{"trade_date": "2026-08-10", "open": 20 + index, "close": 20.25 + index}]
                for index in range(1, 6)
            }
        )
        self.assertTrue(
            process_next_daily_top5_close_email(
                self.db_path,
                cache_db=self.db_path.parent / "cache.sqlite",
                provider=full_provider,
                now_dt=datetime(2026, 8, 10, 16, 5, tzinfo=CN_TZ),
            )
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            status, calc_status = conn.execute(
                "SELECT status, calculation_status FROM daily_top5_close_email_campaigns"
            ).fetchone()
            delivery_count = conn.execute(
                "SELECT COUNT(*) FROM daily_top5_close_email_deliveries"
            ).fetchone()[0]
        self.assertEqual((status, calc_status), ("pending", "ready"))
        self.assertGreater(delivery_count, 0)

    def test_pending_campaign_cannot_auto_run_after_cutoff(self) -> None:
        create_daily_top5_close_email_campaign(
            self.db_path,
            report=complete_report(),
            now_dt=datetime(2026, 8, 10, 9, 30, tzinfo=CN_TZ),
        )
        full_provider = StubProvider(
            {
                f"00000{index}": [{"trade_date": "2026-08-10", "open": 10 + index, "close": 11 + index}]
                for index in range(1, 6)
            }
        )

        self.assertTrue(
            process_next_daily_top5_close_email(
                self.db_path,
                provider=full_provider,
                now_dt=datetime(2026, 8, 10, 23, 0, tzinfo=CN_TZ),
            )
        )

        with closing(sqlite3.connect(self.db_path)) as conn:
            status, calc_status, next_at = conn.execute(
                "SELECT status, calculation_status, next_calculation_at FROM daily_top5_close_email_campaigns"
            ).fetchone()
            delivery_count = conn.execute(
                "SELECT COUNT(*) FROM daily_top5_close_email_deliveries"
            ).fetchone()[0]
        self.assertEqual((status, calc_status, next_at), ("failed", "failed", None))
        self.assertEqual(delivery_count, 0)

    def test_recovery_does_not_rearm_stale_calculation_after_cutoff(self) -> None:
        create_daily_top5_close_email_campaign(
            self.db_path,
            report=complete_report(),
            now_dt=datetime(2026, 8, 10, 9, 30, tzinfo=CN_TZ),
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE daily_top5_close_email_campaigns
                    SET calculation_status = 'calculating',
                        calculation_started_at = '2026-08-10T15:30:00+08:00'
                    """
                )

        recovered = recover_daily_top5_close_email_queue(
            self.db_path,
            now_dt=datetime(2026, 8, 10, 23, 0, tzinfo=CN_TZ),
        )

        self.assertEqual(recovered, 1)
        with closing(sqlite3.connect(self.db_path)) as conn:
            status, calc_status, next_at = conn.execute(
                "SELECT status, calculation_status, next_calculation_at FROM daily_top5_close_email_campaigns"
            ).fetchone()
        self.assertEqual((status, calc_status, next_at), ("failed", "failed", None))


if __name__ == "__main__":
    unittest.main()
