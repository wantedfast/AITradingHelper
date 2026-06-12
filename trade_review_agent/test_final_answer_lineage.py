from __future__ import annotations

import unittest
from typing import Any

from .v3_trade_coach_agent import run_trade_coach_agent


class FinalAnswerLineageTests(unittest.TestCase):
    def test_available_answer_uses_actual_context_paths(self) -> None:
        result = run_trade_coach_agent(
            execution={
                "trade_execution_notes": {"main_lesson": "selection mattered"},
                "execution_advice": "compare peers before entry",
            },
            wang={
                "industry_position": "midstream",
                "profit_flow": {"company_position": "component supplier"},
                "data_sufficiency": {
                    "field_status": {"peer_ranking": "verified_input"},
                    "missing_inputs": [],
                },
            },
            public_equity={
                "investment_rating": "B",
                "financial_validation": ["revenue growth verified"],
                "risks": ["margin pressure"],
                "data_sufficiency": {
                    "field_status": {"investment_rating": "verified_input"},
                    "missing_inputs": [],
                },
            },
            market_scout={
                "market_theme": "grid investment",
                "market_catalyst": [{"fact": "tender volume increased"}],
                "sector_strength": {"value": 4.2},
                "peer_snapshot": [
                    {"code": "000002", "name": "Peer A", "metrics": {"return_20d_pct": 12}}
                ],
            },
            better_opportunity={
                "status": "available",
                "better_candidates": [
                    {"code": "000002", "name": "Peer A", "evidence": ["return_20d_pct=12"]}
                ],
                "superiority_reason": "stronger verified momentum",
                "replacement_thesis": "prefer the stronger peer",
                "confidence": 0.8,
            },
            llm_caller=_complete_answer,
        )

        self.assertEqual("available", result["status"])
        for field in (
            "score",
            "verdict",
            "better_choice",
            "main_reason",
            "mistake_source",
            "next_action",
        ):
            trace = result["source_trace"][f"ai_final_answer.{field}"]
            self.assertEqual("llm", trace["source"])
            self.assertEqual("trade_coach", trace["agent"])
            self.assertIn(trace["confidence"], {"low", "medium", "high"})
            self.assertTrue(trace["depends_on"])
            for path in trace["depends_on"]:
                self.assertTrue(_path_exists(_coach_context(), path), path)

        better_trace = result["source_trace"]["ai_final_answer.better_choice"]
        self.assertEqual(
            ["better_opportunity.better_candidates"],
            better_trace["depends_on"],
        )
        self.assertEqual([], better_trace["missing_dependencies"])
        self.assertEqual("high", better_trace["confidence"])

    def test_missing_answer_reports_empty_layers_and_sufficiency(self) -> None:
        result = run_trade_coach_agent(
            execution={
                "trade_execution_notes": {"main_lesson": "timing unclear"},
            },
            wang={
                "industry_position": "midstream",
                "data_sufficiency": {
                    "field_status": {
                        "moat_radar.numeric_scores": "missing",
                        "peer_ranking": "missing",
                    },
                    "missing_inputs": ["peer_moat_samples", "peer_metrics"],
                },
            },
            public_equity={
                "data_sufficiency": {
                    "field_status": {
                        "investment_rating": "missing",
                        "financial_validation": "missing",
                    },
                    "missing_inputs": ["financials", "valuation"],
                },
            },
            market_scout={},
            better_opportunity={
                "status": "missing",
                "better_candidates": [],
                "missing_reason": "missing comparable peer_snapshot",
            },
            llm_caller=None,
        )

        score_trace = result["source_trace"]["ai_final_answer.score"]
        self.assertEqual("missing", score_trace["source"])
        self.assertEqual("trade_coach", score_trace["agent"])
        self.assertIsNone(score_trace["confidence"])
        self.assertIn("market_scout", score_trace["missing_dependencies"])
        self.assertIn(
            "wang_industry.moat_radar.numeric_scores",
            score_trace["missing_dependencies"],
        )
        self.assertIn(
            "public_equity.data_sufficiency.missing_inputs.financials",
            score_trace["missing_dependencies"],
        )

        better_trace = result["source_trace"]["ai_final_answer.better_choice"]
        self.assertEqual([], better_trace["depends_on"])
        self.assertEqual(
            ["better_opportunity.better_candidates"],
            better_trace["missing_dependencies"],
        )


def _complete_answer(_system: str, _user: str) -> dict[str, Any]:
    return {
        "ai_final_answer": {
            "score": 82,
            "verdict": "Right industry, weaker stock selection.",
            "better_choice": "Peer A",
            "main_reason": "The verified peer had stronger momentum.",
            "mistake_source": "selection",
            "next_action": "Compare verified peer metrics before entry.",
        }
    }


def _coach_context() -> dict[str, Any]:
    return {
        "trade_execution": {
            "trade_execution_notes": {"main_lesson": "selection mattered"},
            "execution_advice": "compare peers before entry",
        },
        "wang_industry": {
            "industry_position": "midstream",
            "profit_flow": {"company_position": "component supplier"},
            "data_sufficiency": {
                "field_status": {"peer_ranking": "verified_input"},
                "missing_inputs": [],
            },
        },
        "public_equity": {
            "investment_rating": "B",
            "financial_validation": ["revenue growth verified"],
            "risks": ["margin pressure"],
            "data_sufficiency": {
                "field_status": {"investment_rating": "verified_input"},
                "missing_inputs": [],
            },
        },
        "market_scout": {
            "market_theme": "grid investment",
            "market_catalyst": [{"fact": "tender volume increased"}],
            "sector_strength": {"value": 4.2},
            "peer_snapshot": [
                {"code": "000002", "name": "Peer A", "metrics": {"return_20d_pct": 12}}
            ],
        },
        "better_opportunity": {
            "status": "available",
            "better_candidates": [
                {"code": "000002", "name": "Peer A", "evidence": ["return_20d_pct=12"]}
            ],
            "superiority_reason": "stronger verified momentum",
            "replacement_thesis": "prefer the stronger peer",
            "confidence": 0.8,
        },
    }


def _path_exists(context: dict[str, Any], path: str) -> bool:
    value: Any = context
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return value not in (None, "", [], {}, "missing")


if __name__ == "__main__":
    unittest.main()
