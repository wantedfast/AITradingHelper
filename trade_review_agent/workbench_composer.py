from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .industry_profiles import IndustryProfile
from .workbench_schema import merge_default_workbench


def compose_workbench_data(context: dict[str, Any], wang: dict[str, Any], equity: dict[str, Any]) -> dict[str, Any]:
    wang = wang if isinstance(wang, dict) else {}
    equity = equity if isinstance(equity, dict) else {}
    company = context.get("company", {}) if isinstance(context, dict) else {}
    action = _dict(equity.get("action"))
    code = str(company.get("code") or "").strip()
    name = str(company.get("name") or code or "个股").strip()
    data = {
        "company": {
            "code": code,
            "name": name,
            "market": company.get("market") or "A-share",
            "sector": _pick(wang.get("sector"), context.get("company", {}).get("sector"), "待验证"),
            "theme": _pick(wang.get("theme"), context.get("company", {}).get("theme"), "待验证"),
        },
        "sector_symbol": _pick(wang.get("sector_symbol"), ""),
        "market_hype_reason": _pick(
            wang.get("market_hype_reason"),
            equity.get("market_hype_reason"),
            context.get("market_hype_reason"),
            "最近炒作原因待验证",
        ),
        "recent_catalysts": _dedupe_list(
            _list(wang.get("recent_catalysts"), [])
            + _list(equity.get("recent_catalysts"), [])
            + _list(context.get("recent_catalysts"), [])
        )[:8],
        "traded_business_line": _pick(
            equity.get("traded_business_line"),
            wang.get("traded_business_line"),
            context.get("traded_business_line"),
            "待验证",
        ),
        "what_market_is_pricing": _pick(
            equity.get("what_market_is_pricing"),
            wang.get("what_market_is_pricing"),
            context.get("what_market_is_pricing"),
            "待验证",
        ),
        "evidence_quality": _pick(
            equity.get("evidence_quality"),
            wang.get("evidence_quality"),
            context.get("evidence_quality"),
            "low",
        ),
        "market_catalyst": context.get("market_catalyst") if isinstance(context.get("market_catalyst"), dict) else {},
        "evidence": _list(context.get("evidence"), []),
        "news": _list(context.get("news"), []),
        "unknowns": _dedupe_list(
            _list(wang.get("unknowns"), [])
            + _list(equity.get("unknowns"), [])
            + _list(context.get("unknowns"), [])
        )[:8],
        "hero": {
            "industry_rating": _pick(wang.get("industry_rating"), "B"),
            "investment_rating": _pick(equity.get("investment_rating"), "B"),
            "tags": (_list(wang.get("industry_tags"), []) + _list(action.get("status_tags"), ["待验证"]))[:6],
            "claims": _list(wang.get("claims"), [_pick(equity.get("one_sentence_conclusion"), "结论待验证")])[:4],
            "note": "首屏展示结构化结论，深度事实以来源和待验证条件约束。",
        },
        "profit_flow": _dict(wang.get("profit_flow")),
        "moat_radar": _dict(wang.get("moat_radar")),
        "logic_tree": _list(wang.get("logic_tree"), []),
        "expectation_gap": _dict(equity.get("expectation_gap")),
        "validation_panel": _list(equity.get("validation_panel"), []),
        "catalysts": _list(equity.get("catalysts"), []),
        "risks": _list(equity.get("risks"), []),
        "action": action,
        "valuation_odds": equity.get("valuation_odds") or "",
        "trade_review": context.get("trade") or {},
        "research_model": context.get("research_model") or {},
        "sources": _list(equity.get("sources"), []) + _list(context.get("evidence"), []) + _list(context.get("news"), []),
        "research_metrics": {
            "wang": _dict(wang.get("research_metrics")),
            "public_equity": _dict(equity.get("research_metrics")),
            "wang_output_mode": wang.get("research_output_mode") or "",
            "public_equity_output_mode": equity.get("research_output_mode") or "",
        },
        "wang_agent": wang,
        "public_equity_agent": equity,
        "deep_memos": {
            "wang": _pick(wang.get("deep_memo"), wang.get("memo"), ""),
            "public_equity": _pick(equity.get("deep_memo"), equity.get("memo"), ""),
        },
    }
    return merge_default_workbench(data, code=code, name=name)


