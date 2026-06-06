from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .data_provider import MarketDataProvider, window
from .schema import ReviewConfig, Trade


@dataclass(frozen=True)
class TradeReview:
    trade: Trade
    execution_date: object
    execution_close: float | None
    execution_pct_chg: float | None
    volume_ratio_5d: float | None
    returns: dict[int, float | None]
    benchmark_returns: dict[int, float | None]
    relative_returns: dict[int, float | None]
    max_gain_10d: float | None
    max_drawdown_10d: float | None
    verdict: str
    problem: str
    improvement: str


def review_trades(trades: list[Trade], config: ReviewConfig) -> list[TradeReview]:
    provider = MarketDataProvider(config.cache_db, adjust=config.adjust, offline=config.offline)
    reviews: list[TradeReview] = []
    max_days = max(config.lookahead_days)
    stock_cache: dict[str, pd.DataFrame] = {}
    min_trade_date = min(trade.trade_date for trade in trades)
    max_trade_date = max(trade.trade_date for trade in trades)
    benchmark_start, _ = window(min_trade_date, max_days)
    _, benchmark_end = window(max_trade_date, max_days)
    benchmark = provider.index_daily(config.benchmark_symbol, benchmark_start, benchmark_end)
    for trade in trades:
        if trade.code not in stock_cache:
            code_dates = [item.trade_date for item in trades if item.code == trade.code]
            code_start, _ = window(min(code_dates), max_days)
            _, code_end = window(max(code_dates), max_days)
            stock_cache[trade.code] = provider.stock_daily(trade.code, code_start, code_end)
        stock = stock_cache[trade.code]
        reviews.append(_review_one(trade, stock, benchmark, config))
    return reviews


def _review_one(trade: Trade, stock: pd.DataFrame, benchmark: pd.DataFrame, config: ReviewConfig) -> TradeReview:
    stock = _sorted_daily(stock)
    benchmark = _sorted_daily(benchmark)
    idx = _first_on_or_after(stock, trade.trade_date)
    bidx = _first_on_or_after(benchmark, trade.trade_date)

    if idx is None:
        return TradeReview(
            trade=trade,
            execution_date=trade.trade_date,
            execution_close=None,
            execution_pct_chg=None,
            volume_ratio_5d=None,
            returns={day: None for day in config.lookahead_days},
            benchmark_returns={day: None for day in config.lookahead_days},
            relative_returns={day: None for day in config.lookahead_days},
            max_gain_10d=None,
            max_drawdown_10d=None,
            verdict="数据不足",
            problem="未取得该股票交易日附近的日K数据。",
            improvement="先确认股票代码、成交日期和 AKShare 数据接口是否可用。",
        )

    entry_close = _num(stock.loc[idx, "close"])
    execution_date = stock.loc[idx, "trade_date"]
    execution_pct_chg = _num(stock.loc[idx, "pct_chg"])
    volume_ratio = _volume_ratio(stock, idx, lookback=5)
    returns = {day: _forward_return(stock, idx, day, entry_close) for day in config.lookahead_days}
    benchmark_entry = _num(benchmark.loc[bidx, "close"]) if bidx is not None else None
    benchmark_returns = {
        day: _forward_return(benchmark, bidx, day, benchmark_entry) if bidx is not None else None
        for day in config.lookahead_days
    }
    relative_returns = {
        day: _subtract(returns.get(day), benchmark_returns.get(day)) for day in config.lookahead_days
    }
    max_gain, max_drawdown = _max_gain_drawdown(stock, idx, entry_close, horizon=10)
    verdict, problem, improvement = _diagnose(trade, execution_pct_chg, volume_ratio, returns, relative_returns, max_gain, max_drawdown)

    return TradeReview(
        trade=trade,
        execution_date=execution_date,
        execution_close=entry_close,
        execution_pct_chg=execution_pct_chg,
        volume_ratio_5d=volume_ratio,
        returns=returns,
        benchmark_returns=benchmark_returns,
        relative_returns=relative_returns,
        max_gain_10d=max_gain,
        max_drawdown_10d=max_drawdown,
        verdict=verdict,
        problem=problem,
        improvement=improvement,
    )


