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
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from cryptography.fernet import Fernet

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import init_auth_db


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> dict:
        return dict(self._payload)


class OutlookGraphApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        self.graph_key = Fernet.generate_key().decode("ascii")
        self.env = patch.dict(
            "os.environ",
            {
                "ADMIN_PHONE": "",
                "ADMIN_PASSWORD": "",
                "PUBLIC_SITE_URL": "https://trade.example.test",
                "OUTLOOK_GRAPH_CLIENT_ID": "graph-client-id",
                "OUTLOOK_GRAPH_CLIENT_SECRET": "graph-client-secret",
                "OUTLOOK_GRAPH_TENANT": "consumers",
                "OUTLOOK_GRAPH_REDIRECT_URI": "https://trade.example.test/api/admin/email-provider/outlook/callback",
                "OUTLOOK_GRAPH_FROM": "ops@example.test",
                "OUTLOOK_GRAPH_TOKEN_ENCRYPTION_KEY": self.graph_key,
                "SMTP_HOST": "smtp.example.test",
                "SMTP_PORT": "465",
                "SMTP_USER": "mailer@example.test",
                "SMTP_PASSWORD": "smtp-secret",
                "SMTP_FROM": "updates@example.test",
            },
            clear=False,
        )
        self.env.start()
        init_auth_db(self.db_path)
        now = "2026-08-10T15:00:00+08:00"
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
                            (f"graph-{role}", f"graph-{role}", f"{role}@example.test", role, f"GRAPH{role.upper()}", now),
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
        self.env.stop()
        self.temp_dir.cleanup()

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        token: str = "",
        payload: dict | None = None,
        no_redirect: bool = False,
    ) -> tuple[int, dict, dict]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self.base_url + path, data=body, method=method, headers=headers)
        opener = build_opener(_NoRedirect) if no_redirect else None
        try:
            context = opener.open(request, timeout=3) if opener is not None else urlopen(request, timeout=3)
            with context as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else {}, dict(response.headers)
        except HTTPError as exc:
            with exc:
                raw = exc.read()
                try:
                    payload_dict = json.loads(raw) if raw else {}
                except Exception:
                    payload_dict = {}
                return exc.code, payload_dict, dict(exc.headers)

    def test_status_masks_sensitive_fields_and_requires_admin(self) -> None:
        admin_status, payload, _headers = self.request("/api/admin/email-provider", token="admin-token")
        user_status, _user_payload, _ = self.request("/api/admin/email-provider", token="user-token")

        self.assertEqual(admin_status, 200)
        self.assertEqual(user_status, 403)
        self.assertIn("provider", payload)
        self.assertIn("smtp", payload)
        self.assertIn("outlook", payload)
        self.assertIn("worker_count", payload)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("graph-client-secret", serialized)
        self.assertNotIn(self.graph_key, serialized)
        self.assertNotIn("smtp-secret", serialized)
        self.assertNotIn("access_token", serialized)
        self.assertNotIn("refresh_token", serialized)

    def test_connect_callback_select_test_and_disconnect_flow(self) -> None:
        connect_status, connect_payload, _ = self.request(
            "/api/admin/email-provider/outlook/connect",
            method="POST",
            token="admin-token",
            payload={},
        )
        self.assertEqual(connect_status, 201)
        query = parse_qs(urlparse(connect_payload["authorization_url"]).query)
        state = query["state"][0]

        cancelled_status, _cancelled_payload, cancelled_headers = self.request(
            "/api/admin/email-provider/outlook/callback?error=access_denied",
            token="",
            no_redirect=True,
        )
        self.assertEqual(cancelled_status, 302)
        self.assertTrue(cancelled_headers["Location"].endswith("/admin/emails?outlook=cancelled"))

        with patch(
            "trade_review_agent.outlook_graph._token_request",
            return_value={
                "access_token": "graph-access-token",
                "refresh_token": "graph-refresh-token",
                "expires_in": 3600,
                "scope": "openid offline_access Mail.Send",
            },
        ):
            callback_status, _callback_payload, callback_headers = self.request(
                f"/api/admin/email-provider/outlook/callback?state={state}&code=oauth-code",
                token="",
                no_redirect=True,
            )
        self.assertEqual(callback_status, 302)
        self.assertTrue(callback_headers["Location"].endswith("/admin/emails?outlook=connected"))

        select_status, selected, _ = self.request(
            "/api/admin/email-provider/select",
            method="POST",
            token="admin-token",
            payload={"provider": "outlook_graph"},
        )
        self.assertEqual(select_status, 200)
        self.assertEqual(selected["provider"], "outlook_graph")

        with patch("trade_review_agent.auth_system.send_outlook_mime") as send_graph:
            test_status, test_payload, _ = self.request(
                "/api/admin/email-provider/test",
                method="POST",
                token="admin-token",
                payload={"email": "probe@example.test"},
            )
        self.assertEqual(test_status, 200)
        self.assertTrue(test_payload["sent"])
        self.assertEqual(test_payload["provider"], "outlook_graph")
        self.assertEqual(test_payload["email"], "pr***@example.test")
        send_graph.assert_called_once()
        serialized = json.dumps(test_payload, ensure_ascii=False)
        self.assertNotIn("graph-client-secret", serialized)
        self.assertNotIn(self.graph_key, serialized)

        smtp_status, smtp_selected, _ = self.request(
            "/api/admin/email-provider/select",
            method="POST",
            token="admin-token",
            payload={"provider": "smtp"},
        )
        self.assertEqual(smtp_status, 200)
        self.assertEqual(smtp_selected["provider"], "smtp")

        disconnect_status, disconnected, _ = self.request(
            "/api/admin/email-provider/outlook/disconnect",
            method="POST",
            token="admin-token",
            payload={},
        )
        self.assertEqual(disconnect_status, 200)
        self.assertEqual(disconnected["provider"], "smtp")
        self.assertTrue(disconnected["smtp"]["configured"])

    def test_device_code_connect_and_poll_activate_outlook(self) -> None:
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

        with patch.dict("os.environ", {"OUTLOOK_GRAPH_REDIRECT_URI": ""}, clear=False):
            with patch("trade_review_agent.outlook_graph.requests.post", side_effect=fake_post):
                connect_status, connect_payload, _ = self.request(
                    "/api/admin/email-provider/outlook/connect",
                    method="POST",
                    token="admin-token",
                    payload={},
                )
                pending_status, pending_payload, _ = self.request(
                    "/api/admin/email-provider/outlook/poll",
                    method="POST",
                    token="admin-token",
                    payload={},
                )
                poll_status, poll_payload, _ = self.request(
                    "/api/admin/email-provider/outlook/poll",
                    method="POST",
                    token="admin-token",
                    payload={},
                )

        self.assertEqual(connect_status, 201)
        self.assertEqual(connect_payload["mode"], "device_code")
        self.assertEqual(connect_payload["user_code"], "ABCD-EFGH")
        self.assertEqual(pending_status, 200)
        self.assertEqual(pending_payload, {"status": "pending", "connected": False})
        self.assertEqual(poll_status, 200)
        self.assertEqual(poll_payload["status"], "connected")
        self.assertTrue(poll_payload["connected"])
        self.assertEqual(poll_payload["provider"], "outlook_graph")

    def test_invalid_callback_state_redirects_error_and_non_admin_routes_are_forbidden(self) -> None:
        callback_status, _payload, headers = self.request(
            "/api/admin/email-provider/outlook/callback?state=bad-state&code=oauth-code",
            token="",
            no_redirect=True,
        )
        self.assertEqual(callback_status, 302)
        self.assertTrue(headers["Location"].endswith("/admin/emails?outlook=error"))

        for path in (
            "/api/admin/email-provider",
            "/api/admin/email-provider/outlook/connect",
            "/api/admin/email-provider/outlook/disconnect",
            "/api/admin/email-provider/outlook/poll",
            "/api/admin/email-provider/select",
            "/api/admin/email-provider/test",
        ):
            with self.subTest(path=path):
                status, _payload, _headers = self.request(
                    path,
                    method="POST" if path != "/api/admin/email-provider" else "GET",
                    token="user-token",
                    payload={},
                )
                self.assertEqual(status, 403)
