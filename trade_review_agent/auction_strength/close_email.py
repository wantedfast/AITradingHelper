from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from trade_review_agent.market.data_provider import MarketDataProvider


CN_TZ = ZoneInfo("Asia/Shanghai")
DAILY_TOP5_CLOSE_START = time(hour=15, minute=10)
DAILY_TOP5_CLOSE_CUTOFF = time(hour=16, minute=0)


def close_email_due_at(trade_date: str) -> datetime:
    day = date.fromisoformat(str(trade_date or "").strip())
    return datetime.combine(day, DAILY_TOP5_CLOSE_START, tzinfo=CN_TZ)


def close_email_cutoff_at(trade_date: str) -> datetime:
    day = date.fromisoformat(str(trade_date or "").strip())
    return datetime.combine(day, DAILY_TOP5_CLOSE_CUTOFF, tzinfo=CN_TZ)


def collect_close_email_snapshot(
    report: dict[str, Any],
    *,
    cache_db: str | Path,
    provider: MarketDataProvider | None = None,
    quote_time: datetime | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    trade_date = str(report.get("trade_date") or "").strip()
    trade_day = date.fromisoformat(trade_date)
    stocks = report.get("top5_strong_stocks") if isinstance(report.get("top5_strong_stocks"), list) else []
    # The email displays the official traded open/close prices, so use the
    # unadjusted daily bar. Forward-adjusted prices preserve most same-day
    # ratios but can make the absolute prices shown to users misleading.
    market = provider or MarketDataProvider(cache_db=cache_db, adjust="", disable_cache=True)
    quote_now = (quote_time or datetime.now(CN_TZ)).astimezone(CN_TZ)
    issues: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []

    for stock in stocks[:5]:
        item = stock if isinstance(stock, dict) else {}
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip()
        rank = int(item.get("rank") or len(rows) + 1)
        frame = market.stock_daily(code, trade_day - timedelta(days=10), trade_day) if code else pd.DataFrame()
        if frame.empty:
            issues.append({"code": code, "name": name, "reason": "market_data_empty"})
            continue
        row = frame.loc[frame["trade_date"] == trade_day]
        if row.empty:
            issues.append({"code": code, "name": name, "reason": "trade_date_missing"})
            continue
        frame = frame.sort_values("trade_date").reset_index(drop=True)
        latest = row.iloc[-1]
        open_price = _price_or_none(latest.get("open"))
        close_price = _price_or_none(latest.get("close"))
        if open_price is None or close_price is None:
            issues.append({"code": code, "name": name, "reason": "open_or_close_missing"})
            continue
        prev_close = _previous_close_price(frame, trade_day)
        change_pct = _round_money((close_price - open_price) / open_price * 100)
        rows.append(
            {
                "rank": rank,
                "code": code,
                "name": name,
                "open_price": _round_money(open_price),
                "close_price": _round_money(close_price),
                "change_pct": change_pct,
                "is_limit_up": _is_limit_up_close(code=code, name=name, close_price=close_price, prev_close=prev_close),
            }
        )

    if issues or len(rows) != 5:
        known = {(item["code"], item["name"]) for item in issues}
        for stock in stocks[:5]:
            item = stock if isinstance(stock, dict) else {}
            key = (str(item.get("code") or "").strip(), str(item.get("name") or "").strip())
            if key not in known and not any(row["code"] == key[0] for row in rows):
                issues.append({"code": key[0], "name": key[1], "reason": "quote_missing"})
        return None, issues

    rows.sort(key=lambda item: int(item["rank"]))
    return {
        "trade_date": trade_date,
        "analysis_time": str(report.get("analysis_time") or "").strip(),
        "quote_time": quote_now.strftime("%Y-%m-%d %H:%M:%S"),
        "top5_close_performance": rows,
    }, []


def _price_or_none(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number) or number <= 0:
        return None
    return number


def _previous_close_price(frame: pd.DataFrame, trade_day: date) -> float | None:
    prior_rows = frame.loc[frame["trade_date"] < trade_day]
    if prior_rows.empty:
        return None
    return _price_or_none(prior_rows.iloc[-1].get("close"))


def _is_limit_up_close(*, code: str, name: str, close_price: float, prev_close: float | None) -> bool:
    if prev_close is None:
        return False
    ratio = _limit_ratio(code=code, name=name)
    limit_price = _round_price(prev_close * (1 + ratio))
    # Equality is intentional. A close above the mechanically derived limit
    # can occur on a no-price-limit day and must not be mislabeled as limit-up.
    return _round_price(close_price) == limit_price


def _limit_ratio(*, code: str, name: str) -> float:
    digits = "".join(ch for ch in str(code or "").strip() if ch.isdigit())
    normalized_name = str(name or "").strip().upper()
    # Board rules take precedence over the risk-warning marker: ChiNext and
    # STAR risk-warning stocks retain their 20% daily price limit.
    if digits.startswith(("300", "301", "688", "689")):
        return 0.20
    if digits.startswith(("4", "8", "920")):
        return 0.30
    if _has_st_risk_marker(normalized_name):
        return 0.05
    return 0.10


def _has_st_risk_marker(name: str) -> bool:
    text = str(name or "").strip().upper()
    if text.startswith("*ST"):
        suffix = text[3:]
    elif text.startswith("ST"):
        suffix = text[2:]
    else:
        return False
    # Chinese security names follow the marker directly; test fixtures and
    # upstream aliases may use whitespace. Do not mistake names such as
    # "Stock" for an ST risk-warning marker.
    return not suffix or suffix[0].isspace() or not suffix[0].isascii() or not suffix[0].isalpha()


def _round_price(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _round_money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
