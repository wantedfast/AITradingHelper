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
from trade_review_agent.watch.alerts import AlertPlan, load_plans, save_plans


class UserHistoryIsolationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "auth.sqlite"
        self.report_root = self.root / "reports"
        self.plan_path = self.root / "alert_plans.json"
        self.seen_path = self.root / "seen.json"
        self.report_root.mkdir()
        init_auth_db(self.db_path)
        self.user_ids = self._create_users()

        self._write_report("user-one-report", self.user_ids[0])
        self._write_report("user-two-report", self.user_ids[1])
        self._write_report("legacy-report", 0)
        save_plans(
            self.plan_path,
            [
                AlertPlan(plan_id="plan-one", code="000001", name="甲", action="观察", thesis="测试", user_id=self.user_ids[0]),
                AlertPlan(plan_id="plan-two", code="000002", name="乙", action="观察", thesis="测试", user_id=self.user_ids[1]),
                AlertPlan(plan_id="legacy-plan", code="000003", name="旧", action="观察", thesis="测试"),
            ],
        )
        self.seen_path.write_text(
            json.dumps({"plan-one:breakout:1": "one", "plan-two:breakout:1": "two"}),
            encoding="utf-8",
        )

        self.stack = ExitStack()
        self.stack.enter_context(patch.object(simple_api, "AUTH_DB", self.db_path))
        self.stack.enter_context(patch.object(simple_api, "REPORT_DIR", self.report_root))
        self.stack.enter_context(patch.object(simple_api, "ALERT_PLANS", self.plan_path))
        self.stack.enter_context(patch.object(simple_api, "WATCH_SEEN_EVENTS", self.seen_path))
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

    def _create_users(self) -> list[int]:
        ids: list[int] = []
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                for index in (1, 2):
                    user_id = int(
                        conn.execute(
                            """
                            INSERT INTO users (
                                phone, username, email, email_verified, password_hash,
                                password_salt, role, status, invite_code, created_at
                            ) VALUES (?, ?, ?, 1, 'hash', 'salt', 'user', 'active', ?, '2026-07-15')
                            """,
                            (f"history-user-{index}", f"history{index}", f"history{index}@example.com", f"HISTORY{index}"),
                        ).lastrowid
                    )
                    ids.append(user_id)
                    conn.execute(
                        "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', '2026-07-15')",
                        (f"user-{index}-token", user_id),
                    )
        return ids

    def _write_report(self, run_id: str, user_id: int) -> None:
        run_dir = self.report_root / run_id
        run_dir.mkdir()
        (run_dir / "report.html").write_text("<html>private report</html>", encoding="utf-8")
        (run_dir / simple_api.RESEARCH_PRESENTER_NAME).write_text(
            json.dumps({"run_id": run_id}), encoding="utf-8"
        )
        (run_dir / simple_api.REPORT_STATUS_NAME).write_text(
            json.dumps({"run_id": run_id, "status": "done", "stage": "done", "user_id": user_id}),
            encoding="utf-8",
        )

    def request(self, path: str, *, token: str = "user-1-token", method: str = "GET") -> tuple[int, object]:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"} if token else {}
        data = b"{}" if method == "POST" else None
        request = Request(self.base_url + path, headers=headers, method=method, data=data)
        try:
            with urlopen(request, timeout=3) as response:
                raw = response.read()
                return response.status, json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw
        except HTTPError as exc:
            with exc:
                raw = exc.read()
                return exc.code, json.loads(raw) if raw else {}

    def test_review_history_and_files_are_owner_scoped(self) -> None:
        status, payload = self.request("/api/reports?limit=30")
        self.assertEqual(status, 200)
        self.assertEqual([item["run_id"] for item in payload["reports"]], ["user-one-report"])

        own_status, _ = self.request(f"/api/reports/user-one-report/{simple_api.RESEARCH_PRESENTER_NAME}")
        other_status, _ = self.request(f"/api/reports/user-two-report/{simple_api.RESEARCH_PRESENTER_NAME}")
        legacy_status, _ = self.request(f"/api/reports/legacy-report/{simple_api.RESEARCH_PRESENTER_NAME}")
        legacy_ack_status, _ = self.request("/api/reports/legacy-report/ack", method="POST")
        legacy_after_ack_status, _ = self.request(
            f"/api/reports/legacy-report/{simple_api.RESEARCH_PRESENTER_NAME}"
        )
        anonymous_status, _ = self.request(
            f"/api/reports/user-one-report/{simple_api.RESEARCH_PRESENTER_NAME}", token=""
        )
        self.assertEqual(own_status, 200)
        self.assertEqual(other_status, 404)
        self.assertEqual(legacy_status, 404)
        self.assertEqual(legacy_ack_status, 404)
        self.assertEqual(legacy_after_ack_status, 404)
        self.assertEqual(anonymous_status, 401)

    def test_watch_history_and_clear_are_owner_scoped(self) -> None:
        status, payload = self.request("/api/watch/plans")
        self.assertEqual(status, 200)
        self.assertEqual([plan["plan_id"] for plan in payload["plans"]], ["plan-one"])

        clear_status, payload = self.request("/api/watch/plans/clear", method="POST")
        self.assertEqual(clear_status, 200)
        self.assertEqual(payload["plans"], [])
        self.assertEqual([plan.plan_id for plan in load_plans(self.plan_path)], ["plan-two", "legacy-plan"])
        seen = json.loads(self.seen_path.read_text(encoding="utf-8"))
        self.assertNotIn("plan-one:breakout:1", seen)
        self.assertIn("plan-two:breakout:1", seen)


if __name__ == "__main__":
    unittest.main()
