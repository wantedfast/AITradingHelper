from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from .data_provider import MarketDataFetch, MarketDataProvider, SOURCE_FALLBACK, SOURCE_MISSING
from .industry_profiles import IndustryProfile
from .stock_resolver import resolve_stock_code
from .trade_rounds import TradeRound
from .workbench_schema import WORKFLOW_TIMING_KEYS


HS300_ETF_SYMBOL = "510300"
HS300_ETF_NAME = "沪深300ETF"


def build_trading_context_payload(
    *,
    provider: MarketDataProvider,
    profile: IndustryProfile,
    trade_round: TradeRound,
    stock_fetch: MarketDataFetch,
    sector_fetch: MarketDataFetch,
    benchmark_fetch: MarketDataFetch,
    analysis: dict[str, Any],
    start: date,
    end: date,
) -> dict[str, Any]:
    peer_fetches, peer_candidates, peer_errors = _load_peer_candidates(
        provider=provider,
        profile=profile,
        trade_round=trade_round,
        start=start,
        end=max(end, trade_round.start_date + timedelta(days=45)),
    )
    data_errors = []
    data_errors.extend(stock_fetch.errors)
    data_errors.extend(sector_fetch.errors)
    data_errors.extend(benchmark_fetch.errors)
    data_errors.extend(peer_errors)

    trade_timing = _build_trade_timing(
        profile=profile,
        trade_round=trade_round,
        stock=stock_fetch.frame,
        sector=sector_fetch.frame,
        benchmark=benchmark_fetch.frame,
        stock_source=stock_fetch.source,
        sector_source=sector_fetch.source,
        benchmark_source=benchmark_fetch.source,
        analysis=analysis,
    )
    peer_comparison = _build_peer_comparison(
        profile=profile,
        trade_round=trade_round,
        peer_fetches=peer_fetches,
    )
    return {
        "trade_timing": trade_timing,
        "peer_comparison": peer_comparison,
        "peer_candidates": peer_candidates,
        "trade_execution_notes": _build_trade_execution_notes(analysis, trade_round),
        "data_source_status": {
            "target_stock": stock_fetch.source,
            "hs300_etf": benchmark_fetch.source,
            "sector_quote": sector_fetch.source,
            "peer_quotes": _peer_quote_source(peer_fetches),
        },
        "data_errors": _dedupe(data_errors),
        "workflow_timings_ms": {key: 0 for key in WORKFLOW_TIMING_KEYS},
    }


def _build_trade_timing(
    *,
    profile: IndustryProfile,
    trade_round: TradeRound,
    stock: pd.DataFrame,
    sector: pd.DataFrame,
    benchmark: pd.DataFrame,
    stock_source: str,
    sector_source: str,
    benchmark_source: str,
    analysis: dict[str, Any],
) -> dict[str, Any]:
    buy_day = _timing_day_payload(
        day=trade_round.start_date,
        stock=stock,
        sector=sector,
        benchmark=benchmark,
        stock_source=stock_source,
        sector_source=sector_source,
        benchmark_source=benchmark_source,
    )
    sell_day = _timing_day_payload(
        day=trade_round.end_date,
        stock=stock,
        sector=sector,
        benchmark=benchmark,
        stock_source=stock_source,
        sector_source=sector_source,
        benchmark_source=benchmark_source,
    )
    return {
        "benchmark_symbol": HS300_ETF_SYMBOL,
        "benchmark_name": HS300_ETF_NAME,
        "sector_name": _sector_name(profile),
        "buy_day": buy_day,
        "sell_day": sell_day,
        "summary": _timing_summary(buy_day, sell_day, analysis, trade_round),
    }


