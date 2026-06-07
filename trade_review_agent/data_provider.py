from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests


SOURCE_TENCENT = "tencent_finance"
SOURCE_AKSHARE = "akshare"
SOURCE_FALLBACK = "fallback_existing"
SOURCE_MISSING = "missing"


@dataclass(frozen=True)
class MarketDataFetch:
    frame: pd.DataFrame
    source: str
    errors: list[str]
    symbol: str
    table: str


class MarketDataProvider:
    """Market facts provider with source tracking.

    Tencent Finance is the primary source for quote data. AKShare is used only
    as a fallback adapter, while older cached rows are labeled as
    ``fallback_existing`` when their original source is unknown.
    """

    def __init__(self, cache_db: str | Path, adjust: str = "qfq", offline: bool = False):
        self.cache_db = Path(cache_db)
        self.adjust = adjust
        self.offline = offline
        self.cache_db.parent.mkdir(parents=True, exist_ok=True)

    def stock_daily(self, code: str, start: date, end: date) -> pd.DataFrame:
        return self.stock_daily_with_status(code, start, end).frame

    def index_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        return self.index_daily_with_status(symbol, start, end).frame

    def stock_daily_with_status(self, code: str, start: date, end: date) -> MarketDataFetch:
        return self._load_with_status(
            table="stock_daily",
            symbol=code,
            start=start,
            end=end,
            fetchers=[
                ("Tencent Finance", SOURCE_TENCENT, lambda: _fetch_tencent_daily(code, start, end, self.adjust, is_index=False)),
                ("AKShare", SOURCE_AKSHARE, lambda: _fetch_akshare_stock_daily(code, start, end, self.adjust)),
            ],
        )

    def index_daily_with_status(self, symbol: str, start: date, end: date) -> MarketDataFetch:
        return self._load_with_status(
            table="index_daily",
            symbol=symbol,
            start=start,
            end=end,
            fetchers=[
                ("Tencent Finance", SOURCE_TENCENT, lambda: _fetch_tencent_daily(symbol, start, end, self.adjust, is_index=True)),
                ("AKShare", SOURCE_AKSHARE, lambda: _fetch_akshare_index_daily(symbol, start, end)),
            ],
        )

    def _load_with_status(
        self,
        *,
        table: str,
        symbol: str,
        start: date,
        end: date,
        fetchers: list[tuple[str, str, object]],
    ) -> MarketDataFetch:
        errors: list[str] = []
        cached = self._read_cache(table, symbol, start, end)
        cached_source = _frame_source(cached)
        if self.offline or _covers(cached, start, end):
            return MarketDataFetch(cached, cached_source, errors, symbol, table)

        for label, source, fetcher in fetchers:
            try:
                frame = fetcher()  # type: ignore[misc]
            except Exception as exc:  # pragma: no cover - defensive guard
                errors.append(f"{label} {symbol}: {exc}")
                frame = pd.DataFrame()
            if frame.empty:
                errors.append(f"{label} returned no rows for {symbol}")
                continue
            self._write_cache(table, _with_source(frame, source), source=source)
            cached = self._read_cache(table, symbol, start, end)
            return MarketDataFetch(cached if not cached.empty else _with_source(frame, source), source, errors, symbol, table)

        if not cached.empty:
            if cached_source == SOURCE_MISSING:
                cached_source = SOURCE_FALLBACK
            return MarketDataFetch(cached, cached_source, errors, symbol, table)
        return MarketDataFetch(pd.DataFrame(), SOURCE_MISSING, errors, symbol, table)

    def _read_cache(self, table: str, symbol: str, start: date, end: date) -> pd.DataFrame:
        if not self.cache_db.exists():
            return pd.DataFrame()
        with sqlite3.connect(self.cache_db) as conn:
            try:
                columns = _table_columns(conn, table)
                if not columns:
                    return pd.DataFrame()
                select_columns = [
                    "symbol",
                    "trade_date",
                    "open",
                    "close",
                    "high",
                    "low",
                    "volume",
                    "amount",
                    "pct_chg",
                    "turnover",
                ]
                if "source" in columns:
                    select_columns.append("source")
                frame = pd.read_sql_query(
                    f"""
                    SELECT {", ".join(select_columns)} FROM {table}
                    WHERE symbol = ? AND trade_date BETWEEN ? AND ?
                    ORDER BY trade_date
                    """,
                    conn,
                    params=(symbol, start.isoformat(), end.isoformat()),
                )
            except Exception:
                return pd.DataFrame()
        if not frame.empty:
            frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
            frame = _ensure_pct_chg(frame)
            if "source" in frame.columns:
                frame["source"] = frame["source"].fillna(SOURCE_FALLBACK).astype(str)
        return frame

    def _write_cache(self, table: str, frame: pd.DataFrame, *, source: str) -> None:
        if frame.empty:
            return
        with sqlite3.connect(self.cache_db) as conn:
            _ensure_cache_table(conn, table)
            rows = _with_source(frame, source).copy()
            rows["trade_date"] = rows["trade_date"].astype(str)
            records = rows[
                ["symbol", "trade_date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover", "source"]
            ].to_records(index=False)
            conn.executemany(
                f"""
                INSERT OR REPLACE INTO {table}
                (symbol, trade_date, open, close, high, low, volume, amount, pct_chg, turnover, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )


def window(start: date, max_lookahead_days: int) -> tuple[date, date]:
    return start - timedelta(days=20), start + timedelta(days=max_lookahead_days * 3 + 10)


def _covers(frame: pd.DataFrame, start: date, end: date) -> bool:
    if frame.empty:
        return False
    dates = sorted(frame["trade_date"])
    return dates[0] <= start and dates[-1] >= end


def _fetch_tencent_daily(symbol: str, start: date, end: date, adjust: str, is_index: bool) -> pd.DataFrame:
    tencent_symbol = _tencent_symbol(symbol)
    adjust_param = "" if is_index else adjust
    param = ",".join(
        [
            tencent_symbol,
            "day",
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            "800",
            adjust_param,
        ]
    )
    try:
        response = requests.get(
            "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            params={"param": param},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {}).get(tencent_symbol, {})
        rows = data.get(_tencent_kline_key(adjust_param, data), [])
    except Exception as exc:
        print(f"[warn] Tencent Finance kline failed for {symbol}: {exc}", file=sys.stderr)
        return pd.DataFrame()

    if not rows:
        print(f"[warn] Tencent Finance returned no kline rows for {symbol}", file=sys.stderr)
        return pd.DataFrame()

    frame = pd.DataFrame(rows).iloc[:, :6]
    frame.columns = ["trade_date", "open", "close", "high", "low", "volume"]
    frame["amount"] = None
    frame["turnover"] = None
    return _standardize_daily_frame(frame, symbol)


def _fetch_akshare_stock_daily(code: str, start: date, end: date, adjust: str) -> pd.DataFrame:
    try:
        import akshare as ak

        raw = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust=adjust,
        )
        return _normalize_ak_stock(raw, code)
    except Exception as exc:
        print(f"[warn] AKShare stock fallback failed for {code}: {exc}", file=sys.stderr)
        return pd.DataFrame()


def _fetch_akshare_index_daily(symbol: str, start: date, end: date) -> pd.DataFrame:
    try:
        import akshare as ak

        if symbol.isdigit() and len(symbol) == 6 and not symbol.startswith(("000", "399")):
            raw = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",
            )
            return _normalize_ak_index(raw, symbol)

        raw = ak.stock_zh_index_daily_em(symbol=symbol)
        normalized = _normalize_ak_index(raw, symbol)
        if not normalized.empty:
            normalized = normalized[
                (normalized["trade_date"] >= start) & (normalized["trade_date"] <= end)
            ].copy()
        return normalized
    except Exception as exc:
        print(f"[warn] AKShare index fallback failed for {symbol}: {exc}", file=sys.stderr)
        return pd.DataFrame()


def _normalize_ak_stock(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
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
        "鏃ユ湡": "trade_date",
        "寮€鐩?": "open",
        "鏀剁洏": "close",
        "鏈€楂?": "high",
        "鏈€浣?": "low",
        "鎴愪氦閲?": "volume",
        "鎴愪氦棰?": "amount",
        "娑ㄨ穼骞?": "pct_chg",
        "鎹㈡墜鐜?": "turnover",
    }
    return _standardize_daily_frame(raw.rename(columns=rename), symbol)


def _normalize_ak_index(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    rename = {
        "date": "trade_date",
        "open": "open",
        "close": "close",
        "high": "high",
        "low": "low",
        "volume": "volume",
        "amount": "amount",
        "日期": "trade_date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "涨跌幅": "pct_chg",
    }
    frame = raw.rename(columns=rename)
    if "pct_chg" not in frame.columns and "close" in frame.columns:
        frame["pct_chg"] = pd.to_numeric(frame["close"], errors="coerce").pct_change() * 100
    frame["turnover"] = frame.get("turnover")
    return _standardize_daily_frame(frame, symbol)


def _standardize_daily_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["symbol"] = symbol
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    for col in ("open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"):
        if col not in frame.columns:
            frame[col] = None
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = _ensure_pct_chg(frame)
    if "source" in frame.columns:
        frame["source"] = frame["source"].fillna(SOURCE_FALLBACK).astype(str)
        return frame[["symbol", "trade_date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover", "source"]]
    return frame[["symbol", "trade_date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"]]


def _ensure_pct_chg(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "close" not in frame.columns:
        return frame
    frame = frame.sort_values("trade_date").copy()
    calculated = pd.to_numeric(frame["close"], errors="coerce").pct_change() * 100
    if "pct_chg" not in frame.columns:
        frame["pct_chg"] = calculated
        return frame
    current = pd.to_numeric(frame["pct_chg"], errors="coerce")
    frame["pct_chg"] = current.fillna(calculated)
    return frame


def _with_source(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    rows = frame.copy()
    rows["source"] = str(source or SOURCE_FALLBACK)
    return rows


def _frame_source(frame: pd.DataFrame) -> str:
    if frame.empty:
        return SOURCE_MISSING
    if "source" not in frame.columns:
        return SOURCE_FALLBACK
    values = [str(item).strip() for item in frame["source"].tolist() if str(item).strip()]
    if not values:
        return SOURCE_FALLBACK
    return max(set(values), key=values.count)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except Exception:
        return set()
    return {str(row[1]) for row in rows}


def _ensure_cache_table(conn: sqlite3.Connection, table: str) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            symbol TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL,
            close REAL,
            high REAL,
            low REAL,
            volume REAL,
            amount REAL,
            pct_chg REAL,
            turnover REAL,
            source TEXT,
            PRIMARY KEY (symbol, trade_date)
        )
        """
    )
    columns = _table_columns(conn, table)
    if "source" not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN source TEXT")


def _tencent_symbol(symbol: str) -> str:
    text = str(symbol or "").strip()
    if text.startswith(("sh", "sz", "bj")):
        return text
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits.startswith(("6", "5", "9")):
        return f"sh{digits}"
    return f"sz{digits}"


def _tencent_kline_key(adjust: str, data: dict) -> str:
    preferred = {"qfq": "qfqday", "hfq": "hfqday", "": "day"}.get(adjust, "day")
    if preferred in data:
        return preferred
    for key in ("qfqday", "hfqday", "day"):
        if key in data:
            return key
    return preferred
