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


class LegacyEmailBindingApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        with patch.dict("os.environ", {"ADMIN_PHONE": "", "ADMIN_PASSWORD": ""}, clear=False):
            init_auth_db(self.db_path)
        salt, password_hash = auth_system._hash_password("safe-password")
        now = "2026-07-15T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                self.legacy_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, '', 0, ?, ?, 'user', 'active', 'LEGACY01', ?)
                        """,
                        ("legacy-phone", "legacyuser", password_hash, salt, now),
                    ).lastrowid
                )
                self.verified_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, ?, ?, 'user', 'active', 'VERIFIED1', ?)
                        """,
                        ("verified-phone", "verifieduser", "used@example.com", password_hash, salt, now),
                    ).lastrowid
                )
                self.admin_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, 'legacy-admin@example.com', 0, ?, ?, 'admin', 'active', 'ADMIN001', ?)
                        """,
                        ("admin-phone", "adminuser", password_hash, salt, now),
                    ).lastrowid
                )
                for token, user_id in (
                    ("legacy-token", self.legacy_id),
                    ("verified-token", self.verified_id),
                    ("admin-token", self.admin_id),
                ):
                    conn.execute(
                        "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', ?)",
                        (token, user_id, now),
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

    def request(
        self,
        path: str,
        *,
        method: str = "POST",
        token: str = "legacy-token",
        payload: dict | None = None,
    ) -> tuple[int, dict]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def seed_code(
        self,
        email: str,
        code: str = "123456",
        *,
        expires_at: str = "2999-01-01T00:00:00+08:00",
    ) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO email_codes (email, code_hash, purpose, ip, consumed, expires_at, created_at)
                    VALUES (?, ?, 'bind_email', '127.0.0.1', 0, ?, '2026-07-15T10:00:00+08:00')
                    """,
                    (email, auth_system._hash_email_code(email, code), expires_at),
                )

    def test_legacy_user_can_bind_verified_email_and_code_is_consumed(self) -> None:
        email = "legacy.bound@example.com"
        with patch("trade_review_agent.auth_system.secrets.randbelow", return_value=123456), patch(
            "trade_review_agent.auth_system._send_email_code", return_value={"provider": "smtp"}
        ) as send_code:
            code_status, code_payload = self.request(
                "/api/auth/email-binding/code", payload={"email": email}
            )

        status, payload = self.request(
            "/api/auth/email-binding", payload={"email": email, "email_code": "123456"}
        )

        self.assertEqual(code_status, 200)
        self.assertTrue(code_payload["ok"])
        send_code.assert_called_once()
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["email"], email)
        self.assertIs(payload["user"]["email_verified"], True)
        self.assertIs(payload["user"]["email_binding_required"], False)
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT email, email_verified FROM users WHERE id = ?", (self.legacy_id,)
            ).fetchone()
            remaining_codes = conn.execute(
                "SELECT COUNT(*) FROM email_codes WHERE email = ?", (email,)
            ).fetchone()[0]
        self.assertEqual(row, (email, 1))
        self.assertEqual(remaining_codes, 0)

    def test_wrong_or_expired_code_does_not_change_legacy_user(self) -> None:
        cases = (
            ("wrong@example.com", "654321", "2999-01-01T00:00:00+08:00", 401),
            ("expired@example.com", "123456", "2000-01-01T00:00:00+08:00", 400),
        )
        for email, submitted_code, expires_at, expected_status in cases:
            with self.subTest(email=email):
                self.seed_code(email, expires_at=expires_at)
                status, _payload = self.request(
                    "/api/auth/email-binding", payload={"email": email, "email_code": submitted_code}
                )
                self.assertEqual(status, expected_status)
                with closing(sqlite3.connect(self.db_path)) as conn:
                    user = conn.execute(
                        "SELECT email, email_verified FROM users WHERE id = ?", (self.legacy_id,)
                    ).fetchone()
                    consumed = conn.execute(
                        "SELECT consumed FROM email_codes WHERE email = ?", (email,)
                    ).fetchone()[0]
                self.assertEqual(user, ("", 0))
                self.assertEqual(consumed, 0)

    def test_duplicate_email_and_already_verified_user_are_rejected(self) -> None:
        self.seed_code("used@example.com")
        duplicate_status, _ = self.request(
            "/api/auth/email-binding",
            payload={"email": "used@example.com", "email_code": "123456"},
        )
        verified_status, _ = self.request(
            "/api/auth/email-binding",
            token="verified-token",
            payload={"email": "new-address@example.com", "email_code": "123456"},
        )

        self.assertEqual(duplicate_status, 409)
        self.assertEqual(verified_status, 409)

    def test_login_and_me_return_strict_flags_with_admin_exemption(self) -> None:
        login_status, login_payload = self.request(
            "/api/auth/password-login",
            token="",
            payload={"account": "legacyuser", "password": "safe-password"},
        )
        me_status, me_payload = self.request("/api/auth/me", method="GET", token="legacy-token")
        admin_status, admin_payload = self.request("/api/auth/me", method="GET", token="admin-token")

        self.assertEqual((login_status, me_status, admin_status), (200, 200, 200))
        for payload in (login_payload, me_payload):
            self.assertIs(payload["user"]["email_verified"], False)
            self.assertIs(payload["user"]["email_binding_required"], True)
        self.assertIs(admin_payload["user"]["email_verified"], False)
        self.assertIs(admin_payload["user"]["email_binding_required"], False)


if __name__ == "__main__":
    unittest.main()
