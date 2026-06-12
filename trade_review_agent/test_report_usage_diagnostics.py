from __future__ import annotations

import unittest

from .report_usage import make_llm_call_record, summarize_token_usage
from .v3_pipeline import run_v3_pipeline
from .visual_report import _report_generation_diagnostics
from .workbench_report_renderer import render_workbench_report


class ReportUsageDiagnosticsTest(unittest.TestCase):
    def test_token_usage_summary_prefers_actual_api_usage(self) -> None:
        calls = [
            make_llm_call_record(
                stage="market_catalyst",
                agent="Market Catalyst Scout",
                model="gpt-4.1",
                status="error",
                error="HTTP 429 insufficient_quota",
                estimated_input_tokens=50,
            ),
            make_llm_call_record(
                stage="wang_industry",
                agent="WANG Agent",
                model="gpt-4.1",
                max_output_tokens=1200,
                api_usage={"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
                estimated_input_tokens=300,
            ),
            make_llm_call_record(
                stage="trade_execution_llm",
                agent="Trade Execution LLM",
                model="gpt-4.1",
                max_output_tokens=800,
                estimated_input_tokens=200,
            ),
        ]

        summary = summarize_token_usage(calls)

        self.assertEqual(summary["observed_call_count"], 1)
        self.assertEqual(summary["missing_usage_call_count"], 2)
        self.assertEqual(summary["actual_input_tokens"], 100)
        self.assertEqual(summary["actual_output_tokens"], 40)
        self.assertGreater(summary["estimated_total_tokens"], summary["actual_total_tokens"])
        self.assertIn("cny", summary["cost_estimate"])
        self.assertEqual(calls[0]["status"], "rate_limited")
        self.assertEqual(calls[0]["attempt_count"], 1)
        self.assertEqual(calls[0]["retry_after"], "unknown")

    def test_generation_diagnostics_collects_stage_usage_and_errors(self) -> None:
        workbench = {
            "ai_final_answer": {"verdict": "missing"},
            "market_catalyst": {
                "agent_error": "market_catalyst_failed: 429",
                "research_metrics": {
                    "seconds": 1.5,
                    "model": "gpt-4.1",
                    "mode": "market_catalyst",
                    "api_usage": {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
                },
            },
            "research_metrics": {
                "wang": {
                    "seconds": 2.0,
                    "model": "gpt-4.1",
                    "mode": "json_only",
                    "api_usage": {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130},
                },
                "public_equity": {"seconds": 3.0, "model": "gpt-4.1", "estimated_total_tokens": 300},
            },
            "research_layers": {
                "better_opportunity": {
                    "research_metrics": {
                        "stage": "v3_better_opportunity",
                        "seconds": 0.8,
                        "model": "gpt-4.1",
                        "api_usage": {"input_tokens": 40, "output_tokens": 20, "total_tokens": 60},
                    }
                }
            },
        }
        execution = {
            "data_source_status": {"errors": ["provider_missing: valuation"]},
            "llm_metrics": {
                "seconds": 0.7,
                "model": "gpt-4.1",
                "mode": "trade_execution_llm",
                "api_usage": {"input_tokens": 80, "output_tokens": 25, "total_tokens": 105},
            },
        }
        presenter = {"agent_errors": ["presenter_structured_output_failed: timeout"]}

        diagnostics = _report_generation_diagnostics(
            workbench=workbench,
            execution_payload=execution,
            presenter_data=presenter,
            timings={
                "input_parse_seconds": 0.0,
                "ocr_seconds": 0.0,
                "market_fetch_seconds": 0.1,
                "total_report_generation_seconds": 8.0,
            },
        )

        self.assertEqual(diagnostics["status"], "partial")
        self.assertGreaterEqual(len(diagnostics["llm_calls"]), 7)
        self.assertEqual(diagnostics["token_usage"]["actual_total_tokens"], 355)
        self.assertIn("provider_missing: valuation", diagnostics["errors"])
        self.assertEqual(diagnostics["timings"]["total_report_generation_seconds"], 8.0)
        stages = {call["stage"]: call for call in diagnostics["llm_calls"]}
        self.assertEqual(stages["presenter"]["status"], "not_run")
        self.assertEqual(stages["v3_trade_coach"]["status"], "not_run")

    def test_html_renders_usage_panel(self) -> None:
        html = render_workbench_report(
            {
                "company": {"name": "TestCo", "code": "000001"},
                "hero": {"claims": ["待验证"]},
                "trade_review": {"rows": []},
                "generation_diagnostics": {
                    "status": "partial",
                    "errors": ["rate_limited"],
                    "timings": {"total_report_generation_seconds": 9.0, "write_artifacts_seconds": 0.2},
                    "token_usage": {
                        "observed_call_count": 1,
                        "missing_usage_call_count": 0,
                        "actual_total_tokens": 120,
                        "actual_input_tokens": 80,
                        "actual_output_tokens": 40,
                        "estimated_total_tokens": 180,
                        "cost_estimate": {"usd": 0.00048, "cny": 0.0034},
                    },
                    "llm_calls": [{"stage": "wang_industry", "status": "ok", "actual_total_tokens": 120, "seconds": 1.2}],
                },
            }
        )

        self.assertIn("Token & Cost", html)
        self.assertIn("LLM Calls", html)
        self.assertIn("wang_industry", html)
        self.assertIn("Actual tokens", html)

    def test_failed_research_layers_are_not_marked_llm(self) -> None:
        payload = run_v3_pipeline(
            company={"code": "000001", "name": "TestCo"},
            market_facts={},
            wang={
                "_agent_error": "WANG agent failed: 429",
                "research_metrics": {"status": "error", "fallback_used": True},
            },
            public_equity={
                "_agent_error": "Public Equity agent failed: 429",
                "research_metrics": {"status": "error", "fallback_used": True},
            },
            trade_execution={"trade_execution_notes": {"buy_verdict": "unknown"}},
            better_opportunity_caller=None,
            trade_coach_caller=None,
        )

        trace = payload["source_trace"]
        self.assertEqual(trace["research_layers.wang_industry"]["source"], "fallback")
        self.assertEqual(trace["research_layers.public_equity"]["source"], "fallback")


if __name__ == "__main__":
    unittest.main()
