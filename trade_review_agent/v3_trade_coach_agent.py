from __future__ import annotations

import json
from typing import Any

from .v3_market_scout import LLMCaller, MISSING


FINAL_FIELDS = ("score", "verdict", "better_choice", "main_reason", "mistake_source", "next_action")

_FIELD_DEPENDENCIES = {
    "score": (
        "trade_execution.trade_execution_notes",
        "trade_execution.execution_advice",
        "trade_execution.trade_timing",
        "trade_execution.buy_verdict",
        "trade_execution.sell_verdict",
        "wang_industry.industry_rating",
        "wang_industry.industry_position",
        "wang_industry.profit_flow.company_position",
        "wang_industry.moat_radar.company_score",
        "public_equity.investment_rating",
        "public_equity.quality_rating",
        "public_equity.financial_validation",
        "public_equity.valuation_odds",
        "public_equity.expectation_gap.gap_score",
        "market_scout.market_theme",
        "market_scout.market_catalyst",
        "market_scout.sector_strength",
        "better_opportunity.better_candidates",
        "better_opportunity.confidence",
    ),
    "verdict": (
        "trade_execution.trade_execution_notes",
        "trade_execution.execution_advice",
        "trade_execution.buy_verdict",
        "trade_execution.sell_verdict",
        "wang_industry.industry_rating",
        "wang_industry.industry_position",
        "wang_industry.profit_flow.company_position",
        "public_equity.investment_rating",
        "public_equity.quality_rating",
        "public_equity.financial_validation",
        "market_scout.market_theme",
        "market_scout.market_catalyst",
        "better_opportunity.better_candidates",
    ),
    "better_choice": (
        "better_opportunity.better_candidates",
    ),
    "main_reason": (
        "trade_execution.trade_execution_notes",
        "wang_industry.industry_position",
        "wang_industry.profit_flow",
        "wang_industry.moat_radar",
        "public_equity.financial_validation",
        "public_equity.expectation_gap",
        "public_equity.risks",
        "market_scout.market_theme",
        "market_scout.market_catalyst",
        "market_scout.sector_strength",
        "better_opportunity.superiority_reason",
        "better_opportunity.replacement_thesis",
    ),
    "mistake_source": (
        "trade_execution.trade_execution_notes",
        "trade_execution.execution_advice",
        "trade_execution.trade_timing",
        "trade_execution.buy_verdict",
        "trade_execution.sell_verdict",
        "wang_industry.weakest_link",
        "public_equity.risks",
        "better_opportunity.better_candidates",
    ),
    "next_action": (
        "trade_execution.execution_advice",
        "trade_execution.trade_execution_notes",
        "wang_industry.weakest_link",
        "wang_industry.logic_tree",
        "public_equity.risks",
        "public_equity.valuation_odds",
        "market_scout.market_catalyst",
        "market_scout.industry_news",
        "better_opportunity.replacement_thesis",
    ),
}


def run_trade_coach_agent(
    *,
    execution: dict[str, Any],
    wang: dict[str, Any],
    public_equity: dict[str, Any],
    better_opportunity: dict[str, Any],
    market_scout: dict[str, Any] | None = None,
    llm_caller: LLMCaller | None = None,
) -> dict[str, Any]:
    context = build_trade_coach_context(
        execution=execution,
        wang=wang,
        public_equity=public_equity,
        better_opportunity=better_opportunity,
        market_scout=market_scout or {},
    )
    evidence = build_answer_evidence(context)
    missing_reason = data_sufficiency_error(context)
    if missing_reason or llm_caller is None:
        return missing_trade_coach_answer(
            missing_reason or "LLM caller is not configured",
            answer_evidence=evidence,
            context=context,
        )

    raw = llm_caller(_system_prompt(), _user_prompt(context))
    return normalize_trade_coach_answer(raw, context=context, answer_evidence=evidence)


def build_trade_coach_context(
    *,
    execution: dict[str, Any],
    wang: dict[str, Any],
    public_equity: dict[str, Any],
    better_opportunity: dict[str, Any],
    market_scout: dict[str, Any],
) -> dict[str, Any]:
    return {
        "trade_execution": execution if isinstance(execution, dict) else {},
        "wang_industry": wang if isinstance(wang, dict) else {},
        "public_equity": public_equity if isinstance(public_equity, dict) else {},
        "better_opportunity": better_opportunity if isinstance(better_opportunity, dict) else {},
        "market_scout": market_scout if isinstance(market_scout, dict) else {},
    }


def data_sufficiency_error(context: dict[str, Any]) -> str:
    execution = _dict(context.get("trade_execution"))
    if not execution:
        return "missing trade execution analysis"
    has_execution_judgment = any(
        _has_value(value)
        for value in (
            execution.get("trade_execution_notes"),
            execution.get("execution_advice"),
            execution.get("trade_timing"),
            execution.get("buy_verdict"),
            execution.get("sell_verdict"),
        )
    )
    if not has_execution_judgment:
        return "trade execution analysis has no usable judgment"
    if not _dict(context.get("wang_industry")) and not _dict(context.get("public_equity")):
        return "missing both WANG and Public Equity research"
    return ""


