from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import (
    AuthError,
    adjust_user_credits,
    admin_dashboard,
    confirm_credit_order,
    create_credit_order,
    get_current_user,
    grant_user_credits,
    init_auth_db,
    mark_order_paid,
    mark_order_paid_by_order_no,
    reject_credit_order,
    require_user,
    set_user_status,
    submit_credit_payment,
)


class CreditPurchaseFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        init_auth_db(self.db_path)
        now = "2026-07-20T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                self.admin_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 'hash', 'salt', 'admin', 'active', ?, ?)
                        """,
                        ("admin-phone", "adminuser", "admin@example.com", "ADMIN001", now),
                    ).lastrowid
                )
                self.user_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 'hash', 'salt', 'user', 'active', ?, ?)
                        """,
                        ("user-phone", "normaluser", "user@example.com", "USER001", now),
                    ).lastrowid
                )
                self.other_user_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 'hash', 'salt', 'user', 'active', ?, ?)
                        """,
                        ("other-phone", "otheruser", "other@example.com", "USER002", now),
                    ).lastrowid
                )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('admin-token', ?, '2999-01-01', ?)",
                    (self.admin_id, now),
                )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('user-token', ?, '2999-01-01', ?)",
                    (self.user_id, now),
                )
                conn.execute(
                    "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, 8, 'seed', NULL, ?)",
                    (self.user_id, now),
                )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def balance(self, user_id: int) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            return int(
                conn.execute(
                    "SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE user_id = ?",
                    (user_id,),
                ).fetchone()[0]
            )

    def test_dashboard_returns_managed_users_beyond_top_30(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                for index in range(35):
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 'hash', 'salt', 'user', 'active', ?, ?)
                        """,
                        (
                            f"managed-{index}",
                            f"managed{index}",
                            f"managed{index}@example.com",
                            f"MANAGED{index:03d}",
                            "2026-07-20T10:00:00+08:00",
                        ),
                    )

        payload = admin_dashboard(self.db_path, days=30)
        self.assertGreaterEqual(len(payload["managed_users"]), 37)
        self.assertLessEqual(len(payload["top_users"]), 30)
        self.assertTrue(all(item["role"] == "user" for item in payload["managed_users"]))

    def test_disabling_user_clears_sessions_and_protected_access_returns_403(self) -> None:
        result = set_user_status(self.db_path, user_id=self.user_id, status="disabled", admin_id=self.admin_id)
        self.assertEqual(result["user"]["status"], "disabled")
        self.assertIsNone(get_current_user(self.db_path, "user-token"))
        with closing(sqlite3.connect(self.db_path)) as conn:
            session_count = int(conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (self.user_id,)).fetchone()[0])
        self.assertEqual(session_count, 0)
        with self.assertRaises(AuthError) as caught:
            require_user(self.db_path, "user-token")
        self.assertEqual(caught.exception.status, 403)

    def test_reenabling_user_keeps_old_session_invalid_and_allows_new_session(self) -> None:
        set_user_status(self.db_path, user_id=self.user_id, status="disabled", admin_id=self.admin_id)
        result = set_user_status(self.db_path, user_id=self.user_id, status="active", admin_id=self.admin_id)
        self.assertEqual(result["user"]["status"], "active")

        with self.assertRaises(AuthError) as old_session:
            require_user(self.db_path, "user-token")
        self.assertEqual(old_session.exception.status, 403)

        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('user-token-new', ?, '2999-01-01', '2026-07-20T11:00:00+08:00')",
                    (self.user_id,),
                )
        self.assertEqual(require_user(self.db_path, "user-token-new")["id"], self.user_id)

    def test_adjustment_request_id_is_idempotent_and_admin_targets_are_rejected(self) -> None:
        with self.assertRaises(AuthError) as admin_target:
            adjust_user_credits(
                self.db_path,
                user_id=self.admin_id,
                delta=3,
                reason="manual topup",
                request_id="adjust-admin-0001",
                admin_id=self.admin_id,
            )
        self.assertEqual(admin_target.exception.status, 403)

        first = adjust_user_credits(
            self.db_path,
            user_id=self.user_id,
            delta=4,
            reason="manual topup",
            request_id="adjust-user-0001",
            admin_id=self.admin_id,
        )
        replay = adjust_user_credits(
            self.db_path,
            user_id=self.user_id,
            delta=4,
            reason="manual topup",
            request_id="adjust-user-0001",
            admin_id=self.admin_id,
        )
        self.assertFalse(first["idempotent"])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(self.balance(self.user_id), 12)

        with self.assertRaises(AuthError) as conflict:
            adjust_user_credits(
                self.db_path,
                user_id=self.user_id,
                delta=5,
                reason="changed",
                request_id="adjust-user-0001",
                admin_id=self.admin_id,
            )
        self.assertEqual(conflict.exception.status, 409)

    def test_concurrent_deductions_do_not_allow_negative_balance(self) -> None:
        def deduct(request_id: str) -> str:
            try:
                adjust_user_credits(
                    self.db_path,
                    user_id=self.user_id,
                    delta=-6,
                    reason="manual correction",
                    request_id=request_id,
                    admin_id=self.admin_id,
                )
                return "ok"
            except AuthError as exc:
                return f"error:{exc.status}"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(deduct, ("deduct-a-0001", "deduct-b-0001")))

        self.assertEqual(sorted(results), ["error:400", "ok"])
        self.assertEqual(self.balance(self.user_id), 2)

    def test_credit_order_uses_server_pricing_rejects_mismatched_amount_and_allows_resubmit_after_reject(self) -> None:
        order = create_credit_order(self.db_path, user_id=self.user_id, credits=5)
        self.assertEqual(order["credits"], 5)
        self.assertEqual(order["amount_cents"], 500)

        with self.assertRaises(AuthError) as mismatch:
            submit_credit_payment(
                self.db_path,
                order_id=int(order["id"]),
                user_id=self.user_id,
                payment_method="alipay",
                payer_name="tester",
                payer_paid_at="2026-07-20T12:00",
                submitted_amount_cents=499,
                payer_note="wrong amount",
            )
        self.assertEqual(mismatch.exception.status, 400)

        submitted = submit_credit_payment(
            self.db_path,
            order_id=int(order["id"]),
            user_id=self.user_id,
            payment_method="alipay",
            payer_name="tester",
            payer_paid_at="2026-07-20T12:00",
            submitted_amount_cents=500,
            payer_note="first submit",
        )
        self.assertEqual(submitted["status"], "submitted")

        rejected = reject_credit_order(
            self.db_path,
            order_id=int(order["id"]),
            admin_id=self.admin_id,
            admin_note="need clearer payment proof",
        )
        self.assertEqual(rejected["status"], "rejected")
        self.assertIn("need clearer", rejected["admin_note"])

        resubmitted = submit_credit_payment(
            self.db_path,
            order_id=int(order["id"]),
            user_id=self.user_id,
            payment_method="wechat",
            payer_name="tester",
            payer_paid_at="2026-07-20T12:30",
            submitted_amount_cents=500,
            payer_note="resubmit",
        )
        self.assertEqual(resubmitted["status"], "submitted")

    def test_concurrent_credit_confirmation_adds_ledger_once(self) -> None:
        order = create_credit_order(self.db_path, user_id=self.user_id, credits=5)
        submit_credit_payment(
            self.db_path,
            order_id=int(order["id"]),
            user_id=self.user_id,
            payment_method="alipay",
            payer_name="tester",
            payer_paid_at="2026-07-20T12:00",
            submitted_amount_cents=500,
            payer_note="proof",
        )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _index: confirm_credit_order(
                        self.db_path,
                        order_id=int(order["id"]),
                        admin_id=self.admin_id,
                        admin_note="到账确认",
                    ),
                    range(2),
                )
            )

        self.assertEqual([item["status"] for item in results], ["paid", "paid"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            ledger_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM credit_ledger WHERE user_id = ? AND reason = 'order_paid' AND related_id = ?",
                    (self.user_id, str(order["id"])),
                ).fetchone()[0]
            )
        self.assertEqual(ledger_count, 1)
        self.assertEqual(self.balance(self.user_id), 13)

    def test_confirm_and_reject_race_keeps_order_and_ledger_consistent(self) -> None:
        order = create_credit_order(self.db_path, user_id=self.user_id, credits=5)
        submit_credit_payment(
            self.db_path,
            order_id=int(order["id"]),
            user_id=self.user_id,
            payment_method="alipay",
            payer_name="tester",
            payer_paid_at="2026-07-20T12:00",
            submitted_amount_cents=500,
        )
        barrier = threading.Barrier(2)

        def confirm() -> str:
            barrier.wait()
            try:
                return str(confirm_credit_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id)["status"])
            except AuthError as exc:
                return f"error:{exc.status}"

        def reject() -> str:
            barrier.wait()
            try:
                return str(reject_credit_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id, admin_note="race reject")["status"])
            except AuthError as exc:
                return f"error:{exc.status}"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(confirm), pool.submit(reject)]
            outcomes = [future.result() for future in results]

        with closing(sqlite3.connect(self.db_path)) as conn:
            stored_status = str(conn.execute("SELECT status FROM orders WHERE id = ?", (order["id"],)).fetchone()[0])
            ledger_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM credit_ledger WHERE reason = 'order_paid' AND related_id = ?",
                    (str(order["id"]),),
                ).fetchone()[0]
            )
        self.assertIn(stored_status, {"paid", "rejected"})
        self.assertEqual(outcomes.count(stored_status), 1)
        self.assertEqual(ledger_count, 1 if stored_status == "paid" else 0)
        self.assertEqual(self.balance(self.user_id), 13 if stored_status == "paid" else 8)

    def test_paid_credit_order_cannot_be_resubmitted_or_rejected(self) -> None:
        order = create_credit_order(self.db_path, user_id=self.user_id, credits=5)
        with self.assertRaises(AuthError):
            reject_credit_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id, admin_note="too early")
        submit_credit_payment(
            self.db_path,
            order_id=int(order["id"]),
            user_id=self.user_id,
            payment_method="alipay",
            payer_name="tester",
            payer_paid_at="2026-07-20T12:00",
            submitted_amount_cents=500,
        )
        confirm_credit_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id)
        with self.assertRaises(AuthError):
            submit_credit_payment(
                self.db_path,
                order_id=int(order["id"]),
                user_id=self.user_id,
                payment_method="wechat",
                payer_name="tester",
                payer_paid_at="2026-07-20T12:30",
                submitted_amount_cents=500,
            )
        with self.assertRaises(AuthError):
            reject_credit_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id, admin_note="late reject")
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT status FROM orders WHERE id = ?", (order["id"],)).fetchone()[0], "paid")
        self.assertEqual(self.balance(self.user_id), 13)

    def test_credit_inputs_require_strict_integers(self) -> None:
        for invalid in (True, 5.0, "5"):
            with self.subTest(kind="purchase", value=invalid), self.assertRaises(AuthError):
                create_credit_order(self.db_path, user_id=self.user_id, credits=invalid)
            with self.subTest(kind="adjust", value=invalid), self.assertRaises(AuthError):
                adjust_user_credits(
                    self.db_path,
                    user_id=self.user_id,
                    delta=invalid,
                    reason="strict input",
                    request_id=f"strict-{type(invalid).__name__}-001",
                    admin_id=self.admin_id,
                )

        order = create_credit_order(self.db_path, user_id=self.user_id, credits=5)
        with self.assertRaises(AuthError):
            submit_credit_payment(
                self.db_path,
                order_id=int(order["id"]),
                user_id=self.user_id,
                payment_method="alipay",
                payer_name="tester",
                payer_paid_at="2026-07-20T12:00",
                submitted_amount_cents=500.0,
            )

    def test_legacy_paid_path_and_admin_targets_cannot_bypass_credit_confirmation(self) -> None:
        pending = create_credit_order(self.db_path, user_id=self.user_id, credits=5)
        with self.assertRaises(AuthError):
            mark_order_paid(self.db_path, order_id=int(pending["id"]))
        with self.assertRaises(AuthError):
            mark_order_paid_by_order_no(
                self.db_path,
                order_no=str(pending["order_no"]),
                total_amount="5.00",
                provider_trade_no="manual-credit-bypass",
            )
        self.assertEqual(self.balance(self.user_id), 8)

        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                admin_order_id = int(
                    conn.execute(
                        """
                        INSERT INTO orders (
                            user_id, order_no, plan_name, credits, amount_cents, status,
                            created_at, product_type, payment_submit_status
                        ) VALUES (?, 'ADMIN-CREDIT-ORDER', '5 次使用', 5, 500, 'submitted', ?, 'credits', 'submitted')
                        """,
                        (self.admin_id, "2026-07-20T12:00:00+08:00"),
                    ).lastrowid
                )
        with self.assertRaises(AuthError) as admin_target:
            confirm_credit_order(self.db_path, order_id=admin_order_id, admin_id=self.admin_id)
        self.assertEqual(admin_target.exception.status, 403)
        self.assertEqual(self.balance(self.admin_id), 0)

    def test_legacy_positive_grant_still_works_for_normal_user(self) -> None:
        result = grant_user_credits(
            self.db_path,
            user_id=self.user_id,
            credits=2,
            reason="legacy support",
            admin_id=self.admin_id,
        )
        self.assertEqual(result["credits_added"], 2)
        self.assertEqual(self.balance(self.user_id), 10)


class CreditPurchaseApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        init_auth_db(self.db_path)
        now = "2026-07-20T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                self.admin_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 'hash', 'salt', 'admin', 'active', ?, ?)
                        """,
                        ("api-admin", "apiadmin", "api-admin@example.com", "APIADMIN", now),
                    ).lastrowid
                )
                self.user_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 'hash', 'salt', 'user', 'active', ?, ?)
                        """,
                        ("api-user", "apiuser", "api-user@example.com", "APIUSER", now),
                    ).lastrowid
                )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('api-admin-token', ?, '2999-01-01', ?)",
                    (self.admin_id, now),
                )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('api-user-token', ?, '2999-01-01', ?)",
                    (self.user_id, now),
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

    def request(self, path: str, *, method: str = "POST", token: str = "", payload: dict | None = None) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            self.base_url + path,
            data=json.dumps(payload or {}).encode(),
            method=method,
            headers=headers,
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_admin_endpoints_reject_anonymous_and_non_admin_requests_without_mutation(self) -> None:
        payload = {"credits": 3, "reason": "api topup", "request_id": "api-adjust-0001"}
        anonymous_status, _ = self.request(f"/api/admin/users/{self.user_id}/credits", payload=payload)
        user_status, _ = self.request(f"/api/admin/users/{self.user_id}/credits", token="api-user-token", payload=payload)

        self.assertEqual(anonymous_status, 401)
        self.assertEqual(user_status, 403)
        with closing(sqlite3.connect(self.db_path)) as conn:
            ledger_count = int(conn.execute("SELECT COUNT(*) FROM credit_ledger").fetchone()[0])
        self.assertEqual(ledger_count, 0)

    def test_admin_adjustment_requires_request_id_and_rejects_admin_target(self) -> None:
        missing_status, _ = self.request(
            f"/api/admin/users/{self.user_id}/credits",
            token="api-admin-token",
            payload={"credits": 3, "reason": "missing idempotency"},
        )
        admin_target_status, _ = self.request(
            f"/api/admin/users/{self.admin_id}/credits",
            token="api-admin-token",
            payload={"credits": 3, "reason": "admin target", "request_id": "api-admin-target-001"},
        )
        self.assertEqual(missing_status, 400)
        self.assertEqual(admin_target_status, 403)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM credit_ledger").fetchone()[0]), 0)

    def test_legacy_paid_api_rejects_new_manual_credit_order(self) -> None:
        order = create_credit_order(self.db_path, user_id=self.user_id, credits=5)
        status, _ = self.request(
            f"/api/admin/orders/{order['id']}/paid",
            token="api-admin-token",
            payload={},
        )
        self.assertEqual(status, 400)
        with closing(sqlite3.connect(self.db_path)) as conn:
            stored = conn.execute("SELECT status FROM orders WHERE id = ?", (order["id"],)).fetchone()
            ledger_count = int(conn.execute("SELECT COUNT(*) FROM credit_ledger").fetchone()[0])
        self.assertEqual(stored[0], "pending")
        self.assertEqual(ledger_count, 0)

    def test_admin_can_pause_user_via_api_and_user_then_gets_403(self) -> None:
        status, payload = self.request(
            f"/api/admin/users/{self.user_id}/status",
            token="api-admin-token",
            payload={"status": "disabled"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["status"], "disabled")

        protected_status, protected_payload = self.request(
            "/api/pay/credits/orders",
            token="api-user-token",
            payload={"credits": 5},
        )
        self.assertEqual(protected_status, 403)
        self.assertIn("暂停", protected_payload["error"])


    def test_admin_can_resume_user_via_api_after_pause(self) -> None:
        paused_status, paused_payload = self.request(
            f"/api/admin/users/{self.user_id}/status",
            token="api-admin-token",
            payload={"status": "disabled"},
        )
        resumed_status, resumed_payload = self.request(
            f"/api/admin/users/{self.user_id}/status",
            token="api-admin-token",
            payload={"status": "active"},
        )

        self.assertEqual(paused_status, 200)
        self.assertEqual(paused_payload["user"]["status"], "disabled")
        self.assertEqual(resumed_status, 200)
        self.assertEqual(resumed_payload["user"]["status"], "active")


if __name__ == "__main__":
    unittest.main()
