from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from trade_review_agent.auth_system import init_auth_db, process_bounce_imap_inbox


class _FakeImapClient:
    def __init__(self, mailbox: dict[str, bytes], unseen: list[str]) -> None:
        self.mailbox = mailbox
        self.unseen = unseen
        self.store_calls: list[tuple[str, str, str, str]] = []
        self.logged_in = False
        self.logged_out = False

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        self.logged_in = bool(username and password)
        return ("OK", [b"logged-in"])

    def select(self, mailbox: str) -> tuple[str, list[bytes]]:
        return ("OK", [b"1"])

    def uid(self, command: str, *args: str) -> tuple[str, list[object]]:
        upper = command.upper()
        if upper == "SEARCH":
            return ("OK", [" ".join(self.unseen).encode("utf-8")])
        if upper == "FETCH":
            uid = args[0]
            raw = self.mailbox[uid]
            return ("OK", [(b"1 (RFC822 {123})", raw), b")"])
        if upper == "STORE":
            self.store_calls.append((command, args[0], args[1], args[2]))
            return ("OK", [b"stored"])
        raise AssertionError(f"unexpected IMAP command: {command} {args}")

    def logout(self) -> tuple[str, list[bytes]]:
        self.logged_out = True
        return ("BYE", [b"logout"])


def _dsn_message(*, subject: str, diagnostic: str, recipient: str, sender: str = "Mailer-Daemon <mailer-daemon@gmail.com>", message_id: str = "<dsn-1@example.test>") -> bytes:
    return (
        "From: " + sender + "\r\n"
        + "Subject: " + subject + "\r\n"
        + "Message-ID: " + message_id + "\r\n"
        + "Auto-Submitted: auto-generated\r\n"
        + "MIME-Version: 1.0\r\n"
        + 'Content-Type: multipart/report; report-type=delivery-status; boundary="BOUND"\r\n'
        + "\r\n"
        + "--BOUND\r\n"
        + "Content-Type: text/plain; charset=utf-8\r\n"
        + "\r\n"
        + diagnostic
        + "\r\n"
        + "--BOUND\r\n"
        + "Content-Type: message/delivery-status\r\n"
        + "\r\n"
        + "Reporting-MTA: dns; gmail.com\r\n"
        + "\r\n"
        + f"Final-Recipient: rfc822; {recipient}\r\n"
        + "Action: failed\r\n"
        + "Status: 5.7.1\r\n"
        + f"Diagnostic-Code: smtp; {diagnostic}\r\n"
        + "\r\n"
        + "--BOUND--\r\n"
    ).encode("utf-8")


def _ordinary_message() -> bytes:
    return (
        "From: alerts@example.test\r\n"
        + "Subject: regular update\r\n"
        + "Message-ID: <regular-1@example.test>\r\n"
        + "MIME-Version: 1.0\r\n"
        + "Content-Type: text/plain; charset=utf-8\r\n"
        + "\r\n"
        + "hello\r\n"
    ).encode("utf-8")


class BounceImapWorkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        init_auth_db(self.db_path)
        self.env = mock.patch.dict(
            os.environ,
            {
                "BOUNCE_IMAP_ENABLED": "1",
                "SMTP_USER": "sender@gmail.com",
                "SMTP_PASSWORD": "app-password",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp_dir.cleanup()

    def test_explicit_block_dsn_suppresses_and_archives_message(self) -> None:
        client = _FakeImapClient(
            mailbox={
                "101": _dsn_message(
                    subject="Delivery Status Notification (Failure)",
                    diagnostic="550 5.7.1 mail is rejected by recipients because user in blacklist",
                    recipient="Blocked@Example.test",
                )
            },
            unseen=["101"],
        )

        result = process_bounce_imap_inbox(self.db_path, client_factory=lambda _host, _port: client)

        self.assertEqual(result, {"checked": 1, "suppressed": 1, "archived": 1})
        self.assertTrue(client.logged_in)
        self.assertTrue(client.logged_out)
        self.assertEqual(
            client.store_calls,
            [
                ("STORE", "101", "+FLAGS", "(\\Seen)"),
                ("STORE", "101", "-X-GM-LABELS", "(\\Inbox)"),
            ],
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            suppression = conn.execute(
                "SELECT email, source_kind FROM email_suppressions"
            ).fetchone()
            event = conn.execute(
                "SELECT mailbox_uid, message_id, status, suppressed_email FROM email_bounce_events"
            ).fetchone()
        self.assertEqual(suppression, ("blocked@example.test", "bounce_imap"))
        self.assertEqual(event, ("101", "<dsn-1@example.test>", "suppressed", "blocked@example.test"))

    def test_temporary_or_unknown_dsn_does_not_suppress_or_archive(self) -> None:
        client = _FakeImapClient(
            mailbox={
                "102": _dsn_message(
                    subject="Delivery Status Notification (Failure)",
                    diagnostic="550 5.1.1 user unknown",
                    recipient="unknown@example.test",
                    message_id="<dsn-2@example.test>",
                )
            },
            unseen=["102"],
        )

        result = process_bounce_imap_inbox(self.db_path, client_factory=lambda _host, _port: client)

        self.assertEqual(result, {"checked": 1, "suppressed": 0, "archived": 0})
        self.assertEqual(client.store_calls, [])
        with closing(sqlite3.connect(self.db_path)) as conn:
            suppression_count = conn.execute("SELECT COUNT(*) FROM email_suppressions").fetchone()[0]
            event = conn.execute(
                "SELECT mailbox_uid, status, suppressed_email FROM email_bounce_events"
            ).fetchone()
        self.assertEqual(suppression_count, 0)
        self.assertEqual(event, ("102", "ignored", ""))

    def test_non_system_unseen_email_is_left_untouched(self) -> None:
        client = _FakeImapClient(mailbox={"103": _ordinary_message()}, unseen=["103"])

        result = process_bounce_imap_inbox(self.db_path, client_factory=lambda _host, _port: client)

        self.assertEqual(result, {"checked": 0, "suppressed": 0, "archived": 0})
        self.assertEqual(client.store_calls, [])
        with closing(sqlite3.connect(self.db_path)) as conn:
            event_count = conn.execute("SELECT COUNT(*) FROM email_bounce_events").fetchone()[0]
        self.assertEqual(event_count, 0)

    def test_message_uid_and_message_id_keep_processing_idempotent(self) -> None:
        mailbox = {
            "104": _dsn_message(
                subject="Delivery Status Notification (Failure)",
                diagnostic="550 5.7.1 blocked by recipient",
                recipient="blocked@example.test",
                message_id="<dsn-repeat@example.test>",
            )
        }
        first = _FakeImapClient(mailbox=mailbox, unseen=["104"])
        second = _FakeImapClient(mailbox=mailbox, unseen=["104"])

        first_result = process_bounce_imap_inbox(self.db_path, client_factory=lambda _host, _port: first)
        second_result = process_bounce_imap_inbox(self.db_path, client_factory=lambda _host, _port: second)

        self.assertEqual(first_result, {"checked": 1, "suppressed": 1, "archived": 1})
        self.assertEqual(second_result, {"checked": 1, "suppressed": 0, "archived": 1})
        with closing(sqlite3.connect(self.db_path)) as conn:
            suppression_count = conn.execute("SELECT COUNT(*) FROM email_suppressions").fetchone()[0]
            event_count = conn.execute("SELECT COUNT(*) FROM email_bounce_events").fetchone()[0]
        self.assertEqual(suppression_count, 1)
        self.assertEqual(event_count, 1)


if __name__ == "__main__":
    unittest.main()
