from __future__ import annotations

import copy
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
from trade_review_agent.auth_system import init_auth_db


SAMPLE_PATH = Path(__file__).resolve().parents[1] / "samples" / "market-day" / "2026-08-12-v2.json"


def market_day_v2_sample_payload() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def market_day_v2_today_payload() -> dict:
    payload = copy.deepcopy(market_day_v2_sample_payload())
    market_date = datetime.now(simple_api.CN_TZ).strftime("%Y-%m-%d")
    payload["run_id"] = f"market-day-{market_date}"
    payload["market_date"] = market_date
    payload["report"]["marketDate"] = market_date
    return payload


def legacy_market_day_v1_payload() -> dict:
    return {
        "run_id": "codex-2026-07-10",
        "market_date": "2026-07-10",
        "report": {
            "oneLineConclusion": "科技主线最强，但成交与广度仍需确认。",
            "marketMood": {"summary": "强修复后的分歧", "score": 7},
            "mainline": {"name": "半导体", "reason": "成交和涨停结构领先"},
            "strongestStocks": [],
            "secondaryLines": [],
            "fakeOrWeakLines": [],
            "watchPoints": ["观察次日承接"],
            "audit": {"missingEvidence": [], "sourceWarnings": []},
        },
    }


class MarketDayV2BeginnerCompatibilityTest(unittest.TestCase):
    def test_market_day_v1_payload_remains_compatible_without_beginner_layer(self) -> None:
        report = simple_api._market_day_report_from_push_payload(
            legacy_market_day_v1_payload(),
            request_id="req-market-day-v1",
        )

        self.assertEqual(report["run_id"], "codex-2026-07-10")
        self.assertEqual(report["market_date"], "2026-07-10")
        self.assertEqual(report["source"], "codex_push")
        self.assertEqual(report["report"]["mainline"]["name"], "半导体")
        self.assertNotIn("schema_version", report)
        self.assertNotIn("beginner_decision", report)

    def test_market_day_v2_parser_preserves_beginner_and_professional_layers(self) -> None:
        payload = market_day_v2_sample_payload()

        report = simple_api._market_day_report_from_push_payload(payload, request_id="req-market-day-v2")

        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["run_id"], "market-day-2026-08-12")
        self.assertEqual(report["market_date"], "2026-08-12")
        self.assertEqual(report["report"]["beginner_decision"]["stance"], "stand_aside")
        self.assertEqual(report["report"]["beginner_decision"]["timeline"][0]["time"], "09:25")
        self.assertTrue(report["report"]["oneLineConclusion"])
        self.assertTrue(report["report"]["sources"])
        self.assertTrue(report["report"]["strongestStocks"])


