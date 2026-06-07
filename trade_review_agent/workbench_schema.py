from __future__ import annotations

from copy import deepcopy
from typing import Any


WORKFLOW_TIMING_KEYS = [
    "data_prep",
    "market_catalyst",
    "trading_context_agent",
    "wang_agent",
    "public_equity_agent",
    "research_agents",
    "presenter",
    "total",
]


def default_workbench_data(code: str = "", name: str = "") -> dict[str, Any]:
    stock_name = name or code or "stock"
    return {
        "company": {
            "code": code,
            "name": stock_name,
            "market": "A-share",
            "sector": "pending verification",
            "theme": "pending verification",
        },
        "market_hype_reason": "recent hype reason pending verification",
        "recent_catalysts": [],
        "traded_business_line": "pending verification",
        "what_market_is_pricing": "pending verification",
        "evidence_quality": "low",
        "unknowns": [],
        "hero": {
            "industry_rating": "B",
            "investment_rating": "B",
            "tags": ["pending verification"],
            "claims": ["research conclusion pending"],
            "note": "Missing fields are shown as pending verification; do not fabricate facts.",
        },
        "profit_flow": {
            "value_pool": "pending verification",
            "items": [],
            "company_position": "pending verification",
            "why_profit_flows_here": "pending verification",
        },
        "moat_radar": {
            "company_score": 50,
            "industry_average": 50,
            "dimensions": [],
            "explanation": "pending verification",
        },
        "logic_tree": [],
        "expectation_gap": {
            "market_believes": ["pending verification"],
            "analyst_view": ["pending verification"],
            "gap_score": 50,
            "underestimated": "pending verification",
            "overestimated": "pending verification",
        },
        "validation_panel": [],
        "catalysts": [],
        "risks": [],
        "action": {
            "status_tags": ["pending verification"],
            "current_action": "add to watchlist",
            "suitable_for": "pending verification",
            "not_suitable_for": "pending verification",
            "recheck_conditions": [],
        },
        "trade_review": {
            "trade_return_pct": 0,
            "trade_score": 0,
            "buy_verdict": "pending verification",
            "sell_verdict": "pending verification",
            "execution_lesson": "pending verification",
        },
        "trade_timing": _default_trade_timing(),
        "peer_comparison": _default_peer_comparison(code, stock_name),
        "peer_candidates": [],
        "trade_execution_notes": _default_trade_execution_notes(),
        "data_source_status": {
            "target_stock": "missing",
            "hs300_etf": "missing",
            "sector_quote": "missing",
            "peer_quotes": "missing",
        },
        "data_errors": [],
        "workflow_timings_ms": _default_workflow_timings(),
        "sources": [],
        "wang_agent": {},
        "public_equity_agent": {},
        "trading_context_agent": {},
        "deep_memos": {},
        "research_model": {
            "tier": "standard",
            "model": "gpt-4.1",
            "wang_model": "gpt-4.1",
            "public_equity_model": "gpt-4.1",
        },
        "requested_research_model": {
            "tier": "standard",
            "model": "gpt-4.1",
            "wang_model": "gpt-4.1",
            "public_equity_model": "gpt-4.1",
        },
        "agent_errors": [],
    }


def merge_default_workbench(data: dict[str, Any], *, code: str = "", name: str = "") -> dict[str, Any]:
    defaults = default_workbench_data(code, name)
    merged = deepcopy(defaults)
    _deep_update(merged, data if isinstance(data, dict) else {})
    return normalize_workbench_data(merged, code=code, name=name, fallback=defaults)


