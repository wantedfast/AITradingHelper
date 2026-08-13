import sqlite3
import os
import smtplib
import tempfile
import threading
import time
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest import mock

from trade_review_agent.auth_system import (
    AuthError,
    UpdateEmailSMTPSession,
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
    _safe_markdown_email_html,
)


class UpdateNoticeTest(unittest.TestCase):
    def test_markdown_email_renders_https_image_safely(self):
        html = _safe_markdown_email_html(
            "![新版研报](https://invest.example.test/images/update.jpg)\n\n"
            "![危险图片](javascript:alert(1))"
        )

        self.assertIn('<img src="https://invest.example.test/images/update.jpg"', html)
        self.assertIn('alt="新版研报"', html)
        self.assertNotIn('<img src="javascript:', html)
        self.assertIn("javascript:alert(1)", html)

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

    def test_long_markdown_notice_is_stored_without_silent_truncation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            admin_id = self._create_admin(db_path)
            markdown = "# 每日公告\n\n" + ("很长的正文内容。" * 3500)

            notice = create_update_notice(
                db_path,
                title="Markdown 公告",
                version="2026-08-07",
                items=[],
                admin_id=admin_id,
                summary="支持长正文",
                content_markdown=markdown,
            )

            self.assertEqual(notice["content_markdown"], markdown)
            self.assertGreater(len(notice["content_markdown"]), 20000)
            self.assertEqual(notice["items"], ["支持长正文"])

    def test_markdown_notice_derives_legacy_items_from_lists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            admin_id = self._create_admin(db_path)
            notice = create_update_notice(
                db_path,
                title="Markdown 公告",
                version="2026-08-07",
                items=[],
                admin_id=admin_id,
                content_markdown="## 更新\n- 支持 **Markdown**\n1. 查看 [使用说明](https://example.test/docs)",
            )

            self.assertEqual(notice["items"], ["支持 Markdown", "查看 使用说明"])

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
            self.assertEqual(campaign["total"], 4)
            self.assertEqual(campaign["pending"], 2)
            self.assertEqual(campaign["skipped"], 2)
            with closing(sqlite3.connect(db_path)) as conn:
                recipients = conn.execute(
                    """
                    SELECT u.username
                    FROM update_email_deliveries d
                    JOIN users u ON u.id = d.user_id
                    ORDER BY u.username
                    """
                ).fetchall()
            self.assertEqual([row[0] for row in recipients], ["noticeuser1", "noticeuser2", "noticeuser3", "noticeuser4"])
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
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    recipient_id = int(conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, update_emails_enabled,
                            password_hash, password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 1, 'hash', 'salt', 'user', 'active', ?, ?)
                        """,
                        ("pref-user", "prefuser", "pref@example.com", "PREFUSER", "2026-07-15T10:00:00+08:00"),
                    ).lastrowid)
            updated = set_update_email_preference(db_path, user_id=recipient_id, enabled=False)
            self.assertFalse(updated["update_emails_enabled"])
            notice = create_update_notice(db_path, title="Update", version="2026-07-15", items=["One"], admin_id=admin_id)
            result = publish_update_notice(
                db_path, notice_id=int(notice["id"]), send_email=True, request_id="campaign-request-002", admin_id=admin_id
            )
            self.assertEqual(result["email_campaign"]["pending"], 0)
            self.assertEqual(result["email_campaign"]["skipped"], 1)

            set_update_email_preference(db_path, user_id=recipient_id, enabled=True)
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
            self.assertEqual(smtp.call_args.args[0], "pref@example.com")
            with closing(sqlite3.connect(db_path)) as conn:
                status = conn.execute("SELECT status FROM update_email_campaigns WHERE id = ?", (campaign_id,)).fetchone()[0]
            self.assertEqual(status, "completed")

    def test_concurrent_workers_claim_each_delivery_once_and_send_in_parallel(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            admin_id = self._create_admin(db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    for index in range(1, 8):
                        conn.execute(
                            """
                            INSERT INTO users (
                                phone, username, email, email_verified, update_emails_enabled,
                                password_hash, password_salt, role, status, invite_code, created_at
                            ) VALUES (?, ?, ?, 1, 1, 'hash', 'salt', 'user', 'active', ?, ?)
                            """,
                            (
                                f"parallel-user-{index}",
                                f"paralleluser{index}",
                                f"parallel{index}@example.com",
                                f"PARALLEL{index}",
                                "2026-07-15T10:00:00+08:00",
                            ),
                        )
            notice = create_update_notice(
                db_path, title="Parallel update", version="2026-07-15", items=["One"], admin_id=admin_id
            )
            result = publish_update_notice(
                db_path,
                notice_id=int(notice["id"]),
                send_email=True,
                request_id="parallel-campaign-001",
                admin_id=admin_id,
            )
            campaign_id = int(result["email_campaign"]["id"])

            sent_ids: list[int] = []
            active = 0
            max_active = 0
            send_lock = threading.Lock()

            def sender(delivery: dict) -> None:
                nonlocal active, max_active
                with send_lock:
                    sent_ids.append(int(delivery["id"]))
                    active += 1
                    max_active = max(max_active, active)
                # Keep the send phase open long enough for other workers to overlap.
                time.sleep(0.08)
                with send_lock:
                    active -= 1

            def process_one(_index: int) -> bool:
                return process_next_update_email(db_path, sender=sender)

            with ThreadPoolExecutor(max_workers=4) as pool:
                processed = list(pool.map(process_one, range(8)))

            self.assertEqual(processed.count(True), 7)
            self.assertEqual(processed.count(False), 1)
            self.assertGreaterEqual(max_active, 2, "queue sends remained serial despite four workers")
            self.assertEqual(len(sent_ids), 7)
            self.assertEqual(Counter(sent_ids), Counter(set(sent_ids)), "a delivery was claimed more than once")
            with closing(sqlite3.connect(db_path)) as conn:
                rows = conn.execute(
                    "SELECT id, status, attempt_count FROM update_email_deliveries WHERE campaign_id = ? ORDER BY id",
                    (campaign_id,),
                ).fetchall()
            self.assertEqual(len(rows), 7)
            self.assertTrue(all(status == "sent" and attempts == 1 for _, status, attempts in rows))

    def test_legacy_admin_delivery_is_skipped_even_after_retry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auth.sqlite"
            admin_id = self._create_admin(db_path)
            notice = create_update_notice(
                db_path, title="Legacy admin delivery", version="2026-07-20", items=["One"], admin_id=admin_id
            )
            result = publish_update_notice(
                db_path,
                notice_id=int(notice["id"]),
                send_email=True,
                request_id="legacy-admin-campaign-001",
                admin_id=admin_id,
            )
            campaign_id = int(result["email_campaign"]["id"])
            with closing(sqlite3.connect(db_path)) as conn:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO update_email_deliveries (
                            campaign_id, user_id, email, status, attempt_count,
                            next_attempt_at, last_error, updated_at
                        ) VALUES (?, ?, 'notice-admin@example.com', 'failed', 3, NULL, 'legacy failure', ?)
                        """,
                        (campaign_id, admin_id, "2026-07-20T10:00:00+08:00"),
                    )
            retried = retry_update_email_campaign(db_path, campaign_id=campaign_id)
            self.assertEqual(retried["pending"], 1)

            sender = mock.Mock()
            self.assertFalse(process_next_update_email(db_path, sender=sender))
            sender.assert_not_called()
            with closing(sqlite3.connect(db_path)) as conn:
                delivery = conn.execute(
                    "SELECT status, last_error FROM update_email_deliveries WHERE campaign_id = ? AND user_id = ?",
                    (campaign_id, admin_id),
                ).fetchone()
                campaign_status = conn.execute(
                    "SELECT status FROM update_email_campaigns WHERE id = ?", (campaign_id,)
                ).fetchone()[0]
            self.assertEqual(delivery[0], "skipped")
            self.assertEqual(delivery[1], "管理员不接收产品更新邮件")
            self.assertEqual(campaign_status, "completed")

    def test_smtp_session_reuses_connection_and_keeps_one_to_recipient_per_message(self):
        server = mock.Mock()
        smtp_env = {
            "SMTP_HOST": "smtp.example.test",
            "SMTP_PORT": "465",
            "SMTP_USER": "mailer@example.test",
            "SMTP_PASSWORD": "secret",
            "SMTP_FROM": "updates@example.test",
            "SMTP_USE_SSL": "1",
        }
        with mock.patch.dict(os.environ, smtp_env, clear=False), mock.patch(
            "trade_review_agent.auth_system.smtplib.SMTP_SSL", return_value=server
        ) as connect:
            session = UpdateEmailSMTPSession()
            session.send("first@example.com", subject="First", text="One")
            session.send("second@example.com", subject="Second", text="Two")
            session.close()

        connect.assert_called_once_with("smtp.example.test", 465, timeout=15)
        server.login.assert_called_once_with("mailer@example.test", "secret")
        self.assertEqual(server.send_message.call_count, 2)
        messages = [call.args[0] for call in server.send_message.call_args_list]
        self.assertEqual([message["To"] for message in messages], ["first@example.com", "second@example.com"])
        self.assertTrue(all(message.get("Cc") is None and message.get("Bcc") is None for message in messages))
        server.quit.assert_called_once_with()

    def test_smtp_session_reconnects_once_after_disconnect(self):
        first_server = mock.Mock()
        first_server.send_message.side_effect = smtplib.SMTPServerDisconnected("connection lost")
        second_server = mock.Mock()
        smtp_env = {
            "SMTP_HOST": "smtp.example.test",
            "SMTP_PORT": "465",
            "SMTP_USER": "mailer@example.test",
            "SMTP_PASSWORD": "secret",
            "SMTP_FROM": "updates@example.test",
            "SMTP_USE_SSL": "1",
            "SMTP_DISCONNECT_COOLDOWN_SECONDS": "0",
        }
        with mock.patch.dict(os.environ, smtp_env, clear=False), mock.patch(
            "trade_review_agent.auth_system.smtplib.SMTP_SSL", side_effect=[first_server, second_server]
        ) as connect:
            session = UpdateEmailSMTPSession()
            session.send(
                "recipient@example.com",
                subject="Update",
                text="Body",
                message_id="daily-top5-c3-d17",
            )
            session.close()

        self.assertEqual(connect.call_count, 2)
        first_server.send_message.assert_called_once()
        second_server.send_message.assert_called_once()
        self.assertEqual(first_server.send_message.call_args.args[0]["To"], "recipient@example.com")
        self.assertEqual(second_server.send_message.call_args.args[0]["To"], "recipient@example.com")
        self.assertEqual(
            first_server.send_message.call_args.args[0]["Message-ID"],
            second_server.send_message.call_args.args[0]["Message-ID"],
        )
        first_server.quit.assert_called_once_with()
        second_server.quit.assert_called_once_with()

    def test_smtp_disconnect_cooldown_is_shared_across_workers(self):
        UpdateEmailSMTPSession._cooldown_until = 0.0
        with mock.patch.dict(os.environ, {"SMTP_DISCONNECT_COOLDOWN_SECONDS": "7"}, clear=False), mock.patch(
            "trade_review_agent.auth_system.time.monotonic", side_effect=[100.0, 102.0]
        ), mock.patch("trade_review_agent.auth_system.time.sleep") as sleep:
            UpdateEmailSMTPSession._record_disconnect()
            UpdateEmailSMTPSession._wait_for_disconnect_cooldown()

        sleep.assert_called_once_with(5.0)
        UpdateEmailSMTPSession._cooldown_until = 0.0


if __name__ == "__main__":
    unittest.main()
