from __future__ import annotations

import os
from typing import Any


def estimate_tokens(text: Any) -> int:
    value = str(text or "")
    if not value:
        return 0
    # Chinese prompts are dense; this deliberately errs high enough for diagnostics.
    return max(1, round(len(value) / 2.2))


def normalize_api_usage(value: Any) -> dict[str, int]:
    usage = value if isinstance(value, dict) else {}
    input_tokens = _int(
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("actual_input_tokens")
    )
    output_tokens = _int(
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("actual_output_tokens")
    )
    total_tokens = _int(
        usage.get("total_tokens")
        or usage.get("actual_total_tokens")
        or (input_tokens + output_tokens if input_tokens or output_tokens else 0)
    )
    result = {
        "actual_input_tokens": input_tokens,
        "actual_output_tokens": output_tokens,
        "actual_total_tokens": total_tokens,
    }
    if input_tokens:
        result["prompt_tokens"] = input_tokens
    if output_tokens:
        result["completion_tokens"] = output_tokens
    return result


def make_llm_call_record(
    *,
    stage: str,
    agent: str,
    model: str = "",
    mode: str = "",
    allow_web: bool | None = None,
    max_output_tokens: int | None = None,
    seconds: float | None = None,
    status: str = "ok",
    api_usage: Any = None,
    estimated_input_tokens: int | None = None,
    estimated_output_tokens: int | None = None,
    error: str = "",
    fallback_used: bool = False,
    cache_hit: bool = False,
    cache_stale: bool = False,
    attempt_count: int | None = None,
) -> dict[str, Any]:
    usage = normalize_api_usage(api_usage)
    output_estimate = estimated_output_tokens
    if output_estimate is None:
        output_estimate = max_output_tokens
    record: dict[str, Any] = {
        "stage": stage,
        "agent": agent,
        "model": str(model or ""),
        "mode": str(mode or stage),
        "allow_web": allow_web,
        "max_output_tokens": max_output_tokens,
        "status": status,
        "seconds": seconds,
        "estimated_input_tokens": int(estimated_input_tokens or 0),
        "estimated_output_tokens": int(output_estimate or 0),
        "estimated_total_tokens": int(estimated_input_tokens or 0) + int(output_estimate or 0),
        "fallback_used": bool(fallback_used),
        "cache_hit": bool(cache_hit),
        "cache_stale": bool(cache_stale),
        "run_id": f"{stage}:{agent}",
    }
    record.update(usage)
    if error:
        record["error_code"] = _error_code(error)
        record["error"] = error
        if "429" in error or "rate" in error.lower():
            record["status"] = "rate_limited"
            record["http_status"] = 429
            record["retryable"] = True
            record["retry_after"] = "unknown"
    if attempt_count is not None:
        record["attempt_count"] = attempt_count
    elif record.get("status") == "rate_limited":
        record["attempt_count"] = 1
    return _drop_empty(record)


