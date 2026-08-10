from __future__ import annotations

import base64
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from email import message_from_bytes
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from trade_review_agent import auth_system
from trade_review_agent.outlook_graph import (
    CN_TZ,
    OutlookGraphError,
    _access_token,
    _connect,
    begin_outlook_connection,
    complete_outlook_connection,
    configure_outlook_graph_runtime,
    disconnect_outlook,
    poll_outlook_device_connection,
    provider_status,
    send_outlook_mime,
    set_active_provider,
)


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> dict:
        return dict(self._payload)


class OutlookGraphModuleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        self.encryption_key = Fernet.generate_key().decode("ascii")
        self.env = mock.patch.dict(
            "os.environ",
            {
                "ADMIN_PHONE": "",
                "ADMIN_PASSWORD": "",
                "OUTLOOK_GRAPH_CLIENT_ID": "graph-client-id",
                "OUTLOOK_GRAPH_CLIENT_SECRET": "graph-client-secret",
                "OUTLOOK_GRAPH_TENANT": "consumers",
                "OUTLOOK_GRAPH_REDIRECT_URI": "https://trade.example.test/api/admin/email-provider/outlook/callback",
                "OUTLOOK_GRAPH_FROM": "ops@example.test",
                "OUTLOOK_GRAPH_TOKEN_ENCRYPTION_KEY": self.encryption_key,
                "SMTP_HOST": "smtp.example.test",
                "SMTP_PORT": "465",
                "SMTP_USER": "mailer@example.test",
                "SMTP_PASSWORD": "smtp-secret",
                "SMTP_FROM": "updates@example.test",
                "EMAIL_PROVIDER": "smtp",
            },
            clear=False,
        )
        self.env.start()
        auth_system.init_auth_db(self.db_path)
        configure_outlook_graph_runtime(self.db_path)
        with _connect(self.db_path) as conn:
            self.primary_admin_id = int(
                conn.execute(
                    """
                    INSERT INTO users (
                        phone, username, email, email_verified, update_emails_enabled,
                        password_hash, password_salt, role, status, invite_code, created_at
                    ) VALUES (?, ?, ?, 1, 1, 'hash', 'salt', 'admin', 'active', ?, ?)
                    """,
                    (
                        "graph-admin-primary",
                        "graph-admin-primary",
                        "graph-admin-primary@example.test",
                        "GRAPHADMINPRIMARY",
                        "2026-08-10T15:00:00+08:00",
                    ),
                ).lastrowid
            )
            self.secondary_admin_id = int(
                conn.execute(
                    """
                    INSERT INTO users (
                        phone, username, email, email_verified, update_emails_enabled,
                        password_hash, password_salt, role, status, invite_code, created_at
                    ) VALUES (?, ?, ?, 1, 1, 'hash', 'salt', 'admin', 'active', ?, ?)
                    """,
                    (
                        "graph-admin-secondary",
                        "graph-admin-secondary",
                        "graph-admin-secondary@example.test",
                        "GRAPHADMINSECONDARY",
                        "2026-08-10T15:00:00+08:00",
                    ),
                ).lastrowid
            )

    def tearDown(self) -> None:
        self.env.stop()
        self.temp_dir.cleanup()

    def _query_state_row(self) -> sqlite3.Row:
        with _connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM outlook_graph_oauth_states").fetchone()
        assert row is not None
        return row

    def _seed_credentials(
        self,
        *,
        access_token: str = "access-token-1",
        refresh_token: str = "refresh-token-1",
        expires_at: str = "2999-01-01T00:00:00+08:00",
        reconnect_required: int = 0,
        last_error: str = "",
    ) -> None:
        token_response = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 3600,
            "scope": "openid offline_access Mail.Send",
        }
        with mock.patch("trade_review_agent.outlook_graph._token_request", return_value=token_response):
            auth = begin_outlook_connection(self.db_path, admin_user_id=self.primary_admin_id)
            state = parse_qs(urlparse(auth["authorization_url"]).query)["state"][0]
            complete_outlook_connection(self.db_path, state=state, code="oauth-code")
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE outlook_graph_credentials
                SET expires_at = ?, reconnect_required = ?, last_error = ?, updated_at = ?
                WHERE id = 1
                """,
                (expires_at, reconnect_required, last_error, datetime.now(CN_TZ).isoformat()),
            )

    def test_begin_and_complete_connection_are_one_time_and_tokens_are_encrypted(self) -> None:
        auth = begin_outlook_connection(self.db_path, admin_user_id=self.secondary_admin_id, redirect_path="/unsafe/path")
        query = parse_qs(urlparse(auth["authorization_url"]).query)
        self.assertEqual(query["client_id"], ["graph-client-id"])
        self.assertEqual(query["scope"], ["openid offline_access Mail.Send"])
        self.assertEqual(query["redirect_uri"], ["https://trade.example.test/api/admin/email-provider/outlook/callback"])
        self.assertEqual(query["prompt"], ["select_account"])
        self.assertIn("state", query)
        self.assertIn("code_challenge", query)
        state = query["state"][0]

        row = self._query_state_row()
        self.assertEqual(str(row["redirect_path"]), "/admin/emails")
        self.assertNotIn(state, str(row["state_hash"]))
        self.assertNotEqual(str(row["code_verifier_encrypted"]), "")

        with mock.patch(
            "trade_review_agent.outlook_graph._token_request",
            return_value={
                "access_token": "plain-access-token",
                "refresh_token": "plain-refresh-token",
                "expires_in": 3600,
                "scope": "openid offline_access Mail.Send",
            },
        ):
            redirect_path = complete_outlook_connection(self.db_path, state=state, code="oauth-code")

        self.assertEqual(redirect_path, "/admin/emails")
        with _connect(self.db_path) as conn:
            state_row = conn.execute("SELECT used_at FROM outlook_graph_oauth_states").fetchone()
            credential = conn.execute("SELECT * FROM outlook_graph_credentials WHERE id = 1").fetchone()
        self.assertTrue(str(state_row["used_at"]))
        self.assertNotEqual(str(credential["access_token_encrypted"]), "plain-access-token")
        self.assertNotEqual(str(credential["refresh_token_encrypted"]), "plain-refresh-token")

        with self.assertRaises(OutlookGraphError):
            complete_outlook_connection(self.db_path, state=state, code="oauth-code-again")

    def test_refresh_token_rotation_updates_encrypted_tokens(self) -> None:
        self._seed_credentials(
            access_token="expired-access",
            refresh_token="refresh-token-1",
            expires_at=(datetime.now(CN_TZ) - timedelta(minutes=5)).isoformat(),
        )
        with _connect(self.db_path) as conn:
            before = conn.execute(
                "SELECT access_token_encrypted, refresh_token_encrypted FROM outlook_graph_credentials WHERE id = 1"
            ).fetchone()

        with mock.patch(
            "trade_review_agent.outlook_graph._token_request",
            return_value={
                "access_token": "access-token-2",
                "refresh_token": "refresh-token-2",
                "expires_in": 7200,
                "scope": "openid offline_access Mail.Send",
            },
        ):
            token = _access_token(self.db_path)

        self.assertEqual(token, "access-token-2")
        with _connect(self.db_path) as conn:
            after = conn.execute(
                "SELECT access_token_encrypted, refresh_token_encrypted, reconnect_required, last_error FROM outlook_graph_credentials WHERE id = 1"
            ).fetchone()
        self.assertNotEqual(str(before["access_token_encrypted"]), str(after["access_token_encrypted"]))
        self.assertNotEqual(str(before["refresh_token_encrypted"]), str(after["refresh_token_encrypted"]))
        self.assertEqual(int(after["reconnect_required"]), 0)
        self.assertEqual(str(after["last_error"]), "")

    def test_send_outlook_mime_preserves_text_html_and_message_id(self) -> None:
        self._seed_credentials(access_token="send-access-token")
        message = auth_system._smtp_message(
            "reader@example.test",
            subject="Graph MIME",
            text="Plain body",
            html="<p>HTML body</p>",
            message_id="graph-c1-d2",
            sender="ops@example.test",
        )

        captured: dict[str, object] = {}

        def fake_post(url: str, headers: dict[str, str], data: str, timeout: int):
            captured["url"] = url
            captured["headers"] = headers
            captured["data"] = data
            captured["timeout"] = timeout
            return _Response(202)

        with mock.patch("trade_review_agent.outlook_graph.requests.post", side_effect=fake_post):
            send_outlook_mime(message.as_bytes())

        self.assertEqual(captured["url"], "https://graph.microsoft.com/v1.0/me/sendMail")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer send-access-token")
        posted = base64.b64decode(str(captured["data"]))
        parsed = message_from_bytes(posted)
        self.assertEqual(parsed["To"], "reader@example.test")
        self.assertIn("graph-c1-d2@", parsed["Message-ID"])
        parts = {part.get_content_type(): part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8") for part in parsed.walk() if not part.is_multipart()}
        self.assertEqual(set(parts), {"text/plain", "text/html"})
        self.assertIn("Plain body", parts["text/plain"])
        self.assertIn("HTML body", parts["text/html"])

    def test_revoked_token_marks_reconnect_required_without_secret_leakage(self) -> None:
        self._seed_credentials(access_token="soon-expiring")

        with mock.patch(
            "trade_review_agent.outlook_graph.requests.post",
            return_value=_Response(403, {"error": "invalid_grant", "error_description": "refresh-token-secret"}),
        ):
            with self.assertRaises(OutlookGraphError) as error:
                send_outlook_mime(b"mime")

        self.assertTrue(error.exception.reconnect_required)
        status = provider_status(self.db_path)
        self.assertFalse(status["outlook"]["connected"])
        self.assertTrue(status["outlook"]["reconnect_required"])
        self.assertNotIn("refresh-token-secret", str(status))
        self.assertNotIn("graph-client-secret", str(status))

    def test_callback_requires_initiating_admin_to_remain_active(self) -> None:
        auth = begin_outlook_connection(self.db_path, admin_user_id=self.secondary_admin_id)
        state = parse_qs(urlparse(auth["authorization_url"]).query)["state"][0]

        for field, value in (("role", "user"), ("status", "disabled")):
            with self.subTest(field=field, value=value):
                with _connect(self.db_path) as conn:
                    conn.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (value, self.secondary_admin_id))
                with mock.patch("trade_review_agent.outlook_graph._token_request") as token_request:
                    with self.assertRaises(OutlookGraphError):
                        complete_outlook_connection(self.db_path, state=state, code="oauth-code")
                token_request.assert_not_called()
                with _connect(self.db_path) as conn:
                    state_row = conn.execute("SELECT used_at FROM outlook_graph_oauth_states").fetchone()
                    credential = conn.execute("SELECT * FROM outlook_graph_credentials WHERE id = 1").fetchone()
                self.assertFalse(state_row["used_at"])
                self.assertIsNone(credential)
                with _connect(self.db_path) as conn:
                    conn.execute(
                        "UPDATE users SET role = 'admin', status = 'active' WHERE id = ?",
                        (self.secondary_admin_id,),
                    )

    def test_device_code_begin_pending_and_success_lifecycle(self) -> None:
        calls: list[tuple[str, dict[str, str]]] = []

        def fake_post(url: str, data: dict[str, str], timeout: int):
            calls.append((url, data))
            if url.endswith("/devicecode"):
                return _Response(
                    200,
                    {
                        "device_code": "device-secret-code",
                        "user_code": "ABCD-EFGH",
                        "verification_uri": "https://microsoft.com/devicelogin",
                        "expires_in": 900,
                        "interval": 5,
                    },
                )
            if len([entry for entry in calls if entry[0].endswith("/token")]) == 1:
                return _Response(400, {"error": "authorization_pending"})
            return _Response(
                200,
                {
                    "access_token": "device-access-token",
                    "refresh_token": "device-refresh-token",
                    "expires_in": 3600,
                    "scope": "openid offline_access Mail.Send",
                },
            )

        with mock.patch.dict("os.environ", {"OUTLOOK_GRAPH_REDIRECT_URI": ""}, clear=False):
            with mock.patch("trade_review_agent.outlook_graph.requests.post", side_effect=fake_post):
                auth = begin_outlook_connection(self.db_path, admin_user_id=self.primary_admin_id)
                pending = poll_outlook_device_connection(self.db_path, admin_user_id=self.primary_admin_id)
                connected = poll_outlook_device_connection(self.db_path, admin_user_id=self.primary_admin_id)

        self.assertEqual(auth["mode"], "device_code")
        self.assertEqual(auth["user_code"], "ABCD-EFGH")
        self.assertEqual(auth["verification_uri"], "https://microsoft.com/devicelogin")
        self.assertEqual(pending, {"status": "pending", "connected": False})
        self.assertEqual(connected, {"status": "connected", "connected": True})
        status = provider_status(self.db_path)
        self.assertTrue(status["outlook"]["connected"])
        with _connect(self.db_path) as conn:
            self.assertIsNone(conn.execute("SELECT * FROM outlook_graph_device_codes WHERE id = 1").fetchone())
            credential = conn.execute("SELECT * FROM outlook_graph_credentials WHERE id = 1").fetchone()
        self.assertIsNotNone(credential)
        self.assertNotEqual(str(credential["access_token_encrypted"]), "device-access-token")

    def test_disconnect_falls_back_to_smtp_and_select_requires_connected_outlook(self) -> None:
        self._seed_credentials()
        status = set_active_provider(self.db_path, "outlook_graph")
        self.assertEqual(status["provider"], "outlook_graph")

        disconnected = disconnect_outlook(self.db_path)
        self.assertEqual(disconnected["provider"], "smtp")
        self.assertTrue(disconnected["smtp"]["configured"])
        with _connect(self.db_path) as conn:
            self.assertIsNone(conn.execute("SELECT * FROM outlook_graph_credentials WHERE id = 1").fetchone())

        with self.assertRaises(OutlookGraphError):
            set_active_provider(self.db_path, "outlook_graph")

    def test_disconnect_falls_back_to_log_when_smtp_is_incomplete(self) -> None:
        self._seed_credentials()
        set_active_provider(self.db_path, "outlook_graph")

        with mock.patch.dict("os.environ", {"SMTP_PASSWORD": ""}, clear=False):
            disconnected = disconnect_outlook(self.db_path)

        self.assertEqual(disconnected["provider"], "log")
        self.assertFalse(disconnected["smtp"]["configured"])
