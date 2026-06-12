from __future__ import annotations

import unittest

from .workbench_composer import compose_workbench_data, workbench_to_profile_payload
from .workbench_schema import SOURCE_TYPES, merge_default_workbench


class WorkbenchV3SchemaContractTests(unittest.TestCase):
    def test_missing_research_does_not_create_fake_conclusions(self) -> None:
        data = merge_default_workbench({}, code="600000", name="Test Co")

        self.assertEqual("yinghang-v3", data["schema_version"])
        self.assertIsNone(data["ai_final_answer"]["score"])
        self.assertEqual("missing", data["ai_final_answer"]["verdict"])
        self.assertEqual("missing", data["hero"]["industry_rating"])
        self.assertEqual("missing", data["hero"]["investment_rating"])
        self.assertEqual({}, data["profit_flow"])
        self.assertEqual({}, data["moat_radar"])
        self.assertEqual([], data["logic_tree"])
        self.assertEqual({}, data["expectation_gap"])
        self.assertEqual({}, data["action"])
        self.assertEqual({}, data["trade_review"])

    def test_partial_research_never_invents_zero_scores_or_names(self) -> None:
        data = merge_default_workbench(
            {
                "profit_flow": {"items": [{"name": "core", "share_pct": None}, {"share_pct": 40}]},
                "moat_radar": {"dimensions": [{"name": "certification"}, {"company": 80}]},
                "logic_tree": [{"node": "demand"}, {"certainty_pct": 70}],
                "expectation_gap": {"market_believes": ["growth"]},
            }
        )

        self.assertEqual([{"name": "core", "highlight": False}], data["profit_flow"]["items"])
        self.assertEqual([{"name": "certification"}], data["moat_radar"]["dimensions"])
        self.assertEqual([{"node": "demand"}], data["logic_tree"])
        self.assertEqual({"market_believes": ["growth"]}, data["expectation_gap"])

    def test_composer_preserves_legacy_fields_and_adds_v3_layers(self) -> None:
        context = {
            "company": {"code": "600000", "name": "Test Co", "market": "A-share"},
            "trade": {"return_pct": 8.5, "trade_score": 72, "trades": [{"side": "buy"}]},
            "market": {"stock_pct_on_buy_day": 2.1},
            "market_catalyst": {
                "market_hype_reason": "order catalyst",
                "recent_catalysts": ["new order"],
                "evidence": ["announcement"],
            },
            "market_hype_reason": "order catalyst",
            "recent_catalysts": ["new order"],
        }
        wang = {
            "industry_rating": "A",
            "theme": "grid",
            "profit_flow": {"items": [{"name": "equipment", "share_pct": 35}]},
        }
        equity = {"investment_rating": "watch", "one_sentence_conclusion": "quality requires validation"}

        data = compose_workbench_data(context, wang, equity)

        for key in ("ai_final_answer", "answer_evidence", "research_layers", "source_trace"):
            self.assertIn(key, data)
        for legacy_key in ("hero", "profit_flow", "wang_agent", "public_equity_agent", "trade_review"):
            self.assertIn(legacy_key, data)
        self.assertEqual("A", data["hero"]["industry_rating"])
        self.assertEqual(35.0, data["profit_flow"]["items"][0]["share_pct"])
        self.assertEqual(wang, data["research_layers"]["wang_industry"])
        self.assertEqual(equity, data["research_layers"]["public_equity"])

    def test_source_trace_uses_only_allowed_sources(self) -> None:
        data = compose_workbench_data(
            {
                "company": {"code": "600000", "name": "Test Co"},
                "trade": {"trades": [{"side": "buy"}]},
                "market": {"recent_stock_performance": "last 20 trading days: 4.00%"},
                "market_catalyst": {
                    "market_hype_reason": "最近炒作原因待验证",
                    "recent_catalysts": [],
                    "evidence": [],
                    "agent_error": "search failed",
                },
                "market_hype_reason": "最近炒作原因待验证",
            },
            {"industry_rating": "missing", "agent_error": "wang failed"},
            {},
        )

        sources = {entry["source"] for entry in data["source_trace"].values()}
        self.assertTrue(sources <= SOURCE_TYPES)
        self.assertEqual("fallback", data["source_trace"]["research_layers.market_scout"]["source"])
        self.assertEqual("fallback", data["source_trace"]["research_layers.wang_industry"]["source"])
        self.assertEqual("missing", data["source_trace"]["hero.industry_rating"]["source"])
        self.assertEqual(
            "missing",
            data["source_trace"]["research_layers.market_scout.market_hype_reason"]["source"],
        )
        self.assertEqual("missing", data["source_trace"]["ai_final_answer.score"]["source"])

    def test_invalid_source_values_are_normalized_to_missing(self) -> None:
        data = merge_default_workbench({"source_trace": {"x": {"source": "guessed"}}})
        self.assertEqual({"source": "missing"}, data["source_trace"]["x"])

    def test_legacy_profile_adapter_does_not_recreate_fake_research(self) -> None:
        payload = workbench_to_profile_payload(merge_default_workbench({}))
        self.assertEqual([], payload["chain_nodes"])
        self.assertEqual([], payload["barriers"])
        self.assertEqual([], payload["profit_levers"])
        self.assertEqual([], payload["financial_validation"])


if __name__ == "__main__":
    unittest.main()
