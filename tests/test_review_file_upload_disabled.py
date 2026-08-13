from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import ExitStack, closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import init_auth_db


class ReviewFileUploadDisabledTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "auth.sqlite"
        self.report_root = self.root / "reports"
        self.upload_root = self.root / "uploads"
        self.report_root.mkdir()
        init_auth_db(self.db_path)

        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            user_id = int(
                conn.execute(
                    """
                    INSERT INTO users (
                        phone, username, email, email_verified, password_hash,
                        password_salt, role, status, invite_code, created_at
                    ) VALUES ('review-admin', 'review-admin', 'review@example.test', 1,
                              'hash', 'salt', 'admin', 'active', 'REVIEWADMIN', '2026-08-12')
                    """
                ).lastrowid
            )
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', '2026-08-12')",
                ("review-admin-token", user_id),
            )

        self.started_tasks: list[dict] = []
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(simple_api, "AUTH_DB", self.db_path))
        self.stack.enter_context(patch.object(simple_api, "REPORT_DIR", self.report_root))
        self.stack.enter_context(patch.object(simple_api, "UPLOAD_DIR", self.upload_root))
        self.stack.enter_context(
            patch.object(simple_api, "_start_report_generation_task", side_effect=lambda **kwargs: self.started_tasks.append(kwargs))
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.stack.close()
        self.temp_dir.cleanup()

    def _post_multipart(self, parts: list[tuple[str, str, bytes | None]]) -> tuple[int, dict]:
        boundary = "review-upload-boundary"
        body = bytearray()
        for name, value, file_content in parts:
            body.extend(f"--{boundary}\r\n".encode())
            if file_content is None:
                body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
            else:
                body.extend(
                    f'Content-Disposition: form-data; name="{name}"; filename="{value}"\r\n'.encode()
                )
                body.extend(b"Content-Type: text/csv\r\n\r\n")
                body.extend(file_content)
                body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        request = Request(
            self.base_url + "/api/reports",
            data=bytes(body),
            method="POST",
            headers={
                "Authorization": "Bearer review-admin-token",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_legacy_file_upload_is_rejected_without_writing_or_starting_a_task(self) -> None:
        status, payload = self._post_multipart(
            [("file", "trades.csv", b"stock_name,trade_date\nExample,2026-08-12\n")]
        )

        self.assertEqual(status, 410)
        self.assertEqual(payload["code"], "AI_REVIEW_FILE_UPLOAD_DISABLED")
        self.assertIn("暂不可用", payload["error"])
        self.assertEqual(self.started_tasks, [])
        self.assertFalse(self.upload_root.exists())
        self.assertEqual(list(self.report_root.iterdir()), [])

    def test_manual_trade_entry_remains_available(self) -> None:
        status, payload = self._post_multipart(
            [
                ("manual_trade", "1", None),
                ("manual_stock_name", "东材科技", None),
                ("manual_trade_at", "2026-08-12T09:25:30", None),
                ("manual_price", "58.71", None),
                ("manual_side", "buy", None),
            ]
        )

        self.assertEqual(status, 202)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(len(self.started_tasks), 1)
        self.assertIsNone(self.started_tasks[0]["upload_path"])
        self.assertEqual(self.started_tasks[0]["manual_trade"]["name"], "东材科技")


if __name__ == "__main__":
    unittest.main()
