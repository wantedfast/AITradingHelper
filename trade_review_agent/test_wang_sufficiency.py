from __future__ import annotations

import unittest
from unittest.mock import patch

from .workbench_agents import apply_wang_sufficiency, run_wang_workbench_agent
from .workbench_composer import compose_workbench_data


LLM_OUTPUT = {
    "industry_rating": "A",
    "profit_flow": {
        "value_pool": "industry pool",
        "items": [{"name": "core", "share_pct": 42, "highlight": True}],
        "company_position": "core supplier",
        "why_profit_flows_here": "pricing power",
    },
    "moat_radar": {
        "company_score": 88,
        "industry_average": 61,
        "dimensions": [{"name": "technology", "company": 90, "average": 60}],
        "explanation": "strong moat",
    },
    "logic_tree": [{"node": "demand expands", "certainty_pct": 79}],
    "peer_ranking": ["Peer A > Peer B"],
}


class WangSufficiencyTests(unittest.TestCase):
    def test_agent_withholds_unsupported_precision(self) -> None:
        with patch(
            "trade_review_agent.workbench_agents._call_json_agent",
            return_value=dict(LLM_OUTPUT),
        ):
            result = run_wang_workbench_agent({"company": {"code": "600000"}})

        flow_item = result["profit_flow"]["items"][0]
        self.assertIsNone(flow_item["share_pct"])
        self.assertEqual(42, flow_item["share_pct_hypothesis"])
        self.assertIsNone(result["moat_radar"]["company_score"])
        self.assertEqual(88, result["moat_radar"]["company_score_hypothesis"])
        dimension = result["moat_radar"]["dimensions"][0]
        self.assertIsNone(dimension["company"])
        self.assertEqual(90, dimension["company_hypothesis"])
        self.assertIsNone(result["logic_tree"][0]["certainty_pct"])
        self.assertEqual(79, result["logic_tree"][0]["certainty_pct_hypothesis"])
        self.assertEqual([], result["peer_ranking"])
        self.assertEqual(["Peer A > Peer B"], result["peer_ranking_hypothesis"])
        self.assertEqual(
            "llm_hypothesis_pending_verification",
            result["data_sufficiency"]["narrative_status"],
        )

    def test_each_structured_input_independently_preserves_its_fields(self) -> None:
        context = {
            "profit_pool_data": [{"segment": "core", "profit_share_pct": 42}],
            "peer_moat_samples": [
                {"code": "600001", "dimensions": {"technology": 60}}
            ],
            "probability_calibration": {
                "method": "historical base rate",
                "nodes": {"demand expands": 0.79},
            },
            "peer_snapshot": [
                {
                    "code": "600001",
                    "name": "Peer A",
                    "metrics": {"return_20d_pct": 12.5},
                }
            ],
        }
        result = apply_wang_sufficiency(LLM_OUTPUT, context)

        self.assertEqual(42, result["profit_flow"]["items"][0]["share_pct"])
        self.assertEqual(88, result["moat_radar"]["company_score"])
        self.assertEqual(90, result["moat_radar"]["dimensions"][0]["company"])
        self.assertEqual(79, result["logic_tree"][0]["certainty_pct"])
        self.assertEqual(["Peer A > Peer B"], result["peer_ranking"])
        self.assertEqual(
            "verified_inputs_available",
            result["data_sufficiency"]["narrative_status"],
        )

    def test_metadata_only_inputs_do_not_unlock_numeric_outputs(self) -> None:
        result = apply_wang_sufficiency(
            LLM_OUTPUT,
            {
                "profit_pool": {"source": "vendor", "status": "pending"},
                "peer_moat_samples": [{"provider": "vendor", "as_of": "2026-06-12"}],
                "probability_calibration": {"source": "model", "note": "pending"},
                "peer_snapshot": [{"code": "600001", "name": "Peer A"}],
            },
        )

        self.assertIsNone(result["profit_flow"]["items"][0].get("share_pct"))
        self.assertIsNone(result["moat_radar"]["company_score"])
        self.assertIsNone(result["logic_tree"][0]["certainty_pct"])
        self.assertEqual([], result["peer_ranking"])

    def test_composer_applies_gate_and_marks_hypothesis_lineage(self) -> None:
        result = compose_workbench_data(
            {"company": {"code": "600000", "name": "Test Co"}},
            {**LLM_OUTPUT, "agent_type": "wang"},
            {},
        )
        wang = result["research_layers"]["wang_industry"]

        self.assertIsNone(result["profit_flow"]["items"][0].get("share_pct"))
        self.assertEqual(42, wang["profit_flow"]["items"][0]["share_pct_hypothesis"])
        self.assertEqual([], wang.get("peer_ranking", []))
        self.assertEqual(
            "missing",
            result["source_trace"][
                "research_layers.wang_industry.profit_flow.items.0.share_pct"
            ]["source"],
        )
        self.assertEqual(
            "llm",
            result["source_trace"][
                "research_layers.wang_industry.profit_flow.items.0.share_pct_hypothesis"
            ]["source"],
        )
        self.assertIn(
            "not a verified measurement",
            result["source_trace"][
                "research_layers.wang_industry.profit_flow.items.0.share_pct_hypothesis"
            ]["detail"],
        )
        self.assertEqual(
            "missing",
            result["source_trace"]["research_layers.wang_industry.peer_ranking"]["source"],
        )
        self.assertEqual(
            "hardcode",
            result["source_trace"][
                "research_layers.wang_industry.data_sufficiency"
            ]["source"],
        )


if __name__ == "__main__":
    unittest.main()
