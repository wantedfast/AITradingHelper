import sqlite3
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest import mock

from trade_review_agent.auth_system import (
    AuthError,
    create_update_notice,
    init_auth_db,
    latest_published_update_notice,
    list_update_notices,
    publish_update_notice,
    process_next_update_email,
    recover_update_email_queue,
    retry_update_email_campaign,
    set_update_email_preference,
    unpublish_update_notice,
    update_update_notice,
)


class UpdateNoticeTest(unittest.TestCase):
    def _create_admin(self, db_path: Path) -> int:
        init_auth_db(db_path)
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO users (
                        phone, username, email, email_verified, password_hash,
                        password_salt, role, status, invite_code, created_at
                    )
                    VALUES (?, ?, ?, 1, 'hash', 'salt', 'admin', 'active', ?, ?)
                    """,
                    ("notice-admin", "noticeadmin", "notice-admin@example.com", "NOTICEADMIN", "2026-07-02T10:00:00+08:00"),
                )
                return int(cursor.lastrowid)

    def test_latest_notice_only_returns_published_notice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            admin_id = self._create_admin(db_path)

            draft = create_update_notice(
                db_path,
                title="Draft update",
                version="2026-07-02",
                items=["Draft item"],
                admin_id=admin_id,
            )
            self.assertIsNone(latest_published_update_notice(db_path))

            published = publish_update_notice(db_path, notice_id=int(draft["id"]))
            latest = latest_published_update_notice(db_path)
            self.assertIsNotNone(latest)
            self.assertEqual(latest["id"], published["notice"]["id"])
            self.assertEqual(latest["items"], ["Draft item"])

            unpublish_update_notice(db_path, notice_id=int(draft["id"]))
            self.assertIsNone(latest_published_update_notice(db_path))

    def test_notice_can_be_edited_and_listed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            admin_id = self._create_admin(db_path)

            notice = create_update_notice(
                db_path,
                title="First title",
                version="v1",
                items=["One"],
                admin_id=admin_id,
            )
            updated = update_update_notice(
                db_path,
                notice_id=int(notice["id"]),
                title="Second title",
                version="v2",
                items=["One", "Two"],
            )
            notices = list_update_notices(db_path)

            self.assertEqual(updated["title"], "Second title")
            self.assertEqual(updated["version"], "v2")
            self.assertEqual(updated["items"], ["One", "Two"])
            self.assertEqual(notices[0]["id"], notice["id"])

    def test_email_campaign_snapshots_verified_opted_in_recipients_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            admin_id = self._create_admin(db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    for index, verified, enabled, status in (
                        (1, 1, 1, "active"),
                        (2, 1, 1, "disabled"),
                        (3, 0, 1, "active"),
                        (4, 1, 0, "active"),
                    ):
                        conn.execute(
                            """
                            INSERT INTO users (
                                phone, username, email, email_verified, update_emails_enabled,
                                password_hash, password_salt, role, status, invite_code, created_at
                            ) VALUES (?, ?, ?, ?, ?, 'hash', 'salt', 'user', ?, ?, ?)
                            """,
                            (f"notice-user-{index}", f"noticeuser{index}", f"user{index}@example.com", verified, enabled, status, f"NOTICE{index}", "2026-07-15T10:00:00+08:00"),
                        )
            notice = create_update_notice(db_path, title="Update", version="2026-07-15", items=["One"], admin_id=admin_id)
            request_id = "campaign-request-001"

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: publish_update_notice(
                    db_path, notice_id=int(notice["id"]), send_email=True, request_id=request_id, admin_id=admin_id
                ), range(2)))

            campaign = results[0]["email_campaign"]
            self.assertEqual(campaign["id"], results[1]["email_campaign"]["id"])
            self.assertEqual(campaign["total"], 5)
            self.assertEqual(campaign["pending"], 3)  # admin + active user + disabled-status verified user
            self.assertEqual(campaign["skipped"], 2)
            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM update_email_campaigns").fetchone()[0], 1)
            other = create_update_notice(db_path, title="Other", version="2026-07-16", items=["Two"], admin_id=admin_id)
            with self.assertRaises(AuthError) as collision:
                publish_update_notice(db_path, notice_id=int(other["id"]), send_email=True, request_id=request_id, admin_id=admin_id)
            self.assertEqual(collision.exception.status, 409)

    def test_preference_affects_future_campaigns_and_queue_can_retry_failures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            admin_id = self._create_admin(db_path)
            updated = set_update_email_preference(db_path, user_id=admin_id, enabled=False)
            self.assertFalse(updated["update_emails_enabled"])
            notice = create_update_notice(db_path, title="Update", version="2026-07-15", items=["One"], admin_id=admin_id)
            result = publish_update_notice(
                db_path, notice_id=int(notice["id"]), send_email=True, request_id="campaign-request-002", admin_id=admin_id
            )
            self.assertEqual(result["email_campaign"]["pending"], 0)
            self.assertEqual(result["email_campaign"]["skipped"], 1)

            set_update_email_preference(db_path, user_id=admin_id, enabled=True)
            result = publish_update_notice(
                db_path, notice_id=int(notice["id"]), send_email=True, request_id="campaign-request-003", admin_id=admin_id
            )
            campaign_id = result["email_campaign"]["id"]
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    conn.execute(
                        "UPDATE update_email_deliveries SET status = 'sending', updated_at = '2000-01-01' WHERE campaign_id = ?",
                        (campaign_id,),
                    )
            self.assertEqual(recover_update_email_queue(db_path), 1)
            with mock.patch("trade_review_agent.auth_system._send_update_notice_email", side_effect=RuntimeError("smtp down")):
                for _ in range(3):
                    self.assertTrue(process_next_update_email(db_path))
                    with closing(sqlite3.connect(db_path)) as conn:
                        with conn:
                            conn.execute("UPDATE update_email_deliveries SET next_attempt_at = '2000-01-01' WHERE campaign_id = ?", (campaign_id,))
            retried = retry_update_email_campaign(db_path, campaign_id=campaign_id)
            self.assertEqual(retried["pending"], 1)
            self.assertEqual(retried["failed"], 0)
            with mock.patch.dict(os.environ, {"PUBLIC_SITE_URL": "https://example.test"}), mock.patch(
                "trade_review_agent.auth_system._send_smtp_message"
            ) as smtp:
                self.assertTrue(process_next_update_email(db_path))
            self.assertEqual(smtp.call_args.args[0], "notice-admin@example.com")
            with closing(sqlite3.connect(db_path)) as conn:
                status = conn.execute("SELECT status FROM update_email_campaigns WHERE id = ?", (campaign_id,)).fetchone()[0]
            self.assertEqual(status, "completed")


if __name__ == "__main__":
    unittest.main()
