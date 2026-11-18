import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from trade_review_agent.auth_system import (
    ADMIN_LOGIN_FAILURE_LIMIT,
    LOGIN_FAILURE_LIMIT,
    AuthError,
    _hash_password,
    create_credit_order,
    init_auth_db,
    login_admin_password_user,
    login_password_user,
    submit_credit_payment,
)

PASSWORD = "Correct-Horse-1"


class LoginThrottleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        init_auth_db(self.db_path)
        salt, digest = _hash_password(PASSWORD)
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                for username, role in (("member", "user"), ("other", "user"), ("boss", "admin")):
                    conn.execute(
                        """
                        INSERT INTO users (phone, username, email, email_verified, password_hash, password_salt,
                                           role, status, invite_code, created_at)
                        VALUES (?, ?, ?, 1, ?, ?, ?, 'active', ?, '2026-11-01T10:00:00+08:00')
                        """,
                        (f"email:{username}@example.test", username, f"{username}@example.test", digest, salt, role, username.upper()),
                    )
                self.user_id = int(conn.execute("SELECT id FROM users WHERE username = 'member'").fetchone()[0])

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def fail_login(self, account: str, *, admin: bool = False) -> int:
        fn = login_admin_password_user if admin else login_password_user
        with self.assertRaises(AuthError) as error:
            fn(self.db_path, account=account, password="wrong-password")
        return error.exception.status

    def test_repeated_failures_lock_the_account_even_for_the_right_password(self) -> None:
        statuses = [self.fail_login("member") for _ in range(LOGIN_FAILURE_LIMIT)]
        self.assertEqual(set(statuses), {401})
        self.assertEqual(self.fail_login("member"), 429)
        with self.assertRaises(AuthError) as error:
            login_password_user(self.db_path, account="member", password=PASSWORD)
        self.assertEqual(error.exception.status, 429)

    def test_lock_is_per_account_and_case_insensitive(self) -> None:
        for _ in range(LOGIN_FAILURE_LIMIT):
            self.fail_login("Member")
        self.assertEqual(self.fail_login("member"), 429)
        self.assertTrue(login_password_user(self.db_path, account="other", password=PASSWORD)["token"])

    def test_success_resets_the_failure_counter(self) -> None:
        for _ in range(LOGIN_FAILURE_LIMIT - 1):
            self.fail_login("member")
        self.assertTrue(login_password_user(self.db_path, account="member", password=PASSWORD)["token"])
        for _ in range(LOGIN_FAILURE_LIMIT - 1):
            self.assertEqual(self.fail_login("member"), 401)

    def test_old_failures_expire(self) -> None:
        for _ in range(LOGIN_FAILURE_LIMIT):
            self.fail_login("member")
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute("UPDATE login_failures SET created_at = '2026-01-01T00:00:00+08:00'")
        self.assertTrue(login_password_user(self.db_path, account="member", password=PASSWORD)["token"])

    def test_admin_login_has_a_stricter_limit(self) -> None:
        for _ in range(ADMIN_LOGIN_FAILURE_LIMIT):
            self.assertEqual(self.fail_login("boss", admin=True), 401)
        self.assertEqual(self.fail_login("boss", admin=True), 429)
        self.assertTrue(login_password_user.__name__)  # user login of other accounts unaffected
        self.assertTrue(login_password_user(self.db_path, account="member", password=PASSWORD)["token"])

    def test_identical_credit_resubmission_is_idempotent(self) -> None:
        order = create_credit_order(self.db_path, user_id=self.user_id, credits=5)
        kwargs = {
            "order_id": int(order["id"]),
            "user_id": self.user_id,
            "payment_method": "wechat",
            "payer_name": "微信昵称",
            "payer_paid_at": "2026-11-18T10:00",
            "submitted_amount_cents": 500,
            "payer_note": order["order_no"],
        }
        first = submit_credit_payment(self.db_path, **kwargs)
        second = submit_credit_payment(self.db_path, **kwargs)
        self.assertEqual(first["status"], "submitted")
        self.assertTrue(second["duplicate_submission"])
        with self.assertRaises(AuthError) as error:
            submit_credit_payment(self.db_path, **(kwargs | {"payer_name": "别人"}))
        self.assertEqual(error.exception.status, 409)


if __name__ == "__main__":
    unittest.main()
