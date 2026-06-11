from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

import pandas as pd

from .trade_rounds import TradeRound
from .workbench_news import build_market_catalyst_context


def build_stock_context(
    *,
    code: str,
    name: str,
    trade_round: TradeRound | None = None,
    analysis: dict[str, Any] | None = None,
    stock: pd.DataFrame | None = None,
    sector: pd.DataFrame | None = None,
    benchmark: pd.DataFrame | None = None,
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
    catalyst = build_market_catalyst_context(code, name)
    context = {
        "company": {
            "code": code,
            "name": name or code,
            "market": "A-share",
        },
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
            "revenue_growth": "pending fetch",
            "profit_growth": "pending fetch",
            "gross_margin": "pending fetch",
            "valuation": "pending fetch",
            "pe_ttm": None,
            "pb": None,
        },
        "market_catalyst": catalyst,
        "recent_catalysts": catalyst.get("recent_catalysts", []),
        "market_hype_reason": catalyst.get("market_hype_reason", "recent hype reason pending verification"),
        "traded_business_line": catalyst.get("traded_business_line", "pending verification"),
        "what_market_is_pricing": catalyst.get("what_market_is_pricing", "pending verification"),
        "evidence_quality": catalyst.get("evidence_quality", "low"),
        "unknowns": catalyst.get("unknowns", []),
        "evidence": catalyst.get("evidence", []),
        "news": catalyst.get("recent_catalysts", []),
    }
    for key in ("market_event_context", "industry_chain_context", "public_equity_context"):
        value = catalyst.get(key)
        if isinstance(value, dict) and value:
            context[key] = value
    if isinstance(catalyst.get("source_status"), dict):
        context["source_status"] = catalyst["source_status"]
    if isinstance(catalyst.get("public_equity_context"), dict):
        context["financials"] = catalyst["public_equity_context"]
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
