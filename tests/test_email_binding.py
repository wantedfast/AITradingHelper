import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from trade_review_agent.auth_system import (
    AuthError,
    _send_email_code,
    bind_user_email,
    get_current_user,
    init_auth_db,
    send_email_binding_code,
)


class EmailBindingTest(unittest.TestCase):
    def _create_user(self, db_path: Path, *, role: str = "user", email: str | None = None, verified: int = 0) -> int:
        init_auth_db(db_path)
        now = "2026-07-15T10:00:00+08:00"
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                user_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, ?, 'hash', 'salt', ?, 'active', ?, ?)
                        """,
                        (f"{role}-{verified}-{email or 'none'}", f"{role}{verified}", email, verified, role, f"CODE{role}{verified}", now),
                    ).lastrowid
                )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', ?)",
                    (f"token-{user_id}", user_id, now),
                )
                return user_id

    def test_legacy_user_can_bind_email_and_code_is_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            user_id = self._create_user(db_path)
            with mock.patch("trade_review_agent.auth_system.secrets.randbelow", return_value=123456), mock.patch(
                "trade_review_agent.auth_system._send_email_code", return_value={"provider": "test"}
            ):
                sent = send_email_binding_code(db_path, user_id=user_id, email=" Legacy@Example.com ")
            self.assertTrue(sent["ok"])
            with closing(sqlite3.connect(db_path)) as conn:
                purpose = conn.execute("SELECT purpose FROM email_codes").fetchone()[0]
            self.assertEqual(purpose, "bind_email")

            user = bind_user_email(db_path, user_id=user_id, email="legacy@example.com", email_code="123456")
            self.assertEqual(user["email"], "legacy@example.com")
            self.assertIs(user["email_verified"], True)
            self.assertIs(user["email_binding_required"], False)
            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM email_codes").fetchone()[0], 0)

    def test_invalid_code_rolls_back_and_verified_or_duplicate_email_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            legacy_id = self._create_user(db_path)
            verified_id = self._create_user(db_path, email="used@example.com", verified=1)
            with mock.patch("trade_review_agent.auth_system.secrets.randbelow", return_value=123456), mock.patch(
                "trade_review_agent.auth_system._send_email_code", return_value={"provider": "test"}
            ):
                send_email_binding_code(db_path, user_id=legacy_id, email="new@example.com")

            with self.assertRaises(AuthError) as invalid:
                bind_user_email(db_path, user_id=legacy_id, email="new@example.com", email_code="000000")
            self.assertEqual(invalid.exception.status, 401)
            with closing(sqlite3.connect(db_path)) as conn:
                row = conn.execute("SELECT email, email_verified FROM users WHERE id = ?", (legacy_id,)).fetchone()
                self.assertEqual(row, (None, 0))
                self.assertEqual(conn.execute("SELECT consumed FROM email_codes").fetchone()[0], 0)

            with self.assertRaises(AuthError) as duplicate:
                send_email_binding_code(db_path, user_id=legacy_id, email="used@example.com")
            self.assertEqual(duplicate.exception.status, 409)
            with self.assertRaises(AuthError) as already_verified:
                bind_user_email(db_path, user_id=verified_id, email="other@example.com", email_code="123456")
            self.assertEqual(already_verified.exception.status, 409)

    def test_binding_required_is_strict_boolean_and_admin_is_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            user_id = self._create_user(db_path)
            admin_id = self._create_user(db_path, role="admin")
            user = get_current_user(db_path, f"token-{user_id}")
            admin = get_current_user(db_path, f"token-{admin_id}")
            self.assertIs(user["email_verified"], False)
            self.assertIs(user["email_binding_required"], True)
            self.assertIs(admin["email_verified"], False)
            self.assertIs(admin["email_binding_required"], False)

    def test_email_code_provider_stays_on_smtp_when_selected(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "EMAIL_PROVIDER": "smtp",
                "OUTLOOK_GRAPH_REFRESH_TOKEN": "future-refresh-token",
                "OUTLOOK_GRAPH_CLIENT_SECRET": "future-client-secret",
            },
            clear=False,
        ), mock.patch("trade_review_agent.auth_system._send_smtp_email") as send_smtp:
            result = _send_email_code("reader@example.test", "123456", None)

        self.assertEqual(result, {"provider": "smtp"})
        send_smtp.assert_called_once_with("reader@example.test", "123456")

if __name__ == "__main__":
    unittest.main()
