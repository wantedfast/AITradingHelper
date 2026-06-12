from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from . import workbench_context, workbench_news
from .workbench_composer import compose_workbench_data


class StructuredMarketFactsTests(unittest.TestCase):
    def test_structured_facts_preserve_supplied_metadata_with_llm_lineage(self) -> None:
        raw = {
            "market_hype_reason": "Order catalyst",
            "recent_catalysts": [
                {
                    "fact": "Company announced a new order",
                    "date": "2026-06-10",
                    "source": "https://example.test/announcement",
                }
            ],
            "industry_news": [
                {
                    "headline": "Sector demand improved",
                    "published_at": "2026-06-09",
                    "source": "Example News",
                }
            ],
            "evidence": ["Legacy evidence summary"],
        }

        result = workbench_news._normalize_market_catalyst(raw, "000001", "Target")

        self.assertEqual(["Company announced a new order"], result["recent_catalysts"])
        self.assertEqual("2026-06-10", result["market_catalyst"][0]["date"])
        self.assertEqual(
            "https://example.test/announcement",
            result["market_catalyst"][0]["source"],
        )
        self.assertEqual("llm", result["market_catalyst"][0]["source_type"])
        self.assertEqual("Example News", result["industry_news"][0]["source"])
        self.assertEqual("llm", result["source_trace"]["market_catalyst"]["source"])

    def test_legacy_strings_become_fact_objects_without_fake_metadata(self) -> None:
        result = workbench_news._normalize_market_catalyst(
            {
                "recent_catalysts": ["Unstructured catalyst"],
                "industry_news": "Unstructured news",
            },
            "000001",
            "Target",
        )

        self.assertEqual(
            {
                "fact": "Unstructured catalyst",
                "date": "",
                "source": "llm",
                "source_type": "llm",
            },
            result["market_catalyst"][0],
        )
        self.assertEqual("", result["industry_news"][0]["date"])
        self.assertEqual("llm", result["industry_news"][0]["source"])

    def test_disabled_news_context_returns_missing_structured_facts(self) -> None:
        with patch.dict(os.environ, {"WORKBENCH_NEWS_CONTEXT_ENABLED": "0"}):
            result = workbench_news.build_market_catalyst_context("000001", "Target")

        self.assertEqual([], result["market_catalyst"])
        self.assertEqual([], result["industry_news"])
        self.assertEqual(
            {"source": "missing"},
            result["source_trace"]["market_catalyst"],
        )

    def test_stock_context_keeps_legacy_and_structured_fields(self) -> None:
        catalyst = {
            "market_hype_reason": "Order catalyst",
            "recent_catalysts": ["Legacy catalyst"],
            "market_catalyst": [
                {
                    "fact": "Structured catalyst",
                    "date": "",
                    "source": "llm",
                    "source_type": "llm",
                }
            ],
            "industry_news": [
                {
                    "fact": "Structured industry news",
                    "date": "2026-06-11",
                    "source": "Publisher",
                    "source_type": "llm",
                }
            ],
            "unknowns": [],
            "evidence": [],
        }
        with patch.object(workbench_context, "build_market_catalyst_context", return_value=catalyst):
            result = workbench_context.build_stock_context(code="000001", name="Target")

        self.assertEqual(["Structured catalyst"], result["recent_catalysts"])
        self.assertEqual("Structured catalyst", result["market_catalyst_facts"][0]["fact"])
        self.assertEqual(["Structured industry news"], result["news"])
        self.assertEqual("llm", result["structured_news"][0]["source_type"])
        self.assertEqual(
            result["market_catalyst_facts"],
            result["market_catalyst"]["market_catalyst"],
        )

    def test_stock_context_converts_legacy_catalyst_strings_for_v3(self) -> None:
        legacy = {
            "market_hype_reason": "Legacy summary",
            "recent_catalysts": ["Legacy string catalyst"],
            "source_trace": {"market_catalyst": {"source": "fallback"}},
        }
        with patch.object(workbench_context, "build_market_catalyst_context", return_value=legacy):
            result = workbench_context.build_stock_context(code="000001", name="Target")

        fact = result["market_catalyst"]["market_catalyst"][0]
        self.assertEqual("Legacy string catalyst", fact["fact"])
        self.assertEqual("", fact["date"])
        self.assertEqual("fallback", fact["source"])
        self.assertEqual("fallback", fact["source_type"])
        self.assertEqual(["Legacy string catalyst"], result["recent_catalysts"])

    def test_composer_preserves_structured_facts_in_market_scout_layer(self) -> None:
        catalyst = {
            "market_hype_reason": "Order catalyst",
            "market_catalyst": [
                {
                    "fact": "Structured catalyst",
                    "date": "2026-06-10",
                    "source": "Publisher",
                    "source_type": "llm",
                }
            ],
            "industry_news": [
                {
                    "fact": "Structured industry news",
                    "date": "",
                    "source": "llm",
                    "source_type": "llm",
                }
            ],
        }
        context = {
            "company": {"code": "000001", "name": "Target"},
            "market_catalyst": catalyst,
            "recent_catalysts": ["Structured catalyst"],
            "news": ["Structured industry news"],
        }

        result = compose_workbench_data(context, {}, {})
        market_layer = result["research_layers"]["market_scout"]

        self.assertEqual("Structured catalyst", market_layer["market_catalyst"][0]["fact"])
        self.assertEqual("Structured industry news", market_layer["industry_news"][0]["fact"])
        self.assertEqual(
            "llm",
            result["source_trace"][
                "research_layers.market_scout.market_catalyst.0.fact"
            ]["source"],
        )


if __name__ == "__main__":
    unittest.main()
