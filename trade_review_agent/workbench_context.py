from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .trade_rounds import TradeRound
from .financial_data_provider import FinancialDataProvider
from .industry_coverage import build_industry_coverage
from .valuation_data_provider import fetch_valuation_snapshot
from .workbench_news import build_market_catalyst_context


FINANCIAL_CACHE_PATH = Path(__file__).resolve().parents[1] / "work" / "real_trade_review_cache.sqlite"


def build_stock_context(
    *,
    code: str,
    name: str,
    trade_round: TradeRound | None = None,
    analysis: dict[str, Any] | None = None,
    stock: pd.DataFrame | None = None,
    sector: pd.DataFrame | None = None,
    benchmark: pd.DataFrame | None = None,
    profile: Any = None,
    company_metadata: dict[str, Any] | None = None,
    financial_snapshot: dict[str, Any] | None = None,
    valuation_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact facts passed to WANG/Public Equity workbench agents."""
    trades = []
    if trade_round is not None:
        for trade in trade_round.trades:
            item = asdict(trade)
            item["trade_date"] = trade.trade_date.isoformat()
            trades.append(item)

    analysis = analysis or {}
    optimal = analysis.get("optimal") or {}
    catalyst = dict(build_market_catalyst_context(code, name))
    fallback_source = "fallback" if catalyst.get("agent_error") else "llm"
    catalyst_source = _lineage_source(catalyst, "market_catalyst", fallback_source)
    news_source = _lineage_source(catalyst, "industry_news", fallback_source)
    catalyst_facts = _fact_objects(
        catalyst.get("market_catalyst")
        or catalyst.get("structured_market_catalysts")
        or catalyst.get("recent_catalysts"),
        fallback_source=catalyst_source,
    )
    industry_news = _fact_objects(
        catalyst.get("industry_news")
        or catalyst.get("structured_industry_news")
        or catalyst.get("news"),
        fallback_source=news_source,
    )
    catalyst["market_catalyst"] = catalyst_facts
    catalyst["structured_market_catalysts"] = catalyst_facts
    catalyst["industry_news"] = industry_news
    catalyst["structured_industry_news"] = industry_news
    source_trace = catalyst.get("source_trace")
    if not isinstance(source_trace, dict):
        source_trace = {}
        catalyst["source_trace"] = source_trace
    source_trace["market_catalyst"] = {
        "source": catalyst_source if catalyst_facts else "missing"
    }
    source_trace["industry_news"] = {
        "source": news_source if industry_news else "missing"
    }
    legacy_catalysts = _fact_texts(catalyst_facts) or _legacy_texts(catalyst.get("recent_catalysts"))
    legacy_news = _fact_texts(industry_news) or legacy_catalysts
    company = {
        "code": code,
        "name": name or code,
        "market": "A-share",
    }
    if isinstance(company_metadata, dict):
        for field in ("sector", "industry", "industry_name", "sector_name", "theme"):
            value = company_metadata.get(field)
            if value not in (None, ""):
                company[field] = value
    valuation = (
        dict(valuation_snapshot)
        if isinstance(valuation_snapshot, dict)
        else fetch_valuation_snapshot(code)
    )
    financial_data = (
        dict(financial_snapshot)
        if isinstance(financial_snapshot, dict)
        else FinancialDataProvider(FINANCIAL_CACHE_PATH).get_financials(code)
    )

    context = {
        "company": company,
        "trade": {
            "buy_date": _date_to_text(getattr(trade_round, "start_date", "")),
            "sell_date": _date_to_text(getattr(trade_round, "end_date", "")),
            "return_pct": _number(analysis.get("return")),
            "trade_score": _number(analysis.get("score")),
            "trade_rating": str(analysis.get("rating") or ""),
            "system_buy_verdict": str(optimal.get("buy_verdict") or optimal.get("buy_label") or ""),
            "system_sell_verdict": str(optimal.get("sell_verdict") or optimal.get("sell_label") or ""),
            "trades": trades[:12],
        },
        "market": {
            "stock_pct_on_buy_day": _number(analysis.get("day_pct")),
            "sector_pct_on_buy_day": _number(analysis.get("sector_pct")),
            "benchmark_pct_on_buy_day": _number(analysis.get("benchmark_pct")),
            "recent_stock_performance": _frame_snapshot(stock),
            "recent_sector_performance": _frame_snapshot(sector),
            "recent_benchmark_performance": _frame_snapshot(benchmark),
        },
        "financials": {
            "revenue": financial_data.get("revenue"),
            "revenue_growth": financial_data.get("revenue_growth"),
            "profit": financial_data.get("net_profit"),
            "profit_growth": financial_data.get("profit_growth"),
            "gross_margin": financial_data.get("gross_margin"),
            "cash_flow": financial_data.get("operating_cash_flow"),
            "free_cash_flow": financial_data.get("free_cash_flow"),
            "debt": financial_data.get("total_liabilities"),
            "debt_to_assets": financial_data.get("debt_to_assets"),
            "roe": financial_data.get("roe"),
            "pe_ttm": valuation.get("pe_ttm"),
            "pb": valuation.get("pb"),
            "ps": valuation.get("ps"),
            "ev_ebitda": valuation.get("ev_ebitda"),
            "valuation_percentile": valuation.get("pe_percentile"),
        },
        "financial_data": financial_data,
        "valuation": valuation,
        "market_catalyst": catalyst,
        "recent_catalysts": legacy_catalysts,
        "market_catalyst_facts": catalyst_facts,
        "industry_news_facts": industry_news,
        "market_hype_reason": catalyst.get("market_hype_reason", "recent hype reason pending verification"),
        "traded_business_line": catalyst.get("traded_business_line", "pending verification"),
        "what_market_is_pricing": catalyst.get("what_market_is_pricing", "pending verification"),
        "evidence_quality": catalyst.get("evidence_quality", "low"),
        "unknowns": catalyst.get("unknowns", []),
        "evidence": catalyst.get("evidence", []),
        "news": legacy_news,
        "structured_news": industry_news,
    }
    context["industry_coverage"] = build_industry_coverage(
        company=company,
        profile=profile,
        context=context,
    )
    return context


def _frame_snapshot(frame: pd.DataFrame | None) -> str:
    if frame is None or frame.empty or "close" not in frame.columns:
        return ""
    data = frame.sort_values("trade_date").tail(20).copy()
    first = float(data["close"].iloc[0])
    last = float(data["close"].iloc[-1])
    if not first:
        return ""
    pct = (last / first - 1) * 100
    return f"last {len(data)} trading days: {pct:.2f}%"


def _date_to_text(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")


def _number(value: Any) -> float:
    try:
        return round(float(value), 4)
    except Exception:
        return 0.0


def _fact_objects(value: Any, *, fallback_source: str) -> list[dict[str, str]]:
    items = value if isinstance(value, (list, tuple)) else [value]
    result: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            fact = str(item.get("fact") or item.get("event") or item.get("headline") or "").strip()
            date_text = str(item.get("date") or item.get("as_of") or "").strip()
            source = str(item.get("source") or "").strip()
            source_type = str(item.get("source_type") or fallback_source).strip().lower()
        else:
            fact = str(item or "").strip()
            date_text = ""
            source = ""
            source_type = fallback_source
        if not fact:
            continue
        if source_type not in {"llm", "fallback", "missing"}:
            source_type = fallback_source if fallback_source in {"llm", "fallback", "missing"} else "missing"
        result.append(
            {
                "fact": fact,
                "date": date_text,
                "source": source or source_type,
                "source_type": source_type,
            }
        )
    return result


def _fact_texts(value: list[dict[str, str]]) -> list[str]:
    return [item["fact"] for item in value if item.get("fact")]


def _legacy_texts(value: Any) -> list[str]:
    items = value if isinstance(value, (list, tuple)) else [value]
    return [
        str(item).strip()
        for item in items
        if item not in (None, "", [], {}) and not isinstance(item, dict)
    ]


def _lineage_source(payload: dict[str, Any], field: str, default: str) -> str:
    trace = payload.get("source_trace")
    entry = trace.get(field) if isinstance(trace, dict) else None
    source = entry.get("source") if isinstance(entry, dict) else entry
    if source in {"llm", "fallback", "missing"}:
        return source
    return default if default in {"llm", "fallback", "missing"} else "missing"