def build_answer_evidence(context: dict[str, Any]) -> dict[str, Any]:
    scout = _dict(context.get("market_scout"))
    wang = _dict(context.get("wang_industry"))
    public = _dict(context.get("public_equity"))
    better = _dict(context.get("better_opportunity"))
    execution = _dict(context.get("trade_execution"))
    return {
        "why_stock_moved": {
            "market_theme": scout.get("market_theme", MISSING),
            "market_catalyst": scout.get("market_catalyst", []),
            "sector_strength": scout.get("sector_strength", MISSING),
        },
        "investment_thesis": {
            "industry_position": wang.get("industry_position")
            or _dict(wang.get("profit_flow")).get("company_position")
            or MISSING,
            "profit_flow": wang.get("profit_flow") or {},
            "quality_rating": public.get("quality_rating") or public.get("investment_rating") or MISSING,
            "expectation_gap": public.get("expectation_gap") or {},
        },
        "better_candidates": better.get("better_candidates")
        if better.get("status") == "available"
        else [],
        "mistake_diagnosis": {
            "execution": execution.get("trade_execution_notes")
            or execution.get("execution_advice")
            or {
                "buy_verdict": execution.get("buy_verdict", MISSING),
                "sell_verdict": execution.get("sell_verdict", MISSING),
            },
            "research_risks": public.get("risks") or [],
            "weakest_industry_link": wang.get("weakest_link") or MISSING,
        },
        "future_rules": [],
    }