def _timing_day_payload(
    *,
    day: date,
    stock: pd.DataFrame,
    sector: pd.DataFrame,
    benchmark: pd.DataFrame,
    stock_source: str,
    sector_source: str,
    benchmark_source: str,
) -> dict[str, Any]:
    stock_row = _row_on_or_after(stock, day)
    sector_row = _row_on_or_after(sector, day)
    benchmark_row = _row_on_or_after(benchmark, day)
    stock_pct = _num(stock_row.get("pct_chg"))
    sector_pct = _num(sector_row.get("pct_chg"))
    benchmark_pct = _num(benchmark_row.get("pct_chg"))
    payload = {
        "date": _row_date(stock_row) or day.isoformat(),
        "stock_pct": stock_pct,
        "hs300_etf_pct": benchmark_pct,
        "sector_pct": sector_pct,
        "vs_hs300_etf_pct": _round2(stock_pct - benchmark_pct),
        "vs_sector_pct": _round2(stock_pct - sector_pct),
        "price_position_pct": _price_position_pct(stock, stock_row),
        "judgment": _timing_judgment(stock_pct, benchmark_pct, sector_pct),
        "reason": _timing_reason(stock_pct, benchmark_pct, sector_pct),
        "data_source": f"stock:{stock_source}; hs300_etf:{benchmark_source}; sector:{sector_source}",
    }
    return payload


def _timing_summary(buy_day: dict[str, Any], sell_day: dict[str, Any], analysis: dict[str, Any], trade_round: TradeRound) -> str:
    ret = _round2(_num(analysis.get("return")))
    status = "已完成卖出" if trade_round.is_closed else "仍在持有"
    return (
        f"买入日相对沪深300ETF{_fmt_signed(buy_day['vs_hs300_etf_pct'])}，"
        f"相对板块{_fmt_signed(buy_day['vs_sector_pct'])}；"
        f"卖出日相对沪深300ETF{_fmt_signed(sell_day['vs_hs300_etf_pct'])}，"
        f"相对板块{_fmt_signed(sell_day['vs_sector_pct'])}。"
        f"本轮交易{status}，区间收益{ret:.2f}%。"
    )


def _build_trade_execution_notes(analysis: dict[str, Any], trade_round: TradeRound) -> dict[str, Any]:
    optimal = analysis.get("optimal") if isinstance(analysis, dict) else {}
    optimal = optimal if isinstance(optimal, dict) else {}
    return {
        "buy_note": str(optimal.get("buy_reason") or optimal.get("buy_verdict") or ""),
        "sell_note": str(optimal.get("sell_reason") or optimal.get("sell_verdict") or ""),
        "discipline_note": str(analysis.get("headline") or ""),
        "summary": (
            f"买点判断：{str(optimal.get('buy_label') or optimal.get('buy_verdict') or '待验证')}；"
            f"卖点判断：{str(optimal.get('sell_label') or optimal.get('sell_verdict') or ('持有中' if not trade_round.is_closed else '待验证'))}。"
        ),
    }


