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
