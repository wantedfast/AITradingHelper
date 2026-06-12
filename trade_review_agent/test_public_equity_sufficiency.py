from __future__ import annotations

import unittest
from unittest.mock import patch

from .workbench_agents import (
    apply_public_equity_sufficiency,
    run_public_equity_workbench_agent,
)
from .workbench_composer import compose_workbench_data


LLM_OUTPUT = {
    "investment_rating": "A",
    "financial_validation": ["收入增长已经验证产业逻辑"],
    "valuation_odds": "当前估值具有吸引力",
    "expectation_gap": {
        "market_believes": ["市场认为需求平稳"],
        "analyst_view": ["需求将加速"],
        "gap_score": 82,
    },
    "validation_panel": [
        {"status": "已验证", "item": "收入增长", "evidence": "LLM judgment"}
    ],
}


class PublicEquitySufficiencyTests(unittest.TestCase):
    def test_agent_downgrades_unsupported_high_value_fields(self) -> None:
        context = {
            "company": {"code": "600000", "name": "Test Co"},
            "financials": {
                "revenue_growth": "pending fetch",
                "profit_growth": "pending fetch",
                "gross_margin": "pending fetch",
                "valuation": "pending fetch",
                "pe_ttm": None,
                "pb": None,
            },
        }
        with patch(
            "trade_review_agent.workbench_agents._call_json_agent",
            return_value=dict(LLM_OUTPUT),
        ):
            result = run_public_equity_workbench_agent(context)

        self.assertIsNone(result["investment_rating"])
        self.assertEqual("A", result["investment_rating_hypothesis"])
        self.assertEqual([], result["financial_validation"])
        self.assertEqual(
            LLM_OUTPUT["financial_validation"],
            result["financial_validation_hypothesis"],
        )
        self.assertIsNone(result.get("valuation_odds"))
        self.assertEqual(
            LLM_OUTPUT["valuation_odds"],
            result["valuation_odds_hypothesis"],
        )
        self.assertIsNone(result["expectation_gap"]["gap_score"])
        self.assertEqual(82, result["expectation_gap"]["gap_score_hypothesis"])
        self.assertEqual("not_quantified", result["expectation_gap"]["verification_status"])
        self.assertEqual("待确认", result["validation_panel"][0]["status"])
        self.assertEqual(
            "llm_hypothesis_pending_verification",
            result["data_sufficiency"]["narrative_status"],
        )

    def test_verified_structured_inputs_preserve_fields(self) -> None:
        context = {
            "financials": {
                "revenue_growth": 12.5,
                "profit_growth": 9.1,
                "pe_ttm": 18.4,
                "pb": 2.1,
            },
        }
        result = apply_public_equity_sufficiency(LLM_OUTPUT, context)

        self.assertEqual("A", result["investment_rating"])
        self.assertEqual(LLM_OUTPUT["financial_validation"], result["financial_validation"])
        self.assertEqual(LLM_OUTPUT["valuation_odds"], result["valuation_odds"])
        self.assertIsNone(result["expectation_gap"]["gap_score"])
        self.assertEqual(82, result["expectation_gap"]["gap_score_hypothesis"])
        self.assertEqual(
            "not_collected",
            result["data_sufficiency"]["field_status"]["expectation_gap.gap_score"],
        )
        self.assertEqual(
            "verified_inputs_available",
            result["data_sufficiency"]["narrative_status"],
        )

    def test_source_metadata_alone_does_not_count_as_financial_data(self) -> None:
        result = apply_public_equity_sufficiency(
            LLM_OUTPUT,
            {
                "financial_data": {"source": "vendor", "status": "pending"},
                "valuation": {"provider": "vendor", "as_of": "2026-06-12"},
            },
        )

        self.assertIsNone(result["investment_rating"])
        self.assertEqual([], result["financial_validation"])
        self.assertIsNone(result.get("valuation_odds"))
        self.assertIsNone(result["expectation_gap"]["gap_score"])

    def test_composer_defensively_marks_hypotheses_and_truthful_trace(self) -> None:
        context = {
            "company": {"code": "600000", "name": "Test Co"},
            "financials": {
                "revenue_growth": "pending fetch",
                "valuation": "pending fetch",
            },
        }
        result = compose_workbench_data(context, {}, LLM_OUTPUT)
        public = result["research_layers"]["public_equity"]

        self.assertEqual("missing", result["hero"]["investment_rating"])
        self.assertIsNone(result.get("valuation_odds"))
        self.assertIsNone(result["expectation_gap"].get("gap_score"))
        self.assertEqual("A", public["investment_rating_hypothesis"])
        self.assertEqual(
            "missing",
            result["source_trace"]["hero.investment_rating"]["source"],
        )
        self.assertIn(
            "Missing verified inputs",
            result["source_trace"]["hero.investment_rating"]["detail"],
        )
        self.assertEqual(
            "llm",
            result["source_trace"][
                "research_layers.public_equity.investment_rating_hypothesis"
            ]["source"],
        )
        self.assertIn(
            "not a verified conclusion",
            result["source_trace"][
                "research_layers.public_equity.investment_rating_hypothesis"
            ]["detail"],
        )


if __name__ == "__main__":
    unittest.main()
