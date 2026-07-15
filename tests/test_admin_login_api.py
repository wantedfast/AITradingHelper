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


class AdminLoginApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        with patch.dict("os.environ", {"ADMIN_PHONE": "", "ADMIN_PASSWORD": ""}, clear=False):
            init_auth_db(self.db_path)

        salt, password_hash = auth_system._hash_password("safe-password")
        now = "2026-07-15T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                self.user_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, ?, ?, 'user', 'active', ?, ?)
                        """,
                        ("user-phone", "normaluser", "user@example.com", password_hash, salt, "USER001", now),
                    ).lastrowid
                )
                self.admin_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, ?, ?, 'admin', 'active', ?, ?)
                        """,
                        ("admin-phone", "adminuser", "admin@example.com", password_hash, salt, "ADMIN001", now),
                    ).lastrowid
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

    def request(self, path: str, payload: dict) -> tuple[int, dict]:
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def session_count(self, user_id: int) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,)).fetchone()[0])

    def test_admin_login_succeeds_for_admin_account(self) -> None:
        status, payload = self.request(
            "/api/auth/admin-login",
            {"account": "adminuser", "password": "safe-password"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["role"], "admin")
        self.assertTrue(payload["token"])
        self.assertEqual(self.session_count(self.admin_id), 1)

    def test_ordinary_login_still_succeeds_for_ordinary_account(self) -> None:
        status, payload = self.request(
            "/api/auth/password-login",
            {"account": "user@example.com", "password": "safe-password"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["role"], "user")
        self.assertTrue(payload["token"])
        self.assertEqual(self.session_count(self.user_id), 1)

    def test_ordinary_login_rejects_admin_without_creating_session(self) -> None:
        status, payload = self.request(
            "/api/auth/password-login",
            {"account": "admin@example.com", "password": "safe-password"},
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "管理员账号请使用运营后台入口登录")
        self.assertEqual(self.session_count(self.admin_id), 0)

    def test_ordinary_login_does_not_reveal_admin_account_for_wrong_password(self) -> None:
        status, payload = self.request(
            "/api/auth/password-login",
            {"account": "admin@example.com", "password": "wrong-password"},
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "账号/邮箱或密码错误")
        self.assertEqual(self.session_count(self.admin_id), 0)

    def test_admin_login_rejects_ordinary_account_with_generic_error_and_no_session(self) -> None:
        status, payload = self.request(
            "/api/auth/admin-login",
            {"account": "normaluser", "password": "safe-password"},
        )
        missing_status, missing_payload = self.request(
            "/api/auth/admin-login",
            {"account": "missing-user", "password": "safe-password"},
        )

        self.assertEqual((status, missing_status), (401, 401))
        self.assertEqual(payload["error"], "管理员账号或权限错误")
        self.assertEqual(missing_payload["error"], payload["error"])
        self.assertEqual(self.session_count(self.user_id), 0)

    def test_admin_login_rejects_wrong_password_without_creating_session(self) -> None:
        status, payload = self.request(
            "/api/auth/admin-login",
            {"account": "admin@example.com", "password": "wrong-password"},
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "管理员账号或权限错误")
        self.assertEqual(self.session_count(self.admin_id), 0)


if __name__ == "__main__":
    unittest.main()
