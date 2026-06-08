from __future__ import annotations

from copy import deepcopy
from typing import Any


SOURCE_VALUES = {"tencent_finance", "akshare", "fallback_existing", "missing"}
QUOTE_STATUS_VALUES = {"ok", "fallback", "missing"}
PEER_STATUS_VALUES = {"ok", "partial", "fallback", "missing"}
STRENGTH_VALUES = {"strong", "weak", "similar", "unknown"}
VERDICT_VALUES = {"good", "average", "poor", "unknown"}
INTRADAY_VALUES = {"low", "middle", "high", "unknown"}


def structure_trade_execution_payload(
    *,
    trade_facts: dict[str, Any] | None,
    execution_analysis: dict[str, Any] | None,
    data_source_status: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize the independent execution-analysis contract."""

    analysis = execution_analysis if isinstance(execution_analysis, dict) else {}
    payload = {
        "trade_timing": _normalize_trade_timing(analysis.get("trade_timing")),
        "relative_strength": _normalize_relative_strength(analysis.get("relative_strength")),
        "peer_comparison": _normalize_peer_comparison(analysis.get("peer_comparison")),
        "trade_execution_notes": _normalize_execution_notes(analysis.get("trade_execution_notes")),
        "execution_advice": _normalize_execution_advice(analysis.get("execution_advice")),
        "data_source_status": _normalize_source_status(data_source_status),
    }
    if trade_facts:
        payload["trade_facts"] = _normalize_trade_facts(trade_facts)
    return payload


def normalize_execution_data_context(value: dict[str, Any] | None) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    return {
        "trade_facts": _normalize_trade_facts(data.get("trade_facts")),
        "market_data": _normalize_market_data(data.get("market_data")),
        "data_source_status": _normalize_source_status(data.get("data_source_status")),
    }


def _normalize_trade_facts(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "stock_name": _text(value.get("stock_name")),
        "stock_code": _text(value.get("stock_code")),
        "trades": [
            {
                "side": _side(item.get("side")),
                "date": _text(item.get("date")),
                "price": _num(item.get("price")),
                "quantity": _num(item.get("quantity")),
            }
            for item in _dict_list(value.get("trades"))
        ],
    }


def _normalize_market_data(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "stock_quotes": [_normalize_quote(item, include_symbol=False) for item in _dict_list(value.get("stock_quotes"))],
        "benchmark_quotes": [_normalize_quote(item, include_symbol=True) for item in _dict_list(value.get("benchmark_quotes"))],
        "sector_quotes": [_normalize_quote(item, include_symbol=True) for item in _dict_list(value.get("sector_quotes"))],
        "peers": [_normalize_peer_quote(item) for item in _dict_list(value.get("peers"))],
    }


def _normalize_trade_timing(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "buy_points": [_normalize_trade_point(item) for item in _dict_list(value.get("buy_points"))],
        "sell_points": [_normalize_trade_point(item) for item in _dict_list(value.get("sell_points"))],
    }


def _normalize_trade_point(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "date": _text(value.get("date")),
        "price": _num(value.get("price")),
        "stock_pct": _num(value.get("stock_pct")),
        "hs300_etf_pct": _num(value.get("hs300_etf_pct")),
        "sector_pct": _num(value.get("sector_pct")),
        "excess_vs_hs300_pct": _num(value.get("excess_vs_hs300_pct")),
        "excess_vs_sector_pct": _num(value.get("excess_vs_sector_pct")),
        "intraday_position": _choice(value.get("intraday_position"), INTRADAY_VALUES),
        "judgment": _text(value.get("judgment"), "unknown"),
        "reason": _text(value.get("reason"), "unknown"),
    }


def _normalize_relative_strength(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "benchmark": _text(value.get("benchmark"), "510300"),
        "stock_vs_benchmark": _choice(value.get("stock_vs_benchmark"), STRENGTH_VALUES),
        "stock_vs_sector": _choice(value.get("stock_vs_sector"), STRENGTH_VALUES),
        "conclusion": _text(value.get("conclusion"), "unknown"),
    }


def _normalize_peer_comparison(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "concept": _text(value.get("concept"), "unknown"),
        "leader": _text(value.get("leader"), "unknown"),
        "rows": [_normalize_peer_row(item) for item in _dict_list(value.get("rows"))],
        "conclusion": _text(value.get("conclusion"), "unknown"),
    }


def _normalize_peer_row(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "name": _text(value.get("name")),
        "code": _text(value.get("code")),
        "day_pct": _num(value.get("day_pct")),
        "five_day_pct": _num(value.get("five_day_pct")),
        "twenty_day_pct": _num(value.get("twenty_day_pct")),
        "advantage": _text(value.get("advantage"), "unknown"),
        "weakness": _text(value.get("weakness"), "unknown"),
    }


def _normalize_execution_notes(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "buy_verdict": _choice(value.get("buy_verdict"), VERDICT_VALUES),
        "sell_verdict": _choice(value.get("sell_verdict"), VERDICT_VALUES),
        "main_lesson": _text(value.get("main_lesson"), "unknown"),
    }


def _normalize_execution_advice(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "summary": _text(value.get("summary"), "unknown"),
        "buy_issue": _text(value.get("buy_issue"), "unknown"),
        "sell_issue": _text(value.get("sell_issue"), "unknown"),
        "next_time_rules": _str_list(value.get("next_time_rules")),
        "confirmation_signals": _str_list(value.get("confirmation_signals")),
    }


def _normalize_source_status(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "stock_quote": _quote_status(value.get("stock_quote")),
        "stock_quote_source": _source(value.get("stock_quote_source")),
        "benchmark_quote": _quote_status(value.get("benchmark_quote")),
        "benchmark_quote_source": _source(value.get("benchmark_quote_source")),
        "sector_quote": _quote_status(value.get("sector_quote")),
        "sector_quote_source": _source(value.get("sector_quote_source")),
        "peer_quotes": _peer_status(value.get("peer_quotes")),
        "peer_quote_source": _source(value.get("peer_quote_source")),
        "fallback_used": _str_list(value.get("fallback_used")),
        "errors": _str_list(value.get("errors")),
    }


def _normalize_quote(value: Any, *, include_symbol: bool) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    quote = {
        "date": _text(value.get("date")),
        "open": _num(value.get("open")),
        "high": _num(value.get("high")),
        "low": _num(value.get("low")),
        "close": _num(value.get("close")),
        "pct": _num(value.get("pct")),
        "source": _source(value.get("source")),
    }
    if include_symbol:
        quote["symbol"] = _text(value.get("symbol"))
        quote["name"] = _text(value.get("name"))
    return quote


def _normalize_peer_quote(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "name": _text(value.get("name")),
        "code": _text(value.get("code")),
        "day_pct": _num(value.get("day_pct")),
        "five_day_pct": _num(value.get("five_day_pct")),
        "twenty_day_pct": _num(value.get("twenty_day_pct")),
        "source": _source(value.get("source")),
    }


def _choice(value: Any, allowed: set[str], fallback: str = "unknown") -> str:
    text = _text(value)
    return text if text in allowed else fallback


def _quote_status(value: Any) -> str:
    text = _text(value)
    return text if text in QUOTE_STATUS_VALUES else "missing"


def _peer_status(value: Any) -> str:
    text = _text(value)
    return text if text in PEER_STATUS_VALUES else "missing"


def _source(value: Any) -> str:
    text = _text(value)
    return text if text in SOURCE_VALUES else "missing"


def _side(value: Any) -> str:
    text = _text(value).lower()
    return text if text in {"buy", "sell"} else "buy"


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return round(float(value), 4)
    except Exception:
        return fallback


def _str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(item) for item in value if isinstance(item, dict)]