def collect_report_llm_calls(
    *,
    workbench: dict[str, Any],
    execution_payload: dict[str, Any],
    presenter_data: dict[str, Any],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    research_metrics = _dict(workbench.get("research_metrics"))
    for stage, agent in (
        ("wang_industry", "WANG Agent"),
        ("public_equity", "Public Equity Agent"),
    ):
        metrics = _dict(research_metrics.get("wang" if stage == "wang_industry" else "public_equity"))
        if metrics:
            calls.append(_record_from_metrics(stage, agent, metrics))

    market_catalyst = _dict(workbench.get("market_catalyst"))
    market_metrics = _dict(market_catalyst.get("research_metrics"))
    if market_metrics:
        calls.append(_record_from_metrics("market_catalyst", "Market Catalyst Scout", market_metrics))

    layers = _dict(workbench.get("research_layers"))
    better = _dict(layers.get("better_opportunity"))
    better_metrics = _dict(better.get("research_metrics"))
    if better_metrics:
        calls.append(_record_from_metrics("v3_better_opportunity", "Better Opportunity Agent", better_metrics))
    coach = _dict(layers.get("trade_coach"))
    coach_metrics = _dict(coach.get("research_metrics"))
    if coach_metrics:
        calls.append(_record_from_metrics("v3_trade_coach", "Trade Coach Agent", coach_metrics))

    execution_metrics = _dict(execution_payload.get("llm_metrics"))
    if not execution_metrics:
        execution_metrics = _dict(_dict(execution_payload.get("llm_output")).get("research_metrics"))
    if execution_metrics:
        calls.append(_record_from_metrics("trade_execution_llm", "Trade Execution LLM", execution_metrics))

    presenter_metrics = _dict(presenter_data.get("research_metrics"))
    if presenter_metrics:
        calls.append(_record_from_metrics("presenter", "Presenter Agent", presenter_metrics))
    return _with_missing_stage_records(calls)


def summarize_token_usage(calls: list[dict[str, Any]]) -> dict[str, Any]:
    observed = [call for call in calls if _int(call.get("actual_total_tokens")) > 0]
    missing = [call for call in calls if _int(call.get("actual_total_tokens")) <= 0]
    actual_input = sum(_int(call.get("actual_input_tokens")) for call in observed)
    actual_output = sum(_int(call.get("actual_output_tokens")) for call in observed)
    actual_total = sum(_int(call.get("actual_total_tokens")) for call in observed)
    estimated_input = sum(_int(call.get("estimated_input_tokens")) for call in calls)
    estimated_output = sum(_int(call.get("estimated_output_tokens")) for call in calls)
    summary = {
        "observed_call_count": len(observed),
        "missing_usage_call_count": len(missing),
        "actual_input_tokens": actual_input,
        "actual_output_tokens": actual_output,
        "actual_total_tokens": actual_total,
        "estimated_input_tokens": estimated_input,
        "estimated_output_tokens": estimated_output,
        "estimated_total_tokens": estimated_input + estimated_output,
    }
    summary["cost_estimate"] = estimate_cost(summary)
    return summary


def estimate_cost(summary: dict[str, Any]) -> dict[str, Any]:
    input_per_m = _float(os.getenv("OPENAI_GPT_4_1_INPUT_USD_PER_1M"), 2.0)
    output_per_m = _float(os.getenv("OPENAI_GPT_4_1_OUTPUT_USD_PER_1M"), 8.0)
    usd_cny = _float(os.getenv("OPENAI_COST_USD_CNY_RATE"), 7.0)
    usd = (_int(summary.get("actual_input_tokens")) / 1_000_000 * input_per_m) + (
        _int(summary.get("actual_output_tokens")) / 1_000_000 * output_per_m
    )
    estimated_usd = (_int(summary.get("estimated_input_tokens")) / 1_000_000 * input_per_m) + (
        _int(summary.get("estimated_output_tokens")) / 1_000_000 * output_per_m
    )
    return {
        "pricing_model": "gpt-4.1 default",
        "input_usd_per_1m": input_per_m,
        "output_usd_per_1m": output_per_m,
        "usd_cny_rate": usd_cny,
        "usd": round(usd, 6),
        "cny": round(usd * usd_cny, 4),
        "estimated_usd": round(estimated_usd, 6),
        "estimated_cny": round(estimated_usd * usd_cny, 4),
        "billing_basis": "actual_usage" if _int(summary.get("actual_total_tokens")) else "estimated_tokens",
        "note": "Actual cost uses API usage when present; estimated cost uses prompt estimates for missing-usage calls.",
    }


def _record_from_metrics(stage: str, agent: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return make_llm_call_record(
        stage=stage,
        agent=str(metrics.get("agent") or agent),
        model=str(metrics.get("model") or ""),
        mode=str(metrics.get("mode") or stage),
        allow_web=metrics.get("allow_web") if "allow_web" in metrics else None,
        max_output_tokens=_optional_int(metrics.get("max_output_tokens")),
        seconds=_optional_float(metrics.get("seconds")),
        status=str(metrics.get("status") or "ok"),
        api_usage=metrics.get("api_usage"),
        estimated_input_tokens=_optional_int(metrics.get("estimated_input_tokens")),
        estimated_output_tokens=_optional_int(metrics.get("estimated_output_tokens")),
        error=str(metrics.get("error") or metrics.get("_agent_error") or ""),
        fallback_used=bool(metrics.get("fallback_used")),
        cache_hit=bool(metrics.get("cache_hit")),
        cache_stale=bool(metrics.get("cache_stale")),
        attempt_count=_optional_int(metrics.get("attempt_count")),
    )


def _with_missing_stage_records(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = [
        ("market_catalyst", "Market Catalyst Scout"),
        ("wang_industry", "WANG Agent"),
        ("public_equity", "Public Equity Agent"),
        ("trade_execution_llm", "Trade Execution LLM"),
        ("v3_better_opportunity", "Better Opportunity Agent"),
        ("v3_trade_coach", "Trade Coach Agent"),
        ("presenter", "Presenter Agent"),
    ]
    existing = {str(call.get("stage") or "") for call in calls}
    result = list(calls)
    for stage, agent in required:
        if stage in existing:
            continue
        result.append(
            make_llm_call_record(
                stage=stage,
                agent=agent,
                status="not_run",
                mode=stage,
            )
        )
    return result


def _drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {})}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _error_code(error: str) -> str:
    lowered = error.lower()
    if "429" in error or "rate" in lowered:
        return "rate_limited"
    if "timeout" in lowered:
        return "timeout"
    return "agent_error"
