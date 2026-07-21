from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import CN_TZ, create_ai_report_email_campaign, init_auth_db
from tests.test_ai_report_email import market_day_report


class AIReportEmailIngestionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "auth.sqlite"
        self.market_root = self.root / "market-day"
        self.research_root = self.root / "ai-research"
        self.report_date = datetime.now(CN_TZ).date().isoformat()
        init_auth_db(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        phone, username, email, email_verified, update_emails_enabled,
                        password_hash, password_salt, role, status, invite_code, created_at
                    ) VALUES ('report-email-user', 'report-email-user', 'report@example.test', 1, 1,
                              'hash', 'salt', 'user', 'active', 'REPORTEMAIL', '2026-07-16T08:00:00+08:00')
                    """
                )
        self.market_payload = {
            "run_id": "market-api-run",
            "market_date": self.report_date,
            "report": {
                "marketDate": self.report_date,
                "oneLineConclusion": "科技主线最强，成交仍需确认",
                "marketMood": {"summary": "修复", "score": 7},
                "mainline": {"name": "半导体", "reason": "成交领先"},
                "watchPoints": ["观察次日承接"],
            },
        }
        self.research_payload = {
            "run_id": "research-api-run",
            "research_date": self.report_date,
            "title": "A股盘前重要信息",
            "summary": "海外通胀与原油信息已整理",
            "markdown": "# 盘前结论\n\n关注 CPI、黄金与原油。",
            "decision_cards": [{"title": "通胀数据", "trigger": "CPI 超预期"}],
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _handler(self, *, path: str, secret_header: str, payload: dict) -> tuple[object, list[tuple[int, dict]]]:
        responses: list[tuple[int, dict]] = []
        handler = object.__new__(simple_api.TradeReviewHandler)
        handler.path = path
        handler.command = "POST"
        handler.client_address = ("127.0.0.1", 12345)
        handler.headers = {secret_header: "secret", "user-agent": "qa-test"}
        handler._request_id = "qa-request"
        handler._read_json_body = lambda: payload
        handler._json = lambda body, status=200: responses.append((status, body))
        return handler, responses

    def test_market_day_and_research_ingestion_create_one_campaign_on_replay(self) -> None:
        cases = (
            (
                "market_day", "/api/market-day/reports/push", "x-market-day-secret", self.market_payload,
                "MARKET_DAY_WEBHOOK_SECRET", self.market_root, "_receive_market_day_report_push",
                simple_api.MARKET_DAY_REPORT_NAME,
            ),
            (
                "ai_research", "/api/ai-research/reports", "x-ai-research-secret", self.research_payload,
                "AI_RESEARCH_WEBHOOK_SECRET", self.research_root, "_receive_ai_research_report",
                simple_api.AI_RESEARCH_REPORT_NAME,
            ),
        )
        for report_type, path, header, payload, env_key, report_root, method_name, filename in cases:
            with self.subTest(report_type=report_type):
                handler, responses = self._handler(path=path, secret_header=header, payload=payload)
                dir_patch = "MARKET_DAY_REPORT_DIR" if report_type == "market_day" else "AI_RESEARCH_REPORT_DIR"
                simple_api.UPDATE_EMAIL_QUEUE_WAKE.clear()
                with (
                    patch.object(simple_api, "AUTH_DB", self.db_path),
                    patch.object(simple_api, dir_patch, report_root),
                    patch.dict("os.environ", {env_key: "secret"}, clear=False),
                ):
                    getattr(handler, method_name)()
                    getattr(handler, method_name)()

                self.assertEqual([item[0] for item in responses], [202, 202])
                self.assertTrue(responses[0][1]["success"])
                self.assertTrue(responses[0][1]["stored"])
                self.assertEqual(responses[0][1]["run_id"], str(payload["run_id"]))
                self.assertIsNotNone(responses[0][1]["email_campaign"])
                self.assertEqual(
                    responses[0][1]["email_campaign"]["id"],
                    responses[1][1]["email_campaign"]["id"],
                )
                self.assertTrue(simple_api.UPDATE_EMAIL_QUEUE_WAKE.is_set())
                run_id = str(payload["run_id"])
                self.assertTrue((report_root / run_id / filename).is_file())
                with closing(sqlite3.connect(self.db_path)) as conn:
                    self.assertEqual(conn.execute(
                        "SELECT COUNT(*) FROM ai_report_email_campaigns WHERE report_type = ? AND run_id = ?",
                        (report_type, run_id),
                    ).fetchone()[0], 1)

    def test_campaign_failure_never_blocks_report_publication_for_either_ingestion_path(self) -> None:
        cases = (
            (
                "market_day", "/api/market-day/reports/push", "x-market-day-secret", self.market_payload,
                "MARKET_DAY_WEBHOOK_SECRET", self.market_root, "_receive_market_day_report_push",
                simple_api.MARKET_DAY_REPORT_NAME,
            ),
            (
                "ai_research", "/api/ai-research/reports", "x-ai-research-secret", self.research_payload,
                "AI_RESEARCH_WEBHOOK_SECRET", self.research_root, "_receive_ai_research_report",
                simple_api.AI_RESEARCH_REPORT_NAME,
            ),
        )
        for report_type, path, header, payload, env_key, report_root, method_name, filename in cases:
            with self.subTest(report_type=report_type):
                handler, responses = self._handler(path=path, secret_header=header, payload=payload)
                dir_patch = "MARKET_DAY_REPORT_DIR" if report_type == "market_day" else "AI_RESEARCH_REPORT_DIR"
                simple_api.UPDATE_EMAIL_QUEUE_WAKE.clear()
                with (
                    patch.object(simple_api, "AUTH_DB", self.db_path),
                    patch.object(simple_api, dir_patch, report_root),
                    patch.dict("os.environ", {env_key: "secret"}, clear=False),
                    patch.object(simple_api, "create_ai_report_email_campaign", side_effect=RuntimeError("queue unavailable")),
                    patch.object(simple_api, "_write_api_error") as write_error,
                ):
                    getattr(handler, method_name)()

                self.assertEqual(responses[0][0], 202)
                self.assertTrue(responses[0][1]["ok"])
                self.assertIsNone(responses[0][1]["email_campaign"])
                self.assertTrue((report_root / str(payload["run_id"]) / filename).is_file())
                self.assertFalse(simple_api.UPDATE_EMAIL_QUEUE_WAKE.is_set())
                write_error.assert_called_once()
                self.assertTrue(write_error.call_args.kwargs["recovered"])

    def test_incomplete_reports_are_published_without_creating_a_campaign(self) -> None:
        incomplete_market = {
            "run_id": "market-incomplete",
            "market_date": self.report_date,
            "report": {"oneLineConclusion": "只有结论，尚无分析明细"},
        }
        incomplete_research = {
            "run_id": "research-incomplete",
            "research_date": self.report_date,
            "title": "只有标题",
            "summary": "只有摘要",
        }
        cases = (
            (
                "market_day", "/api/market-day/reports/push", "x-market-day-secret", incomplete_market,
                "MARKET_DAY_WEBHOOK_SECRET", self.market_root, "_receive_market_day_report_push",
                simple_api.MARKET_DAY_REPORT_NAME,
            ),
            (
                "ai_research", "/api/ai-research/reports", "x-ai-research-secret", incomplete_research,
                "AI_RESEARCH_WEBHOOK_SECRET", self.research_root, "_receive_ai_research_report",
                simple_api.AI_RESEARCH_REPORT_NAME,
            ),
        )
        for report_type, path, header, payload, env_key, report_root, method_name, filename in cases:
            with self.subTest(report_type=report_type):
                handler, responses = self._handler(path=path, secret_header=header, payload=payload)
                dir_patch = "MARKET_DAY_REPORT_DIR" if report_type == "market_day" else "AI_RESEARCH_REPORT_DIR"
                with (
                    patch.object(simple_api, "AUTH_DB", self.db_path),
                    patch.object(simple_api, dir_patch, report_root),
                    patch.dict("os.environ", {env_key: "secret"}, clear=False),
                    patch.object(simple_api, "_write_api_error") as write_error,
                ):
                    getattr(handler, method_name)()

                self.assertEqual(responses[0][0], 202)
                self.assertIsNone(responses[0][1]["email_campaign"])
                self.assertTrue((report_root / str(payload["run_id"]) / filename).is_file())
                write_error.assert_called_once()
                with closing(sqlite3.connect(self.db_path)) as conn:
                    self.assertEqual(conn.execute(
                        "SELECT COUNT(*) FROM ai_report_email_campaigns WHERE report_type = ? AND run_id = ?",
                        (report_type, str(payload["run_id"])),
                    ).fetchone()[0], 0)

    def test_internal_market_day_generation_creates_campaign_after_report_is_done(self) -> None:
        run_id = "internal-market-run"
        run_dir = self.market_root / run_id
        generated = {
            "market_date": self.report_date,
            "report": {
                "marketDate": self.report_date,
                "oneLineConclusion": "内部生成完成",
                "mainline": {"name": "算力", "reason": "成交领先"},
                "watchPoints": ["观察承接"],
            },
        }
        simple_api.UPDATE_EMAIL_QUEUE_WAKE.clear()
        with (
            patch.object(simple_api, "AUTH_DB", self.db_path),
            patch.object(simple_api, "MARKET_DAY_REPORT_DIR", self.market_root),
            patch.object(simple_api, "run_market_day_agent", return_value=generated),
        ):
            simple_api._run_market_day_generation_task(
                run_id=run_id,
                run_dir=run_dir,
                market_date=self.report_date,
                request_id="internal-request",
                user_id=1,
            )

        status = json.loads((run_dir / simple_api.REPORT_STATUS_NAME).read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "done")
        self.assertTrue((run_dir / simple_api.MARKET_DAY_REPORT_NAME).is_file())
        self.assertTrue(simple_api.UPDATE_EMAIL_QUEUE_WAKE.is_set())
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM ai_report_email_campaigns WHERE report_type = 'market_day' AND run_id = ?",
                (run_id,),
            ).fetchone()[0], 1)

    def test_internal_generation_email_failure_does_not_change_done_report_status(self) -> None:
        run_id = "internal-market-email-failure"
        run_dir = self.market_root / run_id
        generated = {
            "market_date": self.report_date,
            "report": {
                "marketDate": self.report_date,
                "oneLineConclusion": "报告仍应成功",
                "mainline": {"name": "机器人"},
            },
        }
        simple_api.UPDATE_EMAIL_QUEUE_WAKE.clear()
        with (
            patch.object(simple_api, "AUTH_DB", self.db_path),
            patch.object(simple_api, "MARKET_DAY_REPORT_DIR", self.market_root),
            patch.object(simple_api, "run_market_day_agent", return_value=generated),
            patch.object(simple_api, "create_ai_report_email_campaign", side_effect=RuntimeError("queue unavailable")),
            patch.object(simple_api, "_write_api_error") as write_error,
        ):
            simple_api._run_market_day_generation_task(
                run_id=run_id,
                run_dir=run_dir,
                market_date=self.report_date,
                request_id="internal-failure-request",
                user_id=1,
            )

        status = json.loads((run_dir / simple_api.REPORT_STATUS_NAME).read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "done")
        self.assertTrue((run_dir / simple_api.MARKET_DAY_REPORT_NAME).is_file())
        self.assertFalse(simple_api.UPDATE_EMAIL_QUEUE_WAKE.is_set())
        write_error.assert_called_once()
        self.assertTrue(write_error.call_args.kwargs["recovered"])


class AIReportEmailAdminApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "auth.sqlite"
        self.report_date = datetime.now(CN_TZ).date().isoformat()
        init_auth_db(self.db_path)
        now = "2026-07-16T09:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                for phone, username, email, role, token in (
                    ("report-admin", "report-admin", "admin@example.test", "admin", "admin-token"),
                    ("report-user", "report-user", "user@example.test", "user", "user-token"),
                    ("report-extra", "report-extra", "extra@example.test", "user", ""),
                ):
                    user_id = int(conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, update_emails_enabled,
                            password_hash, password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 1, 'hash', 'salt', ?, 'active', ?, ?)
                        """,
                        (phone, username, email, role, username.upper(), now),
                    ).lastrowid)
                    if token:
                        conn.execute(
                            "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2999-01-01', ?)",
                            (token, user_id, now),
                        )
        self.db_patch = patch.object(simple_api, "AUTH_DB", self.db_path)
        self.db_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        token: str = "",
        payload: dict | None = None,
    ) -> tuple[int, dict]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self.base_url + path, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_dashboard_exposes_campaign_and_retry_requires_admin(self) -> None:
        campaign = create_ai_report_email_campaign(
            self.db_path,
            report_type="market_day",
            report=market_day_report(run_id="market-dashboard-run", report_date=self.report_date),
        )
        campaign_id = int(campaign["id"])
        next_retry_at = "2026-07-16T19:15:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE ai_report_email_deliveries
                    SET status = 'failed', attempt_count = 3, next_attempt_at = NULL
                    WHERE campaign_id = ? AND email = 'user@example.test'
                    """,
                    (campaign_id,),
                )
                conn.execute(
                    """
                    UPDATE ai_report_email_deliveries
                    SET next_attempt_at = ?
                    WHERE campaign_id = ? AND email = 'extra@example.test'
                    """,
                    (next_retry_at, campaign_id),
                )
                conn.execute(
                    "UPDATE ai_report_email_campaigns SET status = 'failed' WHERE id = ?",
                    (campaign_id,),
                )

        dashboard_status, dashboard = self.request("/api/admin/dashboard?days=30", token="admin-token")
        self.assertEqual(dashboard_status, 200)
        self.assertEqual(dashboard["ai_report_email_failed_count"], 1)
        self.assertEqual(dashboard["ai_report_email_campaigns"][0]["report_type"], "market_day")
        self.assertEqual(dashboard["ai_report_email_campaigns"][0]["failed"], 1)
        self.assertEqual(dashboard["ai_report_email_campaigns"][0]["next_retry_at"], next_retry_at)

        forbidden_status, _ = self.request(
            f"/api/admin/ai-report-email-campaigns/{campaign_id}/retry",
            method="POST",
            token="user-token",
            payload={},
        )
        simple_api.UPDATE_EMAIL_QUEUE_WAKE.clear()
        retry_status, retried = self.request(
            f"/api/admin/ai-report-email-campaigns/{campaign_id}/retry",
            method="POST",
            token="admin-token",
            payload={},
        )
        self.assertEqual(forbidden_status, 403)
        self.assertEqual(retry_status, 200)
        self.assertEqual(retried["email_campaign"]["pending"], 2)
        self.assertEqual(retried["email_campaign"]["failed"], 0)
        self.assertTrue(simple_api.UPDATE_EMAIL_QUEUE_WAKE.is_set())

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT email, status, attempt_count, next_attempt_at
                FROM ai_report_email_deliveries
                WHERE campaign_id = ?
                ORDER BY email
                """,
                (campaign_id,),
            ).fetchall()
        by_email = {str(row["email"]): row for row in rows}
        self.assertEqual(str(by_email["user@example.test"]["status"]), "pending")
        self.assertEqual(int(by_email["user@example.test"]["attempt_count"]), 0)
        self.assertEqual(str(by_email["extra@example.test"]["next_attempt_at"]), next_retry_at)


if __name__ == "__main__":
    unittest.main()