def workbench_to_profile_payload(data: dict[str, Any]) -> dict[str, Any]:
    company = data.get("company", {})
    hero = data.get("hero", {})
    profit_flow = data.get("profit_flow", {})
    moat = data.get("moat_radar", {})
    gap = data.get("expectation_gap", {})
    action = data.get("action", {})
    public = data.get("public_equity_agent") or data.get("public_equity") or {}
    risks = data.get("risks", [])
    logic = data.get("logic_tree", [])
    validation = data.get("validation_panel", [])

    chain_nodes = []
    for item in logic[:6]:
        if isinstance(item, dict):
            title = str(item.get("node") or "逻辑节点")
            chain_nodes.append(("logic", title, f"确定性 {item.get('certainty_pct', '待验证')}%"))
    if not chain_nodes:
        chain_nodes = [
            ("demand", str(profit_flow.get("value_pool") or "需求冲击"), "待验证"),
            ("company", str(profit_flow.get("company_position") or "公司位置"), "待验证"),
            ("profit", "利润流向", str(profit_flow.get("why_profit_flows_here") or "待验证")),
        ]

    dimensions = moat.get("dimensions") if isinstance(moat, dict) else []
    barriers = []
    if isinstance(dimensions, list):
        barriers = [f"{item.get('name', '壁垒')}：公司{item.get('company', '待验证')} / 行业{item.get('average', '待验证')}" for item in dimensions if isinstance(item, dict)]
    if isinstance(moat, dict) and moat.get("explanation"):
        barriers.insert(0, str(moat["explanation"]))

    flow_items = profit_flow.get("items") if isinstance(profit_flow, dict) else []
    profit_levers = []
    if isinstance(flow_items, list):
        profit_levers = [f"{item.get('name', '环节')}：价值占比约{item.get('share_pct', '待验证')}%" for item in flow_items if isinstance(item, dict)]
    if isinstance(profit_flow, dict) and profit_flow.get("why_profit_flows_here"):
        profit_levers.insert(0, str(profit_flow["why_profit_flows_here"]))

    return {
        "code": company.get("code"),
        "name": company.get("name"),
        "theme": company.get("theme"),
        "core_driver": _first(hero.get("claims"), profit_flow.get("value_pool"), "主线待验证"),
        "node": profit_flow.get("company_position") or company.get("sector") or "产业链位置待验证",
        "sector_symbol": wang_sector_symbol(data),
        "chain_nodes": chain_nodes,
        "barriers": barriers or ["壁垒待验证"],
        "profit_levers": profit_levers or ["利润流向待验证"],
        "peers": [],
        "industry_judgment": _join(hero.get("claims")),
        "company_judgment": equity_conclusion(data),
        "financial_validation": [_validation_text(item) for item in validation[:6]] or ["财务验证待补充"],
        "expectation_gap": _gap_text(gap),
        "valuation_odds": str(data.get("valuation_odds") or ""),
        "catalysts": [_event_text(item) for item in data.get("catalysts", [])[:6]],
        "disconfirming_signals": [_risk_text(item) for item in risks[:6]],
        "position_sizing": action.get("current_action") or "",
        "one_sentence_thesis": equity_conclusion(data),
        "rerating_anchor": gap.get("underestimated") if isinstance(gap, dict) else "",
        "market_position": ", ".join(_list(action.get("status_tags"), [])),
        "peer_ranking": [],
        "best_expression": action.get("suitable_for") or public.get("best_expression") or "",
        "trading_implication": data.get("trade_review", {}).get("execution_lesson") or action.get("not_suitable_for") or "",
        "evidence": [str(item) for item in data.get("sources", [])[:6]],
        "wang_investor_report": str((data.get("deep_memos") or {}).get("wang") or ""),
        "public_equity_report": str((data.get("deep_memos") or {}).get("public_equity") or ""),
    }


