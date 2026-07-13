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
from urllib.request import urlopen

from trade_review_agent import auth_system
from trade_review_agent.api.simple_api import TradeReviewHandler, _audited_client_ip
from trade_review_agent.auth_system import AuthError, init_auth_db, login_password_user, register_password_user
from trade_review_agent.legal_agreements import (
    REGISTRATION_AGREEMENT_TYPE,
    REGISTRATION_AGREEMENT_VERSION,
    registration_agreement_payload,
)


EXPECTED_CONTENT_HASH = "7f63c5f04d3aba2c6c36e7140ba655a0f3a10da25abe94e4cc2637505d2fa240"


class RegistrationAgreementTest(unittest.TestCase):
    def _init_db(self, db_path: Path) -> None:
        with patch.dict("os.environ", {"ADMIN_PHONE": "", "ADMIN_PASSWORD": ""}, clear=False):
            init_auth_db(db_path)

    def _seed_email_code(self, db_path: Path, email: str, code: str = "123456") -> None:
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO email_codes (
                        email, code_hash, purpose, ip, consumed, expires_at, created_at
                    )
                    VALUES (?, ?, 'register', '127.0.0.1', 0, ?, ?)
                    """,
                    (
                        email,
                        auth_system._hash_email_code(email, code),
                        "2999-01-01T00:00:00+08:00",
                        "2026-07-13T10:00:00+08:00",
                    ),
                )

    def _register(self, db_path: Path, email: str, **overrides: object) -> dict:
        arguments: dict[str, object] = {
            "username": "newuser",
            "email": email,
            "password": "safe-password",
            "email_code": "123456",
            "agreement_accepted": True,
            "agreement_version": REGISTRATION_AGREEMENT_VERSION,
            "ip": "203.0.113.8",
            "user_agent": "unit-test",
        }
        arguments.update(overrides)
        return register_password_user(db_path, **arguments)  # type: ignore[arg-type]

    def test_public_payload_schema_and_hash_are_stable(self) -> None:
        first = registration_agreement_payload()
        second = registration_agreement_payload()

        self.assertEqual(
            set(first),
            {
                "agreement_type",
                "version",
                "effective_at",
                "title",
                "operator_name",
                "sections",
                "confirmation",
                "content_hash",
            },
        )
        self.assertEqual(first, second)
        self.assertEqual(first["content_hash"], EXPECTED_CONTENT_HASH)
        self.assertEqual(first["version"], REGISTRATION_AGREEMENT_VERSION)
        self.assertEqual(first["operator_name"], "盈航运营方")
        self.assertEqual(len(first["sections"]), 16)
        self.assertTrue(all(set(section) == {"id", "title", "paragraphs", "important"} for section in first["sections"]))

        # Callers cannot mutate the server's canonical agreement through a returned payload.
        first["sections"][0]["title"] = "tampered"
        self.assertNotEqual(registration_agreement_payload()["sections"][0]["title"], "tampered")

    def test_public_endpoint_serves_current_agreement_without_caching(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), TradeReviewHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(
                f"http://127.0.0.1:{server.server_address[1]}/api/legal/registration-agreement",
                timeout=3,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        self.assertEqual(payload, registration_agreement_payload())

    def test_rejected_consent_never_consumes_code_or_creates_user(self) -> None:
        cases = [
            ({"agreement_accepted": None}, 400),
            ({"agreement_accepted": False}, 400),
            ({"agreement_accepted": "true"}, 400),
            ({"agreement_version": "2026-01-01-v0"}, 409),
            ({"agreement_version": None}, 409),
        ]
        for index, (overrides, expected_status) in enumerate(cases):
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / "auth.sqlite"
                email = f"reject{index}@example.com"
                self._init_db(db_path)
                self._seed_email_code(db_path, email)

                with self.assertRaises(AuthError) as raised:
                    self._register(db_path, email, **overrides)

                self.assertEqual(raised.exception.status, expected_status)
                with closing(sqlite3.connect(db_path)) as conn:
                    consumed = conn.execute("SELECT consumed FROM email_codes WHERE email = ?", (email,)).fetchone()[0]
                    user_count = conn.execute("SELECT COUNT(*) FROM users WHERE email = ?", (email,)).fetchone()[0]
                    acceptance_count = conn.execute("SELECT COUNT(*) FROM agreement_acceptances").fetchone()[0]
                self.assertEqual(consumed, 0)
                self.assertEqual(user_count, 0)
                self.assertEqual(acceptance_count, 0)

    def test_accepted_registration_persists_exact_audit_record_and_referral(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            email = "accepted@example.com"
            self._init_db(db_path)
            salt, password_hash = auth_system._hash_password("referrer-password")
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    referrer_id = conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        )
                        VALUES (?, ?, ?, 1, ?, ?, 'user', 'active', 'REFER123', ?)
                        """,
                        (
                            "referrer@example.com",
                            "referrer",
                            "referrer@example.com",
                            password_hash,
                            salt,
                            "2026-07-13T09:00:00+08:00",
                        ),
                    ).lastrowid
            self._seed_email_code(db_path, email)
            long_user_agent = "A" * 600

            result = self._register(
                db_path,
                email,
                invite_code="REFER123",
                user_agent=long_user_agent,
            )

            self.assertTrue(result["token"])
            user_id = result["user"]["id"]
            with closing(sqlite3.connect(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                acceptance = conn.execute(
                    "SELECT * FROM agreement_acceptances WHERE user_id = ?", (user_id,)
                ).fetchone()
                referral = conn.execute(
                    "SELECT * FROM referrals WHERE referred_user_id = ?", (user_id,)
                ).fetchone()
                consumed_codes = conn.execute("SELECT COUNT(*) FROM email_codes WHERE email = ?", (email,)).fetchone()[0]

            self.assertIsNotNone(acceptance)
            self.assertEqual(acceptance["agreement_type"], REGISTRATION_AGREEMENT_TYPE)
            self.assertEqual(acceptance["agreement_version"], REGISTRATION_AGREEMENT_VERSION)
            self.assertEqual(acceptance["content_hash"], EXPECTED_CONTENT_HASH)
            self.assertEqual(acceptance["ip"], "203.0.113.8")
            self.assertEqual(acceptance["user_agent"], "A" * 512)
            self.assertEqual(acceptance["acceptance_method"], "registration_modal")
            self.assertTrue(acceptance["accepted_at"])
            self.assertEqual(referral["referrer_user_id"], referrer_id)
            self.assertEqual(consumed_codes, 0)

    def test_failure_after_user_insert_rolls_back_user_code_and_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            email = "rollback@example.com"
            self._init_db(db_path)
            self._seed_email_code(db_path, email)

            with patch(
                "trade_review_agent.auth_system.registration_agreement_payload",
                side_effect=RuntimeError("simulated persistence failure"),
            ):
                with self.assertRaises(RuntimeError):
                    self._register(db_path, email)

            with closing(sqlite3.connect(db_path)) as conn:
                consumed = conn.execute("SELECT consumed FROM email_codes WHERE email = ?", (email,)).fetchone()[0]
                user_count = conn.execute("SELECT COUNT(*) FROM users WHERE email = ?", (email,)).fetchone()[0]
                acceptance_count = conn.execute("SELECT COUNT(*) FROM agreement_acceptances").fetchone()[0]
            self.assertEqual(consumed, 0)
            self.assertEqual(user_count, 0)
            self.assertEqual(acceptance_count, 0)

    def test_additive_migration_preserves_existing_user_login_and_referral(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            self._init_db(db_path)
            salt, password_hash = auth_system._hash_password("legacy-password")
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    referrer_id = conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, 'legacyref', ?, 1, ?, ?, 'user', 'active', 'LEGACYR1', ?)
                        """,
                        ("legacy-ref@example.com", "legacy-ref@example.com", password_hash, salt, "2026-07-01T10:00:00+08:00"),
                    ).lastrowid
                    referred_id = conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, referred_by, created_at
                        ) VALUES (?, 'legacyuser', ?, 1, ?, ?, 'user', 'active', 'LEGACYU1', ?, ?)
                        """,
                        ("legacy@example.com", "legacy@example.com", password_hash, salt, referrer_id, "2026-07-02T10:00:00+08:00"),
                    ).lastrowid
                    conn.execute(
                        """
                        INSERT INTO referrals (
                            referrer_user_id, referred_user_id, reward_credits, status, created_at
                        ) VALUES (?, ?, 5, 'completed', ?)
                        """,
                        (referrer_id, referred_id, "2026-07-02T10:00:00+08:00"),
                    )

            # Re-running initialization models upgrading an existing production database.
            self._init_db(db_path)
            result = login_password_user(
                db_path,
                account="legacyuser",
                password="legacy-password",
                ip="127.0.0.1",
            )

            self.assertEqual(result["user"]["id"], referred_id)
            with closing(sqlite3.connect(db_path)) as conn:
                referral_count = conn.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
                table_count = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'agreement_acceptances'"
                ).fetchone()[0]
            self.assertEqual(referral_count, 1)
            self.assertEqual(table_count, 1)

    def test_audit_ip_uses_proxy_appended_last_hop(self) -> None:
        self.assertEqual(_audited_client_ip("198.51.100.25, 10.0.0.2", "127.0.0.1"), "10.0.0.2")
        self.assertEqual(_audited_client_ip(" spoofed, , 192.0.2.10 ", "127.0.0.1"), "192.0.2.10")
        self.assertEqual(_audited_client_ip("", "127.0.0.1"), "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
