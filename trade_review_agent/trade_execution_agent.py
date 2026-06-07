from __future__ import annotations

from datetime import date
from typing import Any


def analyze_trade_execution(data_context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic execution-quality read from market facts only."""

    data_context = data_context if isinstance(data_context, dict) else {}
    facts = data_context.get("trade_facts") if isinstance(data_context.get("trade_facts"), dict) else {}
    market = data_context.get("market_data") if isinstance(data_context.get("market_data"), dict) else {}
    trades = facts.get("trades") if isinstance(facts.get("trades"), list) else []
    stock_quotes = _by_date(market.get("stock_quotes"))
    benchmark_quotes = _by_date(market.get("benchmark_quotes"))
    sector_quotes = _by_date(market.get("sector_quotes"))
    buy_points = [
        _point_payload(trade, stock_quotes, benchmark_quotes, sector_quotes, side="buy")
        for trade in trades
        if _side(trade) == "buy"
    ]
    sell_points = [
        _sell_point_payload(trade, stock_quotes, benchmark_quotes, sector_quotes, trades)
        for trade in trades
        if _side(trade) == "sell"
    ]
    relative = _relative_strength(buy_points, sell_points)
    peer = _peer_comparison(facts, market, relative)
    notes = _execution_notes(buy_points, sell_points, peer, relative)
    return {
        "trade_timing": {"buy_points": buy_points, "sell_points": sell_points},
        "relative_strength": relative,
        "peer_comparison": peer,
        "trade_execution_notes": notes,
    }


def _point_payload(
    trade: dict[str, Any],
    stock_quotes: dict[str, dict[str, Any]],
    benchmark_quotes: dict[str, dict[str, Any]],
    sector_quotes: dict[str, dict[str, Any]],
    *,
    side: str,
) -> dict[str, Any]:
    trade_date = str(trade.get("date") or "")
    stock = stock_quotes.get(trade_date, {})
    benchmark = benchmark_quotes.get(trade_date, {})
    sector = sector_quotes.get(trade_date, {})
    stock_pct = _num(stock.get("pct"))
    benchmark_pct = _num(benchmark.get("pct"))
    sector_pct = _num(sector.get("pct"))
    excess_benchmark = round(stock_pct - benchmark_pct, 4)
    excess_sector = round(stock_pct - sector_pct, 4)
    position = _intraday_position(_num(trade.get("price")), stock)
    judgment, reason = _buy_judgment(stock_pct, benchmark_pct, sector_pct, position)
    if side == "sell":
        judgment, reason = _sell_judgment(stock_pct, benchmark_pct, sector_pct, position, "unknown")
    return {
        "date": trade_date,
        "price": _num(trade.get("price")),
        "stock_pct": stock_pct,
        "hs300_etf_pct": benchmark_pct,
        "sector_pct": sector_pct,
        "excess_vs_hs300_pct": excess_benchmark,
        "excess_vs_sector_pct": excess_sector,
        "intraday_position": position,
        "judgment": judgment,
        "reason": reason,
    }


def _sell_point_payload(
    trade: dict[str, Any],
    stock_quotes: dict[str, dict[str, Any]],
    benchmark_quotes: dict[str, dict[str, Any]],
    sector_quotes: dict[str, dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = _point_payload(trade, stock_quotes, benchmark_quotes, sector_quotes, side="sell")
    sold_flying = _sold_flying(trade, stock_quotes)
    judgment, reason = _sell_judgment(
        payload["stock_pct"],
        payload["hs300_etf_pct"],
        payload["sector_pct"],
        payload["intraday_position"],
        sold_flying,
    )
    payload["judgment"] = judgment
    payload["reason"] = reason
    return payload


def _relative_strength(buy_points: list[dict[str, Any]], sell_points: list[dict[str, Any]]) -> dict[str, Any]:
    anchor = buy_points[0] if buy_points else {}
    vs_benchmark = _strength_label(_num(anchor.get("excess_vs_hs300_pct")))
    vs_sector = _strength_label(_num(anchor.get("excess_vs_sector_pct")))
    if vs_benchmark == "strong" and vs_sector == "strong":
        conclusion = "买入日个股同时强于沪深300ETF和板块，收益更偏个股主动强势。"
    elif vs_sector == "weak":
        conclusion = "买入日个股弱于板块，更像板块带动下的跟随或补涨。"
    elif vs_benchmark == "strong":
        conclusion = "买入日强于大盘但相对板块优势有限，收益来源偏题材/板块带动。"
    elif vs_benchmark == "unknown" or vs_sector == "unknown":
        conclusion = "行情数据不足，暂不能稳定判断收益来自个股、板块还是大盘。"
    else:
        conclusion = "买入日相对强弱接近板块和大盘，交易优势不明显。"
    return {
        "benchmark": "510300",
        "stock_vs_benchmark": vs_benchmark,
        "stock_vs_sector": vs_sector,
        "conclusion": conclusion,
    }


def _peer_comparison(facts: dict[str, Any], market: dict[str, Any], relative: dict[str, Any]) -> dict[str, Any]:
    peers = market.get("peers") if isinstance(market.get("peers"), list) else []
    rows = []
    for peer in peers:
        day_pct = _num(peer.get("day_pct"))
        five_day_pct = _num(peer.get("five_day_pct"))
        twenty_day_pct = _num(peer.get("twenty_day_pct"))
        rows.append(
            {
                "name": str(peer.get("name") or ""),
                "code": str(peer.get("code") or ""),
                "day_pct": day_pct,
                "five_day_pct": five_day_pct,
                "twenty_day_pct": twenty_day_pct,
                "advantage": _peer_advantage(day_pct, five_day_pct, twenty_day_pct),
                "weakness": _peer_weakness(day_pct, five_day_pct, twenty_day_pct),
            }
        )
    rows = sorted(rows, key=lambda item: (item["day_pct"], item["five_day_pct"], item["twenty_day_pct"]), reverse=True)
    leader = rows[0]["name"] if rows else "unknown"
    stock_name = str(facts.get("stock_name") or facts.get("stock_code") or "目标公司")
    concept = _concept_from_market(market)
    if not rows:
        conclusion = f"{stock_name}同概念样本不足，暂不能判断龙头、跟风或补涨。"
    elif relative.get("stock_vs_sector") == "strong":
        conclusion = f"{stock_name}买入日强于板块，可按强势核心或主动走强观察，但仍需和{leader}等龙头持续比较。"
    elif relative.get("stock_vs_sector") == "weak":
        conclusion = f"{stock_name}买入日弱于板块，更像跟风或补涨，追高风险高于板块核心。"
    else:
        conclusion = f"{stock_name}相对板块优势不明显，暂按同概念中位跟随品种处理。"
    return {"concept": concept, "leader": leader, "rows": rows, "conclusion": conclusion}


def _execution_notes(
    buy_points: list[dict[str, Any]],
    sell_points: list[dict[str, Any]],
    peer: dict[str, Any],
    relative: dict[str, Any],
) -> dict[str, Any]:
    buy = buy_points[0] if buy_points else {}
    buy_verdict = _buy_verdict(buy)
    sell_verdict = _sell_verdict(sell_points)
    main_lesson = _main_lesson(buy_verdict, sell_verdict, peer, relative)
    return {"buy_verdict": buy_verdict, "sell_verdict": sell_verdict, "main_lesson": main_lesson}


def _buy_judgment(stock_pct: float, benchmark_pct: float, sector_pct: float, position: str) -> tuple[str, str]:
    excess_benchmark = stock_pct - benchmark_pct
    excess_sector = stock_pct - sector_pct
    if position == "unknown":
        return "unknown", "缺少日内高低点，无法判断买在高位、中位或低位。"
    if excess_benchmark > 1 and excess_sector > 1 and position != "high":
        return "买点质量较好", "买入日个股强于沪深300ETF和板块，且没有买在日内高位。"
    if excess_benchmark < -1 or excess_sector < -1:
        return "买点质量偏弱", "买入日个股相对大盘或板块偏弱，更多是试错而非强势确认。"
    if position == "high":
        return "买点质量一般", "相对强弱没有明显优势，且成交价接近日内高位。"
    return "买点质量中性", "买入日相对强弱接近大盘/板块，需要后续走势确认。"


def _sell_judgment(stock_pct: float, benchmark_pct: float, sector_pct: float, position: str, sold_flying: str) -> tuple[str, str]:
    excess_benchmark = stock_pct - benchmark_pct
    excess_sector = stock_pct - sector_pct
    turned_weak = stock_pct < 0 or excess_benchmark < -1 or excess_sector < -1
    if sold_flying == "yes":
        if turned_weak:
            return "卖点有转弱依据，但存在卖飞", "卖出日已有转弱信号，不过卖出后仍出现明显更高价格，说明减仓节奏偏早。"
        return "未卖在转弱，卖点偏早，存在卖飞", "卖出日个股仍强于沪深300ETF和板块，后续又出现明显更高价格，说明不是卖在转弱。"
    if sold_flying == "no" and turned_weak:
        return "卖点较好，卖在转弱", "卖出日个股转弱或弱于大盘/板块，执行纪律较好。"
    if turned_weak:
        return "卖点有纪律", "卖出日已有转弱迹象，但后续空间不足时仍需复盘卖出价格。"
    if position == "low":
        return "卖点偏弱", "卖出价接近日内低位，容易把正常波动卖成被动止损。"
    return "卖点中性", "卖出日转弱证据不充分，是否卖飞需要结合后续高点确认。"


def _main_lesson(
    buy_verdict: str,
    sell_verdict: str,
    peer: dict[str, Any],
    relative: dict[str, Any],
) -> str:
    if buy_verdict == "poor":
        return f"核心复盘是买点确认不足：{relative.get('conclusion', '相对强弱未知')} {peer.get('conclusion', '')}"
    if sell_verdict == "poor":
        return f"核心复盘是卖点执行偏弱：先确认是否转弱，再决定减仓，避免在日内低位被动卖出。{peer.get('conclusion', '')}"
    return f"核心复盘是把买点相对强弱和同概念位置分开看：{relative.get('conclusion', '')} {peer.get('conclusion', '')}"


def _intraday_position(price: float, stock: dict[str, Any]) -> str:
    high = _num(stock.get("high"))
    low = _num(stock.get("low"))
    if price <= 0 or high <= low:
        return "unknown"
    pct = (price - low) / (high - low)
    if pct <= 0.33:
        return "low"
    if pct >= 0.67:
        return "high"
    return "middle"


def _sold_flying(trade: dict[str, Any], stock_quotes: dict[str, dict[str, Any]]) -> str:
    sell_date = _date(str(trade.get("date") or ""))
    price = _num(trade.get("price"))
    if sell_date is None or price <= 0:
        return "unknown"
    future_highs = []
    for key, quote in stock_quotes.items():
        current = _date(key)
        if current and current > sell_date:
            future_highs.append(_num(quote.get("high")))
    if not future_highs:
        return "unknown"
    return "yes" if max(future_highs) >= price * 1.03 else "no"


def _buy_verdict(point: dict[str, Any]) -> str:
    if not point:
        return "unknown"
    excess_benchmark = _num(point.get("excess_vs_hs300_pct"))
    excess_sector = _num(point.get("excess_vs_sector_pct"))
    position = str(point.get("intraday_position") or "unknown")
    if position == "unknown":
        return "unknown"
    if excess_benchmark > 1 and excess_sector > 1 and position != "high":
        return "good"
    if excess_benchmark < -1 or excess_sector < -1 or position == "high":
        return "poor"
    return "average"


def _sell_verdict(points: list[dict[str, Any]]) -> str:
    if not points:
        return "unknown"
    text = " ".join(str(point.get("judgment") or "") + " " + str(point.get("reason") or "") for point in points)
    if "卖飞" in text or "偏弱" in text:
        return "poor"
    if "较好" in text or "转弱" in text:
        return "good"
    return "average"


def _strength_label(excess: float) -> str:
    if excess >= 1:
        return "strong"
    if excess <= -1:
        return "weak"
    return "similar"


def _peer_advantage(day_pct: float, five_day_pct: float, twenty_day_pct: float) -> str:
    if day_pct > 5 or five_day_pct > 8:
        return "短线涨幅领先，资金关注度较高"
    if twenty_day_pct > 10:
        return "近20日趋势较强"
    return "暂无明显领先优势"


def _peer_weakness(day_pct: float, five_day_pct: float, twenty_day_pct: float) -> str:
    if day_pct < 0 and five_day_pct < 0:
        return "短线转弱，承接不足"
    if twenty_day_pct < -5:
        return "中期走势偏弱"
    return "主要风险是涨幅持续性待验证"


def _concept_from_market(market: dict[str, Any]) -> str:
    rows = market.get("sector_quotes") if isinstance(market.get("sector_quotes"), list) else []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if name:
            return name
    return "unknown"


def _by_date(value: Any) -> dict[str, dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    result = {}
    for item in rows:
        if isinstance(item, dict) and item.get("date"):
            result[str(item.get("date"))] = item
    return result


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except Exception:
        return None


def _side(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("side") or "").strip().lower()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default
