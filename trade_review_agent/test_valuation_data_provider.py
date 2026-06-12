from __future__ import annotations

import unittest

import pandas as pd

from .valuation_data_provider import fetch_valuation_snapshot


class _FakeAkshare:
    def stock_value_em(self, *, symbol: str) -> pd.DataFrame:
        assert symbol == "000895"
        return pd.DataFrame(
            {
                "数据日期": pd.date_range("2026-01-01", periods=20),
                "PE(TTM)": list(range(1, 21)),
                "市净率": [value / 10 for value in range(1, 21)],
                "市销率": [value / 20 for value in range(1, 21)],
            }
        )

    def stock_zh_valuation_comparison_em(self, *, symbol: str) -> pd.DataFrame:
        assert symbol == "SZ000895"
        return pd.DataFrame({"代码": ["000895", "行业中值"], "EV/EBITDA-24A": [12.5, 18.5]})


class ValuationDataProviderTest(unittest.TestCase):
    def test_reads_current_metrics_and_calculates_history_percentiles(self) -> None:
        result = fetch_valuation_snapshot(
            "000895",
            akshare_loader=lambda: _FakeAkshare(),
            minimum_history=20,
        )

        self.assertEqual("available", result["status"])
        self.assertEqual(20.0, result["pe_ttm"])
        self.assertEqual(2.0, result["pb"])
        self.assertEqual(1.0, result["ps"])
        self.assertEqual(12.5, result["ev_ebitda"])
        self.assertEqual(100.0, result["pe_percentile"])
        self.assertEqual("2026-01-20", result["as_of"])

    def test_returns_missing_values_when_providers_fail(self) -> None:
        def fail() -> object:
            raise ModuleNotFoundError("akshare")

        result = fetch_valuation_snapshot("600000", akshare_loader=fail)

        self.assertEqual("unavailable", result["status"])
        self.assertIsNone(result["pe_ttm"])
        self.assertFalse(result["web_search_fallback"]["invoked"])
        self.assertIn("AKShare unavailable", result["errors"][0])

    def test_tencent_injection_only_fills_real_returned_values(self) -> None:
        result = fetch_valuation_snapshot(
            "600000",
            akshare_loader=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
            tencent_fetcher=lambda code: {"pe_ttm": 6.8, "pb": None, "as_of": "2026-06-12"},
        )

        self.assertEqual(6.8, result["pe_ttm"])
        self.assertIsNone(result["pb"])
        self.assertEqual("2026-06-12", result["as_of"])


if __name__ == "__main__":
    unittest.main()
