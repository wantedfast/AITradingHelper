import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trade_review_agent.auth_system import AuthError
from trade_review_agent.api import simple_api


class MarketDayApiHelpersTest(unittest.TestCase):
    def _push_payload(self, run_id: str = "codex-2026-07-10") -> dict:
        return {
            "run_id": run_id,
            "market_date": "2026-07-10",
            "report": {
                "oneLineConclusion": "科技主线最强，成交与广度仍需确认。",
                "marketMood": {"summary": "强修复后的分化", "score": 7},
                "mainline": {"name": "半导体", "reason": "成交和涨停结构领先"},
                "strongestStocks": [],
                "secondaryLines": [],
                "fakeOrWeakLines": [],
                "watchPoints": ["观察次日承接"],
                "audit": {"missingEvidence": [], "sourceWarnings": []},
            },
        }

    def test_market_day_status_payload_uses_market_day_routes(self):
        payload = simple_api._market_day_status_payload(
            "run-1",
            status="queued",
            stage="queued",
            request_id="req-1",
        )

        self.assertEqual(payload["run_id"], "run-1")
        self.assertEqual(payload["status_url"], "/api/market-day/reports/run-1/status")
        self.assertEqual(payload["report_url"], "/api/market-day/reports/run-1/market_day_report.json")
        self.assertEqual(payload["request_id"], "req-1")

    def test_recent_market_day_report_summaries_use_frontend_route(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "20260619_120000"
            run_dir.mkdir()
            report = {
                "market_date": "2026-06-19",
                "report": {
                    "oneLineConclusion": "主线清晰",
                    "mainline": {"name": "机器人"},
                },
            }
            (run_dir / simple_api.MARKET_DAY_REPORT_NAME).write_text(json.dumps(report), encoding="utf-8")

            with patch.object(simple_api, "MARKET_DAY_REPORT_DIR", root):
                summaries = simple_api._recent_market_day_report_summaries(limit=10)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["run_id"], "20260619_120000")
        self.assertEqual(summaries[0]["title"], "2026-06-19 AI当日行情")
        self.assertEqual(summaries[0]["mainline"], "机器人")
        self.assertEqual(summaries[0]["report_route"], "/market-day/report/20260619_120000")
        self.assertEqual(summaries[0]["report_url"], "/api/market-day/reports/20260619_120000/market_day_report.json")

    def test_codex_push_payload_maps_to_existing_report_envelope(self):
        report = simple_api._market_day_report_from_push_payload(self._push_payload(), request_id="req-codex")

        self.assertEqual(report["run_id"], "codex-2026-07-10")
        self.assertEqual(report["market_date"], "2026-07-10")
        self.assertEqual(report["source"], "codex_push")
        self.assertEqual(report["report"]["mainline"]["name"], "半导体")
        self.assertNotIn("headers", report)
        self.assertNotIn("user", report)

    def test_codex_push_payload_rejects_missing_or_invalid_required_fields(self):
        invalid_payloads = [
            {},
            {"run_id": "bad/id", "market_date": "2026-07-10", "report": {"x": 1}},
            {"run_id": "valid", "market_date": "2026/07/10", "report": {"x": 1}},
            {"run_id": "valid", "market_date": "2026-07-10", "report": {}},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                simple_api._market_day_report_from_push_payload(payload, request_id="req-invalid")

    def test_codex_push_secret_fails_closed_and_is_header_only(self):
        with self.assertRaises(AuthError) as missing:
            simple_api._assert_market_day_push_secret(expected="", provided="")
        self.assertEqual(missing.exception.status, 503)

        with self.assertRaises(AuthError) as mismatch:
            simple_api._assert_market_day_push_secret(expected="secret", provided="wrong")
        self.assertEqual(mismatch.exception.status, 401)

        simple_api._assert_market_day_push_secret(expected="secret", provided="secret")

    def test_push_handler_writes_one_idempotent_report_without_calling_models(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            responses = []
            handler = object.__new__(simple_api.TradeReviewHandler)
            handler.headers = {"x-market-day-secret": "secret"}
            handler._request_id = "req-push"
            handler._read_json_body = lambda: self._push_payload()
            handler._json = lambda payload, status=200: responses.append((status, payload))

            with (
                patch.object(simple_api, "MARKET_DAY_REPORT_DIR", root),
                patch.dict("os.environ", {"MARKET_DAY_WEBHOOK_SECRET": "secret"}, clear=False),
                patch.object(simple_api, "run_market_day_agent") as run_agent,
            ):
                handler._receive_market_day_report_push()
                handler._receive_market_day_report_push()

            run_agent.assert_not_called()
            self.assertEqual(len(list(root.iterdir())), 1)
            self.assertEqual(responses[-1][0], 202)
            self.assertEqual(responses[-1][1]["source"], "codex_push")
            stored = json.loads((root / "codex-2026-07-10" / simple_api.MARKET_DAY_REPORT_NAME).read_text(encoding="utf-8"))
            status = json.loads((root / "codex-2026-07-10" / simple_api.REPORT_STATUS_NAME).read_text(encoding="utf-8"))

        self.assertEqual(stored["report"]["oneLineConclusion"], "科技主线最强，成交与广度仍需确认。")
        self.assertTrue(status["ownerless"])
        self.assertEqual(status["billing_status"], "ready_to_charge")
        self.assertNotIn("user_id", status)
        self.assertNotIn("user", status)


if __name__ == "__main__":
    unittest.main()
