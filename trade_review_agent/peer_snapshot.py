from __future__ import annotations

from typing import Any


QUOTE_SOURCE_TYPES = {
    "tencent_finance": "real_data",
    "akshare": "real_data",
    "fallback_existing": "fallback",
}

UNIVERSE_SOURCE_TYPES = {
    "akshare": "real_data",
    "profile": "fallback",
    "missing": "missing",
}


def build_peer_snapshot(execution_data_context: Any) -> list[dict[str, Any]]:
    """Build comparable peer facts from verified Trade Execution quote rows."""

    context = execution_data_context if isinstance(execution_data_context, dict) else {}
    market_data = context.get("market_data")
    market_data = market_data if isinstance(market_data, dict) else {}
    peers = market_data.get("peers")
    if not isinstance(peers, list):
        return []

    as_of = _trade_anchor_date(context.get("trade_facts"))
    snapshot: list[dict[str, Any]] = []
    for peer in peers:
        if not isinstance(peer, dict):
            continue
        code = _text(peer.get("code"))
        name = _text(peer.get("name"))
        source = _text(peer.get("source"))
        source_type = QUOTE_SOURCE_TYPES.get(source)
        if not code or not name or not source_type:
            continue

        metrics = _quote_metrics(peer)
        if not metrics:
            continue
        universe_source = _text(peer.get("universe_source")) or "missing"
        universe_source_type = UNIVERSE_SOURCE_TYPES.get(universe_source, "missing")
        universe_detail = _text(peer.get("universe_detail")) or "Peer universe source unavailable"
        detail = f"Trade Execution peer quotes from {source}"
        snapshot.append(
            {
                "code": code,
                "name": name,
                "metrics": metrics,
                "as_of": as_of or "missing",
                "source": source,
                "universe_source": universe_source,
                "universe_detail": universe_detail,
                "source_trace": {
                    "code": {"source": universe_source_type, "detail": universe_detail},
                    "name": {"source": universe_source_type, "detail": universe_detail},
                    "metrics": {"source": source_type, "detail": detail},
                    "as_of": {
                        "source": "real_data" if as_of else "missing",
                        "detail": "Trade anchor date" if as_of else "Trade anchor date unavailable",
                    },
                    "source": {"source": source_type, "detail": detail},
                    "universe_source": {"source": universe_source_type, "detail": universe_detail},
                },
            }
        )
    return snapshot


def _quote_metrics(peer: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for source_field, metric_name in (
        ("day_pct", "return_1d_pct"),
        ("five_day_pct", "return_5d_pct"),
        ("twenty_day_pct", "return_20d_pct"),
    ):
        value = _number(peer.get(source_field))
        if value is not None:
            metrics[metric_name] = value
    return metrics


def _trade_anchor_date(value: Any) -> str:
    facts = value if isinstance(value, dict) else {}
    trades = facts.get("trades")
    if not isinstance(trades, list):
        return ""
    dates = sorted(
        _text(item.get("date"))
        for item in trades
        if isinstance(item, dict) and _text(item.get("date"))
    )
    return dates[0] if dates else ""


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "", [], {}) else ""
