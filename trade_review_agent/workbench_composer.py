from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .industry_profiles import IndustryProfile
from .workbench_agents import apply_public_equity_sufficiency
from .workbench_schema import merge_default_workbench


def compose_workbench_data(context: dict[str, Any], wang: dict[str, Any], equity: dict[str, Any]) -> dict[str, Any]:
    wang = wang if isinstance(wang, dict) else {}
    equity = equity if isinstance(equity, dict) else {}
    if _requires_public_equity_sufficiency(equity, context):
        equity = apply_public_equity_sufficiency(equity, context)
    company = context.get("company", {}) if isinstance(context, dict) else {}
    action = _dict(equity.get("action"))
    code = str(company.get("code") or "").strip()
    name = str(company.get("name") or code or "个股").strip()
    market_scout = context.get("market_catalyst") if isinstance(context.get("market_catalyst"), dict) else {}
    wang_source = _agent_source(wang)
    equity_source = _agent_source(equity)
    market_scout_source = _context_source(market_scout)
    market_hype_reason, market_hype_source = _pick_with_source(
        (wang.get("market_hype_reason"), wang_source),
        (equity.get("market_hype_reason"), equity_source),
        (context.get("market_hype_reason"), market_scout_source),
    )
    traded_business_line, traded_line_source = _pick_with_source(
        (equity.get("traded_business_line"), equity_source),
        (wang.get("traded_business_line"), wang_source),
        (context.get("traded_business_line"), market_scout_source),
    )
    market_pricing, market_pricing_source = _pick_with_source(
        (equity.get("what_market_is_pricing"), equity_source),
        (wang.get("what_market_is_pricing"), wang_source),
        (context.get("what_market_is_pricing"), market_scout_source),
    )
    evidence_quality, evidence_quality_source = _pick_with_source(
        (equity.get("evidence_quality"), equity_source),
        (wang.get("evidence_quality"), wang_source),
        (context.get("evidence_quality"), market_scout_source),
    )
    why_stock_moved = _evidence_dict(
        market_narrative=market_hype_reason,
        market_theme=_pick(wang.get("theme"), context.get("company", {}).get("theme")),
        market_catalyst=_list(context.get("recent_catalysts"), []),
    )
    investment_thesis = _evidence_dict(
        traded_business_line=traded_business_line,
        what_market_is_pricing=market_pricing,
        industry_driver=_pick(wang.get("theme")),
    )
    data = {
        "schema_version": "yinghang-v3",
        "ai_final_answer": {
            "score": None,
            "verdict": "missing",
            "better_choice": "missing",
            "main_reason": "missing",
            "mistake_source": "missing",
            "next_action": "missing",
        },
        "answer_evidence": {
            "why_stock_moved": why_stock_moved,
            "investment_thesis": investment_thesis,
            "better_candidates": [],
            "mistake_diagnosis": {},
            "future_rules": [],
        },
        "research_layers": {
            "market_scout": market_scout,
            "wang_industry": wang,
            "public_equity": equity,
            "trade_execution": {},
        },
        "source_trace": _build_source_trace(
            context=context,
            wang=wang,
            equity=equity,
            market_hype_reason=market_hype_reason,
            traded_business_line=traded_business_line,
            market_pricing=market_pricing,
            market_hype_source=market_hype_source,
            traded_line_source=traded_line_source,
            market_pricing_source=market_pricing_source,
            evidence_quality_source=evidence_quality_source,
        ),
        "company": {
            "code": code,
            "name": name,
            "market": company.get("market") or "A-share",
            "sector": _pick(wang.get("sector"), context.get("company", {}).get("sector"), "missing"),
            "theme": _pick(wang.get("theme"), context.get("company", {}).get("theme"), "missing"),
        },
        "sector_symbol": _pick(wang.get("sector_symbol"), ""),
        "market_hype_reason": market_hype_reason or "missing",
        "recent_catalysts": _dedupe_list(
            _list(wang.get("recent_catalysts"), [])
            + _list(equity.get("recent_catalysts"), [])
            + _list(context.get("recent_catalysts"), [])
        )[:8],
        "traded_business_line": traded_business_line or "missing",
        "what_market_is_pricing": market_pricing or "missing",
        "evidence_quality": evidence_quality or "missing",
        "market_catalyst": market_scout,
        "evidence": _list(context.get("evidence"), []),
        "news": _list(context.get("news"), []),
        "unknowns": _dedupe_list(
            _list(wang.get("unknowns"), [])
            + _list(equity.get("unknowns"), [])
            + _list(context.get("unknowns"), [])
        )[:8],
        "hero": {
            "industry_rating": _pick(wang.get("industry_rating"), "missing"),
            "investment_rating": _pick(equity.get("investment_rating"), "missing"),
            "tags": (_list(wang.get("industry_tags"), []) + _list(action.get("status_tags"), []))[:6],
            "claims": _list(wang.get("claims"), _list(equity.get("one_sentence_conclusion"), []))[:4],
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
        "valuation_odds": equity.get("valuation_odds") or None,
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


def _build_source_trace(
    *,
    context: dict[str, Any],
    wang: dict[str, Any],
    equity: dict[str, Any],
    market_hype_reason: str,
    traded_business_line: str,
    market_pricing: str,
    market_hype_source: str,
    traded_line_source: str,
    market_pricing_source: str,
    evidence_quality_source: str,
) -> dict[str, dict[str, str]]:
    wang_source = _agent_source(wang)
    equity_source = _agent_source(equity)
    market_scout = _dict(context.get("market_catalyst"))
    market_scout_source = _context_source(market_scout)
    action = _dict(equity.get("action"))
    sufficiency = _dict(equity.get("data_sufficiency"))
    trace = {
        "schema_version": _trace("hardcode", "YingHang V3 contract identifier"),
        "ai_final_answer.score": _trace("missing", "Trade Coach Agent not implemented"),
        "ai_final_answer.verdict": _trace("missing", "Trade Coach Agent not implemented"),
        "ai_final_answer.better_choice": _trace("missing", "Better Opportunity Agent not implemented"),
        "ai_final_answer.main_reason": _trace("missing", "Trade Coach Agent not implemented"),
        "ai_final_answer.mistake_source": _trace("missing", "Trade Coach Agent not implemented"),
        "ai_final_answer.next_action": _trace("missing", "Trade Coach Agent not implemented"),
        "answer_evidence.why_stock_moved.market_narrative": _trace(market_hype_source),
        "answer_evidence.why_stock_moved": _trace(
            _source_for_values(
                (market_hype_reason, market_hype_source),
                (wang.get("theme"), wang_source),
                (context.get("recent_catalysts"), market_scout_source),
            )
        ),
        "answer_evidence.why_stock_moved.market_theme": _trace(
            wang_source if _has_value(wang.get("theme")) else "missing"
        ),
        "answer_evidence.why_stock_moved.market_catalyst": _trace(
            market_scout_source if _has_value(context.get("recent_catalysts")) else "missing"
        ),
        "answer_evidence.investment_thesis.traded_business_line": _trace(traded_line_source),
        "answer_evidence.investment_thesis": _trace(
            _source_for_values(
                (traded_business_line, traded_line_source),
                (market_pricing, market_pricing_source),
                (wang.get("theme"), wang_source),
            )
        ),
        "answer_evidence.investment_thesis.what_market_is_pricing": _trace(market_pricing_source),
        "answer_evidence.investment_thesis.industry_driver": _trace(
            wang_source if _has_value(wang.get("theme")) else "missing"
        ),
        "answer_evidence.better_candidates": _trace("missing", "Better Opportunity Agent not implemented"),
        "answer_evidence.mistake_diagnosis": _trace("missing", "Trade Coach Agent not implemented"),
        "answer_evidence.future_rules": _trace("missing", "Trade Coach Agent not implemented"),
        "company.code": _trace("real_data" if _has_value(_dict(context.get("company")).get("code")) else "missing"),
        "company.name": _trace("real_data" if _has_value(_dict(context.get("company")).get("name")) else "missing"),
        "company.market": _trace(
            "real_data" if _has_value(_dict(context.get("company")).get("market")) else "hardcode"
        ),
        "company.sector": _trace(wang_source if _has_value(wang.get("sector")) else "missing"),
        "company.theme": _trace(
            wang_source
            if _has_value(wang.get("theme"))
            else ("real_data" if _has_value(_dict(context.get("company")).get("theme")) else "missing")
        ),
        "market_hype_reason": _trace(market_hype_source),
        "recent_catalysts": _trace(
            _source_for_values(
                (wang.get("recent_catalysts"), wang_source),
                (equity.get("recent_catalysts"), equity_source),
                (context.get("recent_catalysts"), market_scout_source),
            )
        ),
        "traded_business_line": _trace(traded_line_source),
        "what_market_is_pricing": _trace(market_pricing_source),
        "evidence_quality": _trace(evidence_quality_source),
        "hero.industry_rating": _trace(wang_source if _has_value(wang.get("industry_rating")) else "missing"),
        "hero.investment_rating": _trace(
            equity_source if _has_value(equity.get("investment_rating")) else "missing",
            _sufficiency_detail(sufficiency, "investment_rating"),
        ),
        "hero.tags": _trace(
            _source_for_values(
                (wang.get("industry_tags"), wang_source),
                (action.get("status_tags"), equity_source),
            )
        ),
        "hero.claims": _trace(
            wang_source
            if _has_value(wang.get("claims"))
            else (equity_source if _has_value(equity.get("one_sentence_conclusion")) else "missing")
        ),
        "profit_flow": _trace(wang_source if _has_value(wang.get("profit_flow")) else "missing"),
        "moat_radar": _trace(wang_source if _has_value(wang.get("moat_radar")) else "missing"),
        "logic_tree": _trace(wang_source if _has_value(wang.get("logic_tree")) else "missing"),
        "expectation_gap": _trace(
            equity_source if _has_value(equity.get("expectation_gap")) else "missing",
            _sufficiency_detail(sufficiency, "expectation_gap.gap_score"),
        ),
        "validation_panel": _trace(
            equity_source if _has_value(equity.get("validation_panel")) else "missing"
        ),
        "catalysts": _trace(equity_source if _has_value(equity.get("catalysts")) else "missing"),
        "risks": _trace(equity_source if _has_value(equity.get("risks")) else "missing"),
        "action": _trace(equity_source if _has_value(action) else "missing"),
        "trade_review": _trace("real_data" if _has_value(context.get("trade")) else "missing"),
        "research_layers.market_scout": _trace(market_scout_source),
        "research_layers.wang_industry": _trace(wang_source),
        "research_layers.public_equity": _trace(equity_source),
        "research_layers.trade_execution": _trace("missing", "Joined later in the report pipeline"),
    }
    for path in (
        "industry_rating",
        "sector",
        "theme",
        "industry_tags",
        "claims",
        "profit_flow",
        "moat_radar",
        "logic_tree",
        "weakest_link",
        "sector_symbol",
        "peer_ranking",
        "reasoning_summary",
        "deep_memo",
    ):
        trace[f"research_layers.wang_industry.{path}"] = _trace(
            wang_source if _has_value(wang.get(path)) else "missing"
        )
    for path in (
        "investment_rating",
        "one_sentence_conclusion",
        "expectation_gap",
        "validation_panel",
        "catalysts",
        "risks",
        "action",
        "financial_validation",
        "valuation_odds",
        "position_sizing",
        "trading_implication",
        "deep_memo",
    ):
        trace[f"research_layers.public_equity.{path}"] = _trace(
            equity_source if _has_value(equity.get(path)) else "missing",
            _sufficiency_detail(sufficiency, path),
        )
    _trace_research_leaves(trace, "market_scout", market_scout, market_scout_source)
    _trace_research_leaves(trace, "wang_industry", wang, wang_source)
    _trace_research_leaves(trace, "public_equity", equity, equity_source)
    trace["research_layers.public_equity.financial_validation"] = _trace(
        equity_source if _has_value(equity.get("financial_validation")) else "missing",
        _sufficiency_detail(sufficiency, "financial_validation")
        or "No structured financial statements are present in stock_context",
    )
    trace["research_layers.public_equity.valuation_odds"] = _trace(
        equity_source if _has_value(equity.get("valuation_odds")) else "missing",
        _sufficiency_detail(sufficiency, "valuation_odds")
        or "No PE/PB or valuation percentile data are present in stock_context",
    )
    for path in (
        "investment_rating_hypothesis",
        "financial_validation_hypothesis",
        "valuation_odds_hypothesis",
        "expectation_gap.gap_score_hypothesis",
    ):
        value = _path_value(equity, path)
        trace[f"research_layers.public_equity.{path}"] = _trace(
            equity_source if _has_value(value) else "missing",
            "LLM hypothesis retained for review; not a verified conclusion",
        )
    return trace


def _requires_public_equity_sufficiency(equity: dict[str, Any], context: dict[str, Any]) -> bool:
    if equity.get("agent_type") == "public_equity" or isinstance(equity.get("data_sufficiency"), dict):
        return True
    return any(
        key in context
        for key in (
            "financials",
            "financial_data",
            "financial_statements",
            "fundamentals",
            "valuation",
            "consensus",
            "analyst_consensus",
            "consensus_estimates",
            "estimates",
        )
    )


def _sufficiency_detail(sufficiency: dict[str, Any], field: str) -> str:
    status = _dict(sufficiency.get("field_status")).get(field)
    if status == "missing":
        missing = ", ".join(str(item) for item in _list(sufficiency.get("missing_inputs"), []))
        return f"Missing verified inputs: {missing or 'required source data'}"
    if status == "verified_input":
        return "Required structured input is present; conclusion remains LLM-generated"
    return ""


def _path_value(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _trace_research_leaves(
    trace: dict[str, dict[str, str]],
    layer_name: str,
    value: Any,
    source: str,
    *,
    prefix: str = "",
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _trace_research_leaves(trace, layer_name, item, source, prefix=child)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            child = f"{prefix}.{index}" if prefix else str(index)
            _trace_research_leaves(trace, layer_name, item, source, prefix=child)
        return
    if prefix:
        path = f"research_layers.{layer_name}.{prefix}"
        trace[path] = _trace(source if _has_value(value) else "missing")


def _context_source(market_scout: dict[str, Any]) -> str:
    if not market_scout:
        return "missing"
    if market_scout.get("agent_error"):
        return "fallback"
    if (
        not _has_value(market_scout.get("evidence"))
        and not _has_value(market_scout.get("recent_catalysts"))
        and str(market_scout.get("market_hype_reason") or "") in {"最近炒作原因待验证", "missing"}
    ):
        return "fallback"
    return "llm"


def _agent_source(agent: dict[str, Any]) -> str:
    if not agent:
        return "missing"
    return "fallback" if agent.get("agent_error") else "llm"


def _pick_with_source(*candidates: tuple[Any, str]) -> tuple[str, str]:
    for value, source in candidates:
        if _has_value(value):
            return str(value), source
    return "", "missing"


def _source_for_values(*candidates: tuple[Any, str]) -> str:
    sources = [source for value, source in candidates if _has_value(value)]
    if not sources:
        return "missing"
    if "llm" in sources:
        return "llm"
    if "real_data" in sources:
        return "real_data"
    if "fallback" in sources:
        return "fallback"
    if "hardcode" in sources:
        return "hardcode"
    return "missing"


def _evidence_dict(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if _has_value(value)}


def _trace(source: str, detail: str = "") -> dict[str, str]:
    result = {"source": source if source in {"llm", "real_data", "fallback", "hardcode", "missing"} else "missing"}
    if detail:
        result["detail"] = detail
    return result


def _has_value(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {
            "missing",
            "pending verification",
            "pending fetch",
            "待验证",
            "最近炒作原因待验证",
        }
    return True


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
        "core_driver": _first(hero.get("claims"), profit_flow.get("value_pool")),
        "node": profit_flow.get("company_position") or company.get("sector") or "",
        "sector_symbol": wang_sector_symbol(data),
        "chain_nodes": chain_nodes,
        "barriers": barriers,
        "profit_levers": profit_levers,
        "peers": [],
        "industry_judgment": _join(hero.get("claims")),
        "company_judgment": equity_conclusion(data),
        "financial_validation": [_validation_text(item) for item in validation[:6]],
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
