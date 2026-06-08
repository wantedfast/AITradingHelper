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
        _sell_point_payload(trade, stock_quotes, benchmark_quotes, sector_quotes)
        for trade in trades
        if _side(trade) == "sell"
    ]
    relative = _relative_strength(buy_points)
    peer = _peer_comparison(facts, market, relative)
    notes = _execution_notes(buy_points, sell_points, peer, relative)
    advice = _execution_advice(buy_points, sell_points, relative, peer, notes)
    recommendations = _peer_recommendations(peer)
    return {
        "trade_timing": {"buy_points": buy_points, "sell_points": sell_points},
        "relative_strength": relative,
        "peer_comparison": peer,
        "trade_execution_notes": notes,
        "execution_advice": advice,
        "peer_recommendations": recommendations,
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


def _relative_strength(buy_points: list[dict[str, Any]]) -> dict[str, Any]:
    anchor = buy_points[0] if buy_points else {}
    vs_benchmark = _strength_label(_num(anchor.get("excess_vs_hs300_pct")), has_point=bool(anchor))
    vs_sector = _strength_label(_num(anchor.get("excess_vs_sector_pct")), has_point=bool(anchor))
    if vs_benchmark == "strong" and vs_sector == "strong":
        conclusion = "买入日个股同时强于沪深300ETF和板块，收益更偏个股主动强势。"
    elif vs_sector == "weak":
        conclusion = "买入日个股弱于板块，更像板块带动下的跟随或补涨。"
    elif vs_benchmark == "strong":
        conclusion = "买入日强于大盘但相对板块优势有限，收益来源偏题材或板块带动。"
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


def _execution_advice(
    buy_points: list[dict[str, Any]],
    sell_points: list[dict[str, Any]],
    relative: dict[str, Any],
    peer: dict[str, Any],
    notes: dict[str, Any],
) -> dict[str, Any]:
    buy = buy_points[0] if buy_points else {}
    sell = sell_points[0] if sell_points else {}
    buy_issue = _advice_buy_issue(buy, relative, peer)
    sell_issue = _advice_sell_issue(sell)
    return {
        "summary": _advice_summary(notes, buy_issue, sell_issue),
        "buy_issue": buy_issue,
        "sell_issue": sell_issue,
        "next_time_rules": _next_time_rules(notes, peer),
        "confirmation_signals": _confirmation_signals(relative, peer),
    }


def _advice_summary(notes: dict[str, Any], buy_issue: str, sell_issue: str) -> str:
    buy_verdict = str(notes.get("buy_verdict") or "unknown")
    sell_verdict = str(notes.get("sell_verdict") or "unknown")
    if buy_verdict == "poor" and sell_verdict == "poor":
        return "这笔交易的核心问题是买点确认不足，卖点偏早或执行质量偏弱。"
    if buy_verdict == "poor":
        return "这笔交易的核心问题是买点确认不足，后续应先确认个股强于大盘和板块。"
    if sell_verdict == "poor":
        return "这笔交易的核心问题是卖点处理偏弱，后续应先确认转弱再减仓。"
    if buy_verdict == "unknown" or sell_verdict == "unknown":
        return f"这笔交易仍有数据不足项，先按保守复盘处理：{buy_issue} {sell_issue}"
    return "这笔交易的买卖点质量中性，下一次重点提高确认信号和分批执行纪律。"


def _advice_buy_issue(buy: dict[str, Any], relative: dict[str, Any], peer: dict[str, Any]) -> str:
    if not buy:
        return "缺少买点行情或交易事实，暂不能评价买点质量。"
    judgment = str(buy.get("judgment") or "unknown")
    reason = str(buy.get("reason") or "")
    relative_text = str(relative.get("conclusion") or "")
    peer_text = str(peer.get("conclusion") or "")
    if judgment == "unknown":
        return reason or "买点数据不足，暂不能判断是否强于沪深300ETF和板块。"
    return " ".join(item for item in [reason, relative_text, peer_text] if item).strip() or judgment


def _advice_sell_issue(sell: dict[str, Any]) -> str:
    if not sell:
        return "缺少卖出记录或卖点行情，暂不能评价卖点质量。"
    judgment = str(sell.get("judgment") or "unknown")
    reason = str(sell.get("reason") or "")
    if judgment == "unknown":
        return reason or "卖点数据不足，暂不能判断是否卖在转弱或是否卖飞。"
    return reason or judgment


def _next_time_rules(notes: dict[str, Any], peer: dict[str, Any]) -> list[str]:
    rows = []
    if notes.get("buy_verdict") in {"poor", "unknown"}:
        rows.append("买入前先确认个股至少不弱于沪深300ETF和所属板块。")
        rows.append("如果同概念核心品种更强，目标股只按跟随或补涨处理，降低仓位和预期。")
    else:
        rows.append("买点成立时也要分批执行，避免一次性追在日内高位。")
    if notes.get("sell_verdict") in {"poor", "unknown"}:
        rows.append("卖出前先确认是否转弱：弱于大盘、弱于板块、跌破日内关键价位至少满足一项。")
        rows.append("个股仍强于板块时，优先用分批止盈或移动止盈，减少卖飞。")
    else:
        rows.append("卖点执行后记录规则触发原因，复盘是否按计划完成。")
    if peer.get("rows"):
        rows.append("每天复核同概念前三名强度，目标股弱于核心品种时不按龙头打法处理。")
    return rows


def _confirmation_signals(relative: dict[str, Any], peer: dict[str, Any]) -> list[str]:
    signals = [
        "买入日个股涨跌幅强于沪深300ETF。",
        "买入日个股涨跌幅强于所属板块或概念。",
        "买入价不处在日内高位，或有明确放量承接。",
    ]
    if peer.get("rows"):
        signals.append("同概念横向比较中，目标股强度至少进入前排而不是明显落后。")
    if relative.get("stock_vs_sector") == "weak":
        signals.append("若个股弱于板块，只能按试错仓位或等待二次确认。")
    return signals


def _peer_recommendations(peer: dict[str, Any]) -> dict[str, Any]:
    rows = peer.get("rows") if isinstance(peer.get("rows"), list) else []
    basis = "从壁垒、利润流向和相对表现综合筛选，不等于投资建议。若缺少真实壁垒数据，则使用行情强度和产业链位置 proxy。"
    if not rows:
        return {"basis": basis, "items": []}
    ranked = sorted((_recommendation_candidate(row) for row in rows), key=lambda item: item["_score"], reverse=True)
    items = []
    for rank, item in enumerate(ranked[:3], start=1):
        items.append(
            {
                "rank": rank,
                "name": item["name"],
                "code": item["code"],
                "why_strong": item["why_strong"],
                "moat_reason": item["moat_reason"],
                "profit_flow_reason": item["profit_flow_reason"],
                "risk_note": item["risk_note"],
            }
        )
    return {"basis": basis, "items": items}


def _recommendation_candidate(row: dict[str, Any]) -> dict[str, Any]:
    name = str(row.get("name") or "")
    code = str(row.get("code") or "")
    day_pct = _num(row.get("day_pct"))
    five_day_pct = _num(row.get("five_day_pct"))
    twenty_day_pct = _num(row.get("twenty_day_pct"))
    proxy = _peer_proxy(name, code)
    score = day_pct * 0.2 + five_day_pct * 0.35 + twenty_day_pct * 0.25 + proxy["score"]
    return {
        "_score": score,
        "name": name,
        "code": code,
        "why_strong": _why_peer_strong(proxy, day_pct, five_day_pct, twenty_day_pct),
        "moat_reason": proxy["moat_reason"],
        "profit_flow_reason": proxy["profit_flow_reason"],
        "risk_note": _peer_recommendation_risk(row, day_pct, five_day_pct, twenty_day_pct),
    }


def _peer_proxy(name: str, code: str) -> dict[str, Any]:
    key = code or name
    proxies = {
        "600487": {
            "score": 28,
            "moat_reason": "规模、客户和光纤光缆行业位置 proxy 更强。",
            "profit_flow_reason": "更接近光纤光缆利润池核心，更可能承接光通信景气修复的利润流。",
        },
        "600522": {
            "score": 26,
            "moat_reason": "海缆、通信网络和客户资源 proxy 较强，行业位置更靠前。",
            "profit_flow_reason": "更可能承接通信基础设施和光通信链条修复带来的利润流。",
        },
        "600498": {
            "score": 22,
            "moat_reason": "通信设备和运营商客户 proxy 较强，产业链位置偏核心。",
            "profit_flow_reason": "更可能受益于通信网络升级和光通信需求改善。",
        },
        "600105": {
            "score": 15,
            "moat_reason": "光纤光缆相关业务具备产业链相关性，但行业位置 proxy 弱于核心龙头。",
            "profit_flow_reason": "可承接部分板块修复利润流，但持续性需要行情和订单继续验证。",
        },
        "000070": {
            "score": 12,
            "moat_reason": "通信相关业务具备题材相关性，但规模和行业位置 proxy 偏弱。",
            "profit_flow_reason": "更偏主题弹性承接，利润流确定性弱于核心光纤光缆标的。",
        },
    }
    if key in proxies:
        return proxies[key]
    return {
        "score": 10,
        "moat_reason": "缺少真实壁垒数据，暂用行情强度和产业链相关性 proxy。",
        "profit_flow_reason": "可能承接同概念景气修复的部分利润流，但需要进一步验证主营相关性。",
    }


def _why_peer_strong(proxy: dict[str, Any], day_pct: float, five_day_pct: float, twenty_day_pct: float) -> str:
    if five_day_pct >= 8 and twenty_day_pct >= 8:
        return "产业链位置 proxy 较强，短中期强度同时领先。"
    if five_day_pct >= 8:
        return "产业链位置 proxy 较强，近5日资金强度领先。"
    if day_pct >= 5:
        return "产业链位置 proxy 较强，买入日相对表现突出。"
    return "产业链位置 proxy 较强，但行情强度仍需继续确认。"


def _peer_recommendation_risk(row: dict[str, Any], day_pct: float, five_day_pct: float, twenty_day_pct: float) -> str:
    weakness = str(row.get("weakness") or "")
    if twenty_day_pct < -5:
        return "中期趋势仍偏弱，短线反弹持续性需要验证。"
    if day_pct > 8 or five_day_pct > 20:
        return "短期涨幅已经较高，追高风险和持续性仍需验证。"
    return weakness or "推荐仅基于行情强度和产业链位置 proxy，不等于投资建议。"


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
    return "买点质量中性", "买入日相对强弱接近大盘或板块，需要后续走势确认。"


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


def _strength_label(excess: float, *, has_point: bool = True) -> str:
    if not has_point:
        return "unknown"
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
