from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from trade_review_agent.industry_profiles import IndustryProfile
from trade_review_agent.presenter_agent import build_presenter_fallback_data
from trade_review_agent.validate_v3_contracts import audit_source_tree


def _profile_with_tempting_defaults() -> IndustryProfile:
    return IndustryProfile(
        code="000001",
        name="测试公司",
        theme="硬编码行业主题",
        core_driver="硬编码利润池",
        node="硬编码产业节点",
        sector_symbol="sh000300",
        chain_nodes=(("upstream", "硬编码上游", "硬编码解释"),),
        barriers=("硬编码壁垒",),
        profit_levers=("硬编码利润杠杆",),
        peers=("硬编码同行",),
        expectation_gap="硬编码预期差",
        valuation_odds="硬编码估值结论",
        catalysts=("硬编码催化剂",),
        disconfirming_signals=("硬编码风险",),
        position_sizing="硬编码仓位建议",
        one_sentence_thesis="硬编码投资结论",
        rerating_anchor="硬编码重估锚",
        best_expression="硬编码最佳表达",
        wang_investor_report="硬编码 WANG 报告",
        public_equity_report="硬编码权益报告",
    )


class PresenterV3TruthfulnessTest(unittest.TestCase):
    def test_missing_research_is_not_synthesized_from_profile(self) -> None:
        result = build_presenter_fallback_data(
            workbench={"company": {"name": "测试公司", "code": "000001"}},
            profile=_profile_with_tempting_defaults(),
            analysis={},
            trade_frame=pd.DataFrame(),
        )

        self.assertIsNone(result["hero"]["industry_rating"])
        self.assertIsNone(result["hero"]["investment_rating"])
        self.assertIsNone(result["expectation_gap"]["gap_score"])
        self.assertEqual(result["profit_flow"]["items"], [])
        self.assertEqual(result["logic_tree"], [])
        self.assertEqual(result["moat"]["dimensions"], [])
        self.assertEqual(result["moat"]["items"], [])
        self.assertNotIn("硬编码投资结论", result["one_sentence_conclusion"])
        self.assertNotIn("硬编码估值结论", result["valuation_odds"])
        self.assertEqual(result["presenter_provenance"]["role"], "expression_only")

    def test_v3_conclusions_and_provenance_are_copied_verbatim(self) -> None:
        final_answer = {
            "score": 84,
            "verdict": "行业选对，公司选错",
            "better_choice": "候选公司",
            "main_reason": "订单质量更高",
            "mistake_source": "选股",
            "next_action": "验证订单和估值",
        }
        source_trace = {
            "ai_final_answer.score": {"source": "llm"},
            "ai_final_answer.verdict": {"source": "llm"},
        }
        result = build_presenter_fallback_data(
            workbench={
                "company": {"name": "测试公司", "code": "000001"},
                "ai_final_answer": final_answer,
                "source_trace": source_trace,
            },
            profile=_profile_with_tempting_defaults(),
            analysis={},
            trade_frame=pd.DataFrame(),
        )

        self.assertEqual(result["ai_final_answer"], final_answer)
        self.assertEqual(result["source_trace"], source_trace)

    def test_presenter_source_has_no_truthfulness_findings(self) -> None:
        root = Path(__file__).resolve().parents[1]
        issues = audit_source_tree(root)
        presenter_issues = [
            issue for issue in issues if "presenter_agent.py" in issue.location
        ]
        self.assertEqual(presenter_issues, [])


if __name__ == "__main__":
    unittest.main()
