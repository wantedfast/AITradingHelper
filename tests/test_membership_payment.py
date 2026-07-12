import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from trade_review_agent.auth_system import (
    confirm_membership_order,
    consume_feature_credit_once,
    create_membership_order,
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
            self.assertEqual(first["credits"], 1)
            self.assertEqual(second["credits"], 1)


if __name__ == "__main__":
    unittest.main()
