from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from trade_review_agent import auth_system
from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import init_auth_db


class AdminSectionApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        with patch.dict("os.environ", {"ADMIN_PHONE": "", "ADMIN_PASSWORD": ""}, clear=False):
            init_auth_db(self.db_path)

        salt, password_hash = auth_system._hash_password("safe-password")
        now = "2026-07-20T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                self.admin_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash, password_salt,
                            role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, ?, ?, 'admin', 'active', ?, ?)
                        """,
                        ("admin-phone", "adminuser", "admin@example.com", password_hash, salt, "ADMIN001", now),
                    ).lastrowid
                )
                self.user_ids = []
                for index in range(3):
                    user_id = int(
                        conn.execute(
                            """
                            INSERT INTO users (
                                phone, username, email, email_verified, update_emails_enabled,
                                password_hash, password_salt, role, status, invite_code, created_at, last_login_at
                            ) VALUES (?, ?, ?, 1, 1, ?, ?, 'user', ?, ?, ?, ?)
                            """,
                            (
                                f"1380000000{index}",
                                f"alpha{index}",
                                f"alpha{index}@example.com",
                                password_hash,
                                salt,
                                "disabled" if index == 2 else "active",
                                f"USER{index:03d}",
                                f"2026-07-1{index}T09:00:00+08:00",
                                f"2026-07-2{index}T08:00:00+08:00",
                            ),
                        ).lastrowid
                    )
                    self.user_ids.append(user_id)
                    conn.execute(
                        "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, ?, 'seed', ?, ?)",
                        (user_id, 10 + index, f"seed-{index}", now),
                    )
                    conn.execute(
                        "INSERT INTO usage_events (user_id, feature, credits_spent, status, related_id, ip, created_at) VALUES (?, 'review_report', ?, 'charged', ?, '', ?)",
                        (user_id, index + 1, f"use-{index}", now),
                    )
                conn.execute(
                    """
                    INSERT INTO credit_grant_campaigns (
                        request_id, credits, reason, status, eligible_count, granted_count, created_by, created_at, completed_at
                    ) VALUES ('credit-campaign-001', 5, '批量补偿', 'completed', 3, 3, ?, ?, ?)
                    """,
                    (self.admin_id, now, now),
                )
                conn.execute(
                    """
                    INSERT INTO orders (
                        user_id, order_no, plan_name, credits, amount_cents, status, created_at,
                        product_type, payment_method, payer_name, payer_paid_at, submitted_amount_cents
                    ) VALUES (?, 'ORDER-001', '购买次数', 12, 1200, 'submitted', ?, 'credits', 'alipay', 'tester', ?, 1200)
                    """,
                    (self.user_ids[0], now, now),
                )
                conn.execute(
                    """
                    INSERT INTO update_notices (
                        title, version, items_json, summary, content_markdown, status, audience, created_by, created_at, updated_at, published_at
                    ) VALUES ('发布更新', '2026-07-20', '["一","二"]', '摘要', '- 一', 'published', 'registered_users', ?, ?, ?, ?)
                    """,
                    (self.admin_id, now, now, now),
                )
                notice_id = int(conn.execute("SELECT id FROM update_notices").fetchone()[0])
                conn.execute(
                    """
                    INSERT INTO update_email_campaigns (notice_id, request_id, status, created_by, created_at)
                    VALUES (?, 'notice-request-001', 'partial_failed', ?, ?)
                    """,
                    (notice_id, self.admin_id, now),
                )
                notice_campaign_id = int(conn.execute("SELECT id FROM update_email_campaigns").fetchone()[0])
                for user_id, state in ((self.user_ids[0], "sent"), (self.user_ids[1], "failed")):
                    conn.execute(
                        """
                        INSERT INTO update_email_deliveries (
                            campaign_id, user_id, email, status, attempt_count, next_attempt_at, last_error, updated_at
                        ) VALUES (?, ?, ?, ?, 1, NULL, '', ?)
                        """,
                        (notice_campaign_id, user_id, f"user{user_id}@example.com", state, now),
                    )
                conn.execute(
                    """
                    INSERT INTO daily_top5_email_campaigns (trade_date, report_id, report_json, status, created_at)
                    VALUES ('2026-07-20', 'top5-001', '{}', 'partial_failed', ?)
                    """,
                    (now,),
                )
                top5_campaign_id = int(conn.execute("SELECT id FROM daily_top5_email_campaigns").fetchone()[0])
                conn.execute(
                    """
                    INSERT INTO daily_top5_email_deliveries (
                        campaign_id, user_id, email, content_variant, membership_active, status, attempt_count, next_attempt_at, last_error, updated_at
                    ) VALUES (?, ?, ?, 'teaser', 0, 'failed', 2, NULL, 'smtp failed', ?)
                    """,
                    (top5_campaign_id, self.user_ids[0], "top5@example.com", now),
                )
                conn.execute(
                    """
                    INSERT INTO ai_report_email_campaigns (report_type, run_id, report_date, report_json, status, created_at)
                    VALUES ('market_day', 'market-001', '2026-07-20', '{}', 'pending', ?)
                    """,
                    (now,),
                )
                ai_campaign_id = int(conn.execute("SELECT id FROM ai_report_email_campaigns").fetchone()[0])
                conn.execute(
                    """
                    INSERT INTO ai_report_email_deliveries (
                        campaign_id, user_id, email, content_variant, membership_active, status, attempt_count, next_attempt_at, last_error, updated_at
                    ) VALUES (?, ?, ?, 'full', 1, 'pending', 0, ?, '', ?)
                    """,
                    (ai_campaign_id, self.user_ids[0], "ai@example.com", now, now),
                )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('admin-token', ?, '2999-01-01T00:00:00+08:00', ?)",
                    (self.admin_id, now),
                )

        self.auth_patch = patch.object(simple_api, "AUTH_DB", self.db_path)
        self.auth_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.auth_patch.stop()
        self.temp_dir.cleanup()

    def request(self, path: str, *, token: str = "admin-token") -> tuple[int, dict]:
        request = Request(self.base_url + path, method="GET", headers={"Authorization": f"Bearer {token}"})
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_users_endpoint_paginates_filters_and_includes_campaigns(self) -> None:
        status, payload = self.request("/api/admin/users?q=alpha2&status=disabled&page=1&page_size=1")

        self.assertEqual(status, 200)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["page_size"], 1)
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["status"], "disabled")
        self.assertEqual(payload["items"][0]["username"], "alpha2")
        self.assertEqual(payload["campaigns"][0]["reason"], "批量补偿")

    def test_orders_endpoint_filters_submitted_orders(self) -> None:
        status, payload = self.request("/api/admin/orders?status=submitted")

        self.assertEqual(status, 200)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["order_no"], "ORDER-001")
        self.assertEqual(payload["items"][0]["username"], "alpha0")
        self.assertEqual(payload["items"][0]["status"], "submitted")

    def test_emails_endpoint_merges_failed_campaigns_across_sources(self) -> None:
        status, payload = self.request("/api/admin/emails?status=failed")

        self.assertEqual(status, 200)
        self.assertEqual(payload["total"], 2)
        self.assertEqual({item["kind"] for item in payload["items"]}, {"update_notice", "daily_top5"})
        self.assertTrue(all(item["failed"] > 0 for item in payload["items"]))
        self.assertEqual(payload["delivery_totals"]["failed"], 2)
        self.assertEqual(payload["delivery_totals"]["sent"], 1)
        self.assertEqual(payload["summary"]["campaigns"], 2)
        self.assertEqual(payload["summary"]["campaigns_with_failures"], 2)
        self.assertEqual(payload["summary"]["recipients"], 3)
        self.assertEqual(payload["summary"]["smtp_acceptance_rate"], 33.3)
        self.assertEqual({item["key"] for item in payload["by_kind"]}, {"update_notice", "daily_top5"})
        self.assertEqual(payload["failure_reasons"], [{"reason": "other", "count": 2}])

    def test_email_detail_returns_failed_recipient_and_error(self) -> None:
        status, payload = self.request("/api/admin/emails/daily_top5/1")

        self.assertEqual(status, 200)
        self.assertEqual(payload["kind"], "daily_top5")
        self.assertEqual(payload["failed_deliveries"], [{
            "email": "top5@example.com",
            "status": "failed",
            "attempt_count": 2,
            "last_error": "smtp failed",
            "next_attempt_at": None,
            "updated_at": "2026-07-20T10:00:00+08:00",
        }])

    def test_email_deliveries_endpoint_lists_all_states_and_filters_recipient(self) -> None:
        status, payload = self.request("/api/admin/emails/update_notice/1/deliveries?page=1&page_size=20")

        self.assertEqual(status, 200)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["status_counts"]["sent"], 1)
        self.assertEqual(payload["status_counts"]["failed"], 1)
        self.assertEqual({item["status"] for item in payload["items"]}, {"sent", "failed"})

        status, filtered = self.request("/api/admin/emails/update_notice/1/deliveries?status=failed&q=user")
        self.assertEqual(status, 200)
        self.assertEqual(filtered["total"], 1)
        self.assertEqual(filtered["items"][0]["status"], "failed")

    def test_email_pagination_does_not_truncate_older_campaigns_before_counting(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            notice_id = int(conn.execute("SELECT id FROM update_notices LIMIT 1").fetchone()[0])
            with conn:
                conn.executemany(
                    """
                    INSERT INTO update_email_campaigns (notice_id, request_id, status, created_by, created_at)
                    VALUES (?, ?, 'completed', ?, ?)
                    """,
                    [
                        (notice_id, f"bulk-campaign-{index:03d}", self.admin_id, f"2026-06-{(index % 28) + 1:02d}T10:00:00+08:00")
                        for index in range(125)
                    ],
                )

        status, payload = self.request("/api/admin/emails?kind=update_notice&page=2&page_size=100")

        self.assertEqual(status, 200)
        self.assertEqual(payload["total"], 126)
        self.assertEqual(payload["total_pages"], 2)
        self.assertEqual(len(payload["items"]), 26)


if __name__ == "__main__":
    unittest.main()
