from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from .industry_coverage import build_industry_coverage
from .workbench_context import build_stock_context


class IndustryCoverageTests(unittest.TestCase):
    def test_manufacturing_requires_manufacturing_kpis(self) -> None:
        result = build_industry_coverage(
            company={"sector": "工业机械制造"},
            context={
                "financials": {"revenue_growth": 12.3, "gross_margin": "pending fetch"},
                "operations": {"order_backlog": 8.2},
            },
        )

        self.assertEqual("manufacturing", result["family"])
        self.assertEqual(["revenue_growth", "order_backlog"], result["available_kpis"])
        self.assertIn("capacity_utilization", result["missing_kpis"])
        self.assertGreater(result["confidence"], 0)

    def test_financials_do_not_receive_manufacturing_kpis(self) -> None:
        result = build_industry_coverage(
            profile=SimpleNamespace(theme="银行金融", sector="银行"),
            context={"financials": {"net_interest_margin": 1.8}},
        )

        self.assertEqual("financials", result["family"])
        self.assertIn("net_interest_margin", result["required_kpis"])
        self.assertNotIn("capacity_utilization", result["required_kpis"])
        self.assertEqual(["net_interest_margin"], result["available_kpis"])

    def test_cross_industry_profiles_get_distinct_kpi_sets(self) -> None:
        cases = {
            "software_internet": "企业软件 SaaS",
            "healthcare": "创新药医药",
            "consumer": "食品饮料消费",
            "resources_utilities": "电力公用事业",
        }

        results = {
            family: build_industry_coverage(company={"theme": theme})
            for family, theme in cases.items()
        }

        for expected, result in results.items():
            self.assertEqual(expected, result["family"])
        self.assertIn("annual_recurring_revenue", results["software_internet"]["required_kpis"])
        self.assertIn("clinical_milestones", results["healthcare"]["required_kpis"])
        self.assertIn("same_store_sales_growth", results["consumer"]["required_kpis"])
        self.assertIn("production_volume", results["resources_utilities"]["required_kpis"])

    def test_unknown_never_inherits_manufacturing_requirements(self) -> None:
        result = build_industry_coverage(
            company={"code": "000001", "name": "A Company"},
            context={"financials": {"revenue_growth": 10}},
        )

        self.assertEqual("unknown", result["family"])
        self.assertEqual([], result["required_kpis"])
        self.assertEqual([], result["available_kpis"])
        self.assertEqual([], result["missing_kpis"])
        self.assertEqual(0.0, result["confidence"])
        self.assertNotIn("capacity_utilization", result["required_kpis"])

    def test_company_name_is_not_used_for_classification(self) -> None:
        result = build_industry_coverage(
            company={"name": "某某银行股份有限公司", "code": "000001"},
        )

        self.assertEqual("unknown", result["family"])

    def test_conflicting_metadata_is_unknown(self) -> None:
        result = build_industry_coverage(
            company={"sector": "银行", "theme": "企业软件"},
        )

        self.assertEqual("unknown", result["family"])
        self.assertIn("conflicting explicit metadata", result["source"])

    def test_stock_context_embeds_coverage_without_breaking_existing_calls(self) -> None:
        catalyst = {
            "market_catalyst": [],
            "industry_news": [],
            "unknowns": [],
            "evidence": [],
        }
        with patch(
            "trade_review_agent.workbench_context.build_market_catalyst_context",
            return_value=catalyst,
        ):
            result = build_stock_context(
                code="000001",
                name="Target",
                financial_snapshot={"status": "missing"},
                valuation_snapshot={"status": "unavailable"},
                company_metadata={"sector": "医疗器械"},
            )

        coverage = result["industry_coverage"]
        self.assertEqual("healthcare", coverage["family"])
        self.assertIn("regulatory_status", coverage["required_kpis"])


    def test_stock_context_exposes_provider_snapshots(self) -> None:
        with patch(
            "trade_review_agent.workbench_context.build_market_catalyst_context",
            return_value={"market_catalyst": [], "industry_news": []},
        ):
            result = build_stock_context(
                code="000895",
                name="Target",
                financial_snapshot={
                    "status": "partial",
                    "provider": "akshare",
                    "revenue_growth": 12.5,
                    "operating_cash_flow": 150.0,
                },
                valuation_snapshot={
                    "status": "available",
                    "provider": "akshare.stock_value_em",
                    "pe_ttm": 20.0,
                    "pb": 2.0,
                    "ps": 1.0,
                    "ev_ebitda": 12.5,
                    "pe_percentile": 80.0,
                },
            )

        self.assertEqual(12.5, result["financials"]["revenue_growth"])
        self.assertEqual(150.0, result["financials"]["cash_flow"])
        self.assertEqual(20.0, result["financials"]["pe_ttm"])
        self.assertEqual("akshare", result["financial_data"]["provider"])
        self.assertEqual("akshare.stock_value_em", result["valuation"]["provider"])


if __name__ == "__main__":
    unittest.main()
