from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import ExitStack, closing
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from unittest.mock import patch

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import init_auth_db


class DailyTop5AccessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "auth.sqlite"
        self.report_path = self.root / "daily-top5.jsonl"
        with patch.dict("os.environ", {"ADMIN_PHONE": "", "ADMIN_PASSWORD": ""}, clear=False):
            init_auth_db(self.db_path)
        self.user_id = self._create_user_with_session_and_credits(20)

        self.stack = ExitStack()
        self.stack.enter_context(patch.object(simple_api, "AUTH_DB", self.db_path))
        self.stack.enter_context(patch.object(simple_api, "AUCTION_STRENGTH_PATH", self.report_path))
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

    def _create_user_with_session_and_credits(self, credits: int) -> int:
        now = "2026-07-15T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                user_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 'hash', 'salt', 'user', 'active', 'TOP50001', ?)
                        """,
                        ("top5-phone", "top5user", "top5@example.com", now),
                    ).lastrowid
                )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('top5-token', ?, '2999-01-01', ?)",
                    (user_id, now),
                )
                conn.execute(
                    "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, ?, 'test', NULL, ?)",
                    (user_id, credits, now),
                )
        return user_id

    def _write_report(self, trade_date: str, report_id: str) -> None:
        payload = {
            "id": report_id,
            "request_id": f"request-{report_id}",
            "received_at": f"{trade_date} 09:26:00",
            "trade_date": trade_date,
            "analysis_time": "09:25",
            "summary": {"one_sentence": report_id, "selection_logic": "test", "data_limit": ""},
            "top5_strong_stocks": [],
            "top5_avoid_stocks": [],
            "global_conclusion": {"one_sentence_for_930": "test"},
        }
        with self.report_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _request(self, path: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Authorization": "Bearer top5-token", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def _balance_and_usage(self) -> tuple[int, list[tuple[int, str, str]]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            balance = int(
                conn.execute(
                    "SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE user_id = ?", (self.user_id,)
                ).fetchone()[0]
            )
            rows = conn.execute(
                """
                SELECT credits_spent, status, related_id
                FROM usage_events
                WHERE user_id = ? AND feature = 'auction_strength_view'
                ORDER BY id
                """,
                (self.user_id,),
            ).fetchall()
        return balance, [(int(row[0]), str(row[1]), str(row[2])) for row in rows]

    def test_list_returns_no_data_without_charging_or_balance_precheck(self) -> None:
        today = datetime.now(simple_api.CN_TZ).date().isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, -20, 'empty_balance', NULL, ?)",
                    (self.user_id, "2026-07-15T10:01:00+08:00"),
                )

        status, payload = self._request(f"/api/auction-strength?{urlencode({'date': today})}")

        self.assertEqual(status, 200)
        self.assertEqual(payload["billing_status"], "no_data")
        self.assertEqual(payload["billing_cost"], 0)
        self.assertEqual(payload["reports"], [])
        self.assertEqual(payload["count"], 0)
        self.assertEqual(self._balance_and_usage(), (0, []))

    def test_today_list_is_pending_even_with_zero_balance_and_does_not_write_usage(self) -> None:
        today = datetime.now(simple_api.CN_TZ).date().isoformat()
        self._write_report(today, "today-first")
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, -20, 'empty_balance', NULL, ?)",
                    (self.user_id, "2026-07-15T10:01:00+08:00"),
                )

        status, payload = self._request(f"/api/auction-strength?{urlencode({'date': today})}")

        self.assertEqual(status, 200)
        self.assertEqual(payload["billing_status"], "pending_view")
        self.assertEqual(payload["billing_cost"], 2)
        self.assertEqual(payload["billing_trade_date"], today)
        self.assertEqual(payload["latest"]["id"], "today-first")
        self.assertEqual(self._balance_and_usage(), (0, []))

    def test_history_is_free_and_ack_never_creates_usage(self) -> None:
        old_date = (datetime.now(simple_api.CN_TZ).date() - timedelta(days=1)).isoformat()
        self._write_report(old_date, "history")

        list_status, listed = self._request(f"/api/auction-strength?{urlencode({'date': old_date})}")
        ack_status, acknowledged = self._request(
            "/api/auction-strength/ack", method="POST", payload={"trade_date": old_date}
        )

        self.assertEqual(list_status, 200)
        self.assertEqual(listed["billing_status"], "free_history")
        self.assertEqual(listed["billing_cost"], 0)
        self.assertEqual(ack_status, 200)
        self.assertEqual(acknowledged["billing_status"], "free_history")
        self.assertEqual(self._balance_and_usage(), (20, []))

    def test_today_ack_charges_two_once_by_trade_date_and_same_day_refresh_is_free(self) -> None:
        today = datetime.now(simple_api.CN_TZ).date().isoformat()
        self._write_report(today, "today-first")

        pending_status, pending = self._request(f"/api/auction-strength?{urlencode({'date': today})}")
        first_status, first = self._request(
            "/api/auction-strength/ack", method="POST", payload={"trade_date": today}
        )
        second_status, second = self._request(
            "/api/auction-strength/ack", method="POST", payload={"trade_date": today}
        )
        self._write_report(today, "today-replacement")
        refresh_status, refreshed = self._request(f"/api/auction-strength?{urlencode({'date': today})}")
        third_status, third = self._request(
            "/api/auction-strength/ack", method="POST", payload={"trade_date": today}
        )

        self.assertEqual(pending_status, 200)
        self.assertEqual(pending["billing_status"], "pending_view")
        self.assertEqual(pending["billing_cost"], 2)
        self.assertEqual((first_status, second_status, refresh_status, third_status), (200, 200, 200, 200))
        self.assertEqual(first["billing_status"], "charged")
        self.assertEqual(second["billing_status"], "charged")
        self.assertEqual(refreshed["billing_status"], "charged")
        self.assertEqual(refreshed["billing_cost"], 0)
        self.assertEqual(refreshed["latest"]["id"], "today-replacement")
        self.assertEqual(third["billing_status"], "charged")
        self.assertEqual(self._balance_and_usage(), (18, [(2, "charged", today)]))

    def test_invalid_date_is_rejected(self) -> None:
        status, _ = self._request("/api/auction-strength?date=2026%2F07%2F15")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