def normalize_workbench_data(
    data: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = fallback if isinstance(fallback, dict) else default_workbench_data(code, name)
    normalized = dict(data if isinstance(data, dict) else {})

    dict_keys = [
        "company",
        "hero",
        "profit_flow",
        "moat_radar",
        "expectation_gap",
        "action",
        "trade_review",
        "trade_timing",
        "peer_comparison",
        "trade_execution_notes",
        "data_source_status",
        "deep_memos",
        "wang_agent",
        "public_equity_agent",
        "trading_context_agent",
        "research_model",
        "requested_research_model",
    ]
    for key in dict_keys:
        if not isinstance(normalized.get(key), dict):
            normalized[key] = deepcopy(defaults.get(key, {}))

    normalized["company"]["code"] = str(normalized["company"].get("code") or code or "").strip()
    normalized["company"]["name"] = str(normalized["company"].get("name") or name or code or "stock").strip()
    for key in ["market", "sector", "theme"]:
        normalized["company"][key] = str(normalized["company"].get(key) or defaults["company"].get(key) or "").strip()

    hero = normalized["hero"]
    hero["industry_rating"] = str(hero.get("industry_rating") or defaults["hero"]["industry_rating"])
    hero["investment_rating"] = str(hero.get("investment_rating") or defaults["hero"]["investment_rating"])
    hero["tags"] = _str_list(hero.get("tags"))[:6] or list(defaults["hero"]["tags"])
    hero["claims"] = _str_list(hero.get("claims"))[:4] or list(defaults["hero"]["claims"])
    hero["note"] = str(hero.get("note") or defaults["hero"]["note"])

    profit = normalized["profit_flow"]
    profit["value_pool"] = str(profit.get("value_pool") or defaults["profit_flow"]["value_pool"])
    profit["company_position"] = str(profit.get("company_position") or defaults["profit_flow"]["company_position"])
    profit["why_profit_flows_here"] = str(profit.get("why_profit_flows_here") or defaults["profit_flow"]["why_profit_flows_here"])
    profit["items"] = [
        {
            "name": str(item.get("name") or "segment"),
            "share_pct": _num(item.get("share_pct"), 0),
            "highlight": bool(item.get("highlight")),
        }
        for item in _dict_list(profit.get("items"))
    ]

    moat = normalized["moat_radar"]
    moat["company_score"] = _num(moat.get("company_score"), 50)
    moat["industry_average"] = _num(moat.get("industry_average"), 50)
    moat["explanation"] = str(moat.get("explanation") or defaults["moat_radar"]["explanation"])
    moat["dimensions"] = [
        {
            "name": str(item.get("name") or "moat"),
            "company": _num(item.get("company"), 0),
            "average": _num(item.get("average"), 0),
        }
        for item in _dict_list(moat.get("dimensions"))
    ]

    normalized["logic_tree"] = [
        {
            "node": str(item.get("node") or "logic node"),
            "certainty_pct": _num(item.get("certainty_pct"), 50),
        }
        for item in _dict_list(normalized.get("logic_tree"))
    ]

    gap = normalized["expectation_gap"]
    gap["market_believes"] = _str_list(gap.get("market_believes")) or list(defaults["expectation_gap"]["market_believes"])
    gap["analyst_view"] = _str_list(gap.get("analyst_view")) or list(defaults["expectation_gap"]["analyst_view"])
    gap["gap_score"] = _num(gap.get("gap_score"), 50)
    gap["underestimated"] = str(gap.get("underestimated") or defaults["expectation_gap"]["underestimated"])
    gap["overestimated"] = str(gap.get("overestimated") or defaults["expectation_gap"]["overestimated"])

    normalized["validation_panel"] = _list(normalized.get("validation_panel"))
    normalized["catalysts"] = _list(normalized.get("catalysts"))
    normalized["risks"] = _list(normalized.get("risks"))
    normalized["sources"] = _str_list(normalized.get("sources"))
    normalized["market_hype_reason"] = str(normalized.get("market_hype_reason") or defaults["market_hype_reason"])
    normalized["recent_catalysts"] = _str_list(normalized.get("recent_catalysts"))
    normalized["traded_business_line"] = str(normalized.get("traded_business_line") or defaults["traded_business_line"])
    normalized["what_market_is_pricing"] = str(normalized.get("what_market_is_pricing") or defaults["what_market_is_pricing"])
    normalized["evidence_quality"] = str(normalized.get("evidence_quality") or defaults["evidence_quality"])
    normalized["unknowns"] = _str_list(normalized.get("unknowns"))

    action = normalized["action"]
    action["status_tags"] = _str_list(action.get("status_tags")) or list(defaults["action"]["status_tags"])
    action["current_action"] = str(action.get("current_action") or defaults["action"]["current_action"])
    action["suitable_for"] = str(action.get("suitable_for") or defaults["action"]["suitable_for"])
    action["not_suitable_for"] = str(action.get("not_suitable_for") or defaults["action"]["not_suitable_for"])
    action["recheck_conditions"] = _str_list(action.get("recheck_conditions"))

    trade = normalized["trade_review"]
    trade["trade_return_pct"] = _num(trade.get("trade_return_pct"), 0)
    trade["trade_score"] = int(_num(trade.get("trade_score"), 0))
    trade["buy_verdict"] = str(trade.get("buy_verdict") or defaults["trade_review"]["buy_verdict"])
    trade["sell_verdict"] = str(trade.get("sell_verdict") or defaults["trade_review"]["sell_verdict"])
    trade["execution_lesson"] = str(trade.get("execution_lesson") or defaults["trade_review"]["execution_lesson"])

    normalized["trade_timing"] = _normalize_trade_timing(normalized.get("trade_timing"), defaults.get("trade_timing"))
    normalized["peer_comparison"] = _normalize_peer_comparison(normalized.get("peer_comparison"), defaults.get("peer_comparison"))
    normalized["peer_candidates"] = _normalize_peer_candidates(normalized.get("peer_candidates"))
    normalized["trade_execution_notes"] = _normalize_trade_execution_notes(
        normalized.get("trade_execution_notes"), defaults.get("trade_execution_notes")
    )
    normalized["data_source_status"] = _normalize_data_source_status(
        normalized.get("data_source_status"), defaults.get("data_source_status")
    )
    normalized["data_errors"] = _str_list(normalized.get("data_errors"))
    normalized["workflow_timings_ms"] = _normalize_timings(normalized.get("workflow_timings_ms"))

    normalized["agent_errors"] = _str_list(normalized.get("agent_errors"))
    normalized["research_model"] = _research_model_metadata(normalized.get("research_model"))
    normalized["requested_research_model"] = _research_model_metadata(normalized.get("requested_research_model"))
    return normalized


def _default_trade_timing() -> dict[str, Any]:
    return {
        "benchmark_symbol": "510300",
        "benchmark_name": "沪深300ETF",
        "sector_name": "pending verification",
        "buy_day": _default_trade_timing_day(),
        "sell_day": _default_trade_timing_day(),
        "summary": "pending verification",
    }


def _default_workflow_timings() -> dict[str, int]:
    return {key: 0 for key in WORKFLOW_TIMING_KEYS}


def _default_trade_timing_day() -> dict[str, Any]:
    return {
        "date": "",
        "stock_pct": 0.0,
        "hs300_etf_pct": 0.0,
        "sector_pct": 0.0,
        "vs_hs300_etf_pct": 0.0,
        "vs_sector_pct": 0.0,
        "price_position_pct": 0.0,
        "judgment": "pending verification",
        "reason": "pending verification",
        "data_source": "stock:missing; hs300_etf:missing; sector:missing",
    }


def _default_peer_comparison(code: str, name: str) -> dict[str, Any]:
    return {
        "concept": "pending verification",
        "sector_symbol": "",
        "target": {"name": name or code or "stock", "code": code},
        "rows": [],
        "conclusion": "pending verification",
        "data_note": "pending verification",
    }


def _default_trade_execution_notes() -> dict[str, Any]:
    return {
        "buy_note": "pending verification",
        "sell_note": "pending verification",
        "discipline_note": "pending verification",
        "summary": "pending verification",
    }


def _normalize_trade_timing(value: Any, fallback: Any) -> dict[str, Any]:
    fallback_dict = fallback if isinstance(fallback, dict) else _default_trade_timing()
    data = deepcopy(fallback_dict)
    if isinstance(value, dict):
        _deep_update(data, value)
    data["benchmark_symbol"] = str(data.get("benchmark_symbol") or fallback_dict["benchmark_symbol"])
    data["benchmark_name"] = str(data.get("benchmark_name") or fallback_dict["benchmark_name"])
    data["sector_name"] = str(data.get("sector_name") or fallback_dict["sector_name"])
    data["buy_day"] = _normalize_trade_timing_day(data.get("buy_day"), fallback_dict.get("buy_day"))
    data["sell_day"] = _normalize_trade_timing_day(data.get("sell_day"), fallback_dict.get("sell_day"))
    data["summary"] = str(data.get("summary") or fallback_dict["summary"])
    return data


def _normalize_trade_timing_day(value: Any, fallback: Any) -> dict[str, Any]:
    fallback_dict = fallback if isinstance(fallback, dict) else _default_trade_timing_day()
    row = deepcopy(fallback_dict)
    if isinstance(value, dict):
        _deep_update(row, value)
    row["date"] = str(row.get("date") or fallback_dict["date"])
    for key in ["stock_pct", "hs300_etf_pct", "sector_pct", "vs_hs300_etf_pct", "vs_sector_pct", "price_position_pct"]:
        row[key] = _num(row.get(key), fallback_dict.get(key, 0.0))
    row["judgment"] = str(row.get("judgment") or fallback_dict["judgment"])
    row["reason"] = str(row.get("reason") or fallback_dict["reason"])
    row["data_source"] = str(row.get("data_source") or fallback_dict["data_source"])
    return row


def _normalize_peer_comparison(value: Any, fallback: Any) -> dict[str, Any]:
    fallback_dict = fallback if isinstance(fallback, dict) else _default_peer_comparison("", "")
    data = deepcopy(fallback_dict)
    if isinstance(value, dict):
        _deep_update(data, value)
    target = data.get("target") if isinstance(data.get("target"), dict) else {}
    data["concept"] = str(data.get("concept") or fallback_dict["concept"])
    data["sector_symbol"] = str(data.get("sector_symbol") or fallback_dict["sector_symbol"])
    data["target"] = {
        "name": str(target.get("name") or fallback_dict["target"]["name"]),
        "code": str(target.get("code") or fallback_dict["target"]["code"]),
    }
    data["rows"] = [
        {
            "name": str(item.get("name") or ""),
            "code": str(item.get("code") or ""),
            "is_target": bool(item.get("is_target")),
            "day_pct": _num(item.get("day_pct"), 0),
            "five_day_pct": _num(item.get("five_day_pct"), 0),
            "twenty_day_pct": _num(item.get("twenty_day_pct"), 0),
            "strength": str(item.get("strength") or "pending verification"),
            "advantage": str(item.get("advantage") or "pending verification"),
            "weakness": str(item.get("weakness") or "pending verification"),
            "quote_source": str(item.get("quote_source") or "missing"),
        }
        for item in _dict_list(data.get("rows"))
    ]
    data["conclusion"] = str(data.get("conclusion") or fallback_dict["conclusion"])
    data["data_note"] = str(data.get("data_note") or fallback_dict["data_note"])
    return data


def _normalize_peer_candidates(value: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": str(item.get("name") or ""),
            "code": str(item.get("code") or ""),
            "is_target": bool(item.get("is_target")),
            "candidate_source": str(item.get("candidate_source") or "pending verification"),
            "quote_source": str(item.get("quote_source") or "missing"),
        }
        for item in _dict_list(value)
    ]


