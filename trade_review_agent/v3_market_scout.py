from __future__ import annotations

import json
from typing import Any, Callable


LLMCaller = Callable[[str, str], dict[str, Any]]
MISSING = "missing"
SOURCE_TYPES = {"real_data", "llm", "fallback", "hardcode", "missing"}

_FORBIDDEN_CONCLUSION_FIELDS = {
    "ai_score",
    "score",
    "verdict",
    "investment_rating",
    "industry_rating",
    "better_choice",
    "next_action",
    "recommendation",
}


def run_market_scout(
    facts: dict[str, Any],
    *,
    llm_caller: LLMCaller | None = None,
    source_trace: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize market facts without producing an investment conclusion."""

    compact_facts = _compact_facts(facts)
    fact_provenance = _merge_provenance(facts, source_trace, provenance)
    if llm_caller is None:
        return normalize_market_scout(
            compact_facts,
            source="fallback",
            input_provenance=fact_provenance,
        )

    raw = llm_caller(_system_prompt(), _user_prompt(compact_facts))
    return normalize_market_scout(
        raw,
        source="llm",
        input_facts=compact_facts,
        input_provenance=fact_provenance,
    )


def normalize_market_scout(
    payload: Any,
    *,
    source: str,
    input_facts: dict[str, Any] | None = None,
    input_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    facts = input_facts or data
    _assert_no_investment_conclusions(data)

    generated_fields: set[str] = set()
    result = {
        "market_theme": _text(data.get("market_theme")) or MISSING,
        "market_catalyst": _fact_list(data.get("market_catalyst")),
        "industry_news": _fact_list(data.get("industry_news")),
        "sector_strength": _normalize_sector_strength(data.get("sector_strength")),
        "peer_snapshot": _normalize_peers(data.get("peer_snapshot")),
        "unknowns": _str_list(data.get("unknowns")),
        "source_trace": {},
    }
    if input_facts is not None:
        for field in ("market_theme", "market_catalyst", "industry_news", "sector_strength", "peer_snapshot"):
            if _has_value(result[field]):
                generated_fields.add(field)
    if not result["market_catalyst"]:
        result["market_catalyst"] = _fact_list(facts.get("market_catalyst"))
        generated_fields.discard("market_catalyst")
    if not result["industry_news"]:
        result["industry_news"] = _fact_list(facts.get("industry_news") or facts.get("news"))
        generated_fields.discard("industry_news")
    if result["sector_strength"] == MISSING:
        result["sector_strength"] = _normalize_sector_strength(facts.get("sector_strength"))
        generated_fields.discard("sector_strength")
    if not result["peer_snapshot"]:
        result["peer_snapshot"] = _normalize_peers(facts.get("peer_snapshot") or facts.get("peers"))
        generated_fields.discard("peer_snapshot")

    normalized_source = source if source in SOURCE_TYPES else "missing"
    for field in ("market_theme", "market_catalyst", "industry_news", "sector_strength", "peer_snapshot"):
        value = result[field]
        field_source = normalized_source
        if field not in generated_fields:
            field_source = _resolve_field_source(
                field,
                facts.get(field),
                input_provenance or {},
                default=normalized_source,
            )
        result["source_trace"][field] = {
            "source": field_source if _has_value(value) else "missing"
        }
    return result


def validate_market_scout_contract(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["market scout output must be an object"]
    errors: list[str] = []
    for field in ("market_theme", "market_catalyst", "industry_news", "sector_strength", "peer_snapshot"):
        if field not in payload:
            errors.append(f"missing field: {field}")
    forbidden = sorted(_FORBIDDEN_CONCLUSION_FIELDS.intersection(payload))
    if forbidden:
        errors.append(f"market scout contains investment conclusions: {', '.join(forbidden)}")
    if not isinstance(payload.get("market_catalyst"), list):
        errors.append("market_catalyst must be a list")
    if not isinstance(payload.get("industry_news"), list):
        errors.append("industry_news must be a list")
    if not isinstance(payload.get("peer_snapshot"), list):
        errors.append("peer_snapshot must be a list")
    return errors


def _compact_facts(facts: Any) -> dict[str, Any]:
    data = facts if isinstance(facts, dict) else {}
    return {
        "company": _dict(data.get("company")),
        "market_theme": data.get("market_theme"),
        "market_catalyst": data.get("market_catalyst"),
        "industry_news": data.get("industry_news") or data.get("news"),
        "sector_strength": data.get("sector_strength"),
        "peer_snapshot": data.get("peer_snapshot") or data.get("peers"),
        "as_of": data.get("as_of"),
    }


def _merge_provenance(
    facts: Any,
    source_trace: dict[str, Any] | None,
    provenance: dict[str, Any] | None,
) -> dict[str, Any]:
    data = facts if isinstance(facts, dict) else {}
    merged: dict[str, Any] = {}
    for candidate in (
        data.get("source_trace"),
        data.get("provenance"),
        source_trace,
        provenance,
    ):
        if isinstance(candidate, dict):
            merged.update(candidate)
    return merged


def _resolve_field_source(
    field: str,
    value: Any,
    provenance: dict[str, Any],
    *,
    default: str,
) -> str:
    for key in (
        field,
        f"market_scout.{field}",
        f"research_layers.market_scout.{field}",
    ):
        source = _source_value(provenance.get(key))
        if source:
            return source
    intrinsic = _intrinsic_fact_source(value)
    if intrinsic:
        return intrinsic
    return default if default in SOURCE_TYPES else "fallback"


def _source_value(value: Any) -> str:
    source = value.get("source") if isinstance(value, dict) else value
    return source if source in SOURCE_TYPES else ""


def _intrinsic_fact_source(value: Any) -> str:
    items = value if isinstance(value, list) else [value]
    declared_sources = {
        _text(item.get("source_type"))
        for item in items
        if isinstance(item, dict) and _text(item.get("source_type")) in SOURCE_TYPES
    }
    if declared_sources:
        return next(iter(declared_sources)) if len(declared_sources) == 1 else "fallback"
    supported = [
        item
        for item in items
        if isinstance(item, dict)
        and _text(item.get("source") or item.get("url"))
        and _text(item.get("source") or item.get("url")) != MISSING
    ]
    return "real_data" if supported and len(supported) == len(items) else ""


def _system_prompt() -> str:
    return (
        "You are YingHang V3 Market Scout. Extract and organize market facts only. "
        "Do not rate, recommend, score, predict, or produce an investment conclusion. "
        "Use only supplied facts. Unknown values must be 'missing'. Return JSON only."
    )


def _user_prompt(facts: dict[str, Any]) -> str:
    contract = {
        "market_theme": "fact-supported theme or missing",
        "market_catalyst": [{"fact": "", "date": "", "source": ""}],
        "industry_news": [{"fact": "", "date": "", "source": ""}],
        "sector_strength": {
            "value": None,
            "unit": "pct",
            "window": "",
            "as_of": "",
            "source": "",
        },
        "peer_snapshot": [
            {
                "code": "",
                "name": "",
                "metrics": {},
                "as_of": "",
                "source": "",
            }
        ],
        "unknowns": [],
    }
    return json.dumps({"contract": contract, "facts": facts}, ensure_ascii=False, default=str)


def _assert_no_investment_conclusions(data: dict[str, Any]) -> None:
    forbidden = _FORBIDDEN_CONCLUSION_FIELDS.intersection(data)
    if forbidden:
        fields = ", ".join(sorted(forbidden))
        raise ValueError(f"Market Scout cannot produce investment conclusions: {fields}")


def _fact_list(value: Any) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    result: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fact = _text(item.get("fact") or item.get("event") or item.get("headline"))
        if not fact:
            continue
        result.append(
            {
                "fact": fact,
                "date": _text(item.get("date") or item.get("as_of")) or MISSING,
                "source": _text(item.get("source") or item.get("url")) or MISSING,
            }
        )
    return result[:20]


def _normalize_sector_strength(value: Any) -> dict[str, Any] | str:
    if not isinstance(value, dict):
        return MISSING
    raw_value = value.get("value")
    try:
        number = float(raw_value)
    except (TypeError, ValueError):
        return MISSING
    return {
        "value": number,
        "unit": _text(value.get("unit")) or "pct",
        "window": _text(value.get("window")) or MISSING,
        "as_of": _text(value.get("as_of")) or MISSING,
        "source": _text(value.get("source")) or MISSING,
    }


def _normalize_peers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        code = _text(item.get("code"))
        name = _text(item.get("name"))
        metrics = _dict(item.get("metrics"))
        if not (code or name) or not metrics:
            continue
        result.append(
            {
                "code": code or MISSING,
                "name": name or code or MISSING,
                "metrics": metrics,
                "as_of": _text(item.get("as_of")) or MISSING,
                "source": _text(item.get("source")) or MISSING,
            }
        )
    return result[:20]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "", [], {}) else ""


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_text(item) for item in value if _text(item)]


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {}, MISSING)
