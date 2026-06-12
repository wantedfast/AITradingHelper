from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_env
from .industry_profiles import DEFAULT_PROFILE, IndustryProfile
from .workbench_agents import normalize_research_model_tier, research_model_metadata, run_public_equity_workbench_agent, run_wang_workbench_agent
from .workbench_composer import compose_workbench_data, profile_from_workbench
from .workbench_context import build_stock_context
from .trade_rounds import TradeRound


BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_PATH = BASE_DIR / "work" / "industry_profile_cache.json"
PROFILE_CACHE_VERSION = "workbench-json-v2-catalyst"


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
) -> dict[str, Any]:
    load_env(BASE_DIR / ".env")
    code = _clean_code(code)
    name = str(name or code).strip()
    requested_research_model = research_model_metadata(research_model_tier)
    research_model = dict(requested_research_model)
    cache = _load_cache()
    key = f"{PROFILE_CACHE_VERSION}:{code}:{name}{_request_cache_suffix(trade_round=trade_round, analysis=analysis, research_model_tier=research_model['tier'])}"
    if not _refresh_enabled():
        cached = cache.get(key)
        if isinstance(cached, dict):
            return cached

    context = build_stock_context(
        code=code,
        name=name,
        trade_round=trade_round,
        analysis=analysis,
        stock=stock,
        sector=sector,
        benchmark=benchmark,
        profile=_base_context_profile(code, name),
    )
    context["research_model_tier"] = research_model["tier"]
    context["research_model"] = research_model
    context["requested_research_model"] = requested_research_model
    key = f"{PROFILE_CACHE_VERSION}:{code}:{name}{_context_cache_suffix(context)}"
    if not _refresh_enabled():
        cached = cache.get(key)
        if isinstance(cached, dict):
            return cached

    agent_errors: list[str] = []
    wang, equity, first_errors = _run_research_agents(context)
    agent_errors.extend(first_errors)
    if agent_errors and research_model["tier"] == "better":
        agent_errors.append("better research model failed, retried standard")
        research_model = research_model_metadata("standard")
        context["research_model_tier"] = research_model["tier"]
        context["research_model"] = research_model
        if not _research_payload_present(wang):
            wang, retry_errors = _run_wang_research_agent(context, "standard")
            agent_errors.extend(retry_errors)
        if not _research_payload_present(equity):
            equity, retry_errors = _run_public_equity_research_agent(context, "standard")
            agent_errors.extend(retry_errors)
        key = f"{PROFILE_CACHE_VERSION}:{code}:{name}{_context_cache_suffix(context)}"
    workbench = compose_workbench_data(context, wang, equity)
    workbench["wang_agent"] = wang
    workbench["public_equity_agent"] = equity
    workbench["research_model"] = research_model
    workbench["requested_research_model"] = requested_research_model
    if agent_errors:
        workbench["agent_errors"] = agent_errors

    cache[key] = workbench
    cache[f"{PROFILE_CACHE_VERSION}:{code}"] = workbench
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return workbench


def _run_research_agents(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    errors: list[str] = []
    tier = normalize_research_model_tier(context.get("research_model_tier") if isinstance(context, dict) else "")
    with ThreadPoolExecutor(max_workers=2) as executor:
        wang_future = executor.submit(_run_wang_research_agent, context, tier)
        equity_future = executor.submit(_run_public_equity_research_agent, context, tier)
        wang, wang_errors = wang_future.result()
        equity, equity_errors = equity_future.result()
    errors.extend(wang_errors)
    errors.extend(equity_errors)
    return wang, equity, errors


def _run_wang_research_agent(context: dict[str, Any], tier: str) -> tuple[dict[str, Any], list[str]]:
    try:
        candidate = run_wang_workbench_agent(context)
        if isinstance(candidate, dict) and candidate.get("_agent_error"):
            return {}, [f"WANG agent failed ({tier}): {candidate.get('_agent_error')}"]
        elif isinstance(candidate, dict) and _research_payload_present(candidate):
            return candidate, []
        elif isinstance(candidate, dict):
            return {}, [f"WANG agent returned empty research payload ({tier})"]
        else:
            return {}, [f"WANG agent returned non-object data ({tier})"]
    except Exception as exc:
        return {}, [f"WANG agent failed ({tier}): {exc}"]


def _run_public_equity_research_agent(context: dict[str, Any], tier: str) -> tuple[dict[str, Any], list[str]]:
    try:
        candidate = run_public_equity_workbench_agent(context)
        if isinstance(candidate, dict) and candidate.get("_agent_error"):
            return {}, [f"Public Equity agent failed ({tier}): {candidate.get('_agent_error')}"]
        elif isinstance(candidate, dict) and _research_payload_present(candidate):
            return candidate, []
        elif isinstance(candidate, dict):
            return {}, [f"Public Equity agent returned empty research payload ({tier})"]
        else:
            return {}, [f"Public Equity agent returned non-object data ({tier})"]
    except Exception as exc:
        return {}, [f"Public Equity agent failed ({tier}): {exc}"]


def _memo_text(agent_data: dict[str, Any]) -> str:
    for key in ("deep_memo", "memo", "raw_text"):
        value = agent_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _research_payload_present(agent_data: dict[str, Any]) -> bool:
    if _memo_text(agent_data):
        return True
    keys = {
        "industry_rating",
        "investment_rating",
        "claims",
        "profit_flow",
        "expectation_gap",
        "action",
        "one_sentence_conclusion",
        "reasoning_summary",
    }
    return any(key in agent_data and agent_data.get(key) not in (None, "", [], {}) for key in keys)


def _context_cache_suffix(context: dict[str, Any]) -> str:
    trade = context.get("trade") if isinstance(context, dict) else {}
    market = context.get("market") if isinstance(context, dict) else {}
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
    ]
    safe = "_".join(part.replace(":", "").replace("/", "").replace("\\", "") for part in parts)
    return f":trade:{safe}"


