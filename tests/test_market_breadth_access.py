from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import Mock, patch

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import AuthError, init_auth_db


SAMPLE_STATE = {
    "updated": "2026-11-17 10:36",
    "error": None,
    "trading": True,
    "snap": {"n": 5572, "up": 1454, "down": 3931, "flat": 187},
    "indexes": [],
    "intraday": [],
    "mcl": {"days": 520, "value": -50.78, "series": []},
    "verdict": {"key": "selloff", "title": "真下跌：资金全面撤退"},
}


class MarketBreadthAccessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        with patch.dict("os.environ", {"ADMIN_PHONE": "", "ADMIN_PASSWORD": ""}, clear=False):
            init_auth_db(self.db_path)

        self.user_id = self._create_user("breadth-token", "user", 10)
        self.member_id = self._create_user("member-token", "user", 0, member=True)
        self.admin_id = self._create_user("admin-token", "admin", 0)

        self.stack = ExitStack()
        self.stack.enter_context(patch.object(simple_api, "AUTH_DB", self.db_path))
        self.fetch_state = self.stack.enter_context(
            patch.object(simple_api, "_fetch_market_breadth_state", return_value=SAMPLE_STATE)
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.stack.close()
        self.temp_dir.cleanup()

    def _create_user(self, token: str, role: str, credits: int, *, member: bool = False) -> int:
        suffix = token.replace("-token", "")
        now = "2026-11-17T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                user_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 'hash', 'salt', ?, 'active', ?, ?)
                        """,
                        (f"phone-{suffix}", f"user_{suffix}", f"{suffix}@example.com", role, f"INV{suffix.upper()}", now),
                    ).lastrowid
                )
                if member:
                    conn.execute(
                        "UPDATE users SET membership_status = 'active', membership_expires_at = '2999-01-01T00:00:00+08:00' WHERE id = ?",
                        (user_id,),
                    )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', ?)",
                    (token, user_id, now),
                )
                if credits:
                    conn.execute(
                        "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, ?, 'test', NULL, ?)",
                        (user_id, credits, now),
                    )
        return user_id

    def _request(self, path: str, *, method: str = "GET", token: str = "breadth-token") -> tuple[int, dict]:
        request = Request(
            self.base_url + path,
            data=b"{}" if method == "POST" else None,
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def _balance_and_usage(self, user_id: int) -> tuple[int, list[tuple[int, str, str]]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            balance = int(
                conn.execute(
                    "SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE user_id = ?", (user_id,)
                ).fetchone()[0]
            )
            rows = conn.execute(
                """
                SELECT credits_spent, status, related_id
                FROM usage_events
                WHERE user_id = ? AND feature = 'market_breadth_view'
                ORDER BY id
                """,
                (user_id,),
            ).fetchall()
        return balance, [(int(row[0]), str(row[1]), str(row[2])) for row in rows]

    def test_access_requires_login_and_starts_pending_without_charging(self) -> None:
        unauthenticated, _ = self._request("/api/market-breadth/access", token="missing")
        status, payload = self._request("/api/market-breadth/access")

        self.assertEqual(unauthenticated, 401)
        self.assertEqual(status, 200)
        self.assertEqual(payload["billing_status"], "pending_view")
        self.assertEqual(payload["billing_cost"], 2)
        self.assertRegex(payload["billing_date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(self._balance_and_usage(self.user_id), (10, []))

    def test_ack_charges_two_once_and_state_is_returned_unchanged(self) -> None:
        before_status, _ = self._request("/api/market-breadth/state")
        first_status, first = self._request("/api/market-breadth/ack", method="POST")
        second_status, second = self._request("/api/market-breadth/ack", method="POST")
        state_status, state = self._request("/api/market-breadth/state")

        self.assertEqual(before_status, 402)
        self.assertEqual((first_status, second_status, state_status), (200, 200, 200))
        self.assertEqual(first["billing_status"], "charged")
        self.assertEqual(second["billing_status"], "charged")
        self.assertEqual(state, SAMPLE_STATE)
        billing_date = first["billing_date"]
        self.assertEqual(
            self._balance_and_usage(self.user_id),
            (8, [(2, "charged", f"market-breadth:{billing_date}")]),
        )

    def test_concurrent_ack_is_idempotent(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self._request("/api/market-breadth/ack", method="POST"), range(8)))

        self.assertTrue(all(status == 200 for status, _ in results))
        billing_date = results[0][1]["billing_date"]
        self.assertEqual(
            self._balance_and_usage(self.user_id),
            (8, [(2, "charged", f"market-breadth:{billing_date}")]),
        )

    def test_member_and_admin_are_free(self) -> None:
        member_status, member = self._request("/api/market-breadth/access", token="member-token")
        admin_status, admin = self._request("/api/market-breadth/access", token="admin-token")
        member_state_status, _ = self._request("/api/market-breadth/state", token="member-token")
        admin_state_status, _ = self._request("/api/market-breadth/state", token="admin-token")

        self.assertEqual((member_status, admin_status, member_state_status, admin_state_status), (200, 200, 200, 200))
        self.assertEqual(member["billing_status"], "membership_free")
        self.assertEqual(admin["billing_status"], "admin_free")
        self.assertEqual(self._balance_and_usage(self.member_id), (0, []))
        self.assertEqual(self._balance_and_usage(self.admin_id), (0, []))

    def test_unavailable_state_does_not_charge(self) -> None:
        self.fetch_state.side_effect = AuthError("市场实时数据仍在准备中，请稍后重试；本次不会扣除使用次数", 503)

        status, payload = self._request("/api/market-breadth/ack", method="POST")

        self.assertEqual(status, 503)
        self.assertIn("不会扣除", payload["error"])
        self.assertEqual(self._balance_and_usage(self.user_id), (10, []))

    def test_insufficient_balance_is_rejected_after_availability_check(self) -> None:
        low_id = self._create_user("low-token", "user", 1)

        status, payload = self._request("/api/market-breadth/ack", method="POST", token="low-token")

        self.assertEqual(status, 402)
        self.assertIn("需要 2 次", payload["error"])
        self.assertEqual(self._balance_and_usage(low_id), (1, []))


class MarketBreadthUpstreamContractTest(unittest.TestCase):
    def test_null_snap_is_unavailable_and_cannot_be_billed(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"updated": None, "snap": None, "error": None}
        with patch.object(simple_api.requests, "get", return_value=response):
            with self.assertRaises(AuthError) as raised:
                simple_api._fetch_market_breadth_state()

        self.assertEqual(raised.exception.status, 503)
        self.assertIn("不会扣除", raised.exception.message)

if __name__ == "__main__":
    unittest.main()
