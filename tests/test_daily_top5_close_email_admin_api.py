from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import (
    CN_TZ,
    create_daily_top5_close_email_campaign,
    init_auth_db,
)
from tests.test_daily_top5_close_email import complete_report


class DailyTop5CloseEmailAdminApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        self.trade_date = datetime.now(CN_TZ).date().isoformat()
        init_auth_db(self.db_path)
        now = "2026-07-16T09:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                for role, token in (("admin", "admin-token"), ("user", "user-token")):
                    user_id = int(
                        conn.execute(
                            """
                            INSERT INTO users (
                                phone, username, email, email_verified, update_emails_enabled,
                                password_hash, password_salt, role, status, invite_code, created_at
                            ) VALUES (?, ?, ?, 1, 1, 'hash', 'salt', ?, 'active', ?, ?)
                            """,
                            (f"top5-close-{role}", f"top5-close-{role}", f"{role}@example.test", role, f"TOP5CLOSE{role.upper()}", now),
                        ).lastrowid
                    )
                    conn.execute(
                        "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', ?)",
                        (token, user_id, now),
                    )
        self.db_patch = patch.object(simple_api, "AUTH_DB", self.db_path)
        self.db_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        token: str = "",
        payload: dict | None = None,
    ) -> tuple[int, dict]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self.base_url + path, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_admin_emails_list_and_detail_expose_daily_top5_close_kind(self) -> None:
        campaign = create_daily_top5_close_email_campaign(
            self.db_path,
            report=complete_report(trade_date=self.trade_date),
        )
        campaign_id = int(campaign["id"])

        list_status, listing = self.request(
            "/api/admin/emails?kind=daily_top5_close&page=1&page_size=20",
            token="admin-token",
        )
        detail_status, detail = self.request(
            f"/api/admin/emails/daily_top5_close/{campaign_id}",
            token="admin-token",
        )

        self.assertEqual(list_status, 200)
        self.assertEqual(detail_status, 200)
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["kind"], "daily_top5_close")
        self.assertEqual(listing["items"][0]["trade_date"], self.trade_date)
        self.assertEqual(detail["kind"], "daily_top5_close")
        self.assertEqual(detail["id"], campaign_id)
        self.assertEqual(detail["trade_date"], self.trade_date)
        self.assertIn("failed_deliveries", detail)

    def test_non_admin_cannot_view_daily_top5_close_email_admin_endpoints(self) -> None:
        campaign = create_daily_top5_close_email_campaign(
            self.db_path,
            report=complete_report(trade_date=self.trade_date),
        )

        list_status, _ = self.request("/api/admin/emails?kind=daily_top5_close", token="user-token")
        detail_status, _ = self.request(
            f"/api/admin/emails/daily_top5_close/{int(campaign['id'])}",
            token="user-token",
        )

        self.assertEqual(list_status, 403)
        self.assertEqual(detail_status, 403)


if __name__ == "__main__":
    unittest.main()
