from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests


class MarketDataProvider:
    """Market facts provider.

    Tencent Finance is the primary source for K-line/index facts. AKShare is
    kept only as a fallback adapter, not as an investment-research source.
    """

    def __init__(self, cache_db: str | Path, adjust: str = "qfq", offline: bool = False, disable_cache: bool = False):
        self.cache_db = Path(cache_db)
        self.adjust = adjust
        self.offline = offline
        self.disable_cache = bool(disable_cache)
        if not self.disable_cache:
            self.cache_db.parent.mkdir(parents=True, exist_ok=True)

    def stock_daily(self, code: str, start: date, end: date) -> pd.DataFrame:
        cached = pd.DataFrame() if self.disable_cache else self._read_cache("stock_daily", code, start, end)
        if self.offline or _covers(cached, start, end):
            return cached

        frame = _fetch_tencent_daily(code, start, end, self.adjust, is_index=False)
        if frame.empty:
            frame = _fetch_akshare_stock_daily(code, start, end, self.adjust)
        if frame.empty:
            return cached

        if self.disable_cache:
            return frame
        self._write_cache("stock_daily", frame)
        return self._read_cache("stock_daily", code, start, end)

    def index_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        cached = pd.DataFrame() if self.disable_cache else self._read_cache("index_daily", symbol, start, end)
        if self.offline or _covers(cached, start, end):
            return cached

        frame = _fetch_tencent_daily(symbol, start, end, self.adjust, is_index=True)
        if frame.empty:
            frame = _fetch_akshare_index_daily(symbol)
        if frame.empty:
            return cached

        if self.disable_cache:
            return frame
        self._write_cache("index_daily", frame)
        return self._read_cache("index_daily", symbol, start, end)

    def _read_cache(self, table: str, symbol: str, start: date, end: date) -> pd.DataFrame:
        if self.disable_cache:
            return pd.DataFrame()
        if not self.cache_db.exists():
            return pd.DataFrame()
        with sqlite3.connect(self.cache_db) as conn:
            try:
                frame = pd.read_sql_query(
                    f"""
                    SELECT * FROM {table}
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
        return frame

    def _write_cache(self, table: str, frame: pd.DataFrame) -> None:
        if self.disable_cache:
            return
        if frame.empty:
            return
        with sqlite3.connect(self.cache_db) as conn:
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
                    PRIMARY KEY (symbol, trade_date)
                )
                """
            )
            rows = frame.copy()
            rows["trade_date"] = rows["trade_date"].astype(str)
            records = rows[
                ["symbol", "trade_date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"]
            ].to_records(index=False)
            conn.executemany(
                f"""
                INSERT OR REPLACE INTO {table}
                (symbol, trade_date, open, close, high, low, volume, amount, pct_chg, turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def _fetch_akshare_index_daily(symbol: str) -> pd.DataFrame:
    try:
        import akshare as ak

        raw = ak.stock_zh_index_daily_em(symbol=symbol)
        return _normalize_ak_index(raw, symbol)
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
    }
    frame = raw.rename(columns=rename)
    if "pct_chg" not in frame.columns and "close" in frame.columns:
        frame["pct_chg"] = pd.to_numeric(frame["close"], errors="coerce").pct_change() * 100
    frame["turnover"] = None
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
