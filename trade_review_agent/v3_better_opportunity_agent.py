from __future__ import annotations

import json
from typing import Any

from .v3_market_scout import LLMCaller, MISSING


def run_better_opportunity_agent(
    *,
    company: dict[str, Any],
    market_scout: dict[str, Any],
    wang: dict[str, Any],
    public_equity: dict[str, Any],
    llm_caller: LLMCaller | None = None,
) -> dict[str, Any]:
    context = build_better_opportunity_context(
        company=company,
        market_scout=market_scout,
        wang=wang,
        public_equity=public_equity,
    )
    missing_reason = data_sufficiency_error(context)
    if missing_reason or llm_caller is None:
        return missing_better_opportunity(
            missing_reason or "LLM caller is not configured",
            peer_snapshot=context["peer_snapshot"],
        )

    raw = llm_caller(_system_prompt(), _user_prompt(context))
    return normalize_better_opportunity(raw, allowed_peers=context["peer_snapshot"])


def build_better_opportunity_context(
    *,
    company: dict[str, Any],
    market_scout: dict[str, Any],
    wang: dict[str, Any],
    public_equity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "company": company if isinstance(company, dict) else {},
        "market_theme": market_scout.get("market_theme"),
        "peer_snapshot": market_scout.get("peer_snapshot") if isinstance(market_scout.get("peer_snapshot"), list) else [],
        "wang": {
            "industry_position": wang.get("industry_position") or _dict(wang.get("profit_flow")).get("company_position"),
            "moat_radar": wang.get("moat_radar"),
            "peer_ranking": wang.get("peer_ranking"),
            "logic_tree": wang.get("logic_tree"),
        },
        "public_equity": {
            "quality_rating": public_equity.get("quality_rating") or public_equity.get("investment_rating"),
            "financial_validation": public_equity.get("financial_validation"),
            "valuation_odds": public_equity.get("valuation_odds"),
            "risk_score": public_equity.get("risk_score"),
            "risks": public_equity.get("risks"),
        },
    }


def data_sufficiency_error(context: dict[str, Any]) -> str:
    peers = context.get("peer_snapshot")
    if not isinstance(peers, list) or not peers:
        return "missing comparable peer_snapshot"

    target = _dict(context.get("company"))
    target_code = _text(target.get("code"))
    target_name = _text(target.get("name"))
    comparable = [
        peer
        for peer in peers
        if isinstance(peer, dict)
        and (_text(peer.get("code")) != target_code or _text(peer.get("name")) != target_name)
        and isinstance(peer.get("metrics"), dict)
        and bool(peer.get("metrics"))
    ]
    if not comparable:
        return "missing peer with comparable real metrics"

    has_industry_context = any(
        _has_value(value)
        for value in (
            context.get("market_theme"),
            _dict(context.get("wang")).get("industry_position"),
            _dict(context.get("wang")).get("moat_radar"),
        )
    )
    if not has_industry_context:
        return "missing industry comparison context"
    return ""


def missing_better_opportunity(reason: str, *, peer_snapshot: list[Any] | None = None) -> dict[str, Any]:
    return {
        "status": MISSING,
        "better_candidates": [],
        "superiority_reason": MISSING,
        "confidence": None,
        "replacement_thesis": MISSING,
        "missing_reason": reason,
        "evaluated_peers": len(peer_snapshot or []),
        "source_trace": {
            "better_candidates": {"source": "missing", "detail": reason},
            "superiority_reason": {"source": "missing", "detail": reason},
            "confidence": {"source": "missing", "detail": reason},
            "replacement_thesis": {"source": "missing", "detail": reason},
        },
    }


def normalize_better_opportunity(
    payload: Any,
    *,
    allowed_peers: list[dict[str, Any]],
) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    allowed = {
        (_text(peer.get("code")), _text(peer.get("name")))
        for peer in allowed_peers
        if isinstance(peer, dict)
    }
    candidates: list[dict[str, Any]] = []
    raw_candidates = data.get("better_candidates")
    if isinstance(raw_candidates, list):
        for item in raw_candidates:
            if not isinstance(item, dict):
                continue
            code = _text(item.get("code"))
            name = _text(item.get("name"))
            if (code, name) not in allowed:
                continue
            candidates.append(
                {
                    "code": code,
                    "name": name,
                    "superiority_reason": _text(item.get("superiority_reason")) or MISSING,
                    "evidence": _str_list(item.get("evidence")),
                }
            )
    confidence = _confidence(data.get("confidence"))
    superiority_reason = _text(data.get("superiority_reason"))
    replacement_thesis = _text(data.get("replacement_thesis"))
    if not candidates or confidence is None or not superiority_reason or not replacement_thesis:
        return missing_better_opportunity(
            "LLM output lacked a supported candidate or required conclusion fields",
            peer_snapshot=allowed_peers,
        )
    return {
        "status": "available",
        "better_candidates": candidates[:5],
        "superiority_reason": superiority_reason,
        "confidence": confidence,
        "replacement_thesis": replacement_thesis,
        "missing_reason": "",
        "evaluated_peers": len(allowed_peers),
        "source_trace": {
            "better_candidates": {"source": "llm"},
            "superiority_reason": {"source": "llm"},
            "confidence": {"source": "llm"},
            "replacement_thesis": {"source": "llm"},
        },
    }


def validate_better_opportunity_contract(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["better opportunity output must be an object"]
    errors: list[str] = []
    for field in ("better_candidates", "superiority_reason", "confidence", "replacement_thesis"):
        if field not in payload:
            errors.append(f"missing field: {field}")
    if payload.get("status") == MISSING:
        if payload.get("better_candidates") != []:
            errors.append("missing result must not contain better candidates")
        if payload.get("confidence") is not None:
            errors.append("missing result must not contain confidence")
    elif payload.get("status") == "available":
        if not isinstance(payload.get("better_candidates"), list) or not payload["better_candidates"]:
            errors.append("available result requires better_candidates")
        if _confidence(payload.get("confidence")) is None:
            errors.append("available result requires confidence from 0 to 1")
    else:
        errors.append("status must be available or missing")
    return errors


def _system_prompt() -> str:
    return (
        "You are YingHang V3 Better Opportunity Agent. Compare only peers present in peer_snapshot. "
        "Do not invent a company, metric, financial fact, or ranking. A candidate must be supported "
        "by supplied comparable metrics. Return JSON only."
    )


def _user_prompt(context: dict[str, Any]) -> str:
    contract = {
        "better_candidates": [
            {
                "code": "must exactly match peer_snapshot",
                "name": "must exactly match peer_snapshot",
                "superiority_reason": "",
                "evidence": ["specific supplied metrics"],
            }
        ],
        "superiority_reason": "",
        "confidence": "number from 0 to 1",
        "replacement_thesis": "",
    }
    return json.dumps({"contract": contract, "context": context}, ensure_ascii=False, default=str)


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= number <= 1:
        return number
    return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "", [], {}) else ""


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_text(item) for item in value if _text(item)]


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {}, MISSING, "pending verification", "待验证")