def missing_trade_coach_answer(
    reason: str,
    *,
    answer_evidence: dict[str, Any],
    context: dict[str, Any] | None = None,
    research_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_context = context if isinstance(context, dict) else {}
    return {
        "status": MISSING,
        "ai_final_answer": {
            "score": None,
            "verdict": MISSING,
            "better_choice": MISSING,
            "main_reason": MISSING,
            "mistake_source": MISSING,
            "next_action": MISSING,
        },
        "answer_evidence": answer_evidence,
        "missing_reason": reason,
        "research_metrics": research_metrics or {},
        "source_trace": build_final_answer_source_trace(
            safe_context,
            source="missing",
            reason=reason,
        ),
    }


def normalize_trade_coach_answer(
    payload: Any,
    *,
    context: dict[str, Any],
    answer_evidence: dict[str, Any],
) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    research_metrics = _dict(data.get("_report_llm_call"))
    if data.get("_agent_error") and research_metrics:
        research_metrics = {**research_metrics, "status": "error", "error": _text(data.get("_agent_error"))}
    answer = _dict(data.get("ai_final_answer")) or data
    score = _score(answer.get("score") if "score" in answer else answer.get("ai_score"))
    verdict = _text(answer.get("verdict"))
    main_reason = _text(answer.get("main_reason"))
    mistake_source = _normalize_mistake_source(answer.get("mistake_source"))
    next_action = _text(answer.get("next_action"))
    better_choice = _validated_better_choice(
        answer.get("better_choice"),
        _dict(context.get("better_opportunity")),
    )
    future_rules = _str_list(data.get("future_rules"))
    investment_principles = _str_list(data.get("investment_principles"))
    correct_decision = _str_list(data.get("correct_decision"))
    wrong_decision = _str_list(data.get("wrong_decision"))

    if None in (score,) or not all((verdict, main_reason, mistake_source, next_action)):
        return missing_trade_coach_answer(
            "LLM output lacked required final-answer fields",
            answer_evidence=answer_evidence,
            context=context,
            research_metrics=research_metrics,
        )

    better_status = _dict(context.get("better_opportunity")).get("status")
    if better_status == "available" and not better_choice:
        return missing_trade_coach_answer(
            "LLM better_choice was not present in supported better candidates",
            answer_evidence=answer_evidence,
            context=context,
            research_metrics=research_metrics,
        )
    if better_status != "available":
        better_choice = MISSING

    answer_evidence = dict(answer_evidence)
    answer_evidence["future_rules"] = future_rules
    answer_evidence["mistake_diagnosis"] = {
        **_dict(answer_evidence.get("mistake_diagnosis")),
        "mistake_source": mistake_source,
        "correct_decision": correct_decision,
        "wrong_decision": wrong_decision,
        "investment_principles": investment_principles,
    }
    return {
        "status": "available",
        "ai_final_answer": {
            "score": score,
            "verdict": verdict,
            "better_choice": better_choice,
            "main_reason": main_reason,
            "mistake_source": mistake_source,
            "next_action": next_action,
        },
        "answer_evidence": answer_evidence,
        "missing_reason": "",
        "research_metrics": research_metrics,
        "source_trace": build_final_answer_source_trace(context, source="llm"),
    }


def build_final_answer_source_trace(
    context: dict[str, Any],
    *,
    source: str,
    reason: str = "",
) -> dict[str, Any]:
    trace: dict[str, Any] = {}
    for field in FINAL_FIELDS:
        depends_on = [
            path
            for path in _FIELD_DEPENDENCIES[field]
            if _has_value(_path_value(context, path))
        ]
        missing_dependencies = _missing_dependencies(context, field)
        entry: dict[str, Any] = {
            "source": source,
            "agent": "trade_coach",
            "depends_on": depends_on,
            "missing_dependencies": missing_dependencies,
            "confidence": (
                _lineage_confidence(field, depends_on, missing_dependencies, context)
                if source == "llm"
                else None
            ),
        }
        if reason:
            entry["detail"] = reason
        trace[f"ai_final_answer.{field}"] = entry
    return trace


def _missing_dependencies(context: dict[str, Any], field: str) -> list[str]:
    relevant_roots = {
        path.split(".", 1)[0]
        for path in _FIELD_DEPENDENCIES[field]
    }
    missing: list[str] = []
    for root in sorted(relevant_roots):
        layer = _dict(context.get(root))
        if not layer:
            missing.append(root)
            continue
        sufficiency = _dict(layer.get("data_sufficiency"))
        field_status = _dict(sufficiency.get("field_status"))
        for status_path, status in field_status.items():
            if status not in {"verified_input", "available", "verified"}:
                missing.append(f"{root}.{status_path}")
        missing_inputs = sufficiency.get("missing_inputs")
        if isinstance(missing_inputs, list):
            missing.extend(
                f"{root}.data_sufficiency.missing_inputs.{item}"
                for item in missing_inputs
                if _text(item)
            )

    if field == "better_choice":
        better = _dict(context.get("better_opportunity"))
        candidates = better.get("better_candidates")
        if better.get("status") != "available" or not isinstance(candidates, list) or not candidates:
            missing.append("better_opportunity.better_candidates")
    return list(dict.fromkeys(missing))


def _lineage_confidence(
    field: str,
    depends_on: list[str],
    missing_dependencies: list[str],
    context: dict[str, Any],
) -> str:
    if field == "better_choice":
        confidence = _dict(context.get("better_opportunity")).get("confidence")
        try:
            number = float(confidence)
        except (TypeError, ValueError):
            return "low"
        if number >= 0.75:
            return "high"
        return "medium" if number >= 0.5 else "low"

    roots = {path.split(".", 1)[0] for path in depends_on}
    if len(roots) >= 4 and not missing_dependencies:
        return "high"
    if len(roots) >= 3:
        return "medium"
    return "low"


def _path_value(context: dict[str, Any], path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def validate_trade_coach_contract(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["trade coach output must be an object"]
    errors: list[str] = []
    answer = payload.get("ai_final_answer")
    if not isinstance(answer, dict):
        return ["ai_final_answer must be an object"]
    for field in FINAL_FIELDS:
        if field not in answer:
            errors.append(f"missing ai_final_answer field: {field}")
    if payload.get("status") == MISSING:
        if answer.get("score") is not None:
            errors.append("missing result must not have a default score")
    elif payload.get("status") == "available":
        if _score(answer.get("score")) is None:
            errors.append("available score must be from 0 to 100")
    else:
        errors.append("status must be available or missing")
    if not isinstance(payload.get("answer_evidence"), dict):
        errors.append("answer_evidence must be an object")
    return errors


def _system_prompt() -> str:
    return (
        "You are YingHang V3 Trade Coach. Synthesize the supplied execution, WANG, Public Equity, "
        "and Better Opportunity outputs into a user-facing answer. Do not invent evidence. "
        "The score must be reasoned from supplied evidence and must never be a default. "
        "If Better Opportunity is missing, better_choice must be 'missing'. Return JSON only."
    )


def _user_prompt(context: dict[str, Any]) -> str:
    contract = {
        "ai_final_answer": {
            "score": "0-100, no default",
            "verdict": "",
            "better_choice": "supported candidate name/code or missing",
            "main_reason": "",
            "mistake_source": "selection/execution/both/none/insufficient_data",
            "next_action": "",
        },
        "future_rules": [],
        "investment_principles": [],
        "correct_decision": [],
        "wrong_decision": [],
    }
    return json.dumps({"contract": contract, "context": context}, ensure_ascii=False, default=str)


def _validated_better_choice(value: Any, better: dict[str, Any]) -> str:
    if better.get("status") != "available":
        return MISSING
    requested = _text(value)
    candidates = better.get("better_candidates")
    if not requested or not isinstance(candidates, list):
        return ""
    for item in candidates:
        if not isinstance(item, dict):
            continue
        code = _text(item.get("code"))
        name = _text(item.get("name"))
        if requested in {code, name, f"{name} {code}".strip(), f"{code} {name}".strip()}:
            return name or code
    return ""


def _normalize_mistake_source(value: Any) -> str:
    text = _text(value).lower()
    aliases = {
        "选股": "selection",
        "逻辑": "selection",
        "执行": "execution",
        "两者": "both",
        "都有": "both",
        "无": "none",
        "数据不足": "insufficient_data",
    }
    text = aliases.get(text, text)
    return text if text in {"selection", "execution", "both", "none", "insufficient_data"} else ""


def _score(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= number <= 100:
        return round(number, 2)
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
