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


class FeedbackAttachmentApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "auth.sqlite"
        self.upload_root = self.root / "uploads" / "feedback"
        init_auth_db(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            for role, token in (("user", "user-token"), ("admin", "admin-token")):
                user_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 'hash', 'salt', ?, 'active', ?, '2026-08-26')
                        """,
                        (f"feedback-{role}", f"feedback-{role}", f"{role}@example.test", role, f"INVITE{role.upper()}"),
                    ).lastrowid
                )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', '2026-08-26')",
                    (token, user_id),
                )

        self.stack = ExitStack()
        self.stack.enter_context(patch.object(simple_api, "AUTH_DB", self.db_path))
        self.stack.enter_context(patch.object(simple_api, "FEEDBACK_UPLOAD_DIR", self.upload_root))
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

    def _multipart(self, *, content: str, filename: str = "screen.png", data: bytes | None = None) -> tuple[int, dict]:
        boundary = "feedback-boundary"
        body = bytearray()
        for name, value in (("category", "页面体验"), ("content", content)):
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        if data is not None:
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
            body.extend(b"Content-Type: image/png\r\n\r\n")
            body.extend(data)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        request = Request(
            self.base_url + "/api/feedback",
            data=bytes(body),
            method="POST",
            headers={
                "Authorization": "Bearer user-token",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_image_is_saved_exactly_and_only_admin_can_read_it(self) -> None:
        image = b"\x89PNG\r\n\x1a\nfeedback-image-content\r\n"
        status, payload = self._multipart(content="TOP5 页面无法加载，请看截图", data=image)
        self.assertEqual(status, 200)
        feedback_id = int(payload["feedback"]["id"])

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
            self.assertEqual(row["attachment_name"], "screen.png")
            self.assertEqual(row["attachment_mime"], "image/png")
            self.assertEqual(row["attachment_size"], len(image))
            stored = Path(row["attachment_path"])
            self.assertEqual(stored.read_bytes(), image)
            self.assertEqual(stored.parent, self.upload_root)

        user_request = Request(
            f"{self.base_url}/api/admin/feedback/{feedback_id}/attachment",
            headers={"Authorization": "Bearer user-token"},
        )
        with self.assertRaises(HTTPError) as denied:
            urlopen(user_request, timeout=3)
        self.assertEqual(denied.exception.code, 403)
        denied.exception.close()

        admin_request = Request(
            f"{self.base_url}/api/admin/feedback/{feedback_id}/attachment",
            headers={"Authorization": "Bearer admin-token"},
        )
        with urlopen(admin_request, timeout=3) as response:
            self.assertEqual(response.headers.get_content_type(), "image/png")
            self.assertEqual(response.read(), image)

        list_request = Request(
            f"{self.base_url}/api/admin/feedback",
            headers={"Authorization": "Bearer admin-token"},
        )
        with urlopen(list_request, timeout=3) as response:
            item = json.loads(response.read())["items"][0]
        self.assertEqual(item["attachment_url"], f"/api/admin/feedback/{feedback_id}/attachment")
        self.assertNotIn("attachment_path", item)

    def test_non_image_and_oversize_uploads_are_rejected_without_files(self) -> None:
        status, payload = self._multipart(content="这是一条带无效附件的反馈", filename="not-image.txt", data=b"plain text")
        self.assertEqual(status, 400)
        self.assertIn("截图格式不支持", payload["error"])

        status, payload = self._multipart(
            content="这是一条附件过大的反馈",
            data=b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024),
        )
        self.assertEqual(status, 413)
        self.assertIn("5MB", payload["error"])
        self.assertFalse(self.upload_root.exists())

    def test_json_feedback_remains_backward_compatible(self) -> None:
        request = Request(
            self.base_url + "/api/feedback",
            data=json.dumps({"category": "产品建议", "content": "继续支持原来的纯文字反馈"}).encode(),
            method="POST",
            headers={"Authorization": "Bearer user-token", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 200)
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT attachment_path FROM feedback ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNone(row[0])


if __name__ == "__main__":
    unittest.main()