def profile_from_workbench(data: dict[str, Any]) -> IndustryProfile:
    payload = workbench_to_profile_payload(data)
    return IndustryProfile(
        code=str(payload.get("code") or ""),
        name=str(payload.get("name") or ""),
        theme=str(payload.get("theme") or "待验证"),
        core_driver=str(payload.get("core_driver") or "待验证"),
        node=str(payload.get("node") or "待验证"),
        sector_symbol=str(payload.get("sector_symbol") or "sh000300"),
        chain_nodes=tuple(tuple(item) for item in payload.get("chain_nodes", [])),
        barriers=tuple(_list(payload.get("barriers"), ["待验证"])),
        profit_levers=tuple(_list(payload.get("profit_levers"), ["待验证"])),
        peers=tuple(_list(payload.get("peers"), [])),
        industry_judgment=str(payload.get("industry_judgment") or ""),
        company_judgment=str(payload.get("company_judgment") or ""),
        financial_validation=tuple(_list(payload.get("financial_validation"), [])),
        expectation_gap=str(payload.get("expectation_gap") or ""),
        valuation_odds=str(payload.get("valuation_odds") or ""),
        catalysts=tuple(_list(payload.get("catalysts"), [])),
        disconfirming_signals=tuple(_list(payload.get("disconfirming_signals"), [])),
        position_sizing=str(payload.get("position_sizing") or ""),
        one_sentence_thesis=str(payload.get("one_sentence_thesis") or ""),
        rerating_anchor=str(payload.get("rerating_anchor") or ""),
        market_position=str(payload.get("market_position") or ""),
        peer_ranking=tuple(_list(payload.get("peer_ranking"), [])),
        best_expression=str(payload.get("best_expression") or ""),
        trading_implication=str(payload.get("trading_implication") or ""),
        evidence=tuple(_list(payload.get("evidence"), [])),
        wang_investor_report="",
        public_equity_report="",
    )


def write_workbench_json(path: str | Path, data: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def wang_sector_symbol(data: dict[str, Any]) -> str:
    symbol = str(data.get("sector_symbol") or "").strip()
    return symbol or "sh000300"


def equity_conclusion(data: dict[str, Any]) -> str:
    public = data.get("public_equity_agent") or data.get("public_equity") or {}
    claims = data.get("hero", {}).get("claims", [""])
    first_claim = claims[0] if isinstance(claims, list) and claims else ""
    return str(public.get("one_sentence_conclusion") or first_claim or "")


def _validation_text(item: Any) -> str:
    if isinstance(item, dict):
        return f"{item.get('status', '待验证')}：{item.get('item', '')} {item.get('evidence', '')}".strip()
    return str(item)


def _event_text(item: Any) -> str:
    if isinstance(item, dict):
        return f"{item.get('time', '待定')}：{item.get('event', '')}（{item.get('impact', '待验证')}）"
    return str(item)


def _risk_text(item: Any) -> str:
    if isinstance(item, dict):
        return f"{item.get('name', '风险')}：{item.get('why_it_matters', '')}；动作：{item.get('downgrade_action', '待验证')}"
    return str(item)


def _gap_text(gap: Any) -> str:
    if not isinstance(gap, dict):
        return str(gap or "")
    return f"低估：{gap.get('underestimated', '待验证')}；高估：{gap.get('overestimated', '待验证')}"


def _join(value: Any) -> str:
    return "；".join(_list(value, []))


def _first(value: Any, *fallbacks: Any) -> str:
    items = _list(value, [])
    if items:
        return str(items[0])
    for item in fallbacks:
        if item:
            return str(item)
    return ""


def _pick(*values: Any) -> str:
    for value in values:
        if value not in (None, "", [], {}):
            return str(value)
    return ""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any, default: list[Any]) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in (None, "", [], {})] or default
    if isinstance(value, tuple):
        return [item for item in value if item not in (None, "", [], {})] or default
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return default


def _dedupe_list(values: list[Any]) -> list[Any]:
    result = []
    seen = set()
    for value in values:
        key = str(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
