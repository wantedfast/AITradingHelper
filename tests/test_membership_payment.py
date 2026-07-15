import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from trade_review_agent.auth_system import (
    AuthError,
    confirm_membership_order,
    consume_feature_credit,
    consume_feature_credit_once,
    create_membership_order,
    ensure_feature_credit_available,
    has_feature_access,
    init_auth_db,
    membership_plans,
    notify_admin_membership_payment,
    submit_membership_payment,
)


class MembershipPaymentTest(unittest.TestCase):
    def _create_user(self, db_path: Path) -> int:
        init_auth_db(db_path)
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO users (
                        phone, username, email, email_verified, password_hash,
                        password_salt, role, status, invite_code, created_at
                    )
                    VALUES (?, ?, ?, 1, 'hash', 'salt', 'user', 'active', ?, ?)
                    """,
                    ("member@example.com", "memberuser", "member@example.com", "MEMBER1", "2026-07-02T10:00:00+08:00"),
                )
                return int(cursor.lastrowid)

    def test_membership_plans_include_monthly_and_annual_options(self):
        with patch.dict(
            "os.environ",
            {
                "PAYMENT_MONTHLY_PLAN_NAME": "月度会员",
                "PAYMENT_MONTHLY_AMOUNT_CENTS": "5900",
                "PAYMENT_MONTHLY_DURATION_DAYS": "31",
                "PAYMENT_ANNUAL_PLAN_NAME": "年度会员",
                "PAYMENT_ANNUAL_AMOUNT_CENTS": "39900",
                "PAYMENT_ANNUAL_DURATION_DAYS": "365",
            },
            clear=False,
        ):
            plans = membership_plans()

        self.assertEqual(
            [(plan["id"], plan["amount_cents"], plan["duration_days"]) for plan in plans],
            [("monthly_membership", 5900, 31), ("annual_membership", 39900, 365)],
        )
        self.assertEqual(plans[1]["plan_name"], "年度会员")

    def test_annual_membership_order_uses_server_plan_amount_and_duration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            user_id = self._create_user(db_path)
            with patch.dict(
                "os.environ",
                {
                    "PAYMENT_ANNUAL_PLAN_NAME": "年度会员",
                    "PAYMENT_ANNUAL_AMOUNT_CENTS": "39900",
                    "PAYMENT_ANNUAL_DURATION_DAYS": "365",
                },
                clear=False,
            ):
                order = create_membership_order(db_path, user_id=user_id, plan_id="annual_membership")

        self.assertEqual(order["package_id"], "annual_membership")
        self.assertEqual(order["plan_name"], "年度会员")
        self.assertEqual(order["amount_cents"], 39900)
        self.assertEqual(order["duration_days"], 365)

    def test_membership_order_rejects_unknown_plan_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            user_id = self._create_user(db_path)

            with self.assertRaises(AuthError) as error:
                create_membership_order(db_path, user_id=user_id, plan_id="annual_membership_399")

        self.assertEqual(error.exception.status, 400)

    def test_annual_confirmation_extends_existing_membership_by_365_days(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            user_id = self._create_user(db_path)
            existing_expiry = "2030-01-01T09:30:00+08:00"
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    conn.execute(
                        "UPDATE users SET membership_plan = '月度会员', membership_status = 'active', membership_expires_at = ? WHERE id = ?",
                        (existing_expiry, user_id),
                    )

            with patch.dict(
                "os.environ",
                {
                    "PAYMENT_ANNUAL_PLAN_NAME": "年度会员",
                    "PAYMENT_ANNUAL_AMOUNT_CENTS": "39900",
                    "PAYMENT_ANNUAL_DURATION_DAYS": "365",
                    "ADMIN_PAYMENT_NOTIFY_EMAIL": "admin@example.com",
                    "EMAIL_PROVIDER": "log",
                },
                clear=False,
            ):
                order = create_membership_order(db_path, user_id=user_id, plan_id="annual_membership")
                with self.assertRaises(AuthError) as amount_error:
                    submit_membership_payment(
                        db_path,
                        order_id=int(order["id"]),
                        user_id=user_id,
                        payment_method="wechat",
                        payer_name="付款用户",
                        payer_paid_at="2026-07-15T12:00",
                        submitted_amount_cents=5900,
                    )
                self.assertEqual(amount_error.exception.status, 400)

                submit_membership_payment(
                    db_path,
                    order_id=int(order["id"]),
                    user_id=user_id,
                    payment_method="wechat",
                    payer_name="付款用户",
                    payer_paid_at="2026-07-15T12:00",
                    submitted_amount_cents=39900,
                )
                paid = confirm_membership_order(db_path, order_id=int(order["id"]), admin_id=1)
                confirmed_again = confirm_membership_order(db_path, order_id=int(order["id"]), admin_id=1)

            self.assertEqual(paid["status"], "paid")
            self.assertEqual(confirmed_again["status"], "paid")
            self.assertEqual(paid["duration_days"], 365)
            with closing(sqlite3.connect(db_path)) as conn:
                membership = conn.execute(
                    "SELECT membership_plan, membership_status, membership_expires_at FROM users WHERE id = ?",
                    (user_id,),
                ).fetchone()
                ledger_count = conn.execute(
                    "SELECT COUNT(*) FROM membership_ledger WHERE order_id = ?",
                    (int(order["id"]),),
                ).fetchone()[0]
            self.assertEqual(membership[0], "年度会员")
            self.assertEqual(membership[1], "active")
            self.assertEqual(membership[2], "2031-01-01T09:30:00+08:00")
            self.assertEqual(ledger_count, 1)

    def test_annual_payment_notification_uses_order_plan_and_amount(self):
        with patch.dict(
            "os.environ",
            {"ADMIN_PAYMENT_NOTIFY_EMAIL": "admin@example.com", "EMAIL_PROVIDER": "smtp"},
            clear=False,
        ), patch("trade_review_agent.auth_system._send_smtp_message") as send_message:
            result = notify_admin_membership_payment(
                order={
                    "order_no": "YM20260715ANNUAL",
                    "plan_name": "年度会员",
                    "amount_cents": 39900,
                    "submitted_amount_cents": 39900,
                    "payment_method": "alipay",
                },
                user={"id": 7, "username": "memberuser", "email": "member@example.com"},
            )

        self.assertTrue(result["sent"])
        self.assertEqual(send_message.call_count, 1)
        self.assertEqual(
            send_message.call_args.kwargs["subject"],
            "【盈航】用户已付款待确认 - 年度会员 ¥399.00 - 订单号 YM20260715ANNUAL",
        )

    def test_membership_payment_submit_notifies_admin_and_confirm_opens_membership(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            user_id = self._create_user(db_path)
            with patch.dict(
                "os.environ",
                {
                    "PAYMENT_MONTHLY_AMOUNT_CENTS": "5900",
                    "ADMIN_PAYMENT_NOTIFY_EMAIL": "admin@example.com",
                    "EMAIL_PROVIDER": "log",
                },
                clear=False,
            ):
                order = create_membership_order(db_path, user_id=user_id)
                submitted = submit_membership_payment(
                    db_path,
                    order_id=int(order["id"]),
                    user_id=user_id,
                    payment_method="alipay",
                    payer_name="付款用户",
                    payer_paid_at="2026-07-02T12:00",
                    submitted_amount_cents=5900,
                    payer_note=order["order_no"],
                )
                self.assertEqual(submitted["status"], "submitted")
                self.assertFalse(submitted["admin_notification"]["sent"])
                self.assertTrue(submitted["admin_notification"]["skipped"])

                paid = confirm_membership_order(db_path, order_id=int(order["id"]), admin_id=1)
                again = confirm_membership_order(db_path, order_id=int(order["id"]), admin_id=1)
                self.assertEqual(paid["status"], "paid")
                self.assertEqual(again["status"], "paid")

                refreshed = consume_feature_credit_once(db_path, user_id=user_id, feature="review_report", related_id="r1")
                self.assertTrue(refreshed["membership_active"])
                with closing(sqlite3.connect(db_path)) as conn:
                    usage = conn.execute("SELECT status, credits_spent FROM usage_events WHERE user_id = ?", (user_id,)).fetchone()
                self.assertEqual(usage[0], "membership_free")
                self.assertEqual(usage[1], 0)

    def test_ai_research_view_charges_once_and_unlocks_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            user_id = self._create_user(db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    conn.execute(
                        "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, 2, 'test', NULL, ?)",
                        (user_id, "2026-07-02T10:00:00+08:00"),
                    )

            self.assertFalse(has_feature_access(db_path, user_id=user_id, feature="ai_research_view", related_id="report-1"))
            first = consume_feature_credit_once(db_path, user_id=user_id, feature="ai_research_view", related_id="report-1")
            second = consume_feature_credit_once(db_path, user_id=user_id, feature="ai_research_view", related_id="report-1")

            self.assertTrue(has_feature_access(db_path, user_id=user_id, feature="ai_research_view", related_id="report-1"))
            self.assertEqual(first["credits"], 0)
            self.assertEqual(second["credits"], 0)

    def test_feature_credit_costs_match_product_pricing(self):
        cases = {
            "review_report": 2,
            "watch_plan": 1,
            "market_day_report": 1,
            "ai_research_view": 2,
            "auction_strength_view": 2,
        }
        for feature, expected_cost in cases.items():
            with self.subTest(feature=feature), tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / "auth.sqlite"
                user_id = self._create_user(db_path)
                with closing(sqlite3.connect(db_path)) as conn:
                    with conn:
                        conn.execute(
                            "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, 5, 'test', NULL, ?)",
                            (user_id, "2026-07-02T10:00:00+08:00"),
                        )

                if feature == "watch_plan":
                    refreshed = consume_feature_credit(db_path, user_id=user_id, feature=feature, related_id="case-1")
                else:
                    refreshed = consume_feature_credit_once(db_path, user_id=user_id, feature=feature, related_id="case-1")

                self.assertEqual(refreshed["credits"], 5 - expected_cost)
                with closing(sqlite3.connect(db_path)) as conn:
                    usage = conn.execute(
                        "SELECT credits_spent FROM usage_events WHERE user_id = ? AND feature = ? AND status = 'charged'",
                        (user_id, feature),
                    ).fetchone()
                self.assertEqual(usage[0], expected_cost)

    def test_two_credit_feature_is_blocked_without_sufficient_balance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            user_id = self._create_user(db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    conn.execute(
                        "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, 1, 'test', NULL, ?)",
                        (user_id, "2026-07-02T10:00:00+08:00"),
                    )

            with self.assertRaises(AuthError) as precheck_error:
                ensure_feature_credit_available(db_path, user_id=user_id, feature="review_report", related_id="report-2")
            self.assertEqual(precheck_error.exception.status, 402)
            self.assertIn("需要 2 次", precheck_error.exception.message)

            with self.assertRaises(AuthError) as charge_error:
                consume_feature_credit_once(db_path, user_id=user_id, feature="ai_research_view", related_id="report-2")
            self.assertEqual(charge_error.exception.status, 402)
            with closing(sqlite3.connect(db_path)) as conn:
                balance = conn.execute(
                    "SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE user_id = ?",
                    (user_id,),
                ).fetchone()[0]
            self.assertEqual(balance, 1)

    def test_market_day_report_access_is_idempotent_and_independent_per_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            first_user = self._create_user(db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    second_user = int(
                        conn.execute(
                            """
                            INSERT INTO users (
                                phone, username, email, email_verified, password_hash,
                                password_salt, role, status, invite_code, created_at
                            ) VALUES (?, ?, ?, 1, 'hash', 'salt', 'user', 'active', ?, ?)
                            """,
                            ("second@example.com", "seconduser", "second@example.com", "SECOND1", "2026-07-02T10:00:00+08:00"),
                        ).lastrowid
                    )
                    for user_id in (first_user, second_user):
                        conn.execute(
                            "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, 2, 'test', NULL, ?)",
                            (user_id, "2026-07-02T10:00:00+08:00"),
                        )

            run_id = "codex-2026-07-10"
            self.assertFalse(has_feature_access(db_path, user_id=first_user, feature="market_day_report", related_id=run_id))
            self.assertFalse(has_feature_access(db_path, user_id=second_user, feature="market_day_report", related_id=run_id))

            first_view = consume_feature_credit_once(db_path, user_id=first_user, feature="market_day_report", related_id=run_id)
            repeated_view = consume_feature_credit_once(db_path, user_id=first_user, feature="market_day_report", related_id=run_id)
            second_view = consume_feature_credit_once(db_path, user_id=second_user, feature="market_day_report", related_id=run_id)

            self.assertEqual(first_view["credits"], 1)
            self.assertEqual(repeated_view["credits"], 1)
            self.assertEqual(second_view["credits"], 1)
            self.assertTrue(has_feature_access(db_path, user_id=first_user, feature="market_day_report", related_id=run_id))
            self.assertTrue(has_feature_access(db_path, user_id=second_user, feature="market_day_report", related_id=run_id))


if __name__ == "__main__":
    unittest.main()
