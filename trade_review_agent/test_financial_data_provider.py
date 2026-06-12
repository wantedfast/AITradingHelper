from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from .financial_data_provider import FinancialDataProvider, normalize_financial_frames


class FinancialNormalizationTests(unittest.TestCase):
    def test_normalizes_latest_period_and_calculates_supported_fields(self) -> None:
        abstract = pd.DataFrame(
            [
                {"指标": "营业总收入", "20231231": 900.0, "20241231": 1000.0},
                {"指标": "营业成本", "20231231": 630.0, "20241231": 700.0},
                {"指标": "归母净利润", "20231231": 90.0, "20241231": 120.0},
                {"指标": "经营活动产生的现金流量净额", "20231231": 110.0, "20241231": 150.0},
                {
                    "指标": "购建固定资产、无形资产和其他长期资产支付的现金",
                    "20231231": 30.0,
                    "20241231": 40.0,
                },
                {"指标": "负债合计", "20231231": 360.0, "20241231": 400.0},
                {"指标": "资产总计", "20231231": 800.0, "20241231": 1000.0},
            ]
        )
        indicators = pd.DataFrame(
            [
                {
                    "日期": "2024-12-31",
                    "主营业务收入增长率(%)": 11.1,
                    "净利润增长率(%)": 33.3,
                    "加权净资产收益率(%)": 14.2,
                }
            ]
        )

        result = normalize_financial_frames(
            "600000",
            {"abstract": abstract, "indicators": indicators},
            provider="akshare",
        )

        self.assertEqual("ok", result["status"])
        self.assertEqual(1000.0, result["revenue"])
        self.assertEqual(11.1, result["revenue_growth"])
        self.assertEqual(120.0, result["net_profit"])
        self.assertAlmostEqual(30.0, result["gross_margin"])
        self.assertEqual(150.0, result["operating_cash_flow"])
        self.assertEqual(110.0, result["free_cash_flow"])
        self.assertEqual(400.0, result["total_liabilities"])
        self.assertEqual(40.0, result["debt_to_assets"])
        self.assertEqual(14.2, result["roe"])
        self.assertEqual("real_data", result["source_trace"]["revenue"]["source"])
        self.assertEqual("verified", result["source_trace"]["revenue"]["status"])
        self.assertEqual("calculated:operating_cash_flow-capital_expenditure", result["source_trace"]["free_cash_flow"]["dataset"])

    def test_missing_values_remain_none_with_field_level_trace(self) -> None:
        result = normalize_financial_frames(
            "000001",
            {"indicators": pd.DataFrame([{"日期": "2025-03-31", "净资产收益率(%)": 3.2}])},
            provider="akshare",
        )

        self.assertEqual("partial", result["status"])
        self.assertEqual(3.2, result["roe"])
        self.assertIsNone(result["revenue"])
        self.assertEqual("missing", result["source_trace"]["revenue"]["source"])
        self.assertEqual("missing", result["source_trace"]["revenue"]["status"])
        self.assertEqual("real_data", result["source_trace"]["roe"]["source"])


class FinancialProviderFallbackTests(unittest.TestCase):
    def test_akshare_failure_uses_injected_verified_tencent_adapter(self) -> None:
        def failed_akshare(code: str):
            raise ConnectionError("network unavailable")

        def verified_tencent(code: str):
            return {
                "verified_financials": pd.DataFrame(
                    [{"报告日期": "2025-03-31", "营业收入": 88.0, "净利润": 9.0}]
                )
            }

        with tempfile.TemporaryDirectory() as tmp:
            provider = FinancialDataProvider(
                Path(tmp) / "cache.sqlite",
                akshare_fetcher=failed_akshare,
                tencent_fetcher=verified_tencent,
            )
            result = provider.get_financials("sh600000")

        self.assertEqual("partial", result["status"])
        self.assertEqual("tencent_finance", result["provider"])
        self.assertEqual(88.0, result["revenue"])
        self.assertTrue(any("network unavailable" in error for error in result["errors"]))
        self.assertEqual("error", result["provider_attempts"][0]["status"])
        self.assertEqual("partial", result["provider_attempts"][1]["status"])

    def test_default_tencent_financial_source_is_explicitly_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = FinancialDataProvider(
                Path(tmp) / "cache.sqlite",
                akshare_fetcher=lambda code: {},
            )
            result = provider.get_financials("000001")

        self.assertEqual("missing", result["status"])
        self.assertIsNone(result["revenue"])
        self.assertEqual("skipped", result["provider_attempts"][-1]["status"])
        self.assertIn("not verified financial statements", result["provider_attempts"][-1]["detail"])
        self.assertFalse(result["web_search_fallback"]["invoked"])

    def test_network_failure_falls_back_to_cache_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.sqlite"
            seed = FinancialDataProvider(
                cache,
                akshare_fetcher=lambda code: {
                    "abstract": pd.DataFrame([{"指标": "营业总收入", "20241231": 123.0}])
                },
            )
            self.assertEqual(123.0, seed.get_financials("600000")["revenue"])

            fallback = FinancialDataProvider(
                cache,
                cache_ttl=pd.Timedelta(microseconds=-1).to_pytimedelta(),
                akshare_fetcher=lambda code: (_ for _ in ()).throw(TimeoutError("timed out")),
            )
            result = fallback.get_financials("600000")

        self.assertEqual("fallback", result["status"])
        self.assertEqual(123.0, result["revenue"])
        self.assertEqual("fallback", result["source_trace"]["revenue"]["source"])
        self.assertEqual("stale_cache", result["source_trace"]["revenue"]["status"])
        self.assertTrue(any("timed out" in error for error in result["errors"]))

    def test_web_search_protocol_is_reserved_but_never_called(self) -> None:
        class SearchFallback:
            def __init__(self) -> None:
                self.calls = 0

            def fetch(self, code: str):
                self.calls += 1
                return {"revenue": 999}

        search = SearchFallback()
        with tempfile.TemporaryDirectory() as tmp:
            provider = FinancialDataProvider(
                Path(tmp) / "cache.sqlite",
                akshare_fetcher=lambda code: {},
                web_search_fallback=search,
            )
            result = provider.get_financials("600000")

        self.assertEqual(0, search.calls)
        self.assertTrue(result["web_search_fallback"]["available"])
        self.assertFalse(result["web_search_fallback"]["invoked"])


if __name__ == "__main__":
    unittest.main()
