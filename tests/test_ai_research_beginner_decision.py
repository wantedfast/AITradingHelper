import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from trade_review_agent.api import simple_api


def valid_v2_payload() -> dict:
    return {
        "schema_version": 2,
        "research_date": "2026-08-13",
        "title": "A股盘前消息简报：2026-08-13",
        "summary": "今天先观察 AI 硬件，但不要开盘追涨。",
        "markdown": "# 完整专业研报\n\n专业证据继续保留。",
        "sources": [{"title": "公开来源", "url": "https://example.com/source"}],
        "evidence_table": [{"event": "隔夜科技上涨", "confidence": "中"}],
        "institutional_research": [{"institution": "Example Research", "title": "AI outlook"}],
        "beginner_decision": {
            "stance": "cautious",
            "headline": "今天先观察 AI 硬件，但不要开盘追涨。",
            "primary_focus": {
                "name": "AI 硬件",
                "reason": "多个相关方向可能受到隔夜科技行情影响。",
            },
            "continue_conditions": [
                {"time": "09:35", "observation": "服务器、光通信、供配电中至少两个方向仍在上涨。", "action": "继续观察，不急着买。"}
            ],
            "stop_conditions": [
                {"time": "10:30", "observation": "冲高回落后一直没有重新走强。", "action": "今天停止关注。"}
            ],
            "timeline": [
                {"time": "09:25", "observation": "是否普遍大幅高开。", "action": "先等待。", "if_unmet": "继续等到 09:35。"},
                {"time": "09:35", "observation": "多个相关方向是否仍在上涨。", "action": "满足才继续观察。", "if_unmet": "放弃 AI 方向。"},
                {"time": "10:30", "observation": "回落后是否重新走强。", "action": "满足才保留关注。", "if_unmet": "结束今天的观察。"},
            ],
            "backup_focus": {
                "name": "创新药 / CRO",
                "condition": "只有它自己明显走强时才观察，不能自动切换。",
            },
            "avoid_actions": ["开盘直接追涨", "条件不满足仍强行参与"],
            "term_explanations": [
                {"term": "回流", "plain": "冲高回落后，相关方向再次被资金推高。"}
            ],
        },
    }


class AIResearchBeginnerDecisionTest(unittest.TestCase):
    def test_v2_payload_preserves_beginner_and_professional_layers(self) -> None:
        payload = valid_v2_payload()

        report = simple_api._ai_research_report_from_payload(
            payload=payload,
            headers={"user-agent": "unit-test"},
            source_ip="127.0.0.1",
            request_id="req-v2",
        )
        public = simple_api._ai_research_public_report(report)

        self.assertEqual(public["schema_version"], 2)
        self.assertEqual(public["beginner_decision"]["stance"], "cautious")
        self.assertEqual(public["beginner_decision"]["primary_focus"]["name"], "AI 硬件")
        self.assertEqual(public["markdown"], payload["markdown"])
        self.assertEqual(public["sources"], payload["sources"])
        self.assertEqual(public["evidence_table"], payload["evidence_table"])
        self.assertEqual(public["institutional_research"], payload["institutional_research"])

    def test_stand_aside_allows_no_primary_or_backup_direction(self) -> None:
        payload = valid_v2_payload()
        payload["beginner_decision"].update({
            "stance": "stand_aside",
            "headline": "今天没有足够清晰的方向，先不参与。",
            "primary_focus": None,
            "continue_conditions": [],
            "backup_focus": None,
        })

        report = simple_api._ai_research_report_from_payload(
            payload=payload,
            headers={},
            source_ip="127.0.0.1",
            request_id="req-stand-aside",
        )

        self.assertIsNone(report["beginner_decision"]["primary_focus"])
        self.assertIsNone(report["beginner_decision"]["backup_focus"])
        self.assertEqual(report["beginner_decision"]["continue_conditions"], [])

    def test_v2_rejects_invalid_or_unsafe_primary_content(self) -> None:
        mutations = (
            ("missing layer", lambda payload: payload.pop("beginner_decision")),
            ("multiple primary directions", lambda payload: payload["beginner_decision"].update({"primary_focus": [{"name": "AI"}, {"name": "医药"}]})),
            ("missing stop condition", lambda payload: payload["beginner_decision"].update({"stop_conditions": []})),
            ("wrong timeline", lambda payload: payload["beginner_decision"]["timeline"].reverse()),
            ("professional jargon", lambda payload: payload["beginner_decision"].update({"headline": "等待板块扩散后再看"})),
            ("investment instruction", lambda payload: payload["beginner_decision"].update({"headline": "09:35 买入 AI 硬件"})),
            ("boolean schema", lambda payload: payload.update({"schema_version": True})),
            ("overlong headline", lambda payload: payload["beginner_decision"].update({"headline": "太" * 161})),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                payload = valid_v2_payload()
                mutate(payload)
                with self.assertRaises(simple_api.AIResearchPayloadError):
                    simple_api._ai_research_report_from_payload(
                        payload=payload,
                        headers={},
                        source_ip="127.0.0.1",
                        request_id="req-invalid",
                    )


class AIResearchBeginnerDecisionHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.report_root = self.root / "reports"
        self.db_path = self.root / "auth.sqlite"
        self.patches = (
            patch.object(simple_api, "AI_RESEARCH_REPORT_DIR", self.report_root),
            patch.object(simple_api, "AUTH_DB", self.db_path),
            patch.dict("os.environ", {"AI_RESEARCH_WEBHOOK_SECRET": "secret"}, clear=False),
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
        payload = valid_v2_payload()
        payload["run_id"] = "invalid-v2"
        payload["beginner_decision"].pop("stop_conditions")
        request = Request(
            self.base_url + "/api/ai-research/reports",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "x-ai-research-secret": "secret",
            },
        )

        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=3)

        response = raised.exception
        self.assertEqual(response.code, 422)
        body = json.loads(response.read())
        response.close()
        self.assertIn("stop_conditions", body["error"])
        self.assertFalse((self.report_root / "invalid-v2").exists())
        self.assertFalse(self.db_path.exists())

    def test_real_2026_08_13_v2_sample_posts_to_local_api_and_keeps_professional_layer(self) -> None:
        sample_path = Path(__file__).resolve().parents[1] / "samples" / "ai-research" / "2026-08-13-v2.json"
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        payload["run_id"] = "real-2026-08-13-v2-e2e"
        request = Request(
            self.base_url + "/api/ai-research/reports",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "x-ai-research-secret": "secret",
            },
        )

        with patch.object(simple_api, "create_ai_report_email_campaign", return_value={"id": 13, "status": "pending"}):
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 202)
                body = json.loads(response.read())

        self.assertTrue(body["success"])
        stored_path = self.report_root / payload["run_id"] / simple_api.AI_RESEARCH_REPORT_NAME
        stored = json.loads(stored_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["schema_version"], 2)
        self.assertEqual(stored["beginner_decision"]["primary_focus"]["name"], "AI 硬件")
        self.assertEqual(stored["markdown"], payload["markdown"].strip())
        self.assertEqual(stored["sources"], payload["sources"])
        self.assertEqual(stored["evidence_table"], payload["evidence_table"])
        self.assertEqual(stored["institutional_research"], payload["institutional_research"])


if __name__ == "__main__":
    unittest.main()
