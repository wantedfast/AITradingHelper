from __future__ import annotations

import unittest

from trade_review_agent.workbench_report_renderer import render_workbench_report


class WorkbenchReportRendererTruthfulnessTests(unittest.TestCase):
    def test_missing_research_stays_visibly_missing(self) -> None:
        html = render_workbench_report(
            {
                "company": {"code": "000001", "name": "测试公司"},
                "hero": {},
                "profit_flow": {},
                "expectation_gap": {},
                "logic_tree": [],
            }
        )

        self.assertIn("产业评级 待验证", html)
        self.assertIn("投资评级 待验证", html)
        self.assertIn("<b>待验证</b><span>预期差</span>", html)
        self.assertIn('<p class="muted">待验证</p>', html)
        self.assertIn("<h3>尚未生成</h3><b>待验证</b>", html)
        self.assertNotIn("产业评级 B", html)
        self.assertNotIn("投资评级 B", html)
        self.assertNotIn("价值池 100%", html)

    def test_legacy_presenter_values_are_rendered_without_recalculation(self) -> None:
        html = render_workbench_report(
            {
                "company": {"code": "000001", "name": "测试公司"},
                "hero": {
                    "industry_rating": "A",
                    "investment_rating": "C",
                },
                "profit_flow": {
                    "value_pool": "设备收入",
                    "items": [{"name": "核心设备", "share_pct": 42, "highlight": True}],
                },
                "expectation_gap": {"gap_score": 73},
                "logic_tree": [{"node": "订单增长", "certainty_pct": 61}],
            }
        )

        self.assertIn("产业评级 A", html)
        self.assertIn("投资评级 C", html)
        self.assertIn("<b>73</b><span>预期差</span>", html)
        self.assertIn("width:42.0%", html)
        self.assertIn("<b>42%</b>", html)
        self.assertIn("<h3>订单增长</h3><b>61%</b>", html)

    def test_partial_legacy_items_do_not_receive_invented_percentages(self) -> None:
        html = render_workbench_report(
            {
                "company": {"name": "测试公司"},
                "profit_flow": {"items": [{"name": "核心设备"}]},
                "logic_tree": [{"node": "订单增长"}],
            }
        )

        self.assertIn("<span>核心设备</span><div class=\"bar\"></div><b>待验证</b>", html)
        self.assertIn("<h3>订单增长</h3><b>待验证</b>", html)


if __name__ == "__main__":
    unittest.main()
