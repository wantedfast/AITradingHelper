from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_env
from .industry_profiles import IndustryProfile
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
    context = build_stock_context(
        code=code,
        name=name,
        trade_round=trade_round,
        analysis=analysis,
        stock=stock,
        sector=sector,
        benchmark=benchmark,
    )
    context["research_model_tier"] = research_model["tier"]
    context["research_model"] = research_model
    context["requested_research_model"] = requested_research_model
    cache = _load_cache()
    key = f"{PROFILE_CACHE_VERSION}:{code}:{name}{_context_cache_suffix(context)}"
    if not _refresh_enabled():
        cached = cache.get(key)
        if isinstance(cached, dict):
            return cached

    agent_errors: list[str] = []
    try:
        wang = run_wang_workbench_agent(context)
        equity = run_public_equity_workbench_agent(_context_with_wang_pre_read(context, wang))
    except Exception as exc:
        if research_model["tier"] != "better":
            raise
        agent_errors.append(f"better research model failed, retried standard: {exc}")
        research_model = research_model_metadata("standard")
        context["research_model_tier"] = research_model["tier"]
        context["research_model"] = research_model
        wang = run_wang_workbench_agent(context)
        equity = run_public_equity_workbench_agent(_context_with_wang_pre_read(context, wang))
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