class MarketDayV2BeginnerPushAcceptanceTest(unittest.TestCase):
    def _seed_recipient(self, db_path: Path, suffix: str) -> None:
        init_auth_db(db_path)
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        phone, username, email, email_verified, update_emails_enabled,
                        password_hash, password_salt, role, status, invite_code, created_at
                    ) VALUES (?, ?, ?, 1, 1, 'hash', 'salt', 'user', 'active', ?, '2026-08-13T08:00:00+08:00')
                    """,
                    (
                        f"qa-market-day-{suffix}",
                        f"qa-market-day-{suffix}",
                        f"qa-market-day-{suffix}@example.test",
                        f"QAMARKETDAY{suffix.upper()}",
                    ),
                )

    def test_market_day_v2_replay_creates_exactly_one_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_root = root / "reports"
            db_path = root / "auth.sqlite"
            self._seed_recipient(db_path, "replay")

            payload = market_day_v2_today_payload()
            request = Request(
                "http://placeholder/api/market-day/reports/push",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                method="POST",
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "x-market-day-secret": "secret",
                },
            )

            patches = (
                patch.object(simple_api, "MARKET_DAY_REPORT_DIR", report_root),
                patch.object(simple_api, "AUTH_DB", db_path),
                patch.dict("os.environ", {"MARKET_DAY_WEBHOOK_SECRET": "secret"}, clear=False),
            )
            for active_patch in patches:
                active_patch.start()
            server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                simple_api.UPDATE_EMAIL_QUEUE_WAKE.clear()
                url = f"http://127.0.0.1:{server.server_address[1]}/api/market-day/reports/push"
                request.full_url = url
                with urlopen(request, timeout=3) as first_response:
                    first = json.loads(first_response.read())
                with urlopen(request, timeout=3) as second_response:
                    second = json.loads(second_response.read())

                self.assertTrue(first["success"])
                self.assertTrue(first["stored"])
                self.assertEqual(first["run_id"], payload["run_id"])
                self.assertEqual(first["source"], "codex_push")
                self.assertEqual(first["email_campaign"]["id"], second["email_campaign"]["id"])
                self.assertTrue((report_root / payload["run_id"] / simple_api.MARKET_DAY_REPORT_NAME).is_file())
                self.assertTrue(simple_api.UPDATE_EMAIL_QUEUE_WAKE.is_set())
                with closing(sqlite3.connect(db_path)) as conn:
                    self.assertEqual(
                        conn.execute(
                            "SELECT COUNT(*) FROM ai_report_email_campaigns WHERE report_type = 'market_day' AND run_id = ?",
                            (payload["run_id"],),
                        ).fetchone()[0],
                        1,
                    )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
                for active_patch in reversed(patches):
                    active_patch.stop()

    def test_market_day_v2_invalid_cases_fail_closed_without_storage_or_email(self) -> None:
        cases = (
            (
                "multiple primary directions",
                "primary_focus",
                lambda payload: payload["report"]["beginner_decision"].update(
                    {"primary_focus": [{"name": "设备"}, {"name": "地产"}]}
                ),
            ),
            (
                "missing stop condition",
                "stop_conditions",
                lambda payload: payload["report"]["beginner_decision"].pop("stop_conditions"),
            ),
            (
                "wrong timeline time",
                "timeline",
                lambda payload: payload["report"]["beginner_decision"]["timeline"].__setitem__(
                    1,
                    {
                        **payload["report"]["beginner_decision"]["timeline"][1],
                        "time": "09:40",
                    },
                ),
            ),
            (
                "forbidden jargon",
                "prohibited jargon",
                lambda payload: payload["report"]["beginner_decision"].update(
                    {"headline": "明天暂不预设主线，等扩散确认后再看。"}
                ),
            ),
            (
                "explicit investment advice",
                "investment instruction",
                lambda payload: payload["report"]["beginner_decision"].update(
                    {"headline": "明天暂不预设主线，09:35 买入设备方向。"}
                ),
            ),
            (
                "stock recommendation implication",
                "stock name",
                lambda payload: payload["report"]["beginner_decision"].update(
                    {"headline": "明天暂不预设主线，先看贵州茅台会不会继续强。"}
                ),
            ),
            (
                "short stock alias implication",
                "stock name",
                lambda payload: payload["report"]["beginner_decision"].update(
                    {"headline": "明天暂不预设主线，但茅台如果继续强，再看白酒方向。"}
                ),
            ),
            (
                "score implication",
                "score implication",
                lambda payload: payload["report"]["beginner_decision"].update(
                    {"headline": "明天暂不预设主线，但设备方向明天是 8/10 分机会。"}
                ),
            ),
            (
                "stand aside with primary focus",
                "primary_focus must be null",
                lambda payload: payload["report"]["beginner_decision"].update(
                    {"primary_focus": {"name": "设备", "reason": "不该在 stand_aside 时保留主方向"}}
                ),
            ),
            (
                "stand aside missing explicit headline",
                "headline must state 明天暂不预设主线",
                lambda payload: payload["report"]["beginner_decision"].update(
                    {"headline": "市场比昨天转强，但明天先观察。"}
                ),
            ),
        )

        for index, (label, error_fragment, mutate) in enumerate(cases, start=1):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                report_root = root / "reports"
                db_path = root / "auth.sqlite"
                self._seed_recipient(db_path, f"invalid{index}")

                patches = (
                    patch.object(simple_api, "MARKET_DAY_REPORT_DIR", report_root),
                    patch.object(simple_api, "AUTH_DB", db_path),
                    patch.dict("os.environ", {"MARKET_DAY_WEBHOOK_SECRET": "secret"}, clear=False),
                )
                for active_patch in patches:
                    active_patch.start()
                server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    payload = market_day_v2_today_payload()
                    mutate(payload)
                    request = Request(
                        f"http://127.0.0.1:{server.server_address[1]}/api/market-day/reports/push",
                        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        method="POST",
                        headers={
                            "Content-Type": "application/json; charset=utf-8",
                            "x-market-day-secret": "secret",
                        },
                    )
                    try:
                        with urlopen(request, timeout=3) as response:
                            status = response.status
                            body = json.loads(response.read())
                    except HTTPError as exc:
                        with exc:
                            status = exc.code
                            body = json.loads(exc.read())

                    self.assertEqual(status, 422, body)
                    self.assertIn(error_fragment, body["error"])
                    self.assertFalse((report_root / payload["run_id"]).exists())
                    with closing(sqlite3.connect(db_path)) as conn:
                        self.assertEqual(
                            conn.execute("SELECT COUNT(*) FROM ai_report_email_campaigns").fetchone()[0],
                            0,
                        )
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)
                    for active_patch in reversed(patches):
                        active_patch.stop()


if __name__ == "__main__":
    unittest.main()
