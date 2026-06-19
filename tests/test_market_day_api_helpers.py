import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trade_review_agent.api import simple_api


class MarketDayApiHelpersTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
