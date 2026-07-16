from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from trade_review_agent.auth_system import (
    CN_TZ,
    FEATURE_CREDIT_COSTS,
    admin_dashboard,
    consume_feature_credit_once,
    init_auth_db,
)


class AdminDashboardAnalyticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        with patch.dict("os.environ", {"ADMIN_PHONE": "", "ADMIN_PASSWORD": ""}, clear=False):
            init_auth_db(self.db_path)

        today = datetime.now(CN_TZ).date()
        self.today = today.isoformat()
        self.six_days_ago = (today - timedelta(days=6)).isoformat()
        before_window = (today - timedelta(days=40)).isoformat()
        just_before_week = (today - timedelta(days=8)).isoformat()
        future_day = (today + timedelta(days=1)).isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                self.user_ids = [
                    self._insert_user(conn, index, "user", before_window if index == 0 else self.six_days_ago)
                    for index in range(6)
                ]
                self.admin_id = self._insert_user(conn, 99, "admin", before_window)
                self.future_user_id = self._insert_user(conn, 100, "user", future_day)

                # Six successful users create a deterministic Top 5. User zero
                # also has a membership-free use, which must count as success.
                for user_index, user_id in enumerate(self.user_ids):
                    for event_index in range(6 - user_index):
                        day = self.today if event_index % 2 == 0 else self.six_days_ago
                        feature = "review_report" if event_index % 2 == 0 else "watch_plan"
                        status = "membership_free" if user_index == 0 and event_index == 0 else "charged"
                        credits = 0 if status == "membership_free" else 1
                        self._insert_usage(conn, user_id, feature, status, credits, day, event_index)

                # Repeatedly opening the same member-unlocked report may have
                # produced duplicate historical rows. Analytics must count the
                # first successful unlock only, not refreshes of that content.
                self._insert_usage(
                    conn,
                    self.user_ids[0],
                    "review_report",
                    "membership_free",
                    0,
                    self.today,
                    0,
                )

                # A duplicate that falls inside the selected window must not
                # count when its first successful unlock predates the window.
                self._insert_usage(
                    conn, self.user_ids[0], "market_day_report", "membership_free", 0, just_before_week, 70
                )
                self._insert_usage(
                    conn, self.user_ids[0], "market_day_report", "membership_free", 0, self.today, 70
                )

                # Neither an administrator nor a blocked attempt may influence
                # any of the new analytics.
                for event_index in range(12):
                    self._insert_usage(
                        conn, self.admin_id, "review_report", "charged", 2, self.today, event_index
                    )
                for event_index in range(10):
                    self._insert_usage(
                        conn,
                        self.user_ids[-1],
                        "ai_research_view",
                        "blocked_no_credits",
                        0,
                        self.today,
                        event_index + 20,
                    )
                self._insert_usage(
                    conn, self.future_user_id, "review_report", "charged", 2, future_day, 50
                )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _insert_user(conn: sqlite3.Connection, index: int, role: str, created_day: str) -> int:
        return int(
            conn.execute(
                """
                INSERT INTO users (
                    phone, username, email, email_verified, password_hash,
                    password_salt, role, status, invite_code, created_at
                ) VALUES (?, ?, ?, 1, 'hash', 'salt', ?, 'active', ?, ?)
                """,
                (
                    f"analytics-phone-{index}",
                    f"analyticsuser{index}",
                    f"analytics{index}@example.com",
                    role,
                    f"AN{index:06d}",
                    f"{created_day}T09:00:00+08:00",
                ),
            ).lastrowid
        )

    @staticmethod
    def _insert_usage(
        conn: sqlite3.Connection,
        user_id: int,
        feature: str,
        status: str,
        credits: int,
        day: str,
        sequence: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO usage_events (
                user_id, feature, credits_spent, status, related_id, ip, created_at
            ) VALUES (?, ?, ?, ?, ?, '', ?)
            """,
            (
                user_id,
                feature,
                credits,
                status,
                f"analytics-{user_id}-{sequence}",
                f"{day}T10:{sequence % 60:02d}:00+08:00",
            ),
        )

    def test_supported_windows_are_bounded_and_zero_filled(self) -> None:
        for requested_days in (7, 30, 90):
            with self.subTest(days=requested_days):
                analytics = admin_dashboard(self.db_path, days=requested_days)["analytics"]
                self.assertEqual(analytics["window"]["days"], requested_days)
                self.assertEqual(len(analytics["user_growth"]["by_day"]), requested_days)
                self.assertEqual(
                    len(analytics["high_frequency_users"][0]["usage_by_day"]), requested_days
                )
                observed_features = len(analytics["feature_usage"]["totals"])
                self.assertEqual(
                    len(analytics["feature_usage"]["by_day"]), requested_days * observed_features
                )

        self.assertEqual(admin_dashboard(self.db_path, days=0)["analytics"]["window"]["days"], 14)
        self.assertEqual(admin_dashboard(self.db_path, days=999)["analytics"]["window"]["days"], 90)

    def test_feature_totals_shares_and_success_status_filtering(self) -> None:
        payload = admin_dashboard(self.db_path, days=7)
        usage = payload["analytics"]["feature_usage"]
        totals = {item["feature"]: item for item in usage["totals"]}

        self.assertEqual(list(totals), list(FEATURE_CREDIT_COSTS))
        self.assertEqual(sum(item["count"] for item in totals.values()), 21)
        self.assertAlmostEqual(sum(item["share"] for item in totals.values()), 1.0, places=3)
        self.assertEqual(totals["ai_research_view"]["count"], 0)
        self.assertEqual(totals["market_day_report"]["count"], 0)
        self.assertTrue(any(item["count"] == 0 for item in usage["by_day"]))

        # The old field remains unchanged and therefore still contains blocked
        # and administrator rows for backward compatibility.
        self.assertGreater(sum(int(item["count"]) for item in payload["usage_by_day"]), 21)

    def test_growth_is_daily_and_cumulative(self) -> None:
        growth = admin_dashboard(self.db_path, days=7)["analytics"]["user_growth"]

        self.assertEqual(growth["starting_users"], 1)
        self.assertEqual(growth["total_users"], 6)
        self.assertEqual(growth["by_day"][0]["day"], self.six_days_ago)
        self.assertEqual(growth["by_day"][0]["new_users"], 5)
        self.assertEqual(growth["by_day"][0]["cumulative_users"], 6)
        self.assertEqual(growth["by_day"][-1]["cumulative_users"], 6)
        self.assertNotEqual(growth["total_users"], 7, "future-dated user leaked into analytics")

    def test_high_frequency_users_are_top_five_with_complete_curves(self) -> None:
        users = admin_dashboard(self.db_path, days=7)["analytics"]["high_frequency_users"]

        self.assertEqual(len(users), 5)
        self.assertEqual([item["total_uses"] for item in users], [6, 5, 4, 3, 2])
        self.assertNotIn(self.admin_id, [item["id"] for item in users])
        self.assertNotIn(self.user_ids[-1], [item["id"] for item in users])
        self.assertEqual(users[0]["active_days"], 2)
        self.assertEqual(sum(day["count"] for day in users[0]["usage_by_day"]), 6)
        self.assertEqual(users[0]["credits_spent"], 5)

    def test_member_unlock_is_idempotent_and_counted_once(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "UPDATE users SET membership_status = 'active', membership_expires_at = ? WHERE id = ?",
                    ((datetime.now(CN_TZ) + timedelta(days=1)).isoformat(), self.user_ids[0]),
                )

        for _ in range(2):
            consume_feature_credit_once(
                self.db_path,
                user_id=self.user_ids[0],
                feature="ai_research_view",
                related_id="same-member-report",
            )

        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT COUNT(*)
                FROM usage_events
                WHERE user_id = ? AND feature = ? AND related_id = ?
                """,
                (self.user_ids[0], "ai_research_view", "same-member-report"),
            ).fetchone()[0]
        self.assertEqual(rows, 1)

        totals = {
            item["feature"]: item
            for item in admin_dashboard(self.db_path, days=7)["analytics"]["feature_usage"]["totals"]
        }
        self.assertEqual(totals["ai_research_view"]["count"], 1)

    def test_failed_attempt_before_success_does_not_hide_real_usage(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                self._insert_usage(
                    conn, self.user_ids[0], "auction_strength_view", "blocked_no_credits", 0, self.today, 80
                )
                self._insert_usage(
                    conn, self.user_ids[0], "auction_strength_view", "charged", 2, self.today, 80
                )

        totals = {
            item["feature"]: item
            for item in admin_dashboard(self.db_path, days=7)["analytics"]["feature_usage"]["totals"]
        }
        self.assertEqual(totals["auction_strength_view"]["count"], 1)
        self.assertEqual(totals["auction_strength_view"]["credits"], 2)

    def test_recent_usage_events_include_username_time_and_top5_market_session(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO usage_events (
                        user_id, feature, credits_spent, status, related_id, ip, created_at
                    ) VALUES (?, 'auction_strength_view', 2, 'charged', 'top5-before-open', '', ?)
                    """,
                    (self.user_ids[0], f"{self.today}T09:26:15+08:00"),
                )
                conn.execute(
                    """
                    INSERT INTO usage_events (
                        user_id, feature, credits_spent, status, related_id, ip, created_at
                    ) VALUES (?, 'auction_strength_view', 0, 'membership_free', 'top5-after-open', '', ?)
                    """,
                    (self.user_ids[1], f"{self.today}T09:31:05+08:00"),
                )

        events = admin_dashboard(self.db_path, days=7)["analytics"]["recent_usage_events"]
        before_open = next(item for item in events if item["related_id"] == "top5-before-open")
        after_open = next(item for item in events if item["related_id"] == "top5-after-open")

        self.assertEqual(before_open["display_name"], "analyticsuser0")
        self.assertEqual(before_open["used_at"], f"{self.today}T09:26:15+08:00")
        self.assertEqual(before_open["market_session"], "before_open")
        self.assertEqual(after_open["market_session"], "after_open")
        self.assertEqual(after_open["status"], "membership_free")
        self.assertNotIn(self.admin_id, [item["user_id"] for item in events])
        self.assertFalse(any(item["status"] == "blocked_no_credits" for item in events))


if __name__ == "__main__":
    unittest.main()
