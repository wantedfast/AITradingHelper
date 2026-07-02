import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from trade_review_agent.auth_system import (
    create_update_notice,
    init_auth_db,
    latest_published_update_notice,
    list_update_notices,
    publish_update_notice,
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
            self.assertEqual(latest["id"], published["id"])
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


if __name__ == "__main__":
    unittest.main()