def _request_cache_suffix(
    *,
    trade_round: TradeRound | None,
    analysis: dict[str, Any] | None,
    research_model_tier: object,
) -> str:
    tier = normalize_research_model_tier(research_model_tier)
    if trade_round is None or not getattr(trade_round, "trades", None):
        return f":tier:{tier}"
    analysis = analysis if isinstance(analysis, dict) else {}
    parts = [
        tier,
        str(getattr(trade_round, "start_date", "") or ""),
        str(getattr(trade_round, "end_date", "") or ""),
        str(_number_for_cache(analysis.get("return"))),
        str(_number_for_cache(analysis.get("score"))),
        str(_number_for_cache(analysis.get("day_pct"))),
        str(_number_for_cache(analysis.get("sector_pct"))),
    ]
    safe = "_".join(part.replace(":", "").replace("/", "").replace("\\", "") for part in parts)
    return f":trade:{safe}"


def _number_for_cache(value: Any) -> float:
    try:
        return round(float(value), 4)
    except Exception:
        return 0.0


def _refresh_enabled() -> bool:
    value = os.getenv("INDUSTRY_AGENT_REFRESH") or os.getenv("WORKBENCH_AGENT_REFRESH") or ""
    return value.strip().lower() in {"1", "true", "yes"}


def _clean_code(code: str) -> str:
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else str(code or "").strip()


def _base_context_profile(code: str, name: str) -> IndustryProfile:
    """Lightweight profile for context assembly; must not call AI recursively."""
    return IndustryProfile(
        code=code,
        name=name or code or DEFAULT_PROFILE.name,
        theme=DEFAULT_PROFILE.theme,
        core_driver=DEFAULT_PROFILE.core_driver,
        node=DEFAULT_PROFILE.node,
        sector_symbol=DEFAULT_PROFILE.sector_symbol,
        chain_nodes=DEFAULT_PROFILE.chain_nodes,
        barriers=DEFAULT_PROFILE.barriers,
        profit_levers=DEFAULT_PROFILE.profit_levers,
        peers=DEFAULT_PROFILE.peers,
        industry_judgment=DEFAULT_PROFILE.industry_judgment,
        company_judgment=DEFAULT_PROFILE.company_judgment,
        financial_validation=DEFAULT_PROFILE.financial_validation,
        expectation_gap=DEFAULT_PROFILE.expectation_gap,
        valuation_odds=DEFAULT_PROFILE.valuation_odds,
        catalysts=DEFAULT_PROFILE.catalysts,
        disconfirming_signals=DEFAULT_PROFILE.disconfirming_signals,
        position_sizing=DEFAULT_PROFILE.position_sizing,
        one_sentence_thesis=DEFAULT_PROFILE.one_sentence_thesis,
        rerating_anchor=DEFAULT_PROFILE.rerating_anchor,
        market_position=DEFAULT_PROFILE.market_position,
        peer_ranking=DEFAULT_PROFILE.peer_ranking,
        best_expression=DEFAULT_PROFILE.best_expression,
        trading_implication=DEFAULT_PROFILE.trading_implication,
        evidence=DEFAULT_PROFILE.evidence,
        wang_investor_report=DEFAULT_PROFILE.wang_investor_report,
        public_equity_report=DEFAULT_PROFILE.public_equity_report,
    )


def _load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _context_with_wang_pre_read(context: dict[str, Any], wang: dict[str, Any]) -> dict[str, Any]:
    """Give Public Equity the current-market read without passing the full memo."""
    enriched = dict(context if isinstance(context, dict) else {})
    wang = wang if isinstance(wang, dict) else {}
    enriched["wang_pre_read"] = {
        "market_hype_reason": wang.get("market_hype_reason"),
        "recent_catalysts": wang.get("recent_catalysts"),
        "traded_business_line": wang.get("traded_business_line"),
        "what_market_is_pricing": wang.get("what_market_is_pricing"),
        "evidence_quality": wang.get("evidence_quality"),
        "unknowns": wang.get("unknowns"),
        "industry_rating": wang.get("industry_rating"),
        "theme": wang.get("theme"),
        "claims": wang.get("claims"),
        "profit_flow": wang.get("profit_flow"),
        "weakest_link": wang.get("weakest_link"),
        "deep_memo_summary": _memo_text(wang)[:1200],
    }
    return enriched


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