def _first_on_or_after(frame: pd.DataFrame, trade_date) -> int | None:
    if frame.empty or "trade_date" not in frame.columns:
        return None
    matches = frame.index[frame["trade_date"] >= trade_date].tolist()
    return matches[0] if matches else None


def _sorted_daily(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "trade_date" not in frame.columns:
        return pd.DataFrame(columns=["trade_date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"])
    return frame.sort_values("trade_date").reset_index(drop=True)


def _forward_return(frame: pd.DataFrame, idx: int | None, days: int, base: float | None) -> float | None:
    if idx is None or base in (None, 0):
        return None
    target = idx + days
    if target >= len(frame):
        return None
    close = _num(frame.loc[target, "close"])
    if close is None:
        return None
    return (close / base - 1) * 100


def _volume_ratio(frame: pd.DataFrame, idx: int, lookback: int) -> float | None:
    if idx < 1:
        return None
    current = _num(frame.loc[idx, "volume"])
    history = frame.loc[max(0, idx - lookback): idx - 1, "volume"].dropna()
    if current is None or history.empty or history.mean() == 0:
        return None
    return current / history.mean()


def _max_gain_drawdown(frame: pd.DataFrame, idx: int, base: float | None, horizon: int) -> tuple[float | None, float | None]:
    if base in (None, 0):
        return None, None
    segment = frame.loc[idx + 1: idx + horizon]
    if segment.empty:
        return None, None
    max_high = segment["high"].max()
    min_low = segment["low"].min()
    return (max_high / base - 1) * 100, (min_low / base - 1) * 100


def _diagnose(
    trade: Trade,
    pct_chg: float | None,
    volume_ratio: float | None,
    returns: dict[int, float | None],
    relative_returns: dict[int, float | None],
    max_gain: float | None,
    max_drawdown: float | None,
) -> tuple[str, str, str]:
    r5 = returns.get(5)
    rel5 = relative_returns.get(5)
    r10 = returns.get(10)

    if trade.side == "buy":
        if _gte(r5, 3) and _gte(rel5, 2):
            return "买入点：合格", "买入后 5 个交易日跑赢基准，短线验证较好。", "记录触发条件，后续观察这类买点是否可重复。"
        if _lte(max_drawdown, -6):
            return "买入点：偏激进", "买入后 10 个交易日内回撤较深，说明入场位置或仓位需要更谨慎。", "下次等待回踩、缩量企稳或突破后确认，再考虑加仓。"
        if _gte(pct_chg, 6) and _gte(volume_ratio, 2):
            return "买入点：追高风险", "买入日涨幅和放量都较大，容易买在情绪高潮。", "追强势股时预先定义失效条件，例如次日不继续放量即降仓。"
        return "买入点：待观察", "后续收益和相对强弱没有给出明显优势。", "把买入理由写得更可检验，例如突破位、放量阈值、行业催化。"

    if _gte(r10, 5):
        return "卖出点：偏早", "卖出后 10 个交易日仍有明显上涨，可能存在盈利单拿不住的问题。", "可尝试用 5 日线、前一日低点或移动止盈替代主观卖出。"
    if _lte(r5, -3):
        return "卖出点：有效", "卖出后短期继续下跌，退出动作避免了进一步回撤。", "复盘卖出触发条件，沉淀为下次可执行的规则。"
    return "卖出点：中性", "卖出后走势没有明显证明过早或过晚。", "结合当时卖出理由，判断是规则退出还是情绪退出。"


def _num(value) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _subtract(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _gte(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _lte(value: float | None, threshold: float) -> bool:
    return value is not None and value <= threshold
