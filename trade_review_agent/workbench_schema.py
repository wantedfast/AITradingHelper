from __future__ import annotations

from copy import deepcopy
from typing import Any


SOURCE_TYPES = {"llm", "real_data", "fallback", "hardcode", "missing"}
MISSING_TEXT = "missing"
PENDING_TEXT = "pending verification"


def default_workbench_data(code: str = "", name: str = "") -> dict[str, Any]:
    return {
        "schema_version": "yinghang-v3",
        "ai_final_answer": {
            "score": None,
            "verdict": MISSING_TEXT,
            "better_choice": MISSING_TEXT,
            "main_reason": MISSING_TEXT,
            "mistake_source": MISSING_TEXT,
            "next_action": MISSING_TEXT,
        },
        "answer_evidence": {
            "why_stock_moved": {},
            "investment_thesis": {},
            "better_candidates": [],
            "mistake_diagnosis": {},
            "future_rules": [],
        },
        "research_layers": {
            "market_scout": {},
            "wang_industry": {},
            "public_equity": {},
            "trade_execution": {},
        },
        "source_trace": {
            "ai_final_answer.score": _source_entry("missing"),
            "ai_final_answer.verdict": _source_entry("missing"),
            "ai_final_answer.better_choice": _source_entry("missing"),
            "ai_final_answer.main_reason": _source_entry("missing"),
            "ai_final_answer.mistake_source": _source_entry("missing"),
            "ai_final_answer.next_action": _source_entry("missing"),
            "answer_evidence.why_stock_moved": _source_entry("missing"),
            "answer_evidence.investment_thesis": _source_entry("missing"),
            "answer_evidence.better_candidates": _source_entry("missing"),
            "answer_evidence.mistake_diagnosis": _source_entry("missing"),
            "answer_evidence.future_rules": _source_entry("missing"),
            "research_layers.market_scout": _source_entry("missing"),
            "research_layers.wang_industry": _source_entry("missing"),
            "research_layers.public_equity": _source_entry("missing"),
            "research_layers.trade_execution": _source_entry("missing"),
        },
        "company": {
            "code": code,
            "name": name or code or "stock",
            "market": "A-share",
            "sector": MISSING_TEXT,
            "theme": MISSING_TEXT,
        },
        "market_hype_reason": MISSING_TEXT,
        "recent_catalysts": [],
        "traded_business_line": MISSING_TEXT,
        "what_market_is_pricing": MISSING_TEXT,
        "evidence_quality": MISSING_TEXT,
        "unknowns": [],
        "hero": {
            "industry_rating": MISSING_TEXT,
            "investment_rating": MISSING_TEXT,
            "tags": [],
            "claims": [],
            "note": "Missing fields are shown as pending verification; do not fabricate facts.",
        },
        "profit_flow": {},
        "moat_radar": {},
        "logic_tree": [],
        "expectation_gap": {},
        "validation_panel": [],
        "catalysts": [],
        "risks": [],
        "action": {},
        "trade_review": {},
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
        "ai_final_answer",
        "answer_evidence",
        "research_layers",
        "source_trace",
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

    normalized["schema_version"] = "yinghang-v3"
    _normalize_v3_contract(normalized, defaults)

    normalized["company"]["code"] = str(normalized["company"].get("code") or code or "").strip()
    normalized["company"]["name"] = str(normalized["company"].get("name") or name or code or "stock").strip()
    for key in ["market", "sector", "theme"]:
        normalized["company"][key] = str(normalized["company"].get(key) or defaults["company"].get(key) or "").strip()

    hero = normalized["hero"]
    hero["industry_rating"] = str(hero.get("industry_rating") or defaults["hero"]["industry_rating"])
    hero["investment_rating"] = str(hero.get("investment_rating") or defaults["hero"]["investment_rating"])
    hero["tags"] = _str_list(hero.get("tags"))[:6]
    hero["claims"] = _str_list(hero.get("claims"))[:4]
    hero["note"] = str(hero.get("note") or defaults["hero"]["note"])

    normalized["profit_flow"] = _normalize_profit_flow(normalized["profit_flow"])
    normalized["moat_radar"] = _normalize_moat_radar(normalized["moat_radar"])

    normalized["logic_tree"] = [
        _without_none(
            {
                "node": _optional_text(item.get("node")),
                "certainty_pct": _optional_num(item.get("certainty_pct")),
            }
        )
        for item in _dict_list(normalized.get("logic_tree"))
        if _optional_text(item.get("node"))
    ]

    normalized["expectation_gap"] = _normalize_expectation_gap(normalized["expectation_gap"])

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

    normalized["action"] = _normalize_action(normalized["action"])
    normalized["trade_review"] = _normalize_trade_review(normalized["trade_review"])

    normalized["agent_errors"] = _str_list(normalized.get("agent_errors"))
    normalized["research_model"] = _research_model_metadata(normalized.get("research_model"))
    normalized["requested_research_model"] = _research_model_metadata(normalized.get("requested_research_model"))
    return normalized


def _normalize_v3_contract(normalized: dict[str, Any], defaults: dict[str, Any]) -> None:
    final_answer = normalized["ai_final_answer"]
    final_answer["score"] = _optional_num(final_answer.get("score"))
    for key in ("verdict", "better_choice", "main_reason", "mistake_source", "next_action"):
        final_answer[key] = str(final_answer.get(key) or defaults["ai_final_answer"][key])

    evidence = normalized["answer_evidence"]
    for key in ("why_stock_moved", "investment_thesis", "mistake_diagnosis"):
        if not isinstance(evidence.get(key), dict):
            evidence[key] = {}
    evidence["better_candidates"] = _list(evidence.get("better_candidates"))
    evidence["future_rules"] = _str_list(evidence.get("future_rules"))

    layers = normalized["research_layers"]
    for key in ("market_scout", "wang_industry", "public_equity", "trade_execution"):
        if not isinstance(layers.get(key), dict):
            layers[key] = {}

    trace = normalized["source_trace"]
    for path, value in list(trace.items()):
        trace[str(path)] = _normalize_source_entry(value)
    for path, value in defaults["source_trace"].items():
        trace.setdefault(path, deepcopy(value))


def _normalize_profit_flow(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    result = _without_none(
        {
            "value_pool": _optional_text(value.get("value_pool")),
            "company_position": _optional_text(value.get("company_position")),
            "why_profit_flows_here": _optional_text(value.get("why_profit_flows_here")),
        }
    )
    items = []
    for item in _dict_list(value.get("items")):
        name = _optional_text(item.get("name"))
        if not name:
            continue
        items.append(
            _without_none(
                {
                    "name": name,
                    "share_pct": _optional_num(item.get("share_pct")),
                    "highlight": bool(item.get("highlight")),
                }
            )
        )
    if items:
        result["items"] = items
    return result


def _normalize_moat_radar(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    result = _without_none(
        {
            "company_score": _optional_num(value.get("company_score")),
            "industry_average": _optional_num(value.get("industry_average")),
            "explanation": _optional_text(value.get("explanation")),
        }
    )
    dimensions = []
    for item in _dict_list(value.get("dimensions")):
        name = _optional_text(item.get("name"))
        if not name:
            continue
        dimensions.append(
            _without_none(
                {
                    "name": name,
                    "company": _optional_num(item.get("company")),
                    "average": _optional_num(item.get("average")),
                }
            )
        )
    if dimensions:
        result["dimensions"] = dimensions
    return result


def _normalize_expectation_gap(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    result = _without_none(
        {
            "gap_score": _optional_num(value.get("gap_score")),
            "underestimated": _optional_text(value.get("underestimated")),
            "overestimated": _optional_text(value.get("overestimated")),
        }
    )
    market_believes = _str_list(value.get("market_believes"))
    analyst_view = _str_list(value.get("analyst_view"))
    if market_believes:
        result["market_believes"] = market_believes
    if analyst_view:
        result["analyst_view"] = analyst_view
    return result


def _normalize_action(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    result = _without_none(
        {
            "current_action": _optional_text(value.get("current_action")),
            "suitable_for": _optional_text(value.get("suitable_for")),
            "not_suitable_for": _optional_text(value.get("not_suitable_for")),
        }
    )
    status_tags = _str_list(value.get("status_tags"))
    recheck_conditions = _str_list(value.get("recheck_conditions"))
    if status_tags:
        result["status_tags"] = status_tags
    if recheck_conditions:
        result["recheck_conditions"] = recheck_conditions
    return result


def _normalize_trade_review(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    result = dict(value)
    for key in ("trade_return_pct", "return_pct"):
        if key in result:
            result[key] = _optional_num(result.get(key))
    if "trade_score" in result:
        score = _optional_num(result.get("trade_score"))
        result["trade_score"] = int(score) if score is not None else None
    return {key: item for key, item in result.items() if item not in (None, "", [], {})}


def _source_entry(source: str, *, detail: str = "") -> dict[str, str]:
    normalized = source if source in SOURCE_TYPES else "missing"
    result = {"source": normalized}
    if detail:
        result["detail"] = detail
    return result


def _normalize_source_entry(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        return _source_entry(value)
    if not isinstance(value, dict):
        return _source_entry("missing")
    return _source_entry(str(value.get("source") or "missing"), detail=str(value.get("detail") or ""))


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


def _optional_num(value: Any) -> float | None:
    if value in (None, "", MISSING_TEXT, PENDING_TEXT):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _optional_text(value: Any) -> str | None:
    if value in (None, "", MISSING_TEXT, PENDING_TEXT, "待验证", "pending fetch"):
        return None
    text = str(value).strip()
    return text or None


def _without_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


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
