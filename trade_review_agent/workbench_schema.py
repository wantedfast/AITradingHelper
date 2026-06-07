from __future__ import annotations

from copy import deepcopy
from typing import Any


def default_workbench_data(code: str = "", name: str = "") -> dict[str, Any]:
    return {
        "company": {
            "code": code,
            "name": name or code or "stock",
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
        "sources": [],
        "wang_agent": {},
        "public_equity_agent": {},
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

    for key in [
        "company",
        "hero",
        "profit_flow",
        "moat_radar",
        "expectation_gap",
        "action",
        "trade_review",
        "deep_memos",
        "wang_agent",
        "public_equity_agent",
        "research_model",
        "requested_research_model",
    ]:
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

    normalized["agent_errors"] = _str_list(normalized.get("agent_errors"))
    normalized["research_model"] = _research_model_metadata(normalized.get("research_model"))
    normalized["requested_research_model"] = _research_model_metadata(normalized.get("requested_research_model"))
    return normalized


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
