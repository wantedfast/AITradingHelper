import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import init_auth_db


def valid_market_day_v2_payload() -> dict:
    return {
        "schema_version": 2,
        "run_id": "market-day-2026-08-13",
        "market_date": "2026-08-13",
        "report": {
            "marketDate": "2026-08-13",
            "oneLineConclusion": "今天收盘后更适合先观察，不急着把强势理解成全面转强。",
            "watchPoints": ["明天先看开盘后十分钟是否还是多个相关方向一起保持偏强。"],
            "beginner_decision": {
                "stance": "cautious",
                "headline": "今天看起来偏强，但明天先确认是不是很多相关方向一起稳住。",
                "what_changed": [
                    "比前一天更活跃，但成交没有同时明显放大。",
                    "热点不只集中在一个方向，说明延续性还要再看。",
                ],
                "primary_focus": {
                    "name": "AI硬件",
                    "reason": "今天相关消息更多，但还需要明天开盘后继续一起保持偏强才算延续。",
                },
                "continue_conditions": [
                    {
                        "time": "09:35",
                        "observation": "至少两个相关方向继续偏强，而且市场整体没有明显转弱。",
                        "action": "继续只观察这个方向，不临时扩展到别的题材。",
                    }
                ],
                "stop_conditions": [
                    {
                        "time": "09:35",
                        "observation": "只有少数个别标的偏强，或者市场很快转弱。",
                        "action": "停止关注这个方向，不临时切去别的方向。",
                    }
                ],
                "timeline": [
                    {
                        "time": "09:25",
                        "observation": "先看是不是普遍高开，而不是只看少数几个点位。",
                        "action": "先记录开盘状态，等09:35再判断。",
                        "if_unmet": "如果开盘表现分散，就先按观察处理。",
                    },
                    {
                        "time": "09:35",
                        "observation": "看相关方向和市场整体是否一起保持偏强。",
                        "action": "全部满足才继续观察。",
                        "if_unmet": "停止关注这个方向。",
                    },
                    {
                        "time": "10:30",
                        "observation": "看早盘回落后是否重新稳住，而且不是只剩很少数在动。",
                        "action": "满足时保留原判断，不新增方向。",
                        "if_unmet": "当天放弃这个判断。",
                    },
                ],
                "backup_focus": {
                    "name": "电网设备",
                    "condition": "只有它自己也出现多个相关方向一起偏强时，才重新单独判断。",
                },
                "avoid_actions": [
                    "不要因为开盘热闹就把今天理解成全面转强。",
                    "不要只看很少数表现就替整个方向下结论。",
                ],
                "term_explanations": [
                    {
                        "term": "回流",
                        "plain": "先走弱后又重新稳住，而且不只是少数个别在动。",
                    }
                ],
            },
        },
    }


class MarketDayBeginnerDecisionTest(unittest.TestCase):
    def test_v2_payload_preserves_beginner_layer(self) -> None:
        report = simple_api._market_day_report_from_push_payload(
            valid_market_day_v2_payload(),
            request_id="req-market-day-v2",
        )

        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["run_id"], "market-day-2026-08-13")
        self.assertEqual(report["report"]["beginner_decision"]["stance"], "cautious")
        self.assertEqual(report["report"]["beginner_decision"]["primary_focus"]["name"], "AI硬件")

    def test_v1_payload_remains_compatible(self) -> None:
        payload = {
            "run_id": "legacy-market-day-run",
            "market_date": "2026-08-13",
            "report": {
                "marketDate": "2026-08-13",
                "oneLineConclusion": "保留旧版结构。",
                "watchPoints": ["继续看市场整体表现。"],
            },
        }

        report = simple_api._market_day_report_from_push_payload(payload, request_id="req-market-day-v1")

        self.assertNotIn("schema_version", report)
        self.assertNotIn("beginner_decision", report["report"])

    def test_stand_aside_requires_no_primary_focus_and_explicit_headline(self) -> None:
        payload = valid_market_day_v2_payload()
        decision = payload["report"]["beginner_decision"]
        decision["stance"] = "stand_aside"
        decision["continue_conditions"] = []

        with self.assertRaisesRegex(simple_api.MarketDayPayloadError, "primary_focus must be null"):
            simple_api._market_day_report_from_push_payload(payload, request_id="stand-aside-focus")

        decision["primary_focus"] = None
        with self.assertRaisesRegex(simple_api.MarketDayPayloadError, "明天暂不预设主线"):
            simple_api._market_day_report_from_push_payload(payload, request_id="stand-aside-headline")

        decision["headline"] = "今天热点分散，明天暂不预设主线。"
        report = simple_api._market_day_report_from_push_payload(payload, request_id="stand-aside-valid")
        self.assertEqual(report["report"]["beginner_decision"]["stance"], "stand_aside")
        self.assertIsNone(report["report"]["beginner_decision"]["primary_focus"])


class MarketDayBeginnerDecisionHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.report_root = self.root / "reports"
        self.db_path = self.root / "auth.sqlite"
        init_auth_db(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        phone, username, email, email_verified, update_emails_enabled,
                        password_hash, password_salt, role, status, invite_code, created_at
                    ) VALUES ('market-day-v2-user', 'market-day-v2-user', 'market-day-v2@example.test', 1, 1,
                              'hash', 'salt', 'user', 'active', 'MARKETDAYV2', '2026-08-13T08:00:00+08:00')
                    """
                )
        self.patches = (
            patch.object(simple_api, "MARKET_DAY_REPORT_DIR", self.report_root),
            patch.object(simple_api, "AUTH_DB", self.db_path),
            patch.dict("os.environ", {"MARKET_DAY_WEBHOOK_SECRET": "secret"}, clear=False),
        )
        for active_patch in self.patches:
            active_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temp_dir.cleanup()

    def test_invalid_v2_returns_422_without_storage_or_email_campaign(self) -> None:
        payload = valid_market_day_v2_payload()
        payload["report"]["beginner_decision"]["headline"] = "明天先看贵州茅台会不会继续强。"
        request = Request(
            self.base_url + "/api/market-day/reports/push",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "x-market-day-secret": "secret",
            },
        )

        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=3)

        response = raised.exception
        self.assertEqual(response.code, 422)
        body = json.loads(response.read())
        response.close()
        self.assertIn("stock name", body["error"])
        self.assertFalse((self.report_root / payload["run_id"]).exists())
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ai_report_email_campaigns").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
