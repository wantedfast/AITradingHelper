from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd

from .industry_profiles import IndustryProfile
from .workbench_agents import _call_json_agent


def build_presenter_data(
    *,
    workbench: dict[str, Any],
    profile: IndustryProfile,
    analysis: dict[str, Any],
    trade_frame: pd.DataFrame,
) -> dict[str, Any]:
    """Convert research memos and structured agent output into UI-ready fields."""
    fallback = build_presenter_fallback_data(
        workbench=workbench,
        profile=profile,
        analysis=analysis,
        trade_frame=trade_frame,
    )
    if not _presenter_agent_enabled():
        return fallback
    try:
        agent_data = run_presenter_workbench_agent(fallback=fallback, workbench=workbench, analysis=analysis)
    except Exception as exc:
        print(f"[warn] presenter agent failed, fallback to deterministic presenter data: {exc}")
        return fallback
    return _merge_presenter_data(fallback, agent_data)


def build_presenter_fallback_data(
    *,
    workbench: dict[str, Any],
    profile: IndustryProfile,
    analysis: dict[str, Any],
    trade_frame: pd.DataFrame,
) -> dict[str, Any]:
    company = _dict(workbench.get("company"))
    hero = _dict(workbench.get("hero"))
    profit_flow = _dict(workbench.get("profit_flow"))
    moat = _dict(workbench.get("moat_radar"))
    gap = _dict(workbench.get("expectation_gap"))
    action = _dict(workbench.get("action"))
    trade_review = _dict(workbench.get("trade_review"))
    memos = _dict(workbench.get("deep_memos"))
    wang = _dict(workbench.get("wang_agent"))
    public = _dict(workbench.get("public_equity_agent"))

    name = _first(company.get("name"), profile.name, "个股")
    code = _first(company.get("code"), profile.code, "")
    theme = _first(company.get("theme"), profile.theme, "产业链待验证")
    node = _first(profit_flow.get("company_position"), profile.node, company.get("sector"), "产业链位置待验证")

    claims = _list(hero.get("claims"))
    if not claims:
        claims = _split_claims(_first(public.get("one_sentence_conclusion"), profile.one_sentence_thesis, analysis.get("headline")))

    value_pool = _first(profit_flow.get("value_pool"), profile.core_driver, theme)
    profit_items = _profit_items(profit_flow, profile)
    logic_tree = _logic_tree(workbench, profile, analysis)
    tags = _list(hero.get("tags")) or _list(action.get("status_tags")) or [theme, node]

    data = {
        "company": {
            "name": name,
            "code": code,
            "subtitle": f"{code}{_exchange_suffix(code)} · {theme} / {node}".strip(" ·"),
            "theme": theme,
            "node": node,
        },
        "hero": {
            "kicker": "这家公司值得研究吗？",
            "title": name,
            "industry_rating": _first(hero.get("industry_rating"), "B"),
            "investment_rating": _first(hero.get("investment_rating"), "B"),
            "tags": tags[:5],
            "claims": claims[:4],
            "note": "首屏先回答：它为什么值得研究、风险在哪里、下一步验证什么。",
        },
        "profit_flow": {
            "title": "利润流向图",
            "description": "用资金流和利润池解释“为什么是它”，而不是让用户在财务指标里猜。",
            "value_pool": value_pool,
            "items": profit_items,
            "company_position": node,
            "why_profit_flows_here": _first(profit_flow.get("why_profit_flows_here"), profile.rerating_anchor, profile.industry_judgment),
        },
        "logic_tree": logic_tree,
        "expectation_gap": {
            "market_believes": _list(gap.get("market_believes")) or ["市场共识待验证"],
            "analyst_view": _list(gap.get("analyst_view")) or [_first(gap.get("underestimated"), profile.expectation_gap, "研究判断待验证")],
            "gap_score": _num(gap.get("gap_score"), 50),
            "underestimated": _first(gap.get("underestimated"), profile.rerating_anchor, "待验证"),
            "overestimated": _first(gap.get("overestimated"), "待验证"),
        },
        "moat": {
            "summary": _first(moat.get("explanation"), "; ".join(profile.barriers), "壁垒待验证"),
            "items": _moat_items(moat, profile),
        },
        "financial_validation": _list(public.get("financial_validation")) or [_validation_text(item) for item in _list(workbench.get("validation_panel"))],
        "valuation_odds": _first(workbench.get("valuation_odds"), public.get("valuation_odds"), profile.valuation_odds, "估值赔率待验证"),
        "catalysts": _event_list(workbench.get("catalysts"), profile.catalysts),
        "disconfirming_signals": _risk_list(workbench.get("risks"), profile.disconfirming_signals),
        "trade_review": {
            "return_pct": _num(trade_review.get("trade_return_pct"), analysis.get("return", 0.0)),
            "score": _num(trade_review.get("trade_score"), analysis.get("score", 0)),
            "buy_verdict": _first(trade_review.get("buy_verdict"), _dict(analysis.get("optimal")).get("buy_label"), "买点待验证"),
            "sell_verdict": _first(trade_review.get("sell_verdict"), _dict(analysis.get("optimal")).get("sell_label"), "卖点待验证"),
            "execution_lesson": _first(trade_review.get("execution_lesson"), _dict(analysis.get("optimal")).get("sell_reason"), analysis.get("headline"), "复盘结论待生成"),
            "rows": _trade_rows(trade_frame),
        },
        "next_action": {
            "current_action": _first(action.get("current_action"), profile.position_sizing, "加入观察池，等待验证"),
            "suitable_for": _first(action.get("suitable_for"), profile.best_expression, "能承受波动并愿意跟踪验证的人"),
            "not_suitable_for": _first(action.get("not_suitable_for"), "不适合只看概念追高的人"),
            "recheck_conditions": _list(action.get("recheck_conditions")) or list(profile.disconfirming_signals[:4]),
        },
        "deep_memos": {
            "wang": _first(memos.get("wang"), wang.get("deep_memo"), profile.wang_investor_report, profile.industry_judgment),
            "public_equity": _first(memos.get("public_equity"), public.get("deep_memo"), profile.public_equity_report, profile.valuation_odds),
        },
        "agent_errors": [str(item) for item in _list(workbench.get("agent_errors"))],
    }
    data.update(_expression_layer(data, workbench, analysis))
    return _normalize_presenter_data(data)


