import json
import time
import unittest
from pathlib import Path

from trade_review_agent.review.final_wang_agent.presenter import present_wang_research_result


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = PROJECT_ROOT / "trade_review_agent" / "review" / "final_wang_agent" / "agent.py"


def _usage_summary(_usage):
    return {}


def _present(answer: str, stock_name: str = "东材科技"):
    return present_wang_research_result(
        {
            "trade": {"stock_name": stock_name, "stock_code": "601208"},
            "answer": answer.strip(),
            "doubao_cost": {},
            "judge_cost": {},
            "seconds": {},
            "models": {},
            "doubao_response": {},
            "judge_response": {},
        },
        usage_token_summary=_usage_summary,
        usd_cny=7.2,
        total_started=time.perf_counter(),
    )


class FinalWangPresenterTest(unittest.TestCase):
    def test_structured_json_answer_maps_without_markdown_heuristics(self):
        answer = json.dumps(
            {
                "schemaVersion": "wang_review_v1",
                "finalJudgment": {
                    "summary": "方向买对，执行和标的优先级需要优化。",
                    "tradeCorrectness": {
                        "score": 80,
                        "boughtRight": "基本买对。",
                        "rightReasons": "踩中 AI 算力硬件到 PCB 的主线。",
                        "wrongReasons": "没有买到当天辨识度最高的核心标的。",
                    },
                    "entryQuality": {
                        "score": 60,
                        "judgment": "买点合格但不够优。",
                        "timing": "09:25 好于 09:32。",
                        "riskReward": "追高后盈亏比下降。",
                        "confirmation": "开盘确认后才追入。",
                        "betterPosition": "应等待换手确认。",
                    },
                    "mainlinePosition": {
                        "score": 60,
                        "level": "主线分支",
                        "reason": "属于 PCB 上游材料，不是板块最高辨识度龙头。",
                    },
                    "improvement": {
                        "wouldBuyAgain": "可以买，但不能当第一优先级。",
                        "shouldSwitchStrongerTarget": "应该优先看泰坦股份和泰和新材。",
                        "biggestMistake": "把材料弹性票当成日内核心龙头。",
                        "biggestCorrectPoint": "方向判断正确。",
                    },
                    "totalScore": 70,
                },
                "tradeLogic": "资金交易的是 AI 服务器带动 PCB 上游材料需求。",
                "industryChain": {
                    "text": "AI服务器 → PCB → 覆铜板 → 树脂材料 → 东材科技",
                    "nodes": ["AI服务器", "PCB", "覆铜板", "树脂材料", "东材科技"],
                },
                "barrierAndProfitFlow": {
                    "barrier": "高速电子树脂验证度较高。",
                    "profitFlow": "利润先流向 PCB 和覆铜板，树脂材料属于后排扩散。",
                },
                "peerComparison": [
                    {
                        "rank": 1,
                        "name": "泰坦股份",
                        "reason": "情绪总龙头。",
                        "tradeMeaning": "短线优先交易最高情绪溢价。",
                    },
                    {
                        "rank": 2,
                        "name": "泰和新材",
                        "reason": "板块连板高标。",
                        "tradeMeaning": "确认板块强度。",
                    },
                ],
                "rerunChoice": {
                    "priority": ["泰坦股份", "泰和新材", "东材科技"],
                    "currentStockRank": "东材科技排在前五名之外。",
                    "reason": "重来优先买辨识度更高的情绪核心。",
                },
                "oneLineConclusion": "买对方向，但没有买到最核心。",
            },
            ensure_ascii=False,
        )

        payload = _present(answer)

        self.assertEqual(payload["presenter_contract"], "answer_first_v3_json_evidence")
        self.assertEqual(payload["review"]["verdict"]["text"], "买对方向，但没有买到最核心。")
        self.assertEqual(
            [(item["key"], item["value"]) for item in payload["review"]["scores"]["items"]],
            [
                ("tradeCorrectness", 8),
                ("entryQuality", 6),
                ("mainlineStrength", 6),
                ("total", 7),
            ],
        )
        judgment_text = "\n".join(item["text"] for item in payload["review"]["judgments"]["items"])
        self.assertIn("买对了吗：基本买对。", judgment_text)
        self.assertIn("是否应该换成更强标的：应该优先看泰坦股份和泰和新材。", judgment_text)
        self.assertEqual(payload["bestChoice"]["name"], "泰坦股份")
        self.assertIn("情绪总龙头", payload["bestChoice"]["ranking"][0]["reason"])
        self.assertEqual(
            [item["label"] for item in payload["themeAnalysis"]["industryChain"]["nodes"]],
            ["AI服务器", "PCB", "覆铜板", "树脂材料", "东材科技"],
        )
        self.assertIn("利润先流向 PCB", payload["themeAnalysis"]["profitFlow"]["text"])
        self.assertEqual(payload["audit"]["missing_fields"], [])
        self.assertEqual(
            payload["audit"]["evidence_map"]["finalJudgment.tradeCorrectness.score"]["evidence"],
            "80",
        )

    def test_structured_json_v2_maps_dual_rankings_and_rerun_choices(self):
        answer = json.dumps(
            {
                "schemaVersion": "wang_review_v2",
                "finalJudgment": {
                    "tradeCorrectness": {
                        "score": 80,
                        "boughtRight": "基本买对。",
                        "rightReasons": "踩中主线。",
                        "wrongReasons": "没有买到最强。",
                        "summary": "方向对标的不强",
                    },
                    "entryQuality": {
                        "score": 60,
                        "judgment": "合格。",
                        "isBestEntry": "不是最佳。",
                        "timing": "偏追。",
                        "riskReward": "一般。",
                        "confirmation": "确认后追入。",
                        "isChasing": "有追涨。",
                        "betterPosition": "等换手。",
                        "summary": "买点偏追",
                    },
                    "mainlinePosition": {
                        "score": 70,
                        "level": "主线强分支",
                        "reason": "在主线内但不是总龙头。",
                        "summary": "主线强分支",
                    },
                    "improvement": {
                        "wouldBuyAgain": "会买但降优先级。",
                        "biggestCorrectPoint": "方向正确。",
                        "biggestMistake": "错把分支当核心。",
                        "summary": "重来换核心",
                    },
                    "totalScore": 73,
                    "totalSummary": "买对方向输在优先级",
                },
                "tradeLogic": {
                    "coreLogic": "资金买主线扩散。",
                    "catalyst": "PCB 涨价。",
                    "performanceValidation": "收入高增。",
                    "capitalRecognition": "涨停确认。",
                    "summary": "主线扩散交易",
                },
                "industryChain": {
                    "text": "AI服务器 ↓ PCB ↓ 树脂材料 ↓ 东材科技",
                    "nodes": ["AI服务器", "PCB", "树脂材料", "东材科技"],
                    "position": "上游材料。",
                    "benefitReason": "需求扩散。",
                    "summary": "上游材料受益",
                },
                "barrierAndProfitFlow": {
                    "technologyBarrier": "高速树脂。",
                    "customerCertificationBarrier": "认证周期长。",
                    "domesticSubstitutionBarrier": "国产替代。",
                    "scaleBarrier": "产能约束。",
                    "profitFlow": "先流向 PCB 核心，再扩散到材料。",
                    "isProfitCenter": "不是主要利润中心。",
                    "positionType": "利润扩散受益者",
                    "summary": "非利润核心",
                },
                "companyComparison": {
                    "shortTermCapitalRanking": [
                        {
                            "rank": 1,
                            "name": "泰坦股份",
                            "reason": "资金辨识度最高。",
                            "weakness": "产业链正宗度不足。",
                            "tradeMeaning": "短线优先。",
                        }
                    ],
                    "industryValueRanking": [
                        {
                            "rank": 1,
                            "name": "生益科技",
                            "reason": "覆铜板核心。",
                            "weakness": "弹性可能不如小票。",
                            "tradeMeaning": "产业优先。",
                        }
                    ],
                    "summary": "短线产业分开看",
                },
                "rerunChoice": {
                    "shortTermFirstChoice": "泰坦股份",
                    "industryFirstChoice": "生益科技",
                    "priority": ["泰坦股份", "生益科技", "东材科技"],
                    "currentStockRank": "东材科技短线排后。",
                    "reason": "重来短线买辨识度，产业买核心环节。",
                    "summary": "短线换龙头",
                },
                "oneLineConclusion": "📌 买对主线，没买到最强",
            },
            ensure_ascii=False,
        )

        payload = _present(answer)

        self.assertEqual(payload["bestChoice"]["name"], "泰坦股份")
        self.assertIn("资金辨识度最高", payload["bestChoice"]["ranking"][0]["reason"])
        self.assertIn("短线优先买谁：泰坦股份", payload["review"]["nextActions"]["items"][0]["text"])
        self.assertIn("产业链优先买谁：生益科技", payload["review"]["nextActions"]["items"][0]["text"])
        self.assertIn(
            "companyComparison.industryValueRanking[0]",
            payload["audit"]["evidence_map"],
        )
        self.assertIn("利润扩散受益者", payload["themeAnalysis"]["profitFlow"]["text"])

    def test_empty_raw_markdown_does_not_fill_primary_contract(self):
        payload = _present("")

        self.assertEqual(payload["presenter_contract"], "answer_first_v2_strict_evidence")
        self.assertIsNone(payload["review"]["verdict"])
        self.assertEqual(payload["review"]["scores"]["items"], [])
        self.assertEqual(payload["review"]["judgments"]["items"], [])
        self.assertEqual(payload["review"]["items"], [])
        self.assertEqual(payload["review"]["nextActions"]["items"], [])
        self.assertFalse(payload["bestChoice"]["available"])
        self.assertIsNone(payload["bestChoice"]["name"])
        self.assertEqual(payload["bestChoice"]["ranking"], [])
        self.assertEqual(payload["themeAnalysis"]["industryChain"]["nodes"], [])
        self.assertIsNone(payload["themeAnalysis"]["profitFlow"]["text"])
        self.assertIsNone(payload["tradeLogic"]["text"])
        self.assertEqual(payload["audit"]["evidence_map"], {})
        self.assertEqual(payload["audit"]["confidence"], {})
        self.assertIn("raw markdown is empty", payload["audit"]["parser_warnings"])

    def test_new_final_judgment_scores_are_mapped_only_from_raw_score_lines(self):
        answer = """
一、最终判断

1. 交易正确性
- 买对了吗？买对了。
- 买对在哪里？踩中 AI 硬件主线。
- 买错在哪里？标的不是最强辨识度。

评分：
**交易正确性：82分**

2. 买点质量
- 买点质量如何？09:25 优于 09:32，整体合格。

评分：
**买点质量：68分**

3. 主线地位
- 判断：主线强分支。

评分：
**主线强度：72分**

4. 是否有值得改进的地方
- 如果重来一次还会不会买？会买，但降低仓位。
- 是否应该换成更强标的？可以优先看金安国纪。
- 最大错误是什么？追在一致性过高的位置。
- 最大正确点是什么？方向判断正确。

5. 综合评分
**综合评分：76分**
"""
        payload = _present(answer)

        self.assertEqual(
            [(item["key"], item["value"]) for item in payload["review"]["scores"]["items"]],
            [
                ("tradeCorrectness", 8.2),
                ("entryQuality", 6.8),
                ("mainlineStrength", 7.2),
                ("total", 7.6),
            ],
        )
        self.assertEqual(
            [item["label"] for item in payload["review"]["judgments"]["items"]],
            ["交易正确性", "买点质量", "主线地位", "是否有值得改进的地方"],
        )
        judgment_text = "\n".join(item["text"] for item in payload["review"]["judgments"]["items"])
        self.assertIn("买对了吗？买对了。", judgment_text)
        self.assertIn("最大错误是什么？追在一致性过高的位置。", judgment_text)
        self.assertNotIn("交易正确性：82分", judgment_text)
        self.assertNotIn("评分标准", judgment_text)

        audit = payload["audit"]
        for path in (
            "review.scores.items[0].value",
            "review.scores.items[1].value",
            "review.scores.items[2].value",
            "review.scores.items[3].value",
            "review.judgments.items[0].text",
            "review.judgments.items[3].text",
        ):
            self.assertIn(path, audit["evidence_map"])
            self.assertEqual(audit["evidence_map"][path]["sourceSection"], "最终判断")

    def test_weighted_v5_score_lines_are_mapped(self):
        payload = _present(
            """
一、最终判断

**综合评分：72分。**
- **方向判断 (30分): 29分**。精准命中主线。
- **买点质量 (30分): 15分**。买点偏差。
- **标的选择 (20分): 18分**。选中核心。
- **产业链优势 (20分): 20分**。产业位置正确。
"""
        )

        self.assertEqual(
            [(item["key"], item["label"], item["value"]) for item in payload["review"]["scores"]["items"]],
            [
                ("directionJudgment", "方向判断", 2.9),
                ("entryQuality", "买点质量", 1.5),
                ("targetSelection", "标的选择", 1.8),
                ("industryChainAdvantage", "产业链优势", 2),
                ("total", "综合评分", 7.2),
            ],
        )
        for index in range(5):
            evidence = payload["audit"]["evidence_map"][f"review.scores.items[{index}].value"]["evidence"]
            self.assertIn("分", evidence)

    def test_missing_score_lines_do_not_create_scores(self):
        payload = _present(
            """
一、最终判断
- **买对了吗？**：买对了方向。
"""
        )

        self.assertEqual(payload["review"]["scores"]["items"], [])
        self.assertIn("review.scores.items", payload["audit"]["missing_fields"])

    def test_updated_replay_question_maps_and_old_wording_stays_compatible(self):
        updated = _present(
            """
一、最终判断
- 如果重来一次应该如何交易？等待分歧换手后再参与。
"""
        )
        legacy = _present(
            """
一、最终判断
- 是否值得重来一次继续买？可以买，但降低优先级。
"""
        )

        self.assertEqual(updated["review"]["items"][0]["key"], "replayDecision")
        self.assertEqual(updated["review"]["items"][0]["text"], "等待分歧换手后再参与。")
        self.assertEqual(legacy["review"]["items"][0]["key"], "replayDecision")
        self.assertEqual(legacy["review"]["items"][0]["text"], "可以买，但降低优先级。")

    def test_explicit_fields_are_traceable_and_no_evidence_leaks_to_ui_contract(self):
        answer = """
一、买对了吗？
方向买对了，但标的不是最核心。

二、买点质量如何？
买点偏高，确认不足。

二、交易逻辑
资金交易的是 AI 服务器带动高速 PCB 材料需求，而不是泛概念标签。

五、同行比较
第一名：金安国纪
理由：PCB 龙头，资金辨识度更高。
第二名：东材科技
理由：材料扩散受益，但优先级靠后。

六、如果重来一次
规则1：等待换手确认后再买。
规则2：非龙头不重仓。

七、一句话结论
方向正确，标的优先级和买点执行需要优化。

三、产业链位置
AI服务器 → PCB → 覆铜板 → 树脂材料

四、壁垒和利润流向
利润流向：利润先集中在 PCB 核心环节，再向覆铜板和树脂材料扩散。
""".strip()
        payload = _present(answer)

        self.assertEqual(payload["review"]["verdict"]["text"], "方向正确，标的优先级和买点执行需要优化。")
        self.assertEqual([item["key"] for item in payload["review"]["items"]], ["buyCorrect", "entryQuality"])
        self.assertEqual(
            [item["text"] for item in payload["review"]["nextActions"]["items"]],
            ["等待换手确认后再买。", "非龙头不重仓。"],
        )
        self.assertTrue(payload["bestChoice"]["available"])
        self.assertEqual(payload["bestChoice"]["name"], "金安国纪")
        self.assertEqual(payload["bestChoice"]["summary"], "PCB 龙头，资金辨识度更高。")
        self.assertEqual(
            [item["name"] for item in payload["bestChoice"]["ranking"]],
            ["金安国纪", "东材科技"],
        )
        self.assertEqual(
            [item["name"] for item in payload["themeAnalysis"]["industryChain"]["nodes"]],
            ["AI服务器", "PCB", "覆铜板", "树脂材料"],
        )
        self.assertEqual(
            payload["themeAnalysis"]["profitFlow"]["text"],
            "利润先集中在 PCB 核心环节，再向覆铜板和树脂材料扩散。",
        )
        self.assertEqual(
            payload["tradeLogic"]["text"],
            "资金交易的是 AI 服务器带动高速 PCB 材料需求，而不是泛概念标签。",
        )
        self.assertEqual(
            payload["audit"]["evidence_map"]["tradeLogic.text"]["sourceSection"],
            "交易逻辑",
        )

        audit = payload["audit"]
        for path, source in audit["evidence_map"].items():
            with self.subTest(path=path):
                self.assertIn(source["evidence"], answer)
                self.assertTrue(source["sourceSection"])
                self.assertIn(audit["confidence"][path], {"high", "medium", "low"})

        display_payload = {
            "review": payload["review"],
            "bestChoice": payload["bestChoice"],
            "tradeLogic": payload["tradeLogic"],
            "themeAnalysis": payload["themeAnalysis"],
        }
        self.assertNotIn("sourceSection", repr(display_payload))
        self.assertNotIn("evidence", repr(display_payload))
        self.assertNotIn("confidence", repr(display_payload))

    def test_profit_flow_is_text_only_without_numeric_business_layers(self):
        payload = _present(
            """
题材分析
产业链：算力需求 → PCB → 覆铜板。
利润流向：利润主要集中在 PCB 和覆铜板环节。
"""
        )

        self.assertEqual(
            [item["name"] for item in payload["themeAnalysis"]["industryChain"]["nodes"]],
            ["算力需求", "PCB", "覆铜板"],
        )
        self.assertEqual(payload["themeAnalysis"]["profitFlow"]["text"], "利润主要集中在 PCB 和覆铜板环节。")
        primary = {
            "review": payload["review"],
            "bestChoice": payload["bestChoice"],
            "themeAnalysis": payload["themeAnalysis"],
        }
        self.assertEqual(payload["review"]["scores"]["items"], [])
        self.assertNotIn("value", repr(primary))
        self.assertNotIn("inferred", repr(primary))

    def test_generic_best_choice_stays_unavailable_and_no_default_actions(self):
        payload = _present(
            """
同行比较
第一名：更高辨识度核心票
理由：优先选择资金最先攻击的方向。

如果重来一次
优先买：更高辨识度核心票。
不要追高。
"""
        )

        self.assertFalse(payload["bestChoice"]["available"])
        self.assertIsNone(payload["bestChoice"]["name"])
        self.assertEqual(payload["bestChoice"]["ranking"], [])
        self.assertEqual(payload["review"]["nextActions"]["items"], [{"text": "不要追高。"}])
        self.assertIn("bestChoice.name", payload["audit"]["missing_fields"])
        self.assertNotIn("bestChoice.name", payload["audit"]["evidence_map"])
        self.assertTrue(payload["audit"]["parser_warnings"])

    def test_inline_final_judgment_fields_map_only_explicit_text(self):
        payload = _present(
            """
一、最终判断
- **买对了吗？**：买对了方向，但不是最优标的。
- **买点质量如何？**：一般，属于确认后的追涨位置。
- **属于主线还是跟风？**：主线支线。
- **是否值得重来一次继续买？**：不作为第一选择。
"""
        )

        self.assertEqual(
            [item["text"] for item in payload["review"]["items"]],
            [
                "买对了方向，但不是最优标的。",
                "一般，属于确认后的追涨位置。",
                "不作为第一选择。",
                "主线支线。",
            ],
        )
        self.assertEqual(payload["review"]["nextActions"]["items"], [])
        self.assertFalse(payload["bestChoice"]["available"])
        for path in (
            "review.items[0].text",
            "review.items[1].text",
            "review.items[2].text",
            "review.items[3].text",
        ):
            self.assertEqual(payload["audit"]["confidence"][path], "high")
            self.assertEqual(payload["audit"]["evidence_map"][path]["sourceSection"], "最终判断")

    def test_multiline_bold_review_questions_map_until_next_question(self):
        payload = _present(
            """
一、最终判断

- **买对了吗？**
  买对了方向，但买点有隐忧。

- **买点质量如何？**
  09:25属于合格买点。
  09:32属于追高。

- **属于主线还是跟风？**
  属于**当日最强主线的趋势核心**，不是跟风。

- **如果重来一次应该如何交易？**
  只保留09:25的买入，放弃09:32追加。

二、交易逻辑
资金交易的是高速电子树脂。
"""
        )

        self.assertEqual(
            [item["text"] for item in payload["review"]["items"]],
            [
                "买对了方向，但买点有隐忧。",
                "09:25属于合格买点。\n09:32属于追高。",
                "只保留09:25的买入，放弃09:32追加。",
                "属于当日最强主线的趋势核心，不是跟风。",
            ],
        )
        for index in range(4):
            evidence = payload["audit"]["evidence_map"][f"review.items[{index}].text"]["evidence"]
            self.assertIn("**", evidence)
            self.assertEqual(
                payload["audit"]["evidence_map"][f"review.items[{index}].text"]["sourceSection"],
                "最终判断",
            )

    def test_rerun_section_is_exposed_as_full_text_with_evidence(self):
        payload = _present(
            """
六、如果重来一次

- **优先买谁？**
  仍然是东材科技优先。

- **为什么？**
  只执行09:25的买点，放弃09:32加仓。
"""
        )

        self.assertEqual(
            payload["review"]["nextActions"]["text"],
            "优先买谁？\n仍然是东材科技优先。\n为什么？\n只执行09:25的买点，放弃09:32加仓。",
        )
        self.assertEqual(
            payload["audit"]["evidence_map"]["review.nextActions.text"]["sourceSection"],
            "如果重来一次",
        )
        self.assertIn(
            "**优先买谁？**",
            payload["audit"]["evidence_map"]["review.nextActions.text"]["evidence"],
        )

    def test_presenter_call_remains_compatible_and_agent_file_is_out_of_scope(self):
        payload = _present("一句话结论：只保留明确结论。")

        self.assertEqual(payload["review"]["verdict"]["text"], "只保留明确结论。")
        self.assertEqual(payload["agent_type"], "wang")
        agent_text = AGENT_PATH.read_text(encoding="utf-8")
        self.assertIn("def run_final_wang_agent", agent_text)
        self.assertNotIn("answer_first_v2_strict_evidence", agent_text)

    def test_bold_ranking_reason_label_is_parsed_from_raw_markdown(self):
        payload = _present(
            """
五、相关公司比较
- **第一名：东材科技**
  - **逻辑**：AI算力上游材料铲子股，稀缺性最高。
"""
        )

        self.assertEqual(payload["bestChoice"]["ranking"][0]["name"], "东材科技")
        self.assertEqual(payload["bestChoice"]["ranking"][0]["reason"], "AI算力上游材料铲子股，稀缺性最高。")
        reason_source = payload["audit"]["evidence_map"]["bestChoice.ranking[0].reason"]["evidence"]
        self.assertIn("**逻辑**", reason_source)

    def test_rank_paragraph_after_company_name_is_used_as_reason(self):
        payload = _present(
            """
五、相关公司比较

**第一名：泰坦股份（12天6板）**
情绪总龙头，市场的旗杆。它可能不直接做PCB，但在那个时间点，它就是“PCB板块”的肉身代表。

**第二名：泰和新材（3连板）**
板块连板高标，地位仅次于泰坦股份。
"""
        )

        self.assertEqual(payload["bestChoice"]["ranking"][0]["name"], "泰坦股份")
        self.assertEqual(
            payload["bestChoice"]["ranking"][0]["reason"],
            "情绪总龙头，市场的旗杆。它可能不直接做PCB，但在那个时间点，它就是“PCB板块”的肉身代表。",
        )
        self.assertEqual(payload["bestChoice"]["ranking"][1]["reason"], "板块连板高标，地位仅次于泰坦股份。")
        evidence = payload["audit"]["evidence_map"]["bestChoice.ranking[0].reason"]["evidence"]
        self.assertIn("情绪总龙头", evidence)

    def test_parallel_company_names_in_same_rank_are_preserved(self):
        payload = _present(
            """
五、相关公司比较

- **第一名：沪硅产业、西安奕材（当日板块核心）**
  - **理由：** 当日领涨结构中的绝对核心，20cm涨停。
- **第二名：东材科技（主线强支线核心）**
  - **理由：** 业绩爆发真实，产品具有全球独家性。
- **第三名：金安国纪、宏昌电子（PCB/元件跟风）**
  - **理由：** PCB/电子布涨价是支线逻辑。
"""
        )

        self.assertEqual(
            [item["name"] for item in payload["bestChoice"]["ranking"]],
            ["沪硅产业、西安奕材", "东材科技", "金安国纪、宏昌电子"],
        )
        self.assertEqual(payload["bestChoice"]["name"], "沪硅产业、西安奕材")
        self.assertFalse(payload["audit"]["parser_warnings"])

    def test_json_industry_chain_nodes_use_label_and_role_fields(self):
        payload = _present(
            """
{
  "finalJudgment": {
    "summary": "方向正确。",
    "tradeCorrectness": {"boughtRight": "买对方向。", "score": 70},
    "entryQuality": {"judgment": "一般。", "score": 55},
    "mainlinePosition": {"level": "主线支线", "reason": "不是核心。", "score": 72},
    "improvement": {"wouldBuyAgain": "会降低仓位。"},
    "totalScore": 66
  },
  "industryChain": {
    "nodes": [
      {"label": "AI算力终端需求", "role": "英伟达等GPU厂商需求爆发"},
      {"label": "东材科技", "role": "高端电子材料供应商"}
    ]
  },
  "tradeLogic": {"coreLogic": "AI算力材料。"},
  "barrierAndProfitFlow": {"profitFlow": "利润扩散。"},
  "companyComparison": {"shortTermCapitalRanking": [{"rank": 1, "name": "沪硅产业", "reason": "更强。"}]},
  "rerunChoice": {"shortTermFirstChoice": "沪硅产业"},
  "oneLineConclusion": "买对主线，没买核心。"
}
"""
        )

        nodes = payload["themeAnalysis"]["industryChain"]["nodes"]
        self.assertEqual(nodes[0]["label"], "AI算力终端需求")
        self.assertEqual(nodes[0]["role"], "英伟达等GPU厂商需求爆发")
        self.assertEqual(nodes[1]["label"], "东材科技")
        self.assertTrue(nodes[1]["current"])


if __name__ == "__main__":
    unittest.main()
