from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_env
from .industry_profiles import IndustryProfile
from .trade_rounds import TradeRound
from .workbench_agents import normalize_research_model_tier, research_model_metadata, run_public_equity_workbench_agent, run_wang_workbench_agent
from .workbench_composer import compose_workbench_data, profile_from_workbench
from .workbench_context import build_stock_context


BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_PATH = BASE_DIR / "work" / "industry_profile_cache.json"
PROFILE_CACHE_VERSION = "workbench-json-v3-trading-context"


SECTOR_PROXY_HINTS = {
    "600183": "512480",
    "600584": "512480",
    "002185": "512480",
}


def get_ai_industry_profile(code: str, name: str = "") -> IndustryProfile:
    code = _clean_code(code)
    name = str(name or code).strip()
    workbench = get_workbench_profile_data(code, name)
    profile = profile_from_workbench(workbench)
    if code in SECTOR_PROXY_HINTS and profile.sector_symbol == "sh000300":
        return _with_sector(profile, SECTOR_PROXY_HINTS[code])
    return profile


def get_workbench_profile_data(
    code: str,
    name: str = "",
    *,
    trade_round: TradeRound | None = None,
    analysis: dict[str, Any] | None = None,
    stock: pd.DataFrame | None = None,
    sector: pd.DataFrame | None = None,
    benchmark: pd.DataFrame | None = None,
    research_model_tier: str = "standard",
    market_catalyst: dict[str, Any] | None = None,
    trading_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    load_env(BASE_DIR / ".env")
    code = _clean_code(code)
    name = str(name or code).strip()
    requested_research_model = research_model_metadata(research_model_tier)
    research_model = dict(requested_research_model)
    trading_context = trading_context if isinstance(trading_context, dict) else {}
    context = build_stock_context(
        code=code,
        name=name,
        trade_round=trade_round,
        analysis=analysis,
        stock=stock,
        sector=sector,
        benchmark=benchmark,
        market_catalyst=market_catalyst,
        trading_context=trading_context,
    )
    context["research_model_tier"] = research_model["tier"]
    context["research_model"] = research_model
    context["requested_research_model"] = requested_research_model
    if trading_context:
        context["workflow_timings_ms"] = dict(trading_context.get("workflow_timings_ms") or {})

    cache = _load_cache()
    key = f"{PROFILE_CACHE_VERSION}:{code}:{name}{_context_cache_suffix(context)}"
    if not _refresh_enabled():
        cached = cache.get(key)
        if isinstance(cached, dict):
            return cached

    agent_errors: list[str] = []
    trading_context_agent, wang, equity, first_errors = _run_research_agents(context, trading_context=trading_context)
    agent_errors.extend(first_errors)
    if agent_errors and research_model["tier"] == "better":
        agent_errors.append("better research model failed, retried standard")
        research_model = research_model_metadata("standard")
        context["research_model_tier"] = research_model["tier"]
        context["research_model"] = research_model
        trading_context_agent, wang, equity, retry_errors = _run_research_agents(context, trading_context=trading_context)
        agent_errors.extend(retry_errors)
        key = f"{PROFILE_CACHE_VERSION}:{code}:{name}{_context_cache_suffix(context)}"

    workbench = compose_workbench_data(context, wang, equity, trading_context_agent)
    workbench["wang_agent"] = wang
    workbench["public_equity_agent"] = equity
    workbench["trading_context_agent"] = trading_context_agent
    workbench["research_model"] = research_model
    workbench["requested_research_model"] = requested_research_model
    timings = dict(trading_context_agent.get("workflow_timings_ms") or workbench.get("workflow_timings_ms") or {})
    workbench["workflow_timings_ms"] = timings
    if agent_errors:
        workbench["agent_errors"] = agent_errors

    cache[key] = workbench
    cache[f"{PROFILE_CACHE_VERSION}:{code}"] = workbench
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return workbench


def _run_research_agents(
    context: dict[str, Any],
    *,
    trading_context: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    errors: list[str] = []
    tier = normalize_research_model_tier(context.get("research_model_tier") if isinstance(context, dict) else "")
    trading_context_agent: dict[str, Any] = {}
    wang: dict[str, Any] = {}
    equity: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="research-agent") as executor:
        future_map = {
            "trading_context": executor.submit(_run_trading_context_agent, context, trading_context or {}),
            "wang": executor.submit(run_wang_workbench_agent, context),
            "public_equity": executor.submit(run_public_equity_workbench_agent, context),
        }
        for name, future in future_map.items():
            try:
                candidate = future.result()
            except Exception as exc:
                errors.append(f"{_agent_label(name)} failed ({tier}): {exc}")
                continue
            if name == "trading_context":
                if isinstance(candidate, dict) and not candidate.get("_agent_error"):
                    trading_context_agent = candidate
                else:
                    errors.append(f"Trading Context agent failed ({tier}): {candidate.get('_agent_error') if isinstance(candidate, dict) else 'non-object result'}")
            elif name == "wang":
                if isinstance(candidate, dict) and candidate.get("_agent_error"):
                    errors.append(f"WANG agent failed ({tier}): {candidate.get('_agent_error')}")
                elif isinstance(candidate, dict) and _memo_text(candidate):
                    wang = candidate
                elif isinstance(candidate, dict):
                    errors.append(f"WANG agent returned empty memo ({tier})")
                else:
                    errors.append(f"WANG agent returned non-object data ({tier})")
            else:
                if isinstance(candidate, dict) and candidate.get("_agent_error"):
                    errors.append(f"Public Equity agent failed ({tier}): {candidate.get('_agent_error')}")
                elif isinstance(candidate, dict) and _memo_text(candidate):
                    equity = candidate
                elif isinstance(candidate, dict):
                    errors.append(f"Public Equity agent returned empty memo ({tier})")
                else:
                    errors.append(f"Public Equity agent returned non-object data ({tier})")
    return trading_context_agent, wang, equity, errors


def _run_trading_context_agent(context: dict[str, Any], trading_context: dict[str, Any]) -> dict[str, Any]:
    if trading_context:
        result = dict(trading_context)
    else:
        result = {
            "trade_timing": context.get("trade_timing", {}),
            "peer_comparison": context.get("peer_comparison", {}),
            "peer_candidates": context.get("peer_candidates", []),
            "trade_execution_notes": context.get("trade_execution_notes", {}),
            "data_source_status": context.get("data_source_status", {}),
            "data_errors": context.get("data_errors", []),
            "workflow_timings_ms": context.get("workflow_timings_ms", {}),
        }
    result["agent_type"] = "trading_context"
    if not isinstance(result.get("trade_timing"), dict):
        result["_agent_error"] = "missing trade_timing"
    return result


def _agent_label(name: str) -> str:
    return {
        "trading_context": "Trading Context agent",
        "wang": "WANG agent",
        "public_equity": "Public Equity agent",
    }.get(name, name)


def _memo_text(agent_data: dict[str, Any]) -> str:
    for key in ("deep_memo", "memo", "raw_text"):
        value = agent_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _context_cache_suffix(context: dict[str, Any]) -> str:
    trade = context.get("trade") if isinstance(context, dict) else {}
    market = context.get("market") if isinstance(context, dict) else {}
    timing = context.get("trade_timing") if isinstance(context, dict) else {}
    tier = normalize_research_model_tier(context.get("research_model_tier") if isinstance(context, dict) else "")
    if not isinstance(trade, dict) or not trade.get("trades"):
        return f":tier:{tier}"
    parts = [
        tier,
        str(trade.get("buy_date") or ""),
        str(trade.get("sell_date") or ""),
        str(trade.get("return_pct") or ""),
        str(trade.get("trade_score") or ""),
        str(market.get("stock_pct_on_buy_day") if isinstance(market, dict) else ""),
        str(market.get("sector_pct_on_buy_day") if isinstance(market, dict) else ""),
        str((timing.get("buy_day") or {}).get("date") if isinstance(timing, dict) else ""),
    ]
    safe = "_".join(part.replace(":", "").replace("/", "").replace("\\", "") for part in parts)
    return f":trade:{safe}"


def _refresh_enabled() -> bool:
    value = os.getenv("INDUSTRY_AGENT_REFRESH") or os.getenv("WORKBENCH_AGENT_REFRESH") or ""
    return value.strip().lower() in {"1", "true", "yes"}


def _clean_code(code: str) -> str:
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else str(code or "").strip()


def _load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _with_sector(profile: IndustryProfile, sector_symbol: str) -> IndustryProfile:
    return IndustryProfile(
        code=profile.code,
        name=profile.name,
        theme=profile.theme,
        core_driver=profile.core_driver,
        node=profile.node,
        sector_symbol=sector_symbol,
        chain_nodes=profile.chain_nodes,
        barriers=profile.barriers,
        profit_levers=profile.profit_levers,
        peers=profile.peers,
        industry_judgment=profile.industry_judgment,
        company_judgment=profile.company_judgment,
        financial_validation=profile.financial_validation,
        expectation_gap=profile.expectation_gap,
        valuation_odds=profile.valuation_odds,
        catalysts=profile.catalysts,
        disconfirming_signals=profile.disconfirming_signals,
        position_sizing=profile.position_sizing,
        one_sentence_thesis=profile.one_sentence_thesis,
        rerating_anchor=profile.rerating_anchor,
        market_position=profile.market_position,
        peer_ranking=profile.peer_ranking,
        best_expression=profile.best_expression,
        trading_implication=profile.trading_implication,
        evidence=profile.evidence,
        wang_investor_report=profile.wang_investor_report,
        public_equity_report=profile.public_equity_report,
    )