def _normalize_trade_execution_notes(value: Any, fallback: Any) -> dict[str, Any]:
    fallback_dict = fallback if isinstance(fallback, dict) else _default_trade_execution_notes()
    data = deepcopy(fallback_dict)
    if isinstance(value, dict):
        _deep_update(data, value)
    for key in ["buy_note", "sell_note", "discipline_note", "summary"]:
        data[key] = str(data.get(key) or fallback_dict[key])
    return data


def _normalize_data_source_status(value: Any, fallback: Any) -> dict[str, str]:
    fallback_dict = fallback if isinstance(fallback, dict) else {
        "target_stock": "missing",
        "hs300_etf": "missing",
        "sector_quote": "missing",
        "peer_quotes": "missing",
    }
    allowed = {"tencent_finance", "akshare", "fallback_existing", "missing"}
    data = deepcopy(fallback_dict)
    if isinstance(value, dict):
        _deep_update(data, value)
    for key in ["target_stock", "hs300_etf", "sector_quote", "peer_quotes"]:
        current = str(data.get(key) or fallback_dict.get(key) or "missing")
        data[key] = current if current in allowed else "missing"
    return data


def _normalize_timings(value: Any) -> dict[str, int]:
    data = value if isinstance(value, dict) else {}
    result = _default_workflow_timings()
    for key in WORKFLOW_TIMING_KEYS:
        item = data.get(key)
        try:
            result[key] = max(0, int(round(float(item))))
        except Exception:
            continue
    return result


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        elif value not in (None, "", [], {}):
            target[key] = deepcopy(value)


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _str_list(value: Any) -> list[str]:
    return [str(item) for item in _list(value)]


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in (None, "", [], {})]
    if isinstance(value, tuple):
        return [item for item in value if item not in (None, "", [], {})]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _num(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _research_model_metadata(value: Any) -> dict[str, str]:
    value = value if isinstance(value, dict) else {}
    tier = "better" if str(value.get("tier") or "").strip().lower() == "better" else "standard"
    default_model = "gpt-5.5" if tier == "better" else "gpt-4.1"
    model = str(value.get("model") or default_model)
    return {
        "tier": tier,
        "model": model,
        "wang_model": str(value.get("wang_model") or model),
        "public_equity_model": str(value.get("public_equity_model") or model),
    }
