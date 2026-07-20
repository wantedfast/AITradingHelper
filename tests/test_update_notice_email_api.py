from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import init_auth_db


class UpdateNoticeEmailApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        init_auth_db(self.db_path)
        now = "2026-07-15T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                for role, token, email in (("admin", "admin-token", "admin@example.com"), ("user", "user-token", "user@example.com")):
                    user_id = int(conn.execute(
                        """
                        INSERT INTO users (phone, username, email, email_verified, password_hash, password_salt, role, status, invite_code, created_at)
                        VALUES (?, ?, ?, 1, 'hash', 'salt', ?, 'active', ?, ?)
                        """,
                        (f"{role}-phone", f"{role}name", email, role, f"{role.upper()}CODE", now),
                    ).lastrowid)
                    conn.execute("INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', ?)", (token, user_id, now))
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

    def request(self, path: str, *, token: str, payload: dict | None = None) -> tuple[int, dict]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.base_url + path, data=body, method="POST", headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_user_can_change_preference_but_value_must_be_boolean(self) -> None:
        bad_status, _ = self.request("/api/auth/email-preferences", token="user-token", payload={"update_emails_enabled": "false"})
        ok_status, payload = self.request("/api/auth/email-preferences", token="user-token", payload={"update_emails_enabled": False})
        self.assertEqual(bad_status, 400)
        self.assertEqual(ok_status, 200)
        self.assertFalse(payload["user"]["update_emails_enabled"])

    def test_publish_requires_explicit_choice_and_request_id(self) -> None:
        base = {"title": "Update", "version": "2026-07-15", "items": ["One"], "status": "published"}
        missing_status, _ = self.request("/api/admin/update-notices", token="admin-token", payload=base)
        invalid_status, _ = self.request("/api/admin/update-notices", token="admin-token", payload={**base, "send_email": False})
        ok_status, payload = self.request("/api/admin/update-notices", token="admin-token", payload={
            **base, "send_email": True, "request_id": "api-campaign-001"
        })
        self.assertEqual(missing_status, 400)
        self.assertEqual(invalid_status, 400)
        self.assertEqual(ok_status, 201)
        self.assertEqual(payload["notice"]["status"], "published")
        self.assertEqual(payload["email_campaign"]["pending"], 1)

    def test_non_admin_cannot_publish_or_retry(self) -> None:
        status, _ = self.request("/api/admin/update-notices", token="user-token", payload={
            "title": "Update", "version": "2026-07-15", "items": ["One"], "status": "published",
            "send_email": False, "request_id": "api-campaign-002",
        })
        retry_status, _ = self.request("/api/admin/update-email-campaigns/1/retry", token="user-token", payload={})
        self.assertEqual(status, 403)
        self.assertEqual(retry_status, 403)


if __name__ == "__main__":
    unittest.main()
