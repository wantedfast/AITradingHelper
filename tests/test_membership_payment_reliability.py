"""Reliability tests for the manual-verification membership payment flow.

Covers the 2026-11-18 incident class: a user paid via the personal WeChat QR
code but the admin had no submitted order to confirm.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import (
    CN_TZ,
    AuthError,
    admin_dashboard,
    cancel_membership_order,
    confirm_membership_order,
    create_membership_order,
    get_current_user,
    get_order,
    init_auth_db,
    latest_open_membership_order,
    list_admin_orders,
    list_admin_users,
    manual_grant_membership,
    reject_membership_order,
    submit_membership_payment,
)

PLAN_ENV = {
    "PAYMENT_MONTHLY_PLAN_NAME": "月度会员",
    "PAYMENT_MONTHLY_AMOUNT_CENTS": "5900",
    "PAYMENT_MONTHLY_DURATION_DAYS": "31",
    "PAYMENT_ANNUAL_PLAN_NAME": "年度会员",
    "PAYMENT_ANNUAL_AMOUNT_CENTS": "39900",
    "PAYMENT_ANNUAL_DURATION_DAYS": "365",
    "ADMIN_PAYMENT_NOTIFY_EMAIL": "",
    "EMAIL_PROVIDER": "log",
}


class _Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict("os.environ", PLAN_ENV, clear=False)
        self.env.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        init_auth_db(self.db_path)
        now = "2026-11-01T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                self.admin_id = self._insert_user(conn, "pay-admin", "payadmin", "admin", now)
                self.user_id = self._insert_user(conn, "pay-user", "payuser", "user", now)
                self.other_user_id = self._insert_user(conn, "pay-other", "payother", "user", now)
                for token, user_id in (
                    ("pay-admin-token", self.admin_id),
                    ("pay-user-token", self.user_id),
                    ("pay-other-token", self.other_user_id),
                ):
                    conn.execute(
                        "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', ?)",
                        (token, user_id, now),
                    )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        self.env.stop()

    @staticmethod
    def _insert_user(conn: sqlite3.Connection, phone: str, username: str, role: str, now: str) -> int:
        return int(
            conn.execute(
                """
                INSERT INTO users (
                    phone, username, email, email_verified, password_hash,
                    password_salt, role, status, invite_code, created_at
                ) VALUES (?, ?, ?, 1, 'hash', 'salt', ?, 'active', ?, ?)
                """,
                (phone, username, f"{username}@example.com", role, username.upper()[:12], now),
            ).lastrowid
        )

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchall()

    def set_membership(self, user_id: int, *, status: str, expires_at: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "UPDATE users SET membership_plan = '月度会员', membership_status = ?, membership_expires_at = ? WHERE id = ?",
                    (status, expires_at, user_id),
                )

    def submit(self, order_id: int, user_id: int | None = None, **overrides):
        payload = {
            "payment_method": "wechat",
            "payer_name": "微信昵称小王",
            "payer_paid_at": "2026-11-18T09:15",
            "submitted_amount_cents": 5900,
            "payer_note": "",
        }
        payload.update(overrides)
        return submit_membership_payment(self.db_path, order_id=order_id, user_id=user_id or self.user_id, **payload)

    def grant_kwargs(self, **overrides):
        kwargs = {
            "admin_id": self.admin_id,
            "user_id": self.user_id,
            "plan_id": "monthly_membership",
            "payment_method": "wechat",
            "amount_cents": 5900,
            "payer_name": "微信昵称小王",
            "payer_paid_at": "2026-11-18T09:15",
            "reason": "用户反馈已付款，核对微信到账记录后补录",
            "request_id": "manual-grant-0001",
        }
        kwargs.update(overrides)
        return kwargs


class MembershipOrderIdempotencyTest(_Fixture):
    def test_same_client_request_id_returns_one_order(self) -> None:
        first = create_membership_order(self.db_path, user_id=self.user_id, plan_id="monthly_membership", client_request_id="checkout-aaaa-0001")
        second = create_membership_order(self.db_path, user_id=self.user_id, plan_id="monthly_membership", client_request_id="checkout-aaaa-0001")
        self.assertEqual(first["id"], second["id"])
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(len(self.query("SELECT id FROM orders WHERE user_id = ?", (self.user_id,))), 1)

    def test_client_request_id_cannot_be_reused_for_another_plan(self) -> None:
        create_membership_order(self.db_path, user_id=self.user_id, plan_id="monthly_membership", client_request_id="checkout-bbbb-0001")
        with self.assertRaises(AuthError) as error:
            create_membership_order(self.db_path, user_id=self.user_id, plan_id="annual_membership", client_request_id="checkout-bbbb-0001")
        self.assertEqual(error.exception.status, 409)

    def test_concurrent_creates_without_key_reuse_one_pending_order(self) -> None:
        with ThreadPoolExecutor(max_workers=6) as pool:
            orders = list(pool.map(lambda _i: create_membership_order(self.db_path, user_id=self.user_id, plan_id="monthly_membership"), range(6)))
        self.assertEqual(len({order["id"] for order in orders}), 1)
        self.assertEqual(len(self.query("SELECT id FROM orders WHERE user_id = ?", (self.user_id,))), 1)

    def test_paid_order_is_not_reused_and_renewal_gets_a_fresh_order(self) -> None:
        first = create_membership_order(self.db_path, user_id=self.user_id)
        self.submit(int(first["id"]))
        confirm_membership_order(self.db_path, order_id=int(first["id"]), admin_id=self.admin_id)
        self.assertIsNone(latest_open_membership_order(self.db_path, user_id=self.user_id))
        renewal = create_membership_order(self.db_path, user_id=self.user_id)
        self.assertNotEqual(renewal["id"], first["id"])
        self.assertEqual(renewal["status"], "pending")

    def test_pending_order_is_restored_as_open_order(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        restored = latest_open_membership_order(self.db_path, user_id=self.user_id)
        self.assertEqual(restored["id"], order["id"])
        self.assertEqual(restored["order_no"], order["order_no"])

    def test_admin_cannot_create_membership_order(self) -> None:
        with self.assertRaises(AuthError) as error:
            create_membership_order(self.db_path, user_id=self.admin_id)
        self.assertEqual(error.exception.status, 403)

    def test_user_can_withdraw_submitted_order_without_reopening_on_stale_retry(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        cancelled = cancel_membership_order(self.db_path, order_id=int(order["id"]), user_id=self.user_id)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNone(latest_open_membership_order(self.db_path, user_id=self.user_id))
        second = create_membership_order(self.db_path, user_id=self.user_id)
        self.submit(int(second["id"]))
        cancelled = cancel_membership_order(self.db_path, order_id=second["id"], user_id=self.user_id)
        self.assertEqual(cancelled["status"], "cancelled")
        with self.assertRaises(AuthError) as error:
            self.submit(second["id"])
        self.assertEqual(error.exception.status, 409)
        with self.assertRaises(AuthError):
            confirm_membership_order(self.db_path, order_id=second["id"], admin_id=self.admin_id)

    def test_cancel_and_confirm_race_delivers_only_if_confirm_wins(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        self.submit(order["id"])
        barrier = threading.Barrier(2)
        def act(cancel):
            barrier.wait(timeout=5)
            try:
                if cancel:
                    return cancel_membership_order(self.db_path, order_id=order["id"], user_id=self.user_id)["status"]
                return confirm_membership_order(self.db_path, order_id=order["id"], admin_id=self.admin_id)["status"]
            except AuthError:
                return "refused"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(act, [True, False]))
        status = self.query("SELECT status FROM orders WHERE id = ?", (order["id"],))[0]["status"]
        self.assertCountEqual(outcomes, [status, "refused"])
        self.assertEqual(len(self.query("SELECT id FROM membership_ledger")), int(status == "paid"))

    def test_distinct_purchase_intents_stack_only_after_each_confirmation(self) -> None:
        def create(key):
            return create_membership_order(self.db_path, user_id=self.user_id, client_request_id=key)["id"]
        first = create("purchase-0001")
        self.submit(first)
        second = create("purchase-0002")
        self.assertNotEqual(first, second)
        self.assertEqual(second, create("purchase-0002"))
        self.submit(second)
        self.assertEqual(len(self.query("SELECT id FROM membership_ledger")), 0)
        for oid in (first, second, second):
            confirm_membership_order(self.db_path, order_id=oid, admin_id=self.admin_id)
        ledger = self.query("SELECT started_at, expires_at FROM membership_ledger ORDER BY id")
        self.assertEqual(len(ledger), 2)
        self.assertEqual(ledger[1]["started_at"], ledger[0]["expires_at"])

    def test_rejected_order_can_be_cancelled_to_switch_to_annual(self) -> None:
        monthly = create_membership_order(self.db_path, user_id=self.user_id, plan_id="monthly_membership")
        self.submit(int(monthly["id"]))
        reject_membership_order(self.db_path, order_id=int(monthly["id"]), admin_id=self.admin_id, admin_note="未查到到账")
        cancelled = cancel_membership_order(self.db_path, order_id=int(monthly["id"]), user_id=self.user_id)
        self.assertEqual(cancelled["status"], "cancelled")
        annual = create_membership_order(self.db_path, user_id=self.user_id, plan_id="annual_membership")
        self.assertEqual(annual["amount_cents"], 39900)
        self.assertEqual(latest_open_membership_order(self.db_path, user_id=self.user_id)["id"], annual["id"])
        submitted = self.submit(int(annual["id"]), submitted_amount_cents=39900)
        self.assertEqual(submitted["status"], "submitted")
        confirm_membership_order(self.db_path, order_id=int(annual["id"]), admin_id=self.admin_id)
        ledger = self.query("SELECT started_at, expires_at FROM membership_ledger WHERE order_id = ?", (int(annual["id"]),))[0]
        days = (datetime.fromisoformat(ledger["expires_at"]) - datetime.fromisoformat(ledger["started_at"])).days
        self.assertEqual(days, 365)

    def test_cancelled_order_still_accepts_payment_report(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        cancel_membership_order(self.db_path, order_id=int(order["id"]), user_id=self.user_id)
        submitted = self.submit(int(order["id"]))
        self.assertEqual(submitted["status"], "submitted")


class MembershipSubmitRetryTest(_Fixture):
    def test_identical_resubmission_is_idempotent_and_does_not_renotify(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        with patch("trade_review_agent.auth_system.notify_admin_membership_payment", return_value={"sent": True}) as notify:
            first = self.submit(int(order["id"]))
            second = self.submit(int(order["id"]))
        self.assertEqual(first["status"], "submitted")
        self.assertEqual(second["status"], "submitted")
        self.assertTrue(second["duplicate_submission"])
        self.assertEqual(second["submitted_at"], first["submitted_at"])
        self.assertEqual(notify.call_count, 1)

    def test_identical_resubmission_after_confirmation_returns_paid_without_error(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        self.submit(int(order["id"]))
        confirm_membership_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id)
        again = self.submit(int(order["id"]))
        self.assertEqual(again["status"], "paid")
        with self.assertRaises(AuthError) as error:
            self.submit(int(order["id"]), payer_name="另一个人")
        self.assertEqual(error.exception.status, 409)

    def test_notification_failure_keeps_order_submitted(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        with patch("trade_review_agent.auth_system._send_email_message", side_effect=OSError("smtp down")), patch.dict(
            "os.environ", {"ADMIN_PAYMENT_NOTIFY_EMAIL": "ops@example.com", "EMAIL_PROVIDER": "smtp"}
        ):
            result = self.submit(int(order["id"]))
        self.assertEqual(result["status"], "submitted")
        self.assertFalse(result["admin_notification"]["sent"])
        self.assertIn("smtp down", result["admin_notification"]["error"])
        stored = get_order(self.db_path, order_id=int(order["id"]), admin=True)
        self.assertEqual(stored["status"], "submitted")
        self.assertEqual(stored["admin_notify_status"], "failed")
        counts = admin_dashboard(self.db_path)["order_counts"]
        self.assertEqual(counts["notify_failed"], 1)

    def test_notification_exception_keeps_order_submitted(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        with patch("trade_review_agent.auth_system.notify_admin_membership_payment", side_effect=RuntimeError("boom")):
            result = self.submit(int(order["id"]))
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(get_order(self.db_path, order_id=int(order["id"]), admin=True)["status"], "submitted")

    def test_other_user_cannot_submit_or_cancel(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        with self.assertRaises(AuthError) as error:
            self.submit(int(order["id"]), user_id=self.other_user_id)
        self.assertEqual(error.exception.status, 404)
        with self.assertRaises(AuthError):
            cancel_membership_order(self.db_path, order_id=int(order["id"]), user_id=self.other_user_id)

    def test_state_changes_are_audited(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        self.submit(int(order["id"]))
        reject_membership_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id, admin_note="金额未到账")
        self.submit(int(order["id"]), payer_name="改正后的昵称")
        confirm_membership_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id)
        events = [row["event"] for row in self.query("SELECT event FROM order_events WHERE order_id = ? ORDER BY id", (int(order["id"]),))]
        self.assertEqual(
            events,
            ["created", "payment_submitted", "rejected", "payment_resubmitted_after_reject", "confirmed"],
        )


class AdminReconciliationTest(_Fixture):
    def test_dashboard_counts_pending_and_submitted_separately(self) -> None:
        pending = create_membership_order(self.db_path, user_id=self.user_id)
        submitted = create_membership_order(self.db_path, user_id=self.other_user_id)
        self.submit(int(submitted["id"]), user_id=self.other_user_id)
        counts = admin_dashboard(self.db_path)["order_counts"]
        self.assertEqual(counts["pending"], 1)
        self.assertEqual(counts["pending_recent"], 1)
        self.assertEqual(counts["submitted"], 1)
        self.assertEqual(counts["attention"], 2)
        listed = list_admin_orders(self.db_path, status="attention")
        self.assertEqual({item["id"] for item in listed["items"]}, {pending["id"], submitted["id"]})
        self.assertEqual(listed["status_counts"]["pending"], 1)

    def test_dashboard_counts_are_not_limited_to_latest_50_orders(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.other_user_id)
        self.submit(int(order["id"]), user_id=self.other_user_id)
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                for index in range(60):
                    conn.execute(
                        "INSERT INTO orders (user_id, order_no, plan_name, credits, amount_cents, status, created_at, product_type) VALUES (?, ?, '次数', 1, 100, 'paid', ?, 'credits')",
                        (self.user_id, f"YCFILL{index:03d}", "2099-01-01T00:00:00+08:00"),
                    )
        self.assertEqual(admin_dashboard(self.db_path)["order_counts"]["submitted"], 1)

    def test_admin_search_matches_payer_nickname_and_order_no(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        self.submit(int(order["id"]), payer_name="独特昵称Zed", payer_note="备注ABC")
        create_membership_order(self.db_path, user_id=self.other_user_id)
        for query in ("独特昵称zed", "备注abc", order["order_no"].lower()):
            found = list_admin_orders(self.db_path, query=query)
            self.assertEqual([item["id"] for item in found["items"]], [order["id"]], query)
        detail = found["items"][0]
        self.assertEqual([event["event"] for event in detail["events"]], ["created", "payment_submitted"])
        for field in ("created_at", "submitted_at", "payer_paid_at", "amount_cents", "payment_method", "order_no", "status"):
            self.assertTrue(detail[field], field)

    def test_old_pending_order_is_flagged_unreported_not_paid(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        old = (datetime.now(CN_TZ) - timedelta(hours=2)).isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute("UPDATE orders SET created_at = ? WHERE id = ?", (old, int(order["id"])))
        item = list_admin_orders(self.db_path, status="pending")["items"][0]
        self.assertTrue(item["unreported_payment"])
        self.assertEqual(item["status"], "pending")
        self.assertEqual(self.query("SELECT COUNT(*) AS c FROM membership_ledger")[0]["c"], 0)

    def test_legacy_alipay_orders_remain_readable(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                order_id = int(
                    conn.execute(
                        """
                        INSERT INTO orders (
                            user_id, order_no, plan_name, credits, amount_cents, status, created_at, paid_at,
                            product_type, package_id, duration_days, payment_method, payer_name, payment_submit_status
                        ) VALUES (?, 'YMLEGACYALIPAY', '月度会员', 0, 5900, 'paid', '2026-07-01T10:00:00+08:00',
                                  '2026-07-01T11:00:00+08:00', 'membership', 'monthly_membership', 31, 'alipay', '旧支付宝', 'submitted')
                        """,
                        (self.user_id,),
                    ).lastrowid
                )
        listed = list_admin_orders(self.db_path, query="YMLEGACYALIPAY")["items"][0]
        self.assertEqual(listed["payment_method"], "alipay")
        self.assertEqual(listed["events"], [])
        self.assertEqual(get_order(self.db_path, order_id=order_id, user_id=self.user_id)["status"], "paid")


class ManualGrantTest(_Fixture):
    def ledger_rows(self) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM membership_ledger WHERE user_id = ?", (self.user_id,))

    def test_manual_grant_creates_one_order_and_one_ledger_row(self) -> None:
        result = manual_grant_membership(self.db_path, **self.grant_kwargs())
        self.assertFalse(result["idempotent"])
        self.assertEqual(result["order"]["status"], "paid")
        self.assertEqual(result["order"]["order_source"], "admin_manual")
        self.assertEqual(len(self.query("SELECT id FROM orders WHERE user_id = ?", (self.user_id,))), 1)
        self.assertEqual(len(self.ledger_rows()), 1)
        grant = self.query("SELECT * FROM admin_membership_grants")[0]
        self.assertEqual(grant["admin_id"], self.admin_id)
        self.assertEqual(grant["order_id"], result["order"]["id"])
        self.assertEqual(grant["ledger_id"], result["ledger_id"])
        self.assertIn("核对微信到账", grant["reason"])
        self.assertTrue(result["user"]["membership_active"])

    def test_retry_with_same_request_id_is_idempotent(self) -> None:
        first = manual_grant_membership(self.db_path, **self.grant_kwargs())
        second = manual_grant_membership(self.db_path, **self.grant_kwargs())
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["order"]["id"], second["order"]["id"])
        self.assertEqual(len(self.ledger_rows()), 1)
        self.assertEqual(first["user"]["membership_expires_at"], second["user"]["membership_expires_at"])

    def test_concurrent_manual_grants_extend_membership_once(self) -> None:
        def run(_index: int):
            try:
                return manual_grant_membership(self.db_path, **self.grant_kwargs())
            except AuthError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(run, range(8)))
        successes = [item for item in results if isinstance(item, dict)]
        self.assertEqual(len(successes), 8, results)
        self.assertEqual(len({item["order"]["id"] for item in successes}), 1)
        self.assertEqual(len(self.ledger_rows()), 1)
        self.assertEqual(len(self.query("SELECT id FROM orders WHERE user_id = ?", (self.user_id,))), 1)

    def test_distinct_request_ids_back_to_back_are_blocked(self) -> None:
        manual_grant_membership(self.db_path, **self.grant_kwargs())
        with self.assertRaises(AuthError) as error:
            manual_grant_membership(self.db_path, **self.grant_kwargs(request_id="manual-grant-0002"))
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(len(self.ledger_rows()), 1)

    def test_request_id_reused_for_other_user_is_rejected(self) -> None:
        manual_grant_membership(self.db_path, **self.grant_kwargs())
        with self.assertRaises(AuthError) as error:
            manual_grant_membership(self.db_path, **self.grant_kwargs(user_id=self.other_user_id))
        self.assertEqual(error.exception.status, 409)

    def test_manual_grant_links_existing_pending_order(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        with self.assertRaises(AuthError) as error:
            manual_grant_membership(self.db_path, **self.grant_kwargs())
        self.assertEqual(error.exception.status, 409)
        self.assertIn(order["order_no"], error.exception.message)
        result = manual_grant_membership(self.db_path, **self.grant_kwargs(order_id=int(order["id"])))
        self.assertEqual(result["order"]["id"], order["id"])
        self.assertEqual(result["order"]["status"], "paid")
        self.assertEqual(len(self.ledger_rows()), 1)
        events = [row["event"] for row in self.query("SELECT event FROM order_events WHERE order_id = ? ORDER BY id", (int(order["id"]),))]
        self.assertEqual(events, ["created", "admin_manual_submit", "confirmed"])

    def test_manual_grant_keeps_users_own_submitted_payment_report(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        self.submit(int(order["id"]), payer_name="用户自己填的昵称")
        result = manual_grant_membership(self.db_path, **self.grant_kwargs(order_id=int(order["id"]), payer_name="管理员填写"))
        self.assertEqual(result["order"]["status"], "paid")
        self.assertEqual(result["order"]["payer_name"], "用户自己填的昵称")
        self.assertEqual(len(self.ledger_rows()), 1)

    def test_manual_grant_on_paid_order_is_rejected(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        self.submit(int(order["id"]))
        confirm_membership_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id)
        with self.assertRaises(AuthError) as error:
            manual_grant_membership(self.db_path, **self.grant_kwargs(order_id=int(order["id"])))
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(len(self.ledger_rows()), 1)

    def test_manual_grant_validates_inputs_and_targets(self) -> None:
        cases = [
            ({"user_id": self.admin_id}, 403),
            ({"amount_cents": 100}, 400),
            ({"reason": ""}, 400),
            ({"request_id": "x"}, 400),
            ({"plan_id": "unknown"}, 400),
            ({"payer_name": ""}, 400),
            ({"admin_id": self.other_user_id}, 403),
        ]
        for overrides, status in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(AuthError) as error:
                    manual_grant_membership(self.db_path, **self.grant_kwargs(**overrides))
                self.assertEqual(error.exception.status, status)
        self.assertEqual(self.query("SELECT COUNT(*) AS c FROM membership_ledger")[0]["c"], 0)
        self.assertEqual(self.query("SELECT COUNT(*) AS c FROM orders")[0]["c"], 0)


class MembershipPeriodTest(_Fixture):
    def expiry(self) -> datetime:
        row = self.query("SELECT membership_expires_at FROM users WHERE id = ?", (self.user_id,))[0]
        return datetime.fromisoformat(row["membership_expires_at"])

    def test_expired_member_starts_from_now(self) -> None:
        self.set_membership(self.user_id, status="active", expires_at="2026-10-01T10:00:00+08:00")
        before = datetime.now(CN_TZ)
        manual_grant_membership(self.db_path, **self.grant_kwargs())
        after = datetime.now(CN_TZ)
        self.assertGreaterEqual(self.expiry(), before + timedelta(days=31))
        self.assertLessEqual(self.expiry(), after + timedelta(days=31))

    def test_unexpired_member_extends_from_current_expiry(self) -> None:
        current = (datetime.now(CN_TZ) + timedelta(days=5)).replace(microsecond=0)
        self.set_membership(self.user_id, status="active", expires_at=current.isoformat())
        order = create_membership_order(self.db_path, user_id=self.user_id)
        self.submit(int(order["id"]))
        confirm_membership_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id)
        self.assertEqual(self.expiry(), current + timedelta(days=31))

    def test_naive_expiry_timestamp_does_not_crash_and_is_treated_as_china_time(self) -> None:
        current = (datetime.now(CN_TZ) + timedelta(days=3)).replace(microsecond=0, tzinfo=None)
        self.set_membership(self.user_id, status="active", expires_at=current.isoformat())
        user = get_current_user(self.db_path, "pay-user-token")
        self.assertTrue(user["membership_active"])
        manual_grant_membership(self.db_path, **self.grant_kwargs())
        self.assertEqual(self.expiry(), current.replace(tzinfo=CN_TZ) + timedelta(days=31))

    def test_active_status_with_past_expiry_is_reported_as_expired(self) -> None:
        self.set_membership(self.user_id, status="active", expires_at="2026-10-01T10:00:00+08:00")
        user = get_current_user(self.db_path, "pay-user-token")
        self.assertFalse(user["membership_active"])
        self.assertEqual(user["membership_status"], "expired")
        admin_row = next(item for item in list_admin_users(self.db_path)["items"] if item["id"] == self.user_id)
        self.assertFalse(admin_row["membership_active"])
        self.assertEqual(admin_row["membership_status"], "expired")


class MembershipPaymentApiTest(_Fixture):
    def setUp(self) -> None:
        super().setUp()
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
        super().tearDown()

    def request(self, path: str, *, method: str = "POST", token: str = "", payload: dict | None = None) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(payload or {}).encode() if method != "GET" else None
        request = Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def grant_payload(self, **overrides) -> dict:
        payload = self.grant_kwargs(**overrides)
        payload.pop("admin_id")
        return payload

    def test_non_admin_manual_grant_returns_403_without_mutation(self) -> None:
        anonymous, _ = self.request("/api/admin/memberships/manual-grant", payload=self.grant_payload())
        user, _ = self.request("/api/admin/memberships/manual-grant", token="pay-user-token", payload=self.grant_payload())
        self.assertEqual(anonymous, 401)
        self.assertEqual(user, 403)
        self.assertEqual(self.query("SELECT COUNT(*) AS c FROM membership_ledger")[0]["c"], 0)
        self.assertEqual(self.query("SELECT COUNT(*) AS c FROM orders")[0]["c"], 0)

    def test_admin_manual_grant_api_retry_is_idempotent(self) -> None:
        status, first = self.request("/api/admin/memberships/manual-grant", token="pay-admin-token", payload=self.grant_payload())
        self.assertEqual(status, 200, first)
        status, second = self.request("/api/admin/memberships/manual-grant", token="pay-admin-token", payload=self.grant_payload())
        self.assertEqual(status, 200, second)
        self.assertTrue(second["idempotent"])
        self.assertEqual(self.query("SELECT COUNT(*) AS c FROM membership_ledger")[0]["c"], 1)

    def test_checkout_api_create_retry_restore_and_submit(self) -> None:
        body = {"plan_id": "monthly_membership", "client_request_id": "checkout-api-0001"}
        status, created = self.request("/api/pay/membership/orders", token="pay-user-token", payload=body)
        self.assertEqual(status, 200, created)
        status, retried = self.request("/api/pay/membership/orders", token="pay-user-token", payload=body)
        self.assertEqual(retried["order"]["id"], created["order"]["id"])
        status, latest = self.request("/api/pay/membership/orders/latest", method="GET", token="pay-user-token")
        self.assertEqual(latest["order"]["id"], created["order"]["id"])
        order_id = created["order"]["id"]
        submit_body = {
            "payment_method": "wechat",
            "payer_name": "微信昵称",
            "payer_paid_at": "2026-11-18T09:15",
            "submitted_amount_cents": 5900,
            "payer_note": created["order"]["order_no"],
        }
        status, submitted = self.request(f"/api/pay/membership/orders/{order_id}/submit", token="pay-user-token", payload=submit_body)
        self.assertEqual(status, 200, submitted)
        status, again = self.request(f"/api/pay/membership/orders/{order_id}/submit", token="pay-user-token", payload=submit_body)
        self.assertEqual(status, 200, again)
        self.assertEqual(again["order"]["status"], "submitted")

    def test_order_history_requires_auth_and_paginates_only_my_memberships(self) -> None:
        path = "/api/pay/membership/orders"
        self.assertEqual(self.request(path, method="GET")[0], 401)
        ids = [create_membership_order(self.db_path, user_id=self.user_id, client_request_id=f"history-{i:04}")["id"] for i in range(22)]
        create_membership_order(self.db_path, user_id=self.other_user_id)
        cancel_membership_order(self.db_path, user_id=self.user_id, order_id=ids[0])
        status, first = self.request(path, method="GET", token="pay-user-token")
        self.assertEqual(status, 200)
        _, second = self.request(f"{path}?before={first['next_before']}", method="GET", token="pay-user-token")
        self.assertEqual([r["id"] for r in first["orders"]+second["orders"]], ids[::-1])
        self.assertEqual(second["orders"][-1]["status"], "cancelled")
        self.assertIsNone(second["next_before"])

    def test_latest_api_hides_paid_order_so_expired_member_can_renew(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        self.submit(int(order["id"]))
        confirm_membership_order(self.db_path, order_id=int(order["id"]), admin_id=self.admin_id)
        self.set_membership(self.user_id, status="active", expires_at="2026-10-01T10:00:00+08:00")
        status, latest = self.request("/api/pay/membership/orders/latest", method="GET", token="pay-user-token")
        self.assertEqual(status, 200)
        self.assertIsNone(latest["order"])
        self.assertEqual(latest["last_order"]["id"], order["id"])
        self.assertEqual(latest["user"]["membership_status"], "expired")

    def test_cancel_api_and_bad_paths(self) -> None:
        order = create_membership_order(self.db_path, user_id=self.user_id)
        status, other = self.request(f"/api/pay/membership/orders/{order['id']}/cancel", token="pay-other-token")
        self.assertEqual(status, 404, other)
        status, cancelled = self.request(f"/api/pay/membership/orders/{order['id']}/cancel", token="pay-user-token")
        self.assertEqual(status, 200, cancelled)
        self.assertEqual(cancelled["order"]["status"], "cancelled")
        status, _ = self.request("/api/pay/membership/orders/abc/submit", token="pay-user-token")
        self.assertEqual(status, 404)

    def test_admin_orders_api_supports_attention_filter_and_counts(self) -> None:
        create_membership_order(self.db_path, user_id=self.user_id)
        status, payload = self.request("/api/admin/orders?status=attention", method="GET", token="pay-admin-token")
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["status_counts"]["pending"], 1)


if __name__ == "__main__":
    unittest.main()
