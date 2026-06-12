from __future__ import annotations

from typing import Any

from .v3_better_opportunity_agent import run_better_opportunity_agent
from .v3_market_scout import LLMCaller, run_market_scout
from .v3_trade_coach_agent import run_trade_coach_agent


def run_v3_pipeline(
    *,
    company: dict[str, Any],
    market_facts: dict[str, Any],
    wang: dict[str, Any],
    public_equity: dict[str, Any],
    trade_execution: dict[str, Any],
    market_scout_caller: LLMCaller | None = None,
    better_opportunity_caller: LLMCaller | None = None,
    trade_coach_caller: LLMCaller | None = None,
) -> dict[str, Any]:
    """Run the standalone V3 stages without modifying the legacy report chain."""

    market_scout = run_market_scout(market_facts, llm_caller=market_scout_caller)
    better = run_better_opportunity_agent(
        company=company,
        market_scout=market_scout,
        wang=wang,
        public_equity=public_equity,
        llm_caller=better_opportunity_caller,
    )
    coach = run_trade_coach_agent(
        execution=trade_execution,
        wang=wang,
        public_equity=public_equity,
        better_opportunity=better,
        market_scout=market_scout,
        llm_caller=trade_coach_caller,
    )
    research_layers = {
        "market_scout": _without_key(market_scout, "source_trace"),
        "wang_industry": wang if isinstance(wang, dict) else {},
        "public_equity": public_equity if isinstance(public_equity, dict) else {},
        "trade_execution": trade_execution if isinstance(trade_execution, dict) else {},
    }
    return {
        "schema_version": "yinghang-v3-pipeline",
        "ai_final_answer": coach["ai_final_answer"],
        "answer_evidence": coach["answer_evidence"],
        "research_layers": research_layers,
        "source_trace": _merge_source_trace(
            market_scout=market_scout,
            research_layers=research_layers,
            better=better,
            coach=coach,
        ),
    }


def validate_v3_pipeline_contract(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["pipeline output must be an object"]
    errors: list[str] = []
    for field in ("ai_final_answer", "answer_evidence", "research_layers", "source_trace"):
        if not isinstance(payload.get(field), dict):
            errors.append(f"{field} must be an object")
    layers = payload.get("research_layers")
    if isinstance(layers, dict):
        for layer in (
            "market_scout",
            "wang_industry",
            "public_equity",
            "trade_execution",
        ):
            if not isinstance(layers.get(layer), dict):
                errors.append(f"research layer must be an object: {layer}")
    return errors


def _merge_source_trace(
    *,
    market_scout: dict[str, Any],
    research_layers: dict[str, dict[str, Any]],
    better: dict[str, Any],
    coach: dict[str, Any],
) -> dict[str, Any]:
    better_available = better.get("status") == "available"
    coach_available = coach.get("status") == "available"
    wang = _dict(research_layers.get("wang_industry"))
    public_equity = _dict(research_layers.get("public_equity"))
    trade_execution = _dict(research_layers.get("trade_execution"))
    answer_evidence = _dict(coach.get("answer_evidence"))
    trace: dict[str, Any] = {
        "research_layers.market_scout": _source_entry(
            "real_data" if _has_market_facts(market_scout) else "missing"
        ),
        "research_layers.wang_industry": _source_entry(
            "llm" if _has_value(wang) else "missing"
        ),
        "research_layers.public_equity": _source_entry(
            "llm" if _has_value(public_equity) else "missing"
        ),
        "research_layers.trade_execution": _source_entry(
            "real_data" if _has_value(trade_execution) else "missing",
            "Upstream execution layer may contain rule and LLM analysis.",
        ),
        "answer_evidence.why_stock_moved": _source_entry(
            "real_data" if _has_market_facts(market_scout) else "missing"
        ),
        "answer_evidence.investment_thesis": _source_entry(
            "llm"
            if _has_value(wang) or _has_value(public_equity)
            else "missing"
        ),
        "answer_evidence.better_candidates": _source_entry(
            "llm" if better_available else "missing"
        ),
        "answer_evidence.mistake_diagnosis": _source_entry(
            "llm" if coach_available else "missing"
        ),
        "answer_evidence.future_rules": _source_entry(
            "llm" if coach_available and _has_value(answer_evidence.get("future_rules")) else "missing"
        ),
    }
    trace.update(_dict(coach.get("source_trace")))
    market_field_trace = _dict(market_scout.get("source_trace"))
    _trace_leaves(
        trace,
        "research_layers.market_scout",
        _dict(research_layers.get("market_scout")),
        source_for_path=lambda path: _dict(market_field_trace.get(path.split(".", 1)[0])).get("source")
        or "missing",
    )
    _trace_leaves(
        trace,
        "research_layers.wang_industry",
        wang,
        source_for_path=lambda _path: "llm",
    )
    _trace_leaves(
        trace,
        "research_layers.public_equity",
        public_equity,
        source_for_path=lambda _path: "llm",
    )
    _trace_leaves(
        trace,
        "research_layers.trade_execution",
        trade_execution,
        source_for_path=lambda _path: "real_data",
    )
    evidence_sources = {
        "why_stock_moved": "real_data",
        "investment_thesis": "llm",
        "better_candidates": "llm" if better_available else "missing",
        "mistake_diagnosis": "llm" if coach_available else "missing",
        "future_rules": "llm" if coach_available else "missing",
    }
    _trace_leaves(
        trace,
        "answer_evidence",
        answer_evidence,
        source_for_path=lambda path: evidence_sources.get(path.split(".", 1)[0], "missing"),
    )
    return trace


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _has_market_facts(market_scout: dict[str, Any]) -> bool:
    return any(
        _has_value(market_scout.get(field))
        for field in ("market_theme", "market_catalyst", "industry_news", "sector_strength", "peer_snapshot")
    )


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {}, "missing", "pending verification")


def _source_entry(source: str, detail: str = "") -> dict[str, str]:
    entry = {"source": source}
    if detail:
        entry["detail"] = detail
    return entry


def _trace_leaves(
    trace: dict[str, Any],
    prefix: str,
    value: Any,
    *,
    source_for_path: Any,
    relative_path: str = "",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{relative_path}.{key}".strip(".")
            _trace_leaves(
                trace,
                prefix,
                child,
                source_for_path=source_for_path,
                relative_path=child_path,
            )
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{relative_path}.{index}".strip(".")
            _trace_leaves(
                trace,
                prefix,
                child,
                source_for_path=source_for_path,
                relative_path=child_path,
            )
        return
    if not _has_value(value):
        return
    trace[f"{prefix}.{relative_path}"] = _source_entry(source_for_path(relative_path))


def _without_key(value: dict[str, Any], key: str) -> dict[str, Any]:
    return {item_key: item_value for item_key, item_value in value.items() if item_key != key}
