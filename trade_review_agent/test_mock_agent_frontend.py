from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .mock_agents import MOCK_FINAL_ANSWER, build_mock_v3_workbench, write_mock_frontend_report
from .workbench_report_renderer import render_workbench_report


class MockAgentFrontendTests(unittest.TestCase):
    def test_mock_agents_generate_frontend_without_openai(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "mock_report.html"
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
                with patch("trade_review_agent.workbench_agents._post_json") as workbench_post:
                    with patch("trade_review_agent.presenter_agent._post_json") as presenter_post:
                        workbench_post.side_effect = AssertionError("OpenAI API must not be called in mock frontend test")
                        presenter_post.side_effect = AssertionError("OpenAI API must not be called in mock frontend test")
                        path = write_mock_frontend_report(output)

            html = path.read_text(encoding="utf-8")
            data = json.loads(path.with_suffix(".presenter.json").read_text(encoding="utf-8"))

        self.assertIn("YingHang AI Investment Coach", html)
        self.assertIn('data-testid="screen1-final-answer"', html)
        self.assertIn("AI 最终结论", html)
        self.assertIn("AI Score", html)
        self.assertIn(">84<", html)
        self.assertIn("Better Choice", html)
        self.assertIn("Main Reason", html)
        self.assertIn("Mistake Source", html)
        self.assertIn("Next Action", html)
        self.assertIn("答案依据", html)
        self.assertIn("Token & Cost", html)
        self.assertIn("LLM Calls", html)
        self.assertIn("820 total", html)
        self.assertIn("hit=False stale=False", html)
        self.assertIn("wang_industry / Mock WANG Agent", html)
        self.assertIn("public_equity / Mock Public Equity Agent", html)
        self.assertIn("v3_better_opportunity / Mock Better Opportunity Agent", html)
        self.assertIn("v3_trade_coach / Mock Trade Coach Agent", html)
        self.assertIn("verdict: llm / mock", html)
        self.assertIn("better_choice: llm / mock", html)
        self.assertIn(MOCK_FINAL_ANSWER["verdict"], html)
        self.assertIn(MOCK_FINAL_ANSWER["better_choice"], html)
        self.assertIn(MOCK_FINAL_ANSWER["main_reason"], html)
        self.assertIn(MOCK_FINAL_ANSWER["mistake_source"], html)
        self.assertIn(MOCK_FINAL_ANSWER["next_action"], html)
        self.assertLess(html.index('data-testid="screen1-final-answer"'), html.index("答案依据"))
        self.assertLess(html.index("答案依据"), html.index("Token & Cost"))

        self.assertEqual(data["generation_diagnostics"]["status"], "ok")
        self.assertEqual(data["generation_diagnostics"]["token_usage"]["actual_total_tokens"], 820)
        self.assertEqual(data["generation_diagnostics"]["cache_diagnostics"]["cache_hit"], False)
        self.assertEqual(data["source_trace"]["ai_final_answer.verdict"]["source"], "llm")
        self.assertEqual(data["source_trace"]["ai_final_answer.verdict"]["mode"], "mock")

    def test_mock_workbench_contains_v3_final_answer_and_usage(self) -> None:
        data = build_mock_v3_workbench()

        self.assertEqual(data["ai_final_answer"], MOCK_FINAL_ANSWER)
        self.assertEqual(data["generation_diagnostics"]["status"], "ok")
        self.assertEqual(data["generation_diagnostics"]["token_usage"]["actual_total_tokens"], 820)
        self.assertEqual(data["source_trace"]["ai_final_answer.verdict"]["source"], "llm")
        self.assertEqual(data["source_trace"]["ai_final_answer.verdict"]["mode"], "mock")
        self.assertTrue(data["source_trace"]["ai_final_answer.verdict"]["mock_agent"])
        stages = {call["stage"]: call["status"] for call in data["generation_diagnostics"]["llm_calls"]}
        self.assertEqual(stages["wang_industry"], "ok")
        self.assertEqual(stages["public_equity"], "ok")
        self.assertEqual(stages["v3_better_opportunity"], "ok")
        self.assertEqual(stages["v3_trade_coach"], "ok")
        self.assertEqual(stages["presenter"], "not_run")

    def test_frontend_displays_fallback_and_cache_flags(self) -> None:
        data = build_mock_v3_workbench()
        diagnostics = data["generation_diagnostics"]
        diagnostics["cache_diagnostics"] = {"cache_hit": True, "cache_stale": False, "provider": "mock-cache"}
        diagnostics["llm_calls"][0]["fallback_used"] = True
        diagnostics["llm_calls"][0]["cache_hit"] = True

        html = render_workbench_report(data)

        self.assertIn("hit=True stale=False", html)
        self.assertIn("fallback", html)
        self.assertIn("cache", html)


if __name__ == "__main__":
    unittest.main()
