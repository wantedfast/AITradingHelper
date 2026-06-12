from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .mock_agents import MOCK_FINAL_ANSWER, build_mock_v3_workbench, write_mock_frontend_report


class MockAgentFrontendTests(unittest.TestCase):
    def test_mock_agents_generate_frontend_without_openai(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "mock_report.html"
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
                with patch("trade_review_agent.workbench_agents._post_json") as post_json:
                    post_json.side_effect = AssertionError("OpenAI API must not be called in mock frontend test")
                    path = write_mock_frontend_report(output)

            html = path.read_text(encoding="utf-8")
            data = path.with_suffix(".presenter.json").read_text(encoding="utf-8")

        self.assertIn("Token & Cost", html)
        self.assertIn("LLM Calls", html)
        self.assertIn("AI 最终结论", html)
        self.assertIn("AI Score", html)
        self.assertIn(">84.0<", html)
        self.assertIn("Mock Agent", html)
        self.assertIn(MOCK_FINAL_ANSWER["verdict"], html)
        self.assertIn(MOCK_FINAL_ANSWER["better_choice"], html)
        self.assertIn(MOCK_FINAL_ANSWER["main_reason"], html)
        self.assertIn(MOCK_FINAL_ANSWER["mistake_source"], html)
        self.assertIn(MOCK_FINAL_ANSWER["next_action"], html)
        self.assertIn('"status": "ok"', data)
        self.assertIn('"actual_total_tokens": 820', data)
        self.assertIn('"cache_hit": false', data)
        self.assertIn('"source": "llm"', data)

    def test_mock_workbench_contains_v3_final_answer_and_usage(self) -> None:
        data = build_mock_v3_workbench()

        self.assertEqual(data["ai_final_answer"], MOCK_FINAL_ANSWER)
        self.assertEqual(data["generation_diagnostics"]["status"], "ok")
        self.assertEqual(data["generation_diagnostics"]["token_usage"]["actual_total_tokens"], 820)
        self.assertEqual(data["source_trace"]["ai_final_answer.verdict"]["source"], "llm")
        stages = {call["stage"]: call["status"] for call in data["generation_diagnostics"]["llm_calls"]}
        self.assertEqual(stages["wang_industry"], "ok")
        self.assertEqual(stages["public_equity"], "ok")
        self.assertEqual(stages["v3_better_opportunity"], "ok")
        self.assertEqual(stages["v3_trade_coach"], "ok")
        self.assertEqual(stages["presenter"], "not_run")


if __name__ == "__main__":
    unittest.main()
