import unittest

from trade_review_agent.market.stock_resolver import resolve_stock_code


class StockResolverTest(unittest.TestCase):
    def test_resolves_known_chinese_stock_names_without_fetch(self):
        self.assertEqual(resolve_stock_code("冰轮环境", allow_fetch=False), "000811")
        self.assertEqual(resolve_stock_code("中国巨石", allow_fetch=False), "600176")
        self.assertEqual(resolve_stock_code("长电科技", allow_fetch=False), "600584")

    def test_extracts_code_from_mixed_stock_input(self):
        self.assertEqual(resolve_stock_code("长电科技 600584", allow_fetch=False), "600584")


if __name__ == "__main__":
    unittest.main()
