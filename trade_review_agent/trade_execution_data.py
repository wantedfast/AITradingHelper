from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from .data_provider import (
    MarketDataProvider,
    _fetch_akshare_index_daily,
    _fetch_akshare_stock_daily,
    _fetch_tencent_daily,
)
from .execution_structurer import normalize_execution_data_context
from .industry_profiles import IndustryProfile
from .trade_rounds import TradeRound


HS300_ETF_SYMBOL = "510300"
HS300_ETF_NAME = "沪深300ETF"
SOURCE_TENCENT = "tencent_finance"
SOURCE_AKSHARE = "akshare"
SOURCE_FALLBACK = "fallback_existing"
SOURCE_MISSING = "missing"


@dataclass(frozen=True)
class QuoteFetch:
    frame: pd.DataFrame
    source: str
    status: str
    errors: tuple[str, ...] = ()


PEER_HINTS: dict[str, dict[str, Any]] = {
    "002491": {
        "concept": "光通信/光纤光缆",
        "sector_symbol": "515880",
        "peers": (
            ("亨通光电", "600487"),
            ("中天科技", "600522"),
            ("烽火通信", "600498"),
            ("特发信息", "000070"),
            ("永鼎股份", "600105"),
        ),
    }
}


def build_trade_execution_data_context(
    *,
    provider: MarketDataProvider,
    profile: IndustryProfile,
    trade_round: TradeRound,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    start = start or trade_round.start_date - timedelta(days=25)
    end = end or max(trade_round.end_date + timedelta(days=20), trade_round.start_date + timedelta(days=45))
    stock_fetch = fetch_daily_with_source(
        provider=provider,
        table="stock_daily",
        symbol=trade_round.code,
        start=start,
        end=end,
        kind="stock",
    )
    benchmark_fetch = fetch_daily_with_source(
        provider=provider,
        table="index_daily",
        symbol=HS300_ETF_SYMBOL,
        start=start,
        end=end,
        kind="etf",
    )
    sector_name, sector_symbol = _sector_identity(profile, trade_round.code)
    sector_fetch = fetch_daily_with_source(
        provider=provider,
        table="index_daily" if _looks_like_index_symbol(sector_symbol) else "stock_daily",
        symbol=sector_symbol,
        start=start,
        end=end,
        kind="index" if _looks_like_index_symbol(sector_symbol) else "etf",
    )
    peer_quotes, peer_status, peer_source, peer_errors = _build_peer_quotes(
        provider=provider,
        profile=profile,
        trade_round=trade_round,
        start=start,
        end=end,
    )
    sector_quotes = _quote_rows(
        sector_fetch.frame,
        source=sector_fetch.source,
        symbol=sector_symbol,
        name=sector_name,
    )
    fallback_used = []
    for label, fetch in (
        ("stock_quote", stock_fetch),
        ("benchmark_quote", benchmark_fetch),
        ("sector_quote", sector_fetch),
    ):
        if fetch.source == SOURCE_FALLBACK:
            fallback_used.append(label)
    if peer_source == SOURCE_FALLBACK:
        fallback_used.append("peer_quotes")

    errors = []
    errors.extend(stock_fetch.errors)
    errors.extend(benchmark_fetch.errors)
    errors.extend(sector_fetch.errors)
    errors.extend(peer_errors)
    data = {
        "trade_facts": _trade_facts(trade_round),
        "market_data": {
            "stock_quotes": _quote_rows(stock_fetch.frame, source=stock_fetch.source),
            "benchmark_quotes": _quote_rows(
                benchmark_fetch.frame,
                source=benchmark_fetch.source,
                symbol=HS300_ETF_SYMBOL,
                name=HS300_ETF_NAME,
            ),
            "sector_quotes": sector_quotes,
            "peers": peer_quotes,
        },
        "data_source_status": {
            "stock_quote": stock_fetch.status,
            "stock_quote_source": stock_fetch.source,
            "benchmark_quote": benchmark_fetch.status,
            "benchmark_quote_source": benchmark_fetch.source,
            "sector_quote": sector_fetch.status,
            "sector_quote_source": sector_fetch.source,
            "peer_quotes": peer_status,
            "peer_quote_source": peer_source,
            "fallback_used": fallback_used,
            "errors": _dedupe(errors),
        },
    }
    return normalize_execution_data_context(data)


def fetch_daily_with_source(
    *,
    provider: MarketDataProvider,
    table: str,
    symbol: str,
    start: date,
    end: date,
    kind: str,
) -> QuoteFetch:
    errors: list[str] = []
    frame = pd.DataFrame()
    try:
        frame = _fetch_tencent_daily(symbol, start, end, provider.adjust, is_index=(kind == "index"))
    except Exception as exc:
        errors.append(f"{symbol}: tencent_finance failed: {exc}")
    if not frame.empty:
        _safe_write_cache(provider, table, frame)
        return QuoteFetch(frame=frame, source=SOURCE_TENCENT, status="ok", errors=tuple(errors))

    try:
        if kind == "stock":
            frame = _fetch_akshare_stock_daily(symbol, start, end, provider.adjust)
        elif kind == "etf":
            frame = _fetch_akshare_etf_daily(symbol, start, end)
        else:
            frame = _fetch_akshare_index_daily(symbol)
    except Exception as exc:
        errors.append(f"{symbol}: akshare failed: {exc}")
    if not frame.empty:
        _safe_write_cache(provider, table, frame)
        return QuoteFetch(frame=frame, source=SOURCE_AKSHARE, status="fallback", errors=tuple(errors))

    cached = _safe_read_cache(provider, table, symbol, start, end)
    if not cached.empty:
        return QuoteFetch(frame=cached, source=SOURCE_FALLBACK, status="fallback", errors=tuple(errors))

    if not errors:
        errors.append(f"{symbol}: no quote rows from Tencent, AkShare, or existing fallback cache")
    return QuoteFetch(frame=pd.DataFrame(), source=SOURCE_MISSING, status="missing", errors=tuple(errors))


def _fetch_akshare_etf_daily(symbol: str, start: date, end: date) -> pd.DataFrame:
    try:
        import akshare as ak

        raw = ak.fund_etf_hist_em(
            symbol="".join(ch for ch in str(symbol) if ch.isdigit())[-6:],
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
        )
    except Exception:
        return pd.DataFrame()
    rename = {
        "日期": "trade_date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "涨跌幅": "pct_chg",
        "换手率": "turnover",
    }
    frame = raw.rename(columns=rename)
    if frame.empty or "trade_date" not in frame.columns:
        return pd.DataFrame()
    frame = frame.copy()
    frame["symbol"] = symbol
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    for col in ("open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"):
        if col not in frame.columns:
            frame[col] = None
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if frame["pct_chg"].isna().all() and "close" in frame.columns:
        frame["pct_chg"] = pd.to_numeric(frame["close"], errors="coerce").pct_change() * 100
    return frame[["symbol", "trade_date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"]]


def _build_peer_quotes(
    *,
    provider: MarketDataProvider,
    profile: IndustryProfile,
    trade_round: TradeRound,
    start: date,
    end: date,
) -> tuple[list[dict[str, Any]], str, str, list[str]]:
    peers = _peer_candidates(profile, trade_round.code)
    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    errors: list[str] = []
    target_date = trade_round.start_date
    for name, code in peers:
        fetch = fetch_daily_with_source(provider=provider, table="stock_daily", symbol=code, start=start, end=end, kind="stock")
        errors.extend(fetch.errors)
        sources.append(fetch.source)
        if fetch.frame.empty:
            continue
        rows.append(
            {
                "name": name,
                "code": code,
                "day_pct": _day_pct(fetch.frame, target_date),
                "five_day_pct": _window_return(fetch.frame, target_date, 5),
                "twenty_day_pct": _window_return(fetch.frame, target_date, 20),
                "source": fetch.source,
            }
        )
    status = "missing"
    if rows and len(rows) >= 3:
        status = "ok" if all(source == SOURCE_TENCENT for source in sources[: len(rows)]) else "partial"
    elif rows:
        status = "partial"
    source = _aggregate_source(sources)
    return rows, status, source, _dedupe(errors)


def _trade_facts(trade_round: TradeRound) -> dict[str, Any]:
    return {
        "stock_name": trade_round.name,
        "stock_code": trade_round.code,
        "trades": [
            {
                "side": trade.side,
                "date": trade.trade_date.isoformat(),
                "price": float(trade.price),
                "quantity": float(trade.quantity),
            }
            for trade in trade_round.trades
        ],
    }


def _quote_rows(
    frame: pd.DataFrame,
    *,
    source: str,
    trade_dates: list[date] | None = None,
    symbol: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    rows = []
    dates = trade_dates or [item for item in frame.sort_values("trade_date")["trade_date"].tolist()] if not frame.empty else []
    for trade_date in dates:
        row = _row_on_or_after(frame, trade_date)
        if not row:
            continue
        item = {
            "date": str(row.get("trade_date") or trade_date.isoformat()),
            "open": _num(row.get("open")),
            "high": _num(row.get("high")),
            "low": _num(row.get("low")),
            "close": _num(row.get("close")),
            "pct": _num(row.get("pct_chg")),
            "source": source,
        }
        if symbol or name:
            item["symbol"] = symbol
            item["name"] = name
        rows.append(item)
    return rows


def _sector_identity(profile: IndustryProfile, code: str) -> tuple[str, str]:
    hint = PEER_HINTS.get(code, {})
    name = str(getattr(profile, "theme", "") or "").strip()
    if not name or "待" in name or "寰" in name:
        name = str(hint.get("concept") or getattr(profile, "node", "") or "板块/概念")
    symbol = str(getattr(profile, "sector_symbol", "") or "").strip()
    if not symbol or symbol == "sh000300":
        symbol = str(hint.get("sector_symbol") or "sh000300")
    return name[:40], symbol


def _peer_candidates(profile: IndustryProfile, code: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for item in getattr(profile, "peers", ()) or ():
        text = str(item or "").strip()
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) >= 6:
            rows.append((text.replace(digits[-6:], "").strip(" -_()（）") or digits[-6:], digits[-6:]))
    rows.extend(PEER_HINTS.get(code, {}).get("peers", ()))
    seen = {code}
    deduped = []
    for name, peer_code in rows:
        clean_code = "".join(ch for ch in str(peer_code) if ch.isdigit())[-6:]
        if len(clean_code) != 6 or clean_code in seen:
            continue
        seen.add(clean_code)
        deduped.append((str(name or clean_code), clean_code))
    return deduped[:6]


def _trade_dates(trade_round: TradeRound) -> list[date]:
    seen: set[date] = set()
    rows = []
    for trade in trade_round.trades:
        if trade.trade_date not in seen:
            seen.add(trade.trade_date)
            rows.append(trade.trade_date)
    return rows


def _day_pct(frame: pd.DataFrame, target: date) -> float:
    return _num(_row_on_or_after(frame, target).get("pct_chg"))


def _window_return(frame: pd.DataFrame, target: date, days: int) -> float:
    if frame.empty:
        return 0.0
    rows = frame.sort_values("trade_date").reset_index(drop=True)
    matches = rows[rows["trade_date"] <= target]
    if matches.empty:
        return 0.0
    end_idx = int(matches.index[-1])
    start_idx = max(0, end_idx - max(1, days))
    start_close = _num(rows.loc[start_idx, "close"])
    end_close = _num(rows.loc[end_idx, "close"])
    if start_close <= 0:
        return 0.0
    return round((end_close / start_close - 1) * 100, 4)


def _row_on_or_after(frame: pd.DataFrame, target: date) -> dict[str, Any]:
    if frame.empty or "trade_date" not in frame.columns:
        return {}
    rows = frame.sort_values("trade_date")
    match = rows[rows["trade_date"] >= target]
    if match.empty:
        match = rows[rows["trade_date"] <= target]
    if match.empty:
        return {}
    return match.iloc[0].to_dict()


def _looks_like_index_symbol(symbol: str) -> bool:
    text = str(symbol or "")
    return text.startswith(("sh000", "sz399"))


def _aggregate_source(sources: list[str]) -> str:
    valid = [source for source in sources if source != SOURCE_MISSING]
    if not valid:
        return SOURCE_MISSING
    if all(source == SOURCE_TENCENT for source in valid):
        return SOURCE_TENCENT
    if any(source == SOURCE_AKSHARE for source in valid):
        return SOURCE_AKSHARE
    return SOURCE_FALLBACK


def _safe_write_cache(provider: MarketDataProvider, table: str, frame: pd.DataFrame) -> None:
    try:
        provider._write_cache(table, frame)
    except Exception:
        return


def _safe_read_cache(provider: MarketDataProvider, table: str, symbol: str, start: date, end: date) -> pd.DataFrame:
    try:
        return provider._read_cache(table, symbol, start, end)
    except Exception:
        return pd.DataFrame()


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            rows.append(text)
    return rows


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return round(float(value), 4)
    except Exception:
        return default