def run_presenter_workbench_agent(*, fallback: dict[str, Any], workbench: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    return _call_json_agent(_presenter_system_prompt(), _presenter_user_prompt(fallback, workbench, analysis))


def _presenter_system_prompt() -> str:
    return """
你是第三个 Presenter Agent。你不负责重新做投资研究，也不要编造事实。
你的任务是读懂 WANG Agent 和 Public Equity Agent 的研究内容，把它整理成前端 workbench/concept HTML 可以直接渲染的表达型 JSON。

必须遵守：
1. 只输出合法 JSON，不要 Markdown。
2. 保留事实边界。证据不足时写“待验证”。
3. 输出必须同时兼容旧字段和新增表达层字段。
4. 文案要短、清楚、适合新手看懂，不要写成长篇报告。
5. 图表字段要能直接驱动前端模块：首屏、一句话结论、利润流向图、产业逻辑树、市场预期差、壁垒验证清单、估值催化剂下一步。
""".strip()


def _presenter_user_prompt(fallback: dict[str, Any], workbench: dict[str, Any], analysis: dict[str, Any]) -> str:
    payload = {
        "fallback_contract": fallback,
        "research_workbench": workbench,
        "trade_analysis": _jsonable(analysis),
    }
    return f"""
请把输入整理成以下 JSON schema。字段名必须保留，数组长度按说明控制：

{{
  "company": {{
    "name": "公司名",
    "code": "代码",
    "subtitle": "代码 + 主题 / 产业位置",
    "theme": "主题",
    "node": "产业链位置"
  }},
  "hero": {{
    "kicker": "这家公司值得研究吗？",
    "title": "公司名",
    "industry_rating": "S/A/B/C",
    "investment_rating": "A+/A/B/C",
    "tags": ["3-5 个短标签"],
    "claims": ["首屏 3-4 条一句话结论"],
    "note": "首屏回答什么"
  }},
  "profit_flow": {{
    "title": "利润流向图",
    "description": "这个图帮助用户理解什么",
    "value_pool": "价值池名称",
    "items": [
      {{"name": "产业环节", "share_pct": 30, "highlight": false}}
    ],
    "company_position": "高亮位置",
    "why_profit_flows_here": "为什么利润流向这里"
  }},
  "logic_tree": [
    {{"node": "逻辑节点", "certainty_pct": 80}}
  ],
  "expectation_gap": {{
    "market_believes": ["市场认为 1", "市场认为 2"],
    "analyst_view": ["实际情况 1", "实际情况 2"],
    "gap_score": 50,
    "underestimated": "低估点",
    "overestimated": "高估点"
  }},
  "moat": {{
    "summary": "壁垒总结",
    "items": ["壁垒 1", "壁垒 2"]
  }},
  "financial_validation": ["财务验证 1", "财务验证 2"],
  "valuation_odds": "估值赔率判断",
  "catalysts": ["催化剂 1", "催化剂 2"],
  "disconfirming_signals": ["反证点 1", "反证点 2"],
  "next_action": {{
    "current_action": "加入观察池/等待回调/规避",
    "suitable_for": "适合谁",
    "not_suitable_for": "不适合谁",
    "recheck_conditions": ["复查条件 1", "复查条件 2"]
  }},
  "newbie_summary": "给新手看的 80-160 字解释",
  "section_narrative": {{
    "hero": "首屏怎么讲",
    "profit_flow": "利润流向图怎么讲",
    "logic_tree": "产业逻辑树怎么讲",
    "expectation_gap": "市场预期差怎么讲",
    "moat_validation": "壁垒与验证清单怎么讲",
    "decision": "估值催化剂和下一步怎么讲"
  }},
  "claim_cards": [
    {{"title": "短标题", "claim": "结论", "evidence": "证据或待验证", "confidence_pct": 70, "risk": "风险"}}
  ],
  "evidence_blocks": [
    {{"type": "industry/financial/news/trade", "title": "证据标题", "evidence": "证据内容", "status": "已验证/待验证/风险"}}
  ],
  "chart_annotations": {{
    "profit_flow": ["标注 1"],
    "logic_tree": ["标注 1"],
    "expectation_gap": ["标注 1"],
    "trade_review": ["标注 1"]
  }},
  "visual_priority": ["hero", "profit_flow", "logic_tree", "expectation_gap", "moat_validation", "decision"],
  "presenter_copy": {{
    "hero": "口播式解释",
    "profit_flow": "口播式解释",
    "logic_tree": "口播式解释",
    "expectation_gap": "口播式解释",
    "moat_validation": "口播式解释",
    "decision": "口播式解释"
  }},
  "frontend_modules": {{
    "hero": {{"enabled": true, "priority": 1}},
    "one_sentence_conclusion": {{"enabled": true, "priority": 2}},
    "profit_flow": {{"enabled": true, "priority": 3}},
    "logic_tree": {{"enabled": true, "priority": 4}},
    "expectation_gap": {{"enabled": true, "priority": 5}},
    "moat_validation": {{"enabled": true, "priority": 6}},
    "decision": {{"enabled": true, "priority": 7}}
  }},
  "deep_memos": {{
    "wang": "保留原 WANG memo",
    "public_equity": "保留原 Public Equity memo"
  }}
}}

输入：
{json.dumps(payload, ensure_ascii=False, default=str)}
""".strip()


def _presenter_agent_enabled() -> bool:
    value = os.getenv("PRESENTER_AGENT_ENABLED", "1").strip().lower()
    return value not in {"0", "false", "no"}


def _merge_presenter_data(fallback: dict[str, Any], agent_data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(agent_data, dict):
        return fallback
    merged = _deep_merge(fallback, agent_data)
    merged.update(_expression_layer(merged, {}, {}))
    return _normalize_presenter_data(merged, fallback)


def _normalize_presenter_data(data: dict[str, Any], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = fallback or {}
    normalized = dict(data if isinstance(data, dict) else {})
    for key in ["company", "hero", "profit_flow", "expectation_gap", "moat", "trade_review", "next_action", "deep_memos", "section_narrative", "chart_annotations", "presenter_copy", "frontend_modules"]:
        if not isinstance(normalized.get(key), dict):
            normalized[key] = _dict(fallback.get(key))
    for key in ["logic_tree", "financial_validation", "catalysts", "disconfirming_signals", "claim_cards", "evidence_blocks", "visual_priority"]:
        normalized[key] = _list(normalized.get(key)) or _list(fallback.get(key))

    hero = normalized["hero"]
    hero["tags"] = [str(item) for item in _list(hero.get("tags"))][:5]
    hero["claims"] = [str(item) for item in _list(hero.get("claims"))][:4]

    profit_flow = normalized["profit_flow"]
    profit_items = []
    for item in _list(profit_flow.get("items")):
        item = _dict(item)
        if item:
            profit_items.append(
                {
                    "name": _first(item.get("name"), "产业环节"),
                    "share_pct": _num(item.get("share_pct"), 10),
                    "highlight": bool(item.get("highlight")),
                }
            )
    profit_flow["items"] = profit_items[:6]

    logic_items = []
    for item in _list(normalized.get("logic_tree")):
        item = _dict(item)
        if item:
            logic_items.append({"node": _first(item.get("node"), "逻辑节点"), "certainty_pct": _num(item.get("certainty_pct"), 50)})
    normalized["logic_tree"] = logic_items[:6]

    gap = normalized["expectation_gap"]
    gap["market_believes"] = [str(item) for item in _list(gap.get("market_believes"))] or ["待验证"]
    gap["analyst_view"] = [str(item) for item in _list(gap.get("analyst_view"))] or ["待验证"]
    gap["gap_score"] = _num(gap.get("gap_score"), 50)

    action = normalized["next_action"]
    action["recheck_conditions"] = [str(item) for item in _list(action.get("recheck_conditions"))][:6]

    normalized.update(_expression_layer(normalized, {}, {}))
    return normalized


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _expression_layer(data: dict[str, Any], workbench: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    hero = _dict(data.get("hero"))
    profit_flow = _dict(data.get("profit_flow"))
    gap = _dict(data.get("expectation_gap"))
    action = _dict(data.get("next_action"))
    company = _dict(data.get("company"))
    claims = _list(hero.get("claims"))[:4]
    financial_validation = _list(data.get("financial_validation"))
    risks = _list(data.get("disconfirming_signals"))
    catalysts = _list(data.get("catalysts"))
    moat_items = _list(_dict(data.get("moat")).get("items"))
    logic_tree = _list(data.get("logic_tree"))[:6]

    claim_cards = []
    for idx, claim in enumerate(claims[:4]):
        claim_cards.append(
            {
                "title": f"核心结论 {idx + 1}",
                "claim": str(claim),
                "evidence": _first(financial_validation[idx] if idx < len(financial_validation) else "", "待验证"),
                "confidence_pct": _num(_dict(logic_tree[idx] if idx < len(logic_tree) else {}).get("certainty_pct"), 65),
                "risk": _first(risks[idx] if idx < len(risks) else "", "待验证"),
            }
        )

    evidence_blocks = []
    for item in financial_validation[:4]:
        evidence_blocks.append({"type": "financial", "title": "财务验证", "evidence": str(item), "status": _status_text(item)})
    for item in risks[:4]:
        evidence_blocks.append({"type": "risk", "title": "反证点", "evidence": str(item), "status": "风险"})
    for item in catalysts[:3]:
        evidence_blocks.append({"type": "event", "title": "催化剂", "evidence": str(item), "status": _status_text(item)})

    section_narrative = {
        "hero": "首屏回答这家公司是否值得进入研究清单。",
        "profit_flow": _first(profit_flow.get("description"), "用利润池和产业链位置解释为什么是它。"),
        "logic_tree": "把上涨逻辑拆成节点，显示每一步的确定性。",
        "expectation_gap": "展示市场共识和研究判断之间的差距。",
        "moat_validation": "保留壁垒、财务验证和反证点，避免只看图表。",
        "decision": "把能不能研究落到现在如何跟踪。",
    }
    presenter_copy = {
        "hero": _first("; ".join(claims), hero.get("note"), "结论待验证"),
        "profit_flow": _first(profit_flow.get("why_profit_flows_here"), "利润流向待验证"),
        "logic_tree": " -> ".join(str(_dict(item).get("node", item)) for item in logic_tree[:4]) or "产业逻辑待验证",
        "expectation_gap": _first(gap.get("underestimated"), "预期差待验证"),
        "moat_validation": "; ".join(str(item) for item in moat_items[:3]) or "壁垒待验证",
        "decision": _first(action.get("current_action"), data.get("valuation_odds"), "下一步待验证"),
    }
    priority = ["hero", "profit_flow", "logic_tree", "expectation_gap", "moat_validation", "decision"]
    return {
        "newbie_summary": _first(
            data.get("newbie_summary"),
            f"{company.get('name', '这家公司')}的核心看点是{company.get('theme', '主题待验证')}，需要同时看产业位置、利润流向、预期差和反证条件。",
        ),
        "section_narrative": _dict(data.get("section_narrative")) or section_narrative,
        "claim_cards": _list(data.get("claim_cards")) or claim_cards,
        "evidence_blocks": _list(data.get("evidence_blocks")) or evidence_blocks,
        "chart_annotations": _dict(data.get("chart_annotations"))
        or {
            "profit_flow": [_first(profit_flow.get("why_profit_flows_here"), "利润流向待验证")],
            "logic_tree": [str(_dict(item).get("node", item)) for item in logic_tree[:4]],
            "expectation_gap": [_first(gap.get("underestimated"), "预期差待验证")],
            "trade_review": [_first(_dict(data.get("trade_review")).get("execution_lesson"), analysis.get("headline"), "交易复盘待验证")],
        },
        "visual_priority": _list(data.get("visual_priority")) or priority,
        "presenter_copy": _dict(data.get("presenter_copy")) or presenter_copy,
        "frontend_modules": _dict(data.get("frontend_modules"))
        or {name: {"enabled": True, "priority": idx + 1} for idx, name in enumerate(["hero", "one_sentence_conclusion", *priority[1:]])},
    }


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return value
    except Exception:
        return str(value)


def _status_text(value: Any) -> str:
    text = str(value)
    if "风险" in text:
        return "风险"
    if "待" in text or "验证" in text:
        return "待验证"
    return "已验证"


def _profit_items(profit_flow: dict[str, Any], profile: IndustryProfile) -> list[dict[str, Any]]:
    items = []
    for item in _list(profit_flow.get("items")):
        if isinstance(item, dict):
            items.append(
                {
                    "name": _first(item.get("name"), "产业环节"),
                    "share_pct": _num(item.get("share_pct"), 10),
                    "highlight": bool(item.get("highlight")),
                }
            )
    if items:
        return items[:6]
    labels = [profile.core_driver, *profile.profit_levers[:4]]
    defaults = [40, 24, 16, 12, 8]
    return [{"name": _first(label, f"环节 {idx + 1}"), "share_pct": defaults[idx], "highlight": idx == 2} for idx, label in enumerate(labels[:5])]


def _logic_tree(workbench: dict[str, Any], profile: IndustryProfile, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in _list(workbench.get("logic_tree")):
        if isinstance(item, dict):
            result.append({"node": _first(item.get("node"), "逻辑节点"), "certainty_pct": _num(item.get("certainty_pct"), 60)})
    if result:
        return result[:6]
    labels = [title for _, title, _ in profile.chain_nodes] or [profile.core_driver, profile.node, "财报验证", "估值消化"]
    base = max(45, min(92, int(analysis.get("score", 70) or 70)))
    return [{"node": _first(label, "逻辑节点"), "certainty_pct": max(35, base - idx * 5)} for idx, label in enumerate(labels[:6])]


def _moat_items(moat: dict[str, Any], profile: IndustryProfile) -> list[str]:
    rows = []
    for item in _list(moat.get("dimensions")):
        if isinstance(item, dict):
            rows.append(f"{_first(item.get('name'), '壁垒')}：公司 {_num(item.get('company'), 0):.0f} / 行业 {_num(item.get('average'), 0):.0f}")
    return rows or list(profile.barriers[:5]) or ["壁垒待验证"]


def _event_list(value: Any, fallback: tuple[str, ...]) -> list[str]:
    rows = []
    for item in _list(value):
        if isinstance(item, dict):
            rows.append(f"{_first(item.get('time'), '待定')}：{_first(item.get('event'), '催化剂待验证')}（影响：{_first(item.get('impact'), '待验证')}）")
        else:
            rows.append(str(item))
    return rows or list(fallback[:5]) or ["催化剂待验证"]


def _risk_list(value: Any, fallback: tuple[str, ...]) -> list[str]:
    rows = []
    for item in _list(value):
        if isinstance(item, dict):
            rows.append(f"{_first(item.get('name'), '风险')}：{_first(item.get('why_it_matters'), '待验证')}；动作：{_first(item.get('downgrade_action'), '待验证')}")
        else:
            rows.append(str(item))
    return rows or list(fallback[:5]) or ["反证点待验证"]


def _validation_text(item: Any) -> str:
    if isinstance(item, dict):
        return f"{_first(item.get('status'), '待验证')}：{_first(item.get('item'), '')} {_first(item.get('evidence'), '')}".strip()
    return str(item)


def _trade_rows(trade_frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    if trade_frame is None or trade_frame.empty:
        return rows
    for row in trade_frame.sort_values("trade_date").itertuples():
        trade_date = getattr(row, "trade_date")
        if hasattr(trade_date, "strftime"):
            date_text = trade_date.strftime("%Y-%m-%d")
        else:
            date_text = str(trade_date)
        rows.append(
            {
                "date": date_text,
                "side": "买入" if getattr(row, "side", "") == "buy" else "卖出",
                "price": float(getattr(row, "price", 0) or 0),
                "quantity": float(getattr(row, "quantity", 0) or 0),
                "amount": float(getattr(row, "amount", 0) or 0),
            }
        )
    return rows


def _split_claims(text: Any) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    parts = [part.strip(" ，。；;") for part in raw.replace("\n", "。").split("。") if part.strip()]
    return parts or [raw]


def _exchange_suffix(code: str) -> str:
    code = str(code or "")
    if code.startswith("6"):
        return ".SH"
    if code.startswith(("0", "3")):
        return ".SZ"
    return ""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in (None, "", [], {})]
    if isinstance(value, tuple):
        return [item for item in value if item not in (None, "", [], {})]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _first(*values: Any) -> str:
    for value in values:
        if value not in (None, "", [], {}):
            return str(value)
    return ""


def _num(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(fallback)


# Final schema guard. This intentionally appears after the earlier helper with
# the same name so module loading uses this stricter contract.
def _normalize_presenter_data(data: dict[str, Any], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = fallback if isinstance(fallback, dict) else {}
    normalized = dict(data if isinstance(data, dict) else {})

    for key in [
        "company",
        "hero",
        "profit_flow",
        "expectation_gap",
        "moat",
        "trade_review",
        "next_action",
        "deep_memos",
        "section_narrative",
        "chart_annotations",
        "presenter_copy",
        "frontend_modules",
    ]:
        if not isinstance(normalized.get(key), dict):
            normalized[key] = _dict(fallback.get(key))

    company = normalized["company"]
    for key in ["name", "code", "subtitle", "theme", "node"]:
        company[key] = _first(company.get(key), _dict(fallback.get("company")).get(key), "待验证" if key != "code" else "")

    hero = normalized["hero"]
    fallback_hero = _dict(fallback.get("hero"))
    hero["kicker"] = _first(hero.get("kicker"), fallback_hero.get("kicker"), "这家公司值得研究吗？")
    hero["title"] = _first(hero.get("title"), company.get("name"), fallback_hero.get("title"), "个股")
    hero["industry_rating"] = _first(hero.get("industry_rating"), fallback_hero.get("industry_rating"), "B")
    hero["investment_rating"] = _first(hero.get("investment_rating"), fallback_hero.get("investment_rating"), "B")
    hero["tags"] = [str(item) for item in (_list(hero.get("tags")) or _list(fallback_hero.get("tags")) or ["待验证"])][:5]
    hero["claims"] = [str(item) for item in (_list(hero.get("claims")) or _list(fallback_hero.get("claims")) or ["结论待验证"])][:4]
    hero["note"] = _first(hero.get("note"), fallback_hero.get("note"), "首屏回答为什么值得研究、风险在哪里、下一步验证什么。")

    profit_flow = normalized["profit_flow"]
    fallback_profit = _dict(fallback.get("profit_flow"))
    profit_flow["title"] = _first(profit_flow.get("title"), fallback_profit.get("title"), "利润流向图")
    profit_flow["description"] = _first(profit_flow.get("description"), fallback_profit.get("description"), "用价值池和产业链位置解释为什么是它。")
    profit_flow["value_pool"] = _first(profit_flow.get("value_pool"), fallback_profit.get("value_pool"), "待验证")
    profit_flow["company_position"] = _first(profit_flow.get("company_position"), fallback_profit.get("company_position"), "待验证")
    profit_flow["why_profit_flows_here"] = _first(profit_flow.get("why_profit_flows_here"), fallback_profit.get("why_profit_flows_here"), "待验证")
    profit_flow["items"] = _normalize_profit_items(profit_flow.get("items")) or _normalize_profit_items(fallback_profit.get("items"))

    normalized["logic_tree"] = _normalize_logic_tree(normalized.get("logic_tree")) or _normalize_logic_tree(fallback.get("logic_tree"))

    gap = normalized["expectation_gap"]
    fallback_gap = _dict(fallback.get("expectation_gap"))
    gap["market_believes"] = [str(item) for item in (_list(gap.get("market_believes")) or _list(fallback_gap.get("market_believes")) or ["待验证"])]
    gap["analyst_view"] = [str(item) for item in (_list(gap.get("analyst_view")) or _list(fallback_gap.get("analyst_view")) or ["待验证"])]
    gap["gap_score"] = _num(gap.get("gap_score"), _num(fallback_gap.get("gap_score"), 50))
    gap["underestimated"] = _first(gap.get("underestimated"), fallback_gap.get("underestimated"), "待验证")
    gap["overestimated"] = _first(gap.get("overestimated"), fallback_gap.get("overestimated"), "待验证")

    moat = normalized["moat"]
    fallback_moat = _dict(fallback.get("moat"))
    moat["summary"] = _first(moat.get("summary"), fallback_moat.get("summary"), "待验证")
    moat["items"] = [str(item) for item in (_list(moat.get("items")) or _list(fallback_moat.get("items")) or ["待验证"])]

    normalized["financial_validation"] = [str(item) for item in (_list(normalized.get("financial_validation")) or _list(fallback.get("financial_validation")))]
    normalized["catalysts"] = [str(item) for item in (_list(normalized.get("catalysts")) or _list(fallback.get("catalysts")))]
    normalized["disconfirming_signals"] = [str(item) for item in (_list(normalized.get("disconfirming_signals")) or _list(fallback.get("disconfirming_signals")))]
    normalized["valuation_odds"] = _first(normalized.get("valuation_odds"), fallback.get("valuation_odds"), "待验证")

    action = normalized["next_action"]
    fallback_action = _dict(fallback.get("next_action"))
    action["current_action"] = _first(action.get("current_action"), fallback_action.get("current_action"), "加入观察池")
    action["suitable_for"] = _first(action.get("suitable_for"), fallback_action.get("suitable_for"), "待验证")
    action["not_suitable_for"] = _first(action.get("not_suitable_for"), fallback_action.get("not_suitable_for"), "待验证")
    action["recheck_conditions"] = [str(item) for item in (_list(action.get("recheck_conditions")) or _list(fallback_action.get("recheck_conditions")))][:6]

    trade = normalized["trade_review"]
    fallback_trade = _dict(fallback.get("trade_review"))
    trade["return_pct"] = _num(trade.get("return_pct"), _num(fallback_trade.get("return_pct"), 0))
    trade["score"] = _num(trade.get("score"), _num(fallback_trade.get("score"), 0))
    trade["trade_return_pct"] = _num(trade.get("trade_return_pct"), trade["return_pct"])
    trade["trade_score"] = _num(trade.get("trade_score"), trade["score"])
    trade["buy_verdict"] = _first(trade.get("buy_verdict"), fallback_trade.get("buy_verdict"), "待验证")
    trade["sell_verdict"] = _first(trade.get("sell_verdict"), fallback_trade.get("sell_verdict"), "待验证")
    trade["execution_lesson"] = _first(trade.get("execution_lesson"), fallback_trade.get("execution_lesson"), "待验证")
    trade["rows"] = _normalize_trade_rows(trade.get("rows")) or _normalize_trade_rows(fallback_trade.get("rows"))

    generated = _expression_layer(normalized, {}, {})
    normalized["newbie_summary"] = _first(normalized.get("newbie_summary"), fallback.get("newbie_summary"), generated.get("newbie_summary"))
    normalized["section_narrative"] = _string_dict(normalized.get("section_narrative")) or _string_dict(fallback.get("section_narrative")) or _string_dict(generated.get("section_narrative"))
    normalized["claim_cards"] = _normalize_claim_cards(normalized.get("claim_cards")) or _normalize_claim_cards(fallback.get("claim_cards")) or _normalize_claim_cards(generated.get("claim_cards"))
    normalized["evidence_blocks"] = _normalize_evidence_blocks(normalized.get("evidence_blocks")) or _normalize_evidence_blocks(fallback.get("evidence_blocks")) or _normalize_evidence_blocks(generated.get("evidence_blocks"))
    normalized["chart_annotations"] = _annotation_dict(normalized.get("chart_annotations")) or _annotation_dict(fallback.get("chart_annotations")) or _annotation_dict(generated.get("chart_annotations"))
    normalized["visual_priority"] = [str(item) for item in (_list(normalized.get("visual_priority")) or _list(fallback.get("visual_priority")) or _list(generated.get("visual_priority")))]
    normalized["presenter_copy"] = _string_dict(normalized.get("presenter_copy")) or _string_dict(fallback.get("presenter_copy")) or _string_dict(generated.get("presenter_copy"))
    normalized["frontend_modules"] = _module_dict(normalized.get("frontend_modules")) or _module_dict(fallback.get("frontend_modules")) or _module_dict(generated.get("frontend_modules"))
    normalized["agent_errors"] = [str(item) for item in (_list(normalized.get("agent_errors")) or _list(fallback.get("agent_errors")))]
    return normalized


def _normalize_profit_items(value: Any) -> list[dict[str, Any]]:
    rows = []
    for item in _list(value):
        item = _dict(item)
        if item:
            rows.append({"name": _first(item.get("name"), "环节"), "share_pct": _num(item.get("share_pct"), 10), "highlight": bool(item.get("highlight"))})
    return rows[:6]


def _normalize_logic_tree(value: Any) -> list[dict[str, Any]]:
    rows = []
    for item in _list(value):
        item = _dict(item)
        if item:
            rows.append({"node": _first(item.get("node"), "逻辑节点"), "certainty_pct": _num(item.get("certainty_pct"), 50)})
    return rows[:6]


def _normalize_claim_cards(value: Any) -> list[dict[str, Any]]:
    rows = []
    for item in _list(value):
        item = _dict(item)
        if item:
            rows.append(
                {
                    "title": _first(item.get("title"), "核心结论"),
                    "claim": _first(item.get("claim"), "待验证"),
                    "evidence": _first(item.get("evidence"), "待验证"),
                    "confidence_pct": _num(item.get("confidence_pct"), 50),
                    "risk": _first(item.get("risk"), "待验证"),
                }
            )
    return rows[:6]


def _normalize_evidence_blocks(value: Any) -> list[dict[str, Any]]:
    rows = []
    for item in _list(value):
        item = _dict(item)
        if item:
            rows.append(
                {
                    "type": _first(item.get("type"), "unknown"),
                    "title": _first(item.get("title"), "证据"),
                    "evidence": _first(item.get("evidence"), "待验证"),
                    "status": _first(item.get("status"), "待验证"),
                }
            )
    return rows[:12]


def _normalize_trade_rows(value: Any) -> list[dict[str, Any]]:
    rows = []
    for item in _list(value):
        item = _dict(item)
        if item:
            rows.append(
                {
                    "date": _first(item.get("date"), ""),
                    "side": _first(item.get("side"), ""),
                    "price": _num(item.get("price"), 0),
                    "quantity": _num(item.get("quantity"), 0),
                    "amount": _num(item.get("amount"), 0),
                }
            )
    return rows


def _string_dict(value: Any) -> dict[str, str]:
    value = _dict(value)
    return {str(key): str(item) for key, item in value.items() if item not in (None, "", [], {})}


def _annotation_dict(value: Any) -> dict[str, list[str]]:
    value = _dict(value)
    result = {}
    for key, item in value.items():
        values = [str(row) for row in _list(item)]
        if values:
            result[str(key)] = values
    return result


def _module_dict(value: Any) -> dict[str, dict[str, Any]]:
    value = _dict(value)
    result = {}
    for key, item in value.items():
        item = _dict(item)
        if item:
            result[str(key)] = {"enabled": bool(item.get("enabled", True)), "priority": int(_num(item.get("priority"), len(result) + 1))}
    return result


# Final compact Presenter override.
# These definitions intentionally appear at the end of the module so they replace
# the older broad-payload prompt above during module loading.
def _presenter_max_output_tokens() -> int:
    try:
        return max(400, int(os.getenv("PRESENTER_MAX_OUTPUT_TOKENS", "1200")))
    except Exception:
        return 1200


def _trim_text(value: Any, limit: int = 900) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _compact_deep_memos(workbench: dict[str, Any], limit: int = 900) -> dict[str, str]:
    memos = _dict(workbench.get("deep_memos"))
    return {
        "wang": _trim_text(memos.get("wang"), limit),
        "public_equity": _trim_text(memos.get("public_equity"), limit),
    }


def _compact_trade_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    analysis = _dict(analysis)
    keys = [
        "name",
        "code",
        "trade_date",
        "side",
        "price",
        "quantity",
        "amount",
        "fee",
        "headline",
        "score",
        "return",
        "market_hype_reason",
        "recent_catalysts",
        "traded_business_line",
        "what_market_is_pricing",
    ]
    return {key: analysis.get(key) for key in keys if key in analysis}


def _compact_presenter_payload(fallback: dict[str, Any], workbench: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    fallback = _dict(fallback)
    workbench = _dict(workbench)
    return {
        "company": _dict(fallback.get("company")) or _dict(workbench.get("company")),
        "hero": _dict(fallback.get("hero")) or _dict(workbench.get("hero")),
        "profit_flow": _dict(fallback.get("profit_flow")) or _dict(workbench.get("profit_flow")),
        "expectation_gap": _dict(fallback.get("expectation_gap")) or _dict(workbench.get("expectation_gap")),
        "action": _dict(fallback.get("next_action")) or _dict(fallback.get("action")) or _dict(workbench.get("action")),
        "risks": _list(fallback.get("disconfirming_signals")) or _list(workbench.get("risks")),
        "validation": _list(fallback.get("financial_validation")) or _list(workbench.get("validation_panel")),
        "market_hype_reason": _first(workbench.get("market_hype_reason"), fallback.get("market_hype_reason"), "最近炒作原因待验证"),
        "recent_catalysts": _list(workbench.get("recent_catalysts")) or _list(fallback.get("recent_catalysts")),
        "traded_business_line": _first(workbench.get("traded_business_line"), fallback.get("traded_business_line"), "待验证"),
        "what_market_is_pricing": _first(workbench.get("what_market_is_pricing"), fallback.get("what_market_is_pricing"), "待验证"),
        "evidence_quality": _first(workbench.get("evidence_quality"), fallback.get("evidence_quality"), "low"),
        "unknowns": _list(workbench.get("unknowns")) or _list(fallback.get("unknowns")),
        "deep_memos_summary": _compact_deep_memos(workbench),
        "trade_analysis": _compact_trade_analysis(analysis),
        "agent_errors": _list(workbench.get("agent_errors")) or _list(fallback.get("agent_errors")),
    }


def _presenter_system_prompt() -> str:
    return """
You are the Presenter Agent for a stock research workbench.
Read the compact research payload and output strict JSON only. Do not write a long memo.
Your output must be page-ready fields for: hero, one_sentence_conclusion, profit_flow,
logic_tree, expectation_gap, moat, financial_validation, catalysts, disconfirming_signals,
next_action, claim_cards, evidence_blocks, chart_annotations, visual_priority,
presenter_copy, frontend_modules, deep_memos, agent_errors.
If recent market hype evidence is weak, write "最近炒作原因待验证" and keep uncertainty visible.
""".strip()


def _presenter_user_prompt(fallback: dict[str, Any], workbench: dict[str, Any], analysis: dict[str, Any]) -> str:
    payload = _compact_presenter_payload(fallback, workbench, analysis)
    return json.dumps(
        {
            "task": "Convert compact research input into frontend workbench/concept JSON.",
            "compact_payload": payload,
            "rules": [
                "one_sentence_conclusion answers whether this stock deserves research now.",
                "profit_flow explains where industry profit pools are moving.",
                "logic_tree links recent market hype to business and financial verification.",
                "expectation_gap separates the market story from verified facts.",
                "next_action lists concrete checks before buying or adding.",
                "deep_memos must be short summaries, not full memo rewrites.",
            ],
        },
        ensure_ascii=False,
        default=str,
    )


def run_presenter_workbench_agent(*, fallback: dict[str, Any], workbench: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    try:
        return _call_json_agent(
            _presenter_system_prompt(),
            _presenter_user_prompt(fallback, workbench, analysis),
            max_output_tokens=_presenter_max_output_tokens(),
            allow_web=False,
        )
    except Exception as exc:
        deterministic = dict(fallback if isinstance(fallback, dict) else {})
        errors = _list(deterministic.get("agent_errors"))
        errors.append(f"presenter_agent_failed: {exc}")
        deterministic["agent_errors"] = errors
        return deterministic