def _build_peer_comparison(
    *,
    profile: IndustryProfile,
    trade_round: TradeRound,
    peer_fetches: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in peer_fetches:
        fetch = item["fetch"]
        frame = fetch.frame
        if frame.empty:
            continue
        day_pct = _row_metric(frame, trade_round.start_date, "pct_chg")
        five_day_pct = _forward_return(frame, trade_round.start_date, 5)
        twenty_day_pct = _forward_return(frame, trade_round.start_date, 20)
        rows.append(
            {
                "name": item["name"],
                "code": item["code"],
                "is_target": bool(item["is_target"]),
                "day_pct": day_pct,
                "five_day_pct": five_day_pct,
                "twenty_day_pct": twenty_day_pct,
                "strength": "",
                "advantage": "",
                "weakness": "",
                "quote_source": fetch.source,
            }
        )
    rows = _rank_peer_rows(rows)
    target_row = next((row for row in rows if row["is_target"]), None)
    conclusion = _peer_conclusion(rows, target_row)
    return {
        "concept": str(profile.theme or profile.node or "待验证"),
        "sector_symbol": str(profile.sector_symbol or ""),
        "target": {"name": profile.name, "code": trade_round.code},
        "rows": rows,
        "conclusion": conclusion,
        "data_note": _peer_data_note(rows, peer_fetches),
    }


def _load_peer_candidates(
    *,
    provider: MarketDataProvider,
    profile: IndustryProfile,
    trade_round: TradeRound,
    start: date,
    end: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    candidates = _candidate_list(profile, trade_round)
    peer_fetches: list[dict[str, Any]] = []
    peer_candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        code = str(candidate["code"]).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        fetch = provider.stock_daily_with_status(code, start, end)
        peer_fetches.append({**candidate, "fetch": fetch})
        peer_candidates.append(
            {
                "name": candidate["name"],
                "code": code,
                "is_target": bool(candidate["is_target"]),
                "candidate_source": candidate["candidate_source"],
                "quote_source": fetch.source,
            }
        )
        for error in fetch.errors:
            errors.append(f"peer {code}: {error}")
    return peer_fetches, peer_candidates, errors


def _candidate_list(profile: IndustryProfile, trade_round: TradeRound) -> list[dict[str, Any]]:
    rows = [
        {
            "name": profile.name or trade_round.name or trade_round.code,
            "code": trade_round.code,
            "is_target": True,
            "candidate_source": "target",
        }
    ]
    for name in profile.peers[:5]:
        code = resolve_stock_code(name)
        if code:
            rows.append(
                {
                    "name": str(name),
                    "code": code,
                    "is_target": False,
                    "candidate_source": "profile_peers",
                }
            )
    return rows


def _peer_quote_source(peer_fetches: list[dict[str, Any]]) -> str:
    sources = {str(item["fetch"].source) for item in peer_fetches if isinstance(item.get("fetch"), MarketDataFetch)}
    if not sources:
        return SOURCE_MISSING
    if SOURCE_MISSING in sources and len(sources) == 1:
        return SOURCE_MISSING
    if SOURCE_FALLBACK in sources and len(sources) == 1:
        return SOURCE_FALLBACK
    if "tencent_finance" in sources:
        return "tencent_finance"
    if "akshare" in sources:
        return "akshare"
    return sorted(sources)[0]


def _rank_peer_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    def score(row: dict[str, Any]) -> float:
        return _num(row.get("day_pct")) + _num(row.get("five_day_pct")) * 0.6 + _num(row.get("twenty_day_pct")) * 0.4

    ordered = sorted(rows, key=score, reverse=True)
    target_score = None
    for row in ordered:
        current = score(row)
        if row["is_target"]:
            target_score = current
        row["strength"] = _strength_label(current, ordered)
        row["advantage"] = _advantage_text(row)
        row["weakness"] = _weakness_text(row)
    if target_score is not None:
        for row in ordered:
            if row["is_target"]:
                row["advantage"] = _target_advantage_text(row, ordered)
                row["weakness"] = _target_weakness_text(row, ordered)
    return ordered


def _strength_label(value: float, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "待验证"
    scores = sorted((_num(row.get("day_pct")) + _num(row.get("five_day_pct")) * 0.6 + _num(row.get("twenty_day_pct")) * 0.4 for row in rows), reverse=True)
    if value >= scores[0]:
        return "领先"
    if len(scores) > 1 and value >= scores[min(1, len(scores) - 1)]:
        return "较强"
    if value <= scores[-1]:
        return "偏弱"
    return "中性"


def _advantage_text(row: dict[str, Any]) -> str:
    day_pct = _num(row.get("day_pct"))
    twenty_day_pct = _num(row.get("twenty_day_pct"))
    if day_pct >= 3 and twenty_day_pct >= 8:
        return "买入当日与20日弹性都较强"
    if day_pct > 0 and twenty_day_pct > 0:
        return "短中期表现为正"
    if twenty_day_pct >= 8:
        return "20日弹性较强"
    return "优势待验证"


def _weakness_text(row: dict[str, Any]) -> str:
    day_pct = _num(row.get("day_pct"))
    twenty_day_pct = _num(row.get("twenty_day_pct"))
    if day_pct < 0 and twenty_day_pct < 0:
        return "买入当日与20日表现都偏弱"
    if twenty_day_pct < 0:
        return "20日表现落后"
    if day_pct < 0:
        return "买入当日反馈偏弱"
    return "弱点待验证"


def _target_advantage_text(target_row: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if not rows:
        return target_row["advantage"]
    if rows and rows[0]["is_target"]:
        return "目标股在同概念样本中综合强度领先"
    return target_row["advantage"]


def _target_weakness_text(target_row: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if rows and rows[-1]["is_target"]:
        return "目标股在同概念样本中综合强度靠后"
    return target_row["weakness"]


def _peer_conclusion(rows: list[dict[str, Any]], target_row: dict[str, Any] | None) -> str:
    if not rows or target_row is None:
        return "缺少可比行情，暂无法判断目标股在同概念中的强弱。"
    top = rows[0]
    if top["is_target"]:
        return "目标股在样本内综合强度靠前，交易时点并未明显落后同概念。"
    return f"样本内更强的是{top['name']}({top['code']})，目标股相对强度仍需和同概念龙头比较。"


def _peer_data_note(rows: list[dict[str, Any]], peer_fetches: list[dict[str, Any]]) -> str:
    if not rows:
        return "未取到可比个股有效行情；当前仅保留候选清单。"
    missing = [item["name"] for item in peer_fetches if item["fetch"].frame.empty]
    if missing:
        return f"部分候选未取到有效行情：{'、'.join(missing[:4])}。"
    return f"共比较{len(rows)}个样本，包含目标股与同概念候选。"


def _row_on_or_after(frame: pd.DataFrame, day: date) -> pd.Series:
    if frame.empty or "trade_date" not in frame.columns:
        return pd.Series(dtype="object")
    ordered = frame.sort_values("trade_date").reset_index(drop=True)
    matches = ordered.index[ordered["trade_date"] >= day].tolist()
    if not matches:
        return pd.Series(dtype="object")
    return ordered.loc[matches[0]]


def _row_metric(frame: pd.DataFrame, day: date, column: str) -> float:
    row = _row_on_or_after(frame, day)
    return _round2(_num(row.get(column)))


def _row_date(row: pd.Series) -> str:
    value = row.get("trade_date")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def _forward_return(frame: pd.DataFrame, day: date, days: int) -> float:
    if frame.empty or "trade_date" not in frame.columns:
        return 0.0
    ordered = frame.sort_values("trade_date").reset_index(drop=True)
    matches = ordered.index[ordered["trade_date"] >= day].tolist()
    if not matches:
        return 0.0
    start_idx = matches[0]
    end_idx = min(len(ordered) - 1, start_idx + days)
    start_close = _num(ordered.loc[start_idx, "close"])
    end_close = _num(ordered.loc[end_idx, "close"])
    if not start_close:
        return 0.0
    return _round2((end_close / start_close - 1) * 100)


def _price_position_pct(frame: pd.DataFrame, row: pd.Series) -> float:
    if frame.empty or row.empty or "trade_date" not in frame.columns:
        return 0.0
    ordered = frame.sort_values("trade_date").reset_index(drop=True)
    matches = ordered.index[ordered["trade_date"] == row.get("trade_date")].tolist()
    if not matches:
        return 0.0
    idx = matches[0]
    window = ordered.loc[max(0, idx - 19): idx]
    low = pd.to_numeric(window["low"], errors="coerce").min()
    high = pd.to_numeric(window["high"], errors="coerce").max()
    close = _num(row.get("close"))
    if pd.isna(low) or pd.isna(high) or high <= low:
        return 50.0 if close else 0.0
    return _round2((close - float(low)) / (float(high) - float(low)) * 100)


def _timing_judgment(stock_pct: float, benchmark_pct: float, sector_pct: float) -> str:
    if stock_pct >= benchmark_pct and stock_pct >= sector_pct:
        return "强于指数和板块"
    if stock_pct >= benchmark_pct:
        return "强于指数但弱于板块"
    if stock_pct >= sector_pct:
        return "强于板块但弱于指数"
    return "弱于指数和板块"


def _timing_reason(stock_pct: float, benchmark_pct: float, sector_pct: float) -> str:
    return (
        f"个股当日{stock_pct:.2f}%，"
        f"沪深300ETF{benchmark_pct:.2f}%，"
        f"板块/概念{sector_pct:.2f}%。"
    )


def _sector_name(profile: IndustryProfile) -> str:
    return str(profile.theme or profile.node or profile.sector_symbol or "板块/概念")


def _fmt_signed(value: float) -> str:
    return f"{value:+.2f}%"


def _round2(value: float) -> float:
    return round(float(value or 0.0), 2)


def _num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
