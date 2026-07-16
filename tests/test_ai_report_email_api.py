from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import init_auth_db


class AIReportEmailIngestionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "auth.sqlite"
        self.market_root = self.root / "market-day"
        self.research_root = self.root / "ai-research"
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
            "market_date": "2026-07-16",
            "report": {
                "marketDate": "2026-07-16",
                "oneLineConclusion": "科技主线最强，成交仍需确认",
                "marketMood": {"summary": "修复", "score": 7},
                "mainline": {"name": "半导体", "reason": "成交领先"},
                "watchPoints": ["观察次日承接"],
            },
        }
        self.research_payload = {
            "run_id": "research-api-run",
            "research_date": "2026-07-16",
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
            "market_date": "2026-07-16",
            "report": {"oneLineConclusion": "只有结论，尚无分析明细"},
        }
        incomplete_research = {
            "run_id": "research-incomplete",
            "research_date": "2026-07-16",
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
            "market_date": "2026-07-16",
            "report": {
                "marketDate": "2026-07-16",
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
                market_date="2026-07-16",
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
            "market_date": "2026-07-16",
            "report": {
                "marketDate": "2026-07-16",
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
                market_date="2026-07-16",
                request_id="internal-failure-request",
                user_id=1,
            )

        status = json.loads((run_dir / simple_api.REPORT_STATUS_NAME).read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "done")
        self.assertTrue((run_dir / simple_api.MARKET_DAY_REPORT_NAME).is_file())
        self.assertFalse(simple_api.UPDATE_EMAIL_QUEUE_WAKE.is_set())
        write_error.assert_called_once()
        self.assertTrue(write_error.call_args.kwargs["recovered"])


if __name__ == "__main__":
    unittest.main()
