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
from trade_review_agent.auth_system import AuthError, grant_credits_to_all_users, init_auth_db


class GrantCreditsToAllUsersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        with patch.dict("os.environ", {"ADMIN_PHONE": "", "ADMIN_PASSWORD": ""}, clear=False):
            init_auth_db(self.db_path)

        now = "2026-07-15T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                self.user_ids: list[int] = []
                for index, (role, status) in enumerate(
                    (("admin", "active"), ("user", "active"), ("user", "inactive")), start=1
                ):
                    self.user_ids.append(
                        int(
                            conn.execute(
                                """
                                INSERT INTO users (
                                    phone, username, email, email_verified, password_hash,
                                    password_salt, role, status, invite_code, created_at
                                ) VALUES (?, ?, ?, 1, 'hash', 'salt', ?, ?, ?, ?)
                                """,
                                (
                                    f"grant-phone-{index}",
                                    f"grantuser{index}",
                                    f"grant{index}@example.com",
                                    role,
                                    status,
                                    f"GRANT{index:03d}",
                                    now,
                                ),
                            ).lastrowid
                        )
                    )
                conn.execute(
                    "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, 3, 'seed', NULL, ?)",
                    (self.user_ids[1], now),
                )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def balances(self) -> dict[int, int]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            return {
                int(row[0]): int(row[1])
                for row in conn.execute(
                    """
                    SELECT u.id, COALESCE(SUM(l.delta), 0)
                    FROM users u
                    LEFT JOIN credit_ledger l ON l.user_id = u.id
                    GROUP BY u.id
                    ORDER BY u.id
                    """
                )
            }

    def campaign_rows(self) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM credit_grant_campaigns").fetchone()[0])

    def test_grants_exact_amount_to_every_existing_user_and_reports_counts(self) -> None:
        before = self.balances()

        result = grant_credits_to_all_users(
            self.db_path,
            credits=10,
            reason="产品更新赠送",
            request_id="grant-all-20260715-a",
            admin_id=self.user_ids[0],
        )

        after = self.balances()
        self.assertFalse(result["idempotent"])
        self.assertEqual(result["campaign"]["credits"], 10)
        self.assertEqual(result["campaign"]["eligible_count"], len(self.user_ids))
        self.assertEqual(result["campaign"]["granted_count"], len(self.user_ids))
        self.assertEqual(result["campaign"]["status"], "completed")
        self.assertEqual(result["campaign"]["created_by"], self.user_ids[0])
        self.assertTrue(result["campaign"]["completed_at"])
        self.assertEqual({user_id: after[user_id] - before[user_id] for user_id in self.user_ids}, {
            user_id: 10 for user_id in self.user_ids
        })

        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT user_id, delta, reason, related_id
                FROM credit_ledger
                WHERE reason = 'admin_grant_all'
                ORDER BY user_id
                """
            ).fetchall()
        self.assertEqual(len(rows), len(self.user_ids))
        self.assertEqual([int(row[0]) for row in rows], self.user_ids)
        self.assertTrue(all(int(row[1]) == 10 for row in rows))
        self.assertTrue(all(str(row[3]).startswith("credit-campaign:") for row in rows))
        self.assertEqual(len({str(row[3]) for row in rows}), 1)

    def test_identical_request_is_idempotent_but_new_request_can_grant_again(self) -> None:
        kwargs = {
            "credits": 10,
            "reason": "周年赠送",
            "request_id": "grant-all-20260715-b",
            "admin_id": self.user_ids[0],
        }
        first = grant_credits_to_all_users(self.db_path, **kwargs)
        after_first = self.balances()
        replay = grant_credits_to_all_users(self.db_path, **kwargs)

        self.assertFalse(first["idempotent"])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(replay["campaign"]["id"], first["campaign"]["id"])
        self.assertEqual(self.balances(), after_first)
        self.assertEqual(self.campaign_rows(), 1)

        second = grant_credits_to_all_users(
            self.db_path,
            credits=10,
            reason="第二轮赠送",
            request_id="grant-all-20260715-c",
            admin_id=self.user_ids[0],
        )
        self.assertFalse(second["idempotent"])
        self.assertNotEqual(second["campaign"]["id"], first["campaign"]["id"])
        self.assertEqual(self.campaign_rows(), 2)
        self.assertEqual(
            {user_id: self.balances()[user_id] - after_first[user_id] for user_id in self.user_ids},
            {user_id: 10 for user_id in self.user_ids},
        )

    def test_request_id_cannot_be_reused_with_changed_campaign_data(self) -> None:
        base = {
            "credits": 10,
            "reason": "固定批次",
            "request_id": "grant-all-20260715-d",
            "admin_id": self.user_ids[0],
        }
        grant_credits_to_all_users(self.db_path, **base)
        after_first = self.balances()

        for changed in ({**base, "credits": 11}, {**base, "reason": "其他原因"}):
            with self.subTest(changed=changed):
                with self.assertRaises(AuthError) as caught:
                    grant_credits_to_all_users(self.db_path, **changed)
                self.assertEqual(caught.exception.status, 409)

        self.assertEqual(self.balances(), after_first)
        self.assertEqual(self.campaign_rows(), 1)

    def test_credits_must_be_a_strict_positive_integer(self) -> None:
        invalid_values = (True, False, "10", 10.0, None, 0, -1)
        for index, credits in enumerate(invalid_values):
            with self.subTest(credits=credits):
                with self.assertRaises(AuthError) as caught:
                    grant_credits_to_all_users(
                        self.db_path,
                        credits=credits,
                        reason="invalid",
                        request_id=f"invalid-grant-{index:02d}",
                        admin_id=self.user_ids[0],
                    )
                self.assertEqual(caught.exception.status, 400)

        self.assertEqual(self.campaign_rows(), 0)
        self.assertEqual(self.balances()[self.user_ids[1]], 3)

    def test_failure_mid_grant_rolls_back_campaign_and_every_ledger_entry(self) -> None:
        before = self.balances()
        original_add_credits = auth_system._add_credits
        call_count = 0

        def fail_on_second_user(conn, user_id, delta, reason, related_id):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("simulated ledger failure")
            return original_add_credits(conn, user_id, delta, reason, related_id)

        with patch.object(auth_system, "_add_credits", side_effect=fail_on_second_user):
            with self.assertRaises(RuntimeError):
                grant_credits_to_all_users(
                    self.db_path,
                    credits=10,
                    reason="事务检查",
                    request_id="grant-all-rollback-01",
                    admin_id=self.user_ids[0],
                )

        self.assertEqual(self.balances(), before)
        self.assertEqual(self.campaign_rows(), 0)
        with closing(sqlite3.connect(self.db_path)) as conn:
            ledger_count = int(
                conn.execute("SELECT COUNT(*) FROM credit_ledger WHERE reason = 'admin_grant_all'").fetchone()[0]
            )
        self.assertEqual(ledger_count, 0)


class GrantCreditsToAllUsersApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        with patch.dict("os.environ", {"ADMIN_PHONE": "", "ADMIN_PASSWORD": ""}, clear=False):
            init_auth_db(self.db_path)
        now = "2026-07-15T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                self.user_ids: list[int] = []
                for role, token in (("admin", "admin-token"), ("user", "user-token")):
                    user_id = int(
                        conn.execute(
                            """
                            INSERT INTO users (
                                phone, username, email, email_verified, password_hash,
                                password_salt, role, status, invite_code, created_at
                            ) VALUES (?, ?, ?, 1, 'hash', 'salt', ?, 'active', ?, ?)
                            """,
                            (
                                f"{role}-grant-phone",
                                f"{role}grantuser",
                                f"{role}.grant@example.com",
                                role,
                                f"{role.upper()}GRANT",
                                now,
                            ),
                        ).lastrowid
                    )
                    self.user_ids.append(user_id)
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

    def request(self, *, token: str = "", payload: dict | None = None) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            self.base_url + "/api/admin/credits/grant-all",
            data=json.dumps(payload or {}).encode(),
            method="POST",
            headers=headers,
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_endpoint_is_admin_only_and_denied_requests_do_not_mutate_ledger(self) -> None:
        payload = {"credits": 10, "reason": "权限检查", "request_id": "api-grant-auth-01"}
        anonymous_status, _ = self.request(payload=payload)
        user_status, _ = self.request(token="user-token", payload=payload)

        self.assertEqual(anonymous_status, 401)
        self.assertEqual(user_status, 403)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credit_grant_campaigns").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credit_ledger").fetchone()[0], 0)

    def test_endpoint_rejects_non_integer_or_non_positive_credits(self) -> None:
        for index, credits in enumerate((True, False, "10", 10.0, None, 0, -10)):
            with self.subTest(credits=credits):
                status, _ = self.request(
                    token="admin-token",
                    payload={"credits": credits, "reason": "参数检查", "request_id": f"api-invalid-{index:02d}"},
                )
                self.assertEqual(status, 400)

        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credit_grant_campaigns").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credit_ledger").fetchone()[0], 0)

    def test_admin_can_grant_and_api_replay_returns_idempotent_counts(self) -> None:
        payload = {"credits": 10, "reason": "全员赠送", "request_id": "api-grant-all-01"}
        first_status, first = self.request(token="admin-token", payload=payload)
        replay_status, replay = self.request(token="admin-token", payload=payload)

        self.assertEqual(first_status, 200)
        self.assertEqual(replay_status, 200)
        self.assertFalse(first["idempotent"])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(first["campaign"]["eligible_count"], 2)
        self.assertEqual(first["campaign"]["granted_count"], 2)
        self.assertEqual(replay["campaign"]["id"], first["campaign"]["id"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credit_ledger").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COALESCE(SUM(delta), 0) FROM credit_ledger").fetchone()[0], 20)


if __name__ == "__main__":
    unittest.main()
