from __future__ import annotations

import unittest

from .v3_market_scout import run_market_scout
from .v3_pipeline import run_v3_pipeline


class V3ProvenanceSemanticsTests(unittest.TestCase):
    def test_legacy_market_summary_without_provenance_is_fallback(self) -> None:
        result = run_market_scout(
            {
                "market_theme": "Legacy LLM summary",
                "market_catalyst": [{"fact": "Narrative without a source"}],
            }
        )

        self.assertEqual("fallback", result["source_trace"]["market_theme"]["source"])
        self.assertEqual("fallback", result["source_trace"]["market_catalyst"]["source"])

    def test_market_facts_inherit_explicit_provenance_per_field(self) -> None:
        result = run_market_scout(
            {
                "market_theme": "Grid investment",
                "sector_strength": {
                    "value": 3.2,
                    "unit": "pct",
                    "window": "20d",
                    "as_of": "2026-06-01",
                    "source": "market feed",
                },
                "source_trace": {
                    "market_theme": {"source": "llm"},
                    "sector_strength": {"source": "real_data"},
                },
            }
        )

        self.assertEqual("llm", result["source_trace"]["market_theme"]["source"])
        self.assertEqual("real_data", result["source_trace"]["sector_strength"]["source"])

    def test_fact_source_type_prevents_llm_summary_from_becoming_real_data(self) -> None:
        result = run_market_scout(
            {
                "market_catalyst": [
                    {
                        "fact": "Web result summarized by an LLM",
                        "source": "Publisher",
                        "source_type": "llm",
                    }
                ]
            }
        )

        self.assertEqual("llm", result["source_trace"]["market_catalyst"]["source"])

    def test_fallback_peer_provider_without_nested_trace_stays_fallback(self) -> None:
        result = run_market_scout(
            {
                "peer_snapshot": [
                    {
                        "code": "600001",
                        "name": "Cached Peer",
                        "metrics": {"return_1d_pct": 1.2},
                        "as_of": "2026-06-01",
                        "source": "fallback_existing",
                    }
                ]
            }
        )

        self.assertEqual("fallback", result["source_trace"]["peer_snapshot"]["source"])

    def test_unknown_peer_provider_without_nested_trace_stays_fallback(self) -> None:
        result = run_market_scout(
            {
                "peer_snapshot": [
                    {
                        "code": "600001",
                        "name": "Unknown Vendor Peer",
                        "metrics": {"return_1d_pct": 1.2},
                        "as_of": "2026-06-01",
                        "source": "some_vendor",
                    }
                ]
            }
        )

        self.assertEqual("fallback", result["source_trace"]["peer_snapshot"]["source"])

    def test_llm_output_and_input_fallback_keep_distinct_sources(self) -> None:
        result = run_market_scout(
            {
                "market_catalyst": [{"fact": "Legacy summary"}],
                "source_trace": {"market_catalyst": {"source": "fallback"}},
            },
            llm_caller=lambda _system, _user: {"market_theme": "LLM organized theme"},
        )

        self.assertEqual("llm", result["source_trace"]["market_theme"]["source"])
        self.assertEqual("fallback", result["source_trace"]["market_catalyst"]["source"])

    def test_trade_execution_unknown_sources_are_never_real_data(self) -> None:
        result = _pipeline(
            trade_execution={
                "trade_score": 72,
                "trade_execution_notes": {"main_lesson": "Wait for confirmation"},
            }
        )

        trace = result["source_trace"]
        self.assertEqual("fallback", trace["research_layers.trade_execution"]["source"])
        self.assertEqual(
            "fallback",
            trace["research_layers.trade_execution.trade_score"]["source"],
        )
        self.assertEqual(
            "fallback",
            trace[
                "research_layers.trade_execution.trade_execution_notes.main_lesson"
            ]["source"],
        )

    def test_trade_execution_preserves_mixed_leaf_provenance(self) -> None:
        result = _pipeline(
            trade_execution={
                "return_pct": 8.5,
                "rule_grade": "late entry",
                "summary": "LLM explanation",
                "source_trace": {
                    "return_pct": {"source": "real_data"},
                    "rule_grade": {"source": "hardcode"},
                    "summary": {"source": "llm"},
                },
            }
        )

        trace = result["source_trace"]
        self.assertEqual("fallback", trace["research_layers.trade_execution"]["source"])
        self.assertEqual(
            "real_data",
            trace["research_layers.trade_execution.return_pct"]["source"],
        )
        self.assertEqual(
            "hardcode",
            trace["research_layers.trade_execution.rule_grade"]["source"],
        )
        self.assertEqual(
            "llm",
            trace["research_layers.trade_execution.summary"]["source"],
        )
        self.assertNotIn("source_trace", result["research_layers"]["trade_execution"])

    def test_pipeline_accepts_external_full_path_provenance(self) -> None:
        result = _pipeline(
            trade_execution={"nested": {"price": 10.5, "note": "rule output"}},
            trade_execution_provenance={
                "research_layers.trade_execution.nested.price": {"source": "real_data"},
                "trade_execution.nested.note": {"source": "hardcode"},
            },
        )

        trace = result["source_trace"]
        self.assertEqual(
            "real_data",
            trace["research_layers.trade_execution.nested.price"]["source"],
        )
        self.assertEqual(
            "hardcode",
            trace["research_layers.trade_execution.nested.note"]["source"],
        )


def _pipeline(
    *,
    trade_execution: dict,
    trade_execution_provenance: dict | None = None,
) -> dict:
    return run_v3_pipeline(
        company={"code": "000001", "name": "Target"},
        market_facts={},
        wang={},
        public_equity={},
        trade_execution=trade_execution,
        trade_execution_provenance=trade_execution_provenance,
    )


if __name__ == "__main__":
    unittest.main()
