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

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import init_auth_db
from tests.test_daily_top5_email import complete_report


class DailyTop5EmailApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.db_path = root / "auth.sqlite"
        self.report_path = root / "auction-strength.jsonl"
        init_auth_db(self.db_path)
        now = "2026-07-16T09:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                for role, token in (("admin", "admin-token"), ("user", "user-token")):
                    user_id = int(conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, update_emails_enabled,
                            password_hash, password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 1, 'hash', 'salt', ?, 'active', ?, ?)
                        """,
                        (f"top5-{role}", f"top5-{role}", f"{role}@example.test", role, f"TOP5{role.upper()}", now),
                    ).lastrowid)
                    conn.execute(
                        "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', ?)",
                        (token, user_id, now),
                    )
        self.db_patch = patch.object(simple_api, "AUTH_DB", self.db_path)
        self.path_patch = patch.object(simple_api, "AUCTION_STRENGTH_PATH", self.report_path)
        self.secret_patch = patch.dict("os.environ", {"AUCTION_STRENGTH_SECRET": "top5-secret"}, clear=False)
        self.db_patch.start()
        self.path_patch.start()
        self.secret_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.secret_patch.stop()
        self.path_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        token: str = "",
        payload: dict | None = None,
        webhook: bool = False,
    ) -> tuple[int, dict]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if webhook:
            headers["x-auction-strength-secret"] = "top5-secret"
        request = Request(self.base_url + path, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_incomplete_webhook_then_complete_webhook_creates_exactly_one_campaign(self) -> None:
        incomplete = complete_report()
        incomplete["top5_strong_stocks"] = [{"rank": index} for index in range(1, 6)]
        status, payload = self.request("/api/auction-strength", method="POST", payload=incomplete, webhook=True)
        self.assertEqual(status, 202)
        self.assertIsNone(payload["email_campaign"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_top5_email_campaigns").fetchone()[0], 0)

        complete = complete_report(report_id="complete-run")
        first_status, first = self.request("/api/auction-strength", method="POST", payload=complete, webhook=True)
        second_status, second = self.request("/api/auction-strength", method="POST", payload=complete, webhook=True)
        self.assertEqual((first_status, second_status), (202, 202))
        self.assertEqual(first["email_campaign"]["id"], second["email_campaign"]["id"])
        self.assertEqual(first["email_campaign"]["pending"], 1)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_top5_email_campaigns").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_top5_email_deliveries").fetchone()[0], 1)

    def test_dashboard_exposes_campaign_and_retry_requires_admin(self) -> None:
        status, posted = self.request(
            "/api/auction-strength", method="POST", payload=complete_report(), webhook=True
        )
        self.assertEqual(status, 202)
        campaign_id = int(posted["email_campaign"]["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "UPDATE daily_top5_email_deliveries SET status = 'failed', attempt_count = 3 WHERE campaign_id = ?",
                    (campaign_id,),
                )
                conn.execute(
                    "UPDATE daily_top5_email_campaigns SET status = 'failed' WHERE id = ?", (campaign_id,)
                )

        dashboard_status, dashboard = self.request("/api/admin/dashboard?days=30", token="admin-token")
        self.assertEqual(dashboard_status, 200)
        self.assertEqual(dashboard["daily_top5_email_failed_count"], 1)
        self.assertEqual(dashboard["daily_top5_email_campaigns"][0]["trade_date"], "2026-07-16")
        self.assertEqual(dashboard["daily_top5_email_campaigns"][0]["failed"], 1)

        forbidden_status, _ = self.request(
            f"/api/admin/daily-top5-email-campaigns/{campaign_id}/retry", method="POST", token="user-token", payload={}
        )
        retry_status, retried = self.request(
            f"/api/admin/daily-top5-email-campaigns/{campaign_id}/retry", method="POST", token="admin-token", payload={}
        )
        self.assertEqual(forbidden_status, 403)
        self.assertEqual(retry_status, 200)
        self.assertEqual(retried["email_campaign"]["pending"], 1)
        self.assertEqual(retried["email_campaign"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
