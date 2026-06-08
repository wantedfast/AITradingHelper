from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from html import escape
from pathlib import Path
import shutil

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .data_provider import MarketDataProvider
from .industry_agent import get_workbench_profile_data
from .industry_profiles import IndustryProfile, get_profile
from .io import read_trade_file
from .schema import Trade
from .sector_strength import build_sector_signal
from .trade_rounds import TradeRound, split_trade_rounds
from .trade_execution_chain import build_trade_execution_chain
from .presenter_agent import build_presenter_data
from .workbench_agents import research_model_metadata
from .workbench_report_renderer import render_workbench_report
from .workbench_composer import write_workbench_json
from .workbench_schema import merge_default_workbench


@dataclass(frozen=True)
class VisualReportResult:
    output: Path
    title: str
    rating: str
    score: int
    trade_type: str
    requested_research_model_tier: str = "standard"
    research_model_tier: str = "standard"
    wang_model: str = "gpt-4.1"
    public_equity_model: str = "gpt-4.1"


def build_all_reports(
    trades_path: str | Path,
    output_dir: str | Path,
    cache_db: str | Path = "work/real_trade_review_cache.sqlite",
    benchmark_symbol: str = "sh000300",
    research_model_tier: str = "standard",
) -> list[VisualReportResult]:
    trades = read_trade_file(trades_path)
    rounds = split_trade_rounds(trades)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[VisualReportResult] = []
    for trade_round in rounds:
        if not any(trade.side == "buy" for trade in trade_round.trades):
            continue
        slug = f"{trade_round.code}_{trade_round.start_date:%Y%m%d}_r{trade_round.round_id}.html"
        result = build_round_html(
            trade_round=trade_round,
            output=output_dir / slug,
            cache_db=cache_db,
            benchmark_symbol=benchmark_symbol,
            research_model_tier=research_model_tier,
        )
        results.append(result)
    _write_first_report_json_aliases(output_dir, results)
    _write_index(output_dir / "index.html", results)
    return results


def _write_first_report_json_aliases(output_dir: Path, results: list[VisualReportResult]) -> None:
    if not results:
        return
    _copy_first_json_alias(results[0].output.with_suffix(".presenter.json"), output_dir / "research_presenter_data.json")
    _copy_first_json_alias(results[0].output.with_suffix(".workbench.json"), output_dir / "research_workbench_data.json")
    _copy_first_json_alias(results[0].output.with_suffix(".trade_execution.json"), output_dir / "trade_execution_analysis.json")
    _copy_first_json_alias(results[0].output.with_suffix(".execution_data_context.json"), output_dir / "execution_data_context.json")
    _copy_first_json_alias(results[0].output.with_suffix(".trade_execution_agent_output.json"), output_dir / "trade_execution_agent_output.json")


def _copy_first_json_alias(source: Path, target: Path) -> None:
    if source.exists() and source.is_file():
        shutil.copyfile(source, target)


def build_single_stock_html(
    trades_path: str | Path,
    code: str,
    output: str | Path,
    cache_db: str | Path = "work/real_trade_review_cache.sqlite",
    benchmark_symbol: str = "sh000300",
    sector_symbol: str | None = None,
    trade_date: str | None = None,
) -> Path:
    trades = [trade for trade in read_trade_file(trades_path) if trade.code == code]
    if not trades:
        raise ValueError(f"No trades found for stock code {code}")
    rounds = split_trade_rounds(trades)
    selected = _select_round(rounds, trade_date)
    profile = get_profile(code, selected.name)
    if sector_symbol:
        profile = _with_sector(profile, sector_symbol)
    result = build_round_html(selected, output, cache_db, benchmark_symbol, profile)
    return result.output


def build_round_html(
    trade_round: TradeRound,
    output: str | Path,
    cache_db: str | Path,
    benchmark_symbol: str = "sh000300",
    profile: IndustryProfile | None = None,
    research_model_tier: str = "standard",
) -> VisualReportResult:
    output = Path(output)
    profile = profile or get_profile(trade_round.code, trade_round.name)
    start = trade_round.start_date - timedelta(days=25)
    end = max(trade_round.end_date + timedelta(days=15), start + timedelta(days=45))
    provider = MarketDataProvider(cache_db=cache_db, adjust="qfq")
    stock = _with_ma(provider.stock_daily(trade_round.code, start, end))
    if stock.empty:
        raise ValueError(f"No stock daily data found for {trade_round.code}")
    sh_index = _relative_close(provider.index_daily("sh000001", start, end))
    benchmark = _relative_close(provider.index_daily(benchmark_symbol, start, end))
    growth_index = _relative_close(provider.index_daily("sz399006", start, end))
    sector = _relative_close(_sector_daily(provider, profile.sector_symbol, start, end))

    trade_frame = pd.DataFrame([trade.__dict__ for trade in trade_round.trades])
    trade_frame["trade_date"] = pd.to_datetime(trade_frame["trade_date"])
    analysis = _analyze(trade_round, profile, stock, sector, benchmark)
    _write_trade_execution_artifacts(output, provider, profile, trade_round)
    workbench_data = _write_round_workbench_data(output, profile, analysis, trade_round, stock, sector, benchmark, research_model_tier)
    presenter_data = build_presenter_data(
        workbench=workbench_data,
        profile=profile,
        analysis=analysis,
        trade_frame=trade_frame,
    )
    write_workbench_json(Path(output).with_suffix(".presenter.json"), presenter_data)
    market_html = _premium_market_context_html(stock, sh_index, benchmark, growth_index, sector, analysis)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_workbench_report(presenter_data), encoding="utf-8")
    research_model = workbench_data.get("research_model") if isinstance(workbench_data, dict) else {}
    if not isinstance(research_model, dict):
        research_model = research_model_metadata("standard")
    requested_research_model = workbench_data.get("requested_research_model") if isinstance(workbench_data, dict) else {}
    if not isinstance(requested_research_model, dict):
        requested_research_model = research_model
    return VisualReportResult(
        output=output,
        title=f"{profile.name} {trade_round.code} {trade_round.start_date:%Y-%m-%d}",
        rating=str(analysis["rating"]),
        score=int(analysis["score"]),
        trade_type=str(analysis["trade_type"]),
        requested_research_model_tier=str(requested_research_model.get("tier") or research_model.get("tier") or "standard"),
        research_model_tier=str(research_model.get("tier") or "standard"),
        wang_model=str(research_model.get("wang_model") or research_model.get("model") or "gpt-4.1"),
        public_equity_model=str(research_model.get("public_equity_model") or research_model.get("model") or "gpt-4.1"),
    )


def _write_trade_execution_artifacts(
    output: Path,
    provider: MarketDataProvider,
    profile: IndustryProfile,
    trade_round: TradeRound,
) -> dict:
    try:
        return build_trade_execution_chain(provider=provider, profile=profile, trade_round=trade_round, output=output)
    except Exception as exc:
        fallback = {
            "trade_timing": {"buy_points": [], "sell_points": []},
            "relative_strength": {
                "benchmark": "510300",
                "stock_vs_benchmark": "unknown",
                "stock_vs_sector": "unknown",
                "conclusion": "执行分析链路失败，暂不能判断相对强弱。",
            },
            "peer_comparison": {"concept": "unknown", "leader": "unknown", "rows": [], "conclusion": "执行分析链路失败，暂不能判断同概念位置。"},
            "peer_recommendations": {
                "basis": "执行分析链路失败，暂不能从壁垒、利润流向和相对表现筛选同行推荐。",
                "items": [],
            },
            "trade_execution_notes": {"buy_verdict": "unknown", "sell_verdict": "unknown", "main_lesson": "执行分析链路失败，请查看 data_source_status.errors。"},
            "execution_advice": {
                "summary": "执行分析链路失败，暂不能给出买卖点评价。",
                "buy_issue": "unknown",
                "sell_issue": "unknown",
                "next_time_rules": [],
                "confirmation_signals": [],
            },
            "data_source_status": {
                "stock_quote": "missing",
                "stock_quote_source": "missing",
                "benchmark_quote": "missing",
                "benchmark_quote_source": "missing",
                "sector_quote": "missing",
                "sector_quote_source": "missing",
                "peer_quotes": "missing",
                "peer_quote_source": "missing",
                "fallback_used": [],
                "errors": [f"trade_execution_chain_failed: {exc}"],
            },
        }
        write_workbench_json(output.with_suffix(".trade_execution.json"), fallback)
        return fallback


def _write_round_workbench_data(
    output: str | Path,
    profile: IndustryProfile,
    analysis: dict,
    trade_round: TradeRound,
    stock: pd.DataFrame,
    sector: pd.DataFrame,
    benchmark: pd.DataFrame,
    research_model_tier: str = "standard",
) -> dict:
    output = Path(output)
    agent_errors: list[str] = []
    requested_research_model = research_model_metadata(research_model_tier)
    try:
        data = get_workbench_profile_data(
            profile.code,
            profile.name,
            trade_round=trade_round,
            analysis=analysis,
            stock=stock,
            sector=sector,
            benchmark=benchmark,
            research_model_tier=research_model_tier,
        )
    except Exception as exc:
        message = f"workbench agents failed for {profile.code}: {exc}"
        print(f"[warn] {message}")
        agent_errors.append(message)
        data = {}
    if not isinstance(data, dict):
        agent_errors.append(f"workbench agents returned non-object data for {profile.code}")
        data = {}
    if agent_errors:
        data["agent_errors"] = agent_errors
    if not data.get("requested_research_model"):
        data["requested_research_model"] = requested_research_model
    if not data.get("research_model"):
        fallback_tier = "standard" if agent_errors else research_model_tier
        data["research_model"] = research_model_metadata(fallback_tier)
    data = merge_default_workbench(data, code=profile.code, name=profile.name)
    trade_review = data.setdefault("trade_review", {})
    optimal = analysis.get("optimal") or {}
    trade_review.update(
        {
            "trade_return_pct": float(analysis.get("return", 0.0) or 0.0),
            "trade_score": int(analysis.get("score", 0) or 0),
            "buy_verdict": str(optimal.get("buy_verdict") or optimal.get("buy_label") or ""),
            "sell_verdict": str(optimal.get("sell_verdict") or optimal.get("sell_label") or ""),
            "execution_lesson": str(optimal.get("sell_reason") or analysis.get("headline") or ""),
        }
    )
    write_workbench_json(output.parent / "research_workbench_data.json", data)
    write_workbench_json(output.with_suffix(".workbench.json"), data)
    return data


def _select_round(rounds: list[TradeRound], trade_date: str | None) -> TradeRound:
    if not rounds:
        raise ValueError("No trade rounds found")
    if trade_date is None:
        return rounds[0]
    target = pd.to_datetime(trade_date).date()
    for item in rounds:
        if item.start_date == target or any(trade.trade_date == target for trade in item.trades):
            return item
    raise ValueError(f"No trade round found for date {trade_date}")


def _with_sector(profile: IndustryProfile, sector_symbol: str) -> IndustryProfile:
    return IndustryProfile(
        code=profile.code,
        name=profile.name,
        theme=profile.theme,
        core_driver=profile.core_driver,
        node=profile.node,
        sector_symbol=sector_symbol,
        chain_nodes=profile.chain_nodes,
        barriers=profile.barriers,
        profit_levers=profile.profit_levers,
        peers=profile.peers,
        industry_judgment=profile.industry_judgment,
        company_judgment=profile.company_judgment,
        financial_validation=profile.financial_validation,
        expectation_gap=profile.expectation_gap,
        valuation_odds=profile.valuation_odds,
        catalysts=profile.catalysts,
        disconfirming_signals=profile.disconfirming_signals,
        position_sizing=profile.position_sizing,
        one_sentence_thesis=profile.one_sentence_thesis,
        rerating_anchor=profile.rerating_anchor,
        market_position=profile.market_position,
        peer_ranking=profile.peer_ranking,
        best_expression=profile.best_expression,
        trading_implication=profile.trading_implication,
        evidence=profile.evidence,
        wang_investor_report=profile.wang_investor_report,
        public_equity_report=profile.public_equity_report,
    )


def _with_ma(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.sort_values("trade_date").copy()
    frame["ma5"] = frame["close"].rolling(5).mean()
    frame["ma10"] = frame["close"].rolling(10).mean()
    return frame


def _relative_close(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.sort_values("trade_date").copy()
    base = frame["close"].iloc[0]
    frame["relative"] = (frame["close"] / base - 1) * 100
    return frame


def _sector_daily(provider: MarketDataProvider, symbol: str, start, end) -> pd.DataFrame:
    symbol = str(symbol or "").strip()
    if symbol.startswith(("sh", "sz")):
        return provider.index_daily(symbol, start, end)
    return provider.stock_daily(symbol or "sh000300", start, end)


def _analyze(trade_round: TradeRound, profile: IndustryProfile, stock: pd.DataFrame, sector: pd.DataFrame, benchmark: pd.DataFrame) -> dict:
    trades = trade_round.trades
    buy_amount = sum(trade.amount for trade in trades if trade.side == "buy")
    buy_qty = sum(trade.quantity for trade in trades if trade.side == "buy")
    sell_amount = sum(trade.amount for trade in trades if trade.side == "sell")
    sell_qty = sum(trade.quantity for trade in trades if trade.side == "sell")
    net_qty = buy_qty - sell_qty
    avg_buy = buy_amount / buy_qty if buy_qty else 0
    avg_sell = sell_amount / sell_qty if sell_qty else 0
    first_day = trade_round.start_date
    last_day = trade_round.end_date
    day_row = stock[stock["trade_date"] >= first_day].iloc[0]
    last_row = stock[stock["trade_date"] >= last_day].iloc[-1]
    future = stock[stock["trade_date"] > first_day]
    last_close = float(last_row["close"])
    marked_value = sell_amount + max(net_qty, 0) * last_close
    profit = marked_value - buy_amount
    total_return = (marked_value / buy_amount - 1) * 100 if buy_amount else 0
    max_gain = (future["high"].max() / day_row["close"] - 1) * 100 if not future.empty else 0
    max_drawdown = (future["low"].min() / day_row["close"] - 1) * 100 if not future.empty else 0
    sector_day = _day_snapshot(sector, first_day)
    benchmark_day = _day_snapshot(benchmark, first_day)
    stock_day = _day_snapshot(stock, first_day)
    is_closed = trade_round.is_closed
    sector_signal = build_sector_signal(profile, sector_day, benchmark_day).to_dict()
    scenario = _classify_trade(stock_day, sector_day, benchmark_day, is_closed, max_gain, max_drawdown, sector_signal)
    optimal = _optimal_decision(trade_round, stock, stock_day, sector_day, benchmark_day, avg_buy, avg_sell, buy_qty, sell_qty)
    scores = dict(scenario["scores"])
    if optimal["sell_score"] is not None:
        scores["sell"] = optimal["sell_score"]
    score = round(sum(scores.values()) / len(scores))
    return {
        "code": trade_round.code,
        "name": profile.name,
        "first_day": first_day,
        "last_day": last_day,
        "avg_buy": avg_buy,
        "avg_sell": avg_sell,
        "buy_qty": buy_qty,
        "sell_qty": sell_qty,
        "net_qty": net_qty,
        "is_closed": is_closed,
        "buy_amount": buy_amount,
        "sell_amount": sell_amount,
        "last_close": last_close,
        "profit": profit,
        "return": total_return,
        "day_pct": stock_day["pct"],
        "day_close": stock_day["close"],
        "sector_pct": sector_day["pct"],
        "benchmark_pct": benchmark_day["pct"],
        "sector_signal": sector_signal,
        "max_gain": max_gain,
        "max_drawdown": max_drawdown,
        "score": score,
        "optimal": optimal,
        **scores,
        **scenario,
    }


def _optimal_decision(
    trade_round: TradeRound,
    stock: pd.DataFrame,
    stock_day: dict[str, float],
    sector_day: dict[str, float],
    benchmark_day: dict[str, float],
    avg_buy: float,
    avg_sell: float,
    buy_qty: float,
    sell_qty: float,
) -> dict:
    idx = _first_index_on_or_after(stock, trade_round.start_date)
    if idx is None or not buy_qty or avg_buy <= 0:
        return {
            "buy_verdict": "数据不足，无法判断买点。",
            "buy_reason": "没有找到交易日附近的日K或买入均价异常。",
            "sell_verdict": "数据不足，无法给出卖点。",
            "sell_reason": "缺少后续K线。",
            "peak_date": None,
            "peak_price": 0.0,
            "peak_return": 0.0,
            "rule_sell_date": None,
            "rule_sell_price": 0.0,
            "rule_sell_return": 0.0,
            "actual_sell_return": None,
            "sell_score": None,
        }

    horizon = stock.iloc[idx : min(len(stock), idx + 16)].copy()
    peak_idx = horizon["high"].idxmax()
    peak_row = stock.loc[peak_idx]
    peak_price = float(peak_row["high"])
    peak_return = (peak_price / avg_buy - 1) * 100

    buy_points = []
    if stock_day["pct"] > benchmark_day["pct"] + 1:
        buy_points.append("个股强于沪深300")
    if sector_day["pct"] > benchmark_day["pct"]:
        buy_points.append("板块强于指数")
    if stock_day["close"] >= stock_day.get("ma5", 0):
        buy_points.append("收盘站在5日线之上")
    if stock_day["vol_ratio"] >= 1.2:
        buy_points.append("量能较5日均量放大")

    if stock_day["pct"] >= 8 and sector_day["pct"] >= 2:
        buy_verdict = "买点偏优：主线或强势股确认日，允许右侧跟随。"
    elif stock_day["pct"] < benchmark_day["pct"] or sector_day["pct"] < 0:
        buy_verdict = "买点偏试错：产业逻辑可以看，但当日市场/板块确认不足。"
    else:
        buy_verdict = "买点中性：可以小仓试，但需要后续强度确认。"
    buy_reason = "；".join(buy_points) if buy_points else "当日没有明显的强于指数、强于板块或量价确认信号。"

    rule_sell = _find_rule_sell(stock, idx, avg_buy)
    actual_sell_return = (avg_sell / avg_buy - 1) * 100 if sell_qty and avg_sell else None
    actual_sell_date = max((trade.trade_date for trade in trade_round.trades if trade.side == "sell"), default=None)

    if rule_sell is None:
        if sell_qty:
            sell_verdict = "实际卖出偏早：规则卖点尚未触发，趋势仍应继续跟踪。"
            sell_reason = "后续窗口内没有出现盈利后跌破5日线、跌破前低或放量长阴等明确纪律卖点；更优做法是继续持有，用5日线和前一日低点移动止盈。"
            sell_score = 55
        else:
            sell_verdict = "当前不急卖：暂未触发纪律卖点。"
            sell_reason = "继续观察5日线、前一日低点和板块强度；若出现盈利后跌破5日线或板块退潮，再执行减仓。"
            sell_score = None
        rule_sell_date = None
        rule_sell_price = 0.0
        rule_sell_return = 0.0
    else:
        rule_sell_date = rule_sell["date"]
        rule_sell_price = rule_sell["price"]
        rule_sell_return = (rule_sell_price / avg_buy - 1) * 100
        if not sell_qty:
            sell_verdict = "还没卖：建议把纪律卖点写进计划。"
            sell_reason = f"系统卖点为 {rule_sell_date:%Y-%m-%d}，触发原因：{rule_sell['reason']}。"
            sell_score = None
        elif actual_sell_date and actual_sell_date < rule_sell_date:
            sell_verdict = "实际卖出偏早：更优卖法是等纪律卖点触发。"
            sell_reason = f"系统卖点为 {rule_sell_date:%Y-%m-%d}，价格约 {rule_sell_price:.2f}，原因：{rule_sell['reason']}。你的平均卖出收益约 {actual_sell_return:.1f}%，规则卖点收益约 {rule_sell_return:.1f}%。"
            sell_score = _sell_score(actual_sell_return, rule_sell_return)
        elif actual_sell_return is not None and actual_sell_return >= rule_sell_return * 0.9:
            sell_verdict = "实际卖出接近最优规则卖点。"
            sell_reason = f"系统卖点为 {rule_sell_date:%Y-%m-%d}，你的卖出收益与规则卖点差距不大，属于执行合格。"
            sell_score = _sell_score(actual_sell_return, rule_sell_return)
        else:
            sell_verdict = "实际卖出偏弱：价格或节奏低于规则卖点。"
            sell_reason = f"系统卖点为 {rule_sell_date:%Y-%m-%d}，触发原因：{rule_sell['reason']}；实际卖出需要复盘是否被情绪影响。"
            sell_score = _sell_score(actual_sell_return, rule_sell_return)

    return {
        "buy_verdict": buy_verdict,
        "buy_reason": buy_reason,
        "sell_verdict": sell_verdict,
        "sell_reason": sell_reason,
        "peak_date": pd.to_datetime(peak_row["trade_date"]).date(),
        "peak_price": peak_price,
        "peak_return": peak_return,
        "rule_sell_date": rule_sell_date,
        "rule_sell_price": rule_sell_price,
        "rule_sell_return": rule_sell_return,
        "actual_sell_return": actual_sell_return,
        "sell_score": sell_score,
    }


def _find_rule_sell(stock: pd.DataFrame, start_idx: int, avg_buy: float) -> dict | None:
    for idx in range(start_idx + 1, min(len(stock), start_idx + 16)):
        row = stock.loc[idx]
        prev = stock.loc[idx - 1]
        close = _safe_float(row.get("close"))
        low = _safe_float(row.get("low"))
        pct_chg = _safe_float(row.get("pct_chg"))
        ma5 = _safe_float(row.get("ma5"), default=None) if "ma5" in row else None
        gain = (close / avg_buy - 1) * 100
        if gain >= 5 and ma5 is not None and close < ma5:
            return {"date": pd.to_datetime(row["trade_date"]).date(), "price": close, "reason": "已有利润后收盘跌破5日线，趋势持有条件失效"}
        if gain >= 5 and low < _safe_float(prev.get("low")):
            return {"date": pd.to_datetime(row["trade_date"]).date(), "price": close, "reason": "已有利润后跌破前一日低点，短线强度转弱"}
        if gain >= 8 and pct_chg <= -5:
            return {"date": pd.to_datetime(row["trade_date"]).date(), "price": close, "reason": "高位出现大阴线，先锁定利润"}
    return None


def _sell_score(actual_return: float | None, rule_return: float) -> int:
    if actual_return is None:
        return 50
    if rule_return <= 0:
        return 70 if actual_return >= 0 else 45
    capture = actual_return / rule_return
    return int(max(35, min(98, round(capture * 100))))


def _classify_trade(
    stock_day: dict[str, float],
    sector_day: dict[str, float],
    benchmark_day: dict[str, float],
    is_closed: bool,
    max_gain: float,
    max_drawdown: float,
    sector_signal: dict,
) -> dict:
    stock_pct = stock_day["pct"]
    sector_pct = sector_day["pct"]
    benchmark_pct = benchmark_day["pct"]
    sector_state = str(sector_signal.get("state") or "")
    sector_score = float(sector_signal.get("score") or 50)
    if sector_state in {"退潮", "走弱"} and stock_pct <= benchmark_pct:
        return {
            "trade_type": "板块走弱日试错买入",
            "rating": "C",
            "stance": "降级观察",
            "headline": f"板块强度仅 {sector_score:.0f} 分，题材对个股买点形成压制；买入必须降低仓位并等待重新转强。",
            "scores": {"logic": 58, "buy": 45, "sell": 56 if not is_closed else 64, "risk": 46},
        }
    if sector_state == "主攻" and stock_pct > benchmark_pct and max_gain > 8:
        return {
            "trade_type": "主攻板块强势股买入",
            "rating": "A-",
            "stance": "顺势跟随",
            "headline": f"板块强度 {sector_score:.0f} 分，个股强于指数，属于题材主攻下的右侧跟随。",
            "scores": {"logic": 90, "buy": 88, "sell": 82, "risk": 78},
        }
    if is_closed and sector_pct > 3 and stock_pct > 8 and max_gain > 8:
        return {
            "trade_type": "主线强势股右侧买入",
            "rating": "A",
            "stance": "优秀买点",
            "headline": "主线强势股右侧买入，板块共振且个股封板确认。",
            "scores": {"logic": 92, "buy": 95, "sell": 88, "risk": 85},
        }
    if sector_pct < -3 and stock_pct < 0:
        return {
            "trade_type": "主线退潮日回补试错",
            "rating": "C",
            "stance": "偏激进",
            "headline": "主线退潮日回补，产业逻辑仍在，但当日板块和个股没有确认。",
            "scores": {"logic": 72, "buy": 45, "sell": 50 if not is_closed else 60, "risk": 48},
        }
    if stock_pct < benchmark_pct:
        return {
            "trade_type": "弱势跟随买入",
            "rating": "C+",
            "stance": "待验证",
            "headline": "个股弱于指数，买点需要后续修复确认。",
            "scores": {"logic": 68, "buy": 52, "sell": 50 if not is_closed else 62, "risk": 55},
        }
    if max_drawdown < -6:
        return {
            "trade_type": "右侧追高回撤",
            "rating": "C+",
            "stance": "偏激进",
            "headline": "买入后回撤较深，说明入场位置或仓位需要更谨慎。",
            "scores": {"logic": 70, "buy": 55, "sell": 55 if not is_closed else 65, "risk": 50},
        }
    return {
        "trade_type": "趋势回补试错",
        "rating": "B-",
        "stance": "待验证",
        "headline": "趋势股回补买入，需观察是否重新转强。",
        "scores": {"logic": 75, "buy": 62, "sell": 50 if not is_closed else 68, "risk": 62},
    }


def _score_figure(analysis: dict) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "indicator"}, {"type": "bar"}]], column_widths=[0.36, 0.64])
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=analysis["score"],
            title={"text": "综合评分"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#D92D20"},
                "steps": [
                    {"range": [0, 60], "color": "#F2F4F7"},
                    {"range": [60, 80], "color": "#FEF0C7"},
                    {"range": [80, 100], "color": "#FEE4E2"},
                ],
            },
        ),
        row=1,
        col=1,
    )
    labels = ["逻辑", "买点", "持仓/卖点", "风控"]
    values = [analysis["logic"], analysis["buy"], analysis["sell"], analysis["risk"]]
    fig.add_trace(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=["#7A5AF8", "#D92D20", "#F79009", "#12B76A"],
            text=[f"{value}/100" for value in values],
            textposition="auto",
        ),
        row=1,
        col=2,
    )
    fig.update_layout(height=290, template="plotly_white", margin={"l": 24, "r": 24, "t": 36, "b": 26})
    fig.update_xaxes(range=[0, 100], row=1, col=2)
    return fig


def _pnl_figure(stock: pd.DataFrame, analysis: dict) -> go.Figure:
    frame = stock[(stock["trade_date"] >= analysis["first_day"]) & (stock["trade_date"] <= analysis["last_day"])].copy()
    frame["floating_return"] = (frame["close"] / analysis["avg_buy"] - 1) * 100 if analysis["avg_buy"] else 0
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.to_datetime(frame["trade_date"]), y=frame["floating_return"], mode="lines+markers", name="浮盈%", line={"color": "#D92D20", "width": 3}, fill="tozeroy", fillcolor="rgba(217,45,32,0.12)"))
    fig.add_hline(y=0, line_color="#98A2B3", line_dash="dot")
    title = "收益曲线：持有过程中赚了多少钱？" if analysis["is_closed"] else "浮盈曲线：买入后当前处于什么状态？"
    fig.update_layout(title=title, height=360, template="plotly_white", margin={"l": 48, "r": 24, "t": 56, "b": 36})
    fig.update_yaxes(title_text="浮盈%")
    return fig


def _resonance_figure(profile: IndustryProfile, analysis: dict) -> go.Figure:
    labels = ["沪深300", "板块/ETF", profile.name]
    values = [analysis["benchmark_pct"], analysis["sector_pct"], analysis["day_pct"]]
    colors = ["#667085", "#7A5AF8", "#D92D20"]
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            text=[f"{value:.2f}%" for value in values],
            textposition="outside",
        )
    )
    fig.add_hline(y=0, line_color="#98A2B3", line_dash="dot")
    fig.update_layout(
        title="板块共振：交易日涨幅对比",
        height=360,
        template="plotly_white",
        margin={"l": 48, "r": 24, "t": 56, "b": 36},
    )
    fig.update_yaxes(title_text="当日涨跌幅%", zeroline=True)
    return fig


def _execution_figure(trade_frame: pd.DataFrame) -> go.Figure:
    labels = [f"{row.side.upper()} {row.trade_date:%m-%d} {row.price:.2f}" for row in trade_frame.itertuples()]
    colors = ["#12B76A" if side == "buy" else "#F04438" for side in trade_frame["side"]]
    fig = go.Figure(go.Bar(x=trade_frame["price"], y=labels, orientation="h", marker_color=colors, text=[f"{price:.2f}" for price in trade_frame["price"]], textposition="auto"))
    has_sell = (trade_frame["side"] == "sell").any()
    title = "买卖执行：分批价格是否合理？" if has_sell else "买入执行：这笔买在什么位置？"
    fig.update_layout(title=title, height=380, template="plotly_white", margin={"l": 118, "r": 24, "t": 56, "b": 36})
    fig.update_xaxes(title_text="成交价格")
    return fig


def _page_html(divs: list[str], profile: IndustryProfile, analysis: dict, market_html: str) -> str:
    trade_status = "已清仓" if analysis["is_closed"] else "持仓中"
    profit_label = "毛利润" if analysis["is_closed"] else "浮动盈亏"
    summary = _hero_summary_html(analysis)
    date_label = analysis["first_day"].strftime("%Y-%m-%d")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{escape(profile.name)} {escape(profile.code)} 交易复盘</title>
  <style>
    body {{ margin: 0; background: #f5f7fb; color: #101828; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; }}
    .page {{ max-width: 1180px; margin: 0 auto; padding: 28px 22px 48px; }}
    .hero {{ background: #101828; color: white; border-radius: 14px; padding: 24px 28px; }}
    .hero h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    .hero p {{ margin: 0; color: #d0d5dd; line-height: 1.6; }}
    .hero-summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 18px; }}
    .hero-summary div {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; padding: 12px; line-height: 1.55; color: #f2f4f7; }}
    .hero-summary b {{ display: block; margin-bottom: 4px; color: #ffffff; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 16px; }}
    .metric {{ background: white; border: 1px solid #eaecf0; border-radius: 10px; padding: 14px 16px; }}
    .metric .label {{ color: #667085; font-size: 13px; }}
    .metric .value {{ margin-top: 6px; font-size: 22px; font-weight: 700; }}
    .section {{ background: white; border: 1px solid #eaecf0; border-radius: 12px; margin-top: 16px; padding: 16px; }}
    .section h2 {{ margin: 0 0 10px; font-size: 18px; }}
    .summary {{ line-height: 1.8; color: #344054; }}
    .context-grid, .chain-layout {{ display: grid; grid-template-columns: 1.05fr 1fr; gap: 16px; align-items: start; }}
    .mini-table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    .mini-table th, .mini-table td {{ border-bottom: 1px solid #eaecf0; padding: 9px 8px; text-align: right; }}
    .mini-table th:first-child, .mini-table td:first-child {{ text-align: left; }}
    .tag {{ display: inline-block; margin: 0 6px 8px 0; padding: 4px 8px; border-radius: 999px; background: #fef3f2; color: #b42318; font-size: 12px; font-weight: 650; }}
    .note, .thesis-card {{ background: #f9fafb; border: 1px solid #eaecf0; border-radius: 10px; padding: 12px 14px; margin-top: 12px; }}
    .decision-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
    .decision-card {{ background: #ffffff; border: 1px solid #eaecf0; border-radius: 10px; padding: 14px; line-height: 1.75; }}
    .decision-card b {{ display: block; margin-bottom: 6px; color: #101828; }}
    .decision-card strong {{ color: #b42318; }}
    .chain-map {{ width: 100%; max-width: 660px; min-height: 430px; }}
    .chain-line {{ stroke: #d0d5dd; stroke-width: 2; }}
    .chain-core {{ fill: #7A5AF8; stroke: #53389E; stroke-width: 2; }}
    .chain-hot {{ fill: #D92D20; stroke: #912018; stroke-width: 2; }}
    .chain-node {{ fill: #f9fafb; stroke: #98a2b3; stroke-width: 1.5; }}
    .chain-peer {{ fill: #fff7ed; stroke: #F79009; stroke-width: 1.5; }}
    .chain-text {{ font-size: 13px; fill: #101828; font-weight: 650; text-anchor: middle; dominant-baseline: middle; }}
    .chain-text-light {{ fill: #ffffff; }}
    @media (max-width: 900px) {{ .cards, .hero-summary, .context-grid, .chain-layout {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>{escape(profile.name)} {escape(profile.code)} 交易复盘｜{date_label}</h1>
      <p>{escape(str(analysis['headline']))} 状态：{trade_status}。</p>
      <div class="hero-summary">{summary}</div>
    </section>
    <section class="cards">
      {_metric_card("收益率", f"{analysis['return']:.1f}%")}
      {_metric_card(profit_label, f"{analysis['profit']:.0f}")}
      {_metric_card("交易评级", str(analysis["rating"]))}
      {_metric_card("综合评分", f"{analysis['score']}/100")}
    </section>
    <section class="section"><h2>最优解：这笔交易该怎么买、怎么卖</h2>{_optimal_action_html(analysis)}</section>
    <section class="section"><h2>页面1：交易评分卡</h2>{divs[0]}</section>
    <section class="section"><h2>页面2：大盘环境与个股日K分析</h2>{market_html}</section>
    <section class="section"><h2>页面3：产业链定位图</h2>{_industry_chain_html(profile)}</section>
    <section class="section"><h2>页面4：板块共振柱状图</h2>{divs[1]}</section>
    <section class="section"><h2>页面5：买卖执行分析</h2>{divs[2]}</section>
  </main>
</body>
</html>"""


def _hero_summary_html(analysis: dict) -> str:
    optimal = analysis["optimal"]
    if analysis["is_closed"]:
        return f"""
        <div><b>为什么买</b>{escape(str(analysis['trade_type']))}。买入时个股/板块共振，交易得到后续价格验证。</div>
        <div><b>买点结论</b>{escape(optimal['buy_verdict'])}</div>
        <div><b>卖点结论</b>{escape(optimal['sell_verdict'])}</div>
        <div><b>下次优化</b>把卖出条件提前写成规则：分批止盈、均线破位或前日低点失效。</div>
        """
    return f"""
        <div><b>为什么买</b>{escape(str(analysis['trade_type']))}。产业链逻辑仍需服从当日板块和个股确认。</div>
        <div><b>买点结论</b>{escape(optimal['buy_verdict'])}</div>
        <div><b>卖点计划</b>{escape(optimal['sell_verdict'])}</div>
        <div><b>当前状态</b>买入均价 {analysis['avg_buy']:.2f}，最新收盘 {analysis['last_close']:.2f}，浮动收益 {analysis['return']:.1f}%。</div>
        """


def _optimal_action_html(analysis: dict) -> str:
    optimal = analysis["optimal"]
    peak_date = optimal["peak_date"].strftime("%Y-%m-%d") if optimal["peak_date"] else "N/A"
    rule_date = optimal["rule_sell_date"].strftime("%Y-%m-%d") if optimal["rule_sell_date"] else "暂未触发"
    actual = "尚未卖出" if optimal["actual_sell_return"] is None else f"{optimal['actual_sell_return']:.1f}%"
    rule_return = "N/A" if not optimal["rule_sell_date"] else f"{optimal['rule_sell_return']:.1f}%"
    return f"""
      <div class="decision-grid">
        <div class="decision-card">
          <b>1. 是否应该买？</b>
          <strong>{escape(optimal['buy_verdict'])}</strong><br>
          理由：{escape(optimal['buy_reason'])}
        </div>
        <div class="decision-card">
          <b>2. 最优卖点在哪里？</b>
          事后最高点：<strong>{peak_date} / {optimal['peak_price']:.2f} / {optimal['peak_return']:.1f}%</strong><br>
          可执行规则卖点：<strong>{rule_date}</strong>，规则收益：{rule_return}
        </div>
        <div class="decision-card">
          <b>3. 实际卖得好不好？</b>
          <strong>{escape(optimal['sell_verdict'])}</strong><br>
          实际卖出收益：{actual}<br>
          理由：{escape(optimal['sell_reason'])}
        </div>
      </div>
      <div class="note summary">
        <b>卖出评价依据：</b>先用买入均价计算实际卖出收益，再和“可执行规则卖点”比较。规则卖点只在已有利润后触发，核心条件是收盘跌破5日线、跌破前一日低点，或盈利较高后出现大阴线。若实际卖出早于规则卖点，且规则卖点收益明显更高，系统判为卖早；若实际收益接近规则卖点收益，判为合格；若规则尚未触发就卖出，判为偏早或情绪化兑现。
      </div>
    """


def _market_context_html(stock: pd.DataFrame, sh_index: pd.DataFrame, benchmark: pd.DataFrame, growth_index: pd.DataFrame, sector: pd.DataFrame, analysis: dict) -> str:
    trade_date = analysis["first_day"]
    rows = [
        ("上证指数", _day_snapshot(sh_index, trade_date)),
        ("沪深300", _day_snapshot(benchmark, trade_date)),
        ("创业板指", _day_snapshot(growth_index, trade_date)),
        ("板块/ETF", _day_snapshot(sector, trade_date)),
        (analysis["name"], _day_snapshot(stock, trade_date)),
    ]
    table_rows = "\n".join(
        f"<tr><td>{escape(name)}</td><td>{_fmt_pct(item['pct'])}</td><td>{_fmt_ratio(item['vol_ratio'])}</td><td>{_fmt_price(item['close'])}</td></tr>"
        for name, item in rows
    )
    stock_day = rows[-1][1]
    sector_signal = analysis.get("sector_signal", {})
    sector_strength_html = ""
    if sector_signal:
        sector_strength_html = f"""
          <p class="summary-text">板块强度：{escape(str(sector_signal.get("name", "板块")))}
          {int(sector_signal.get("score", 0))}/100，状态：{escape(str(sector_signal.get("state", "待确认")))}。
          相对沪深300：{_fmt_pct(float(sector_signal.get("relative_to_benchmark", 0.0)))}；
          资金状态：{escape(str(sector_signal.get("fund_flow_status", "待确认")))}。
          {escape(str(sector_signal.get("warning", "")))}</p>
        """
    market_tone = "偏强" if rows[1][1]["pct"] > 0 and rows[3][1]["pct"] > 0 else "偏弱/分歧"
    return f"""
      <div class="context-grid">
        <div>
          <table class="mini-table">
            <thead><tr><th>对象</th><th>当日涨跌</th><th>量能/5日均量</th><th>收盘</th></tr></thead>
            <tbody>{table_rows}</tbody>
          </table>
          <div class="note summary">
            <b>大盘判断：</b>当日环境为 {market_tone}。沪深300 {_fmt_pct(rows[1][1]['pct'])}，板块/ETF {_fmt_pct(rows[3][1]['pct'])}。
            交易质量要看个股是否强于指数、是否与板块共振，而不是只看产业逻辑。
          </div>
        </div>
        <div class="summary">
          <span class="tag">{escape(str(analysis['trade_type']))}</span>
          <span class="tag">{escape(str(analysis['stance']))}</span>
          <div class="note">
            <b>{escape(str(analysis['name']))} 日K分析：</b><br>
            当日开盘 {stock_day['open']:.2f}，最低 {stock_day['low']:.2f}，最高 {stock_day['high']:.2f}，收盘 {stock_day['close']:.2f}，涨跌 {_fmt_pct(stock_day['pct'])}。
            这笔交易被系统识别为“{escape(str(analysis['trade_type']))}”，评分为 {analysis['score']}/100。
          </div>
          <div class="note">
            <b>结论：</b>{escape(str(analysis['headline']))}
          </div>
        </div>
      </div>
    """


def _industry_chain_html(profile: IndustryProfile) -> str:
    nodes = _chain_positions(profile.chain_nodes)
    lines = "\n".join(
        f'<line class="chain-line" x1="330" y1="210" x2="{x}" y2="{y}" />'
        for _, _, _, x, y, _ in nodes
    )
    circles = "\n".join(_chain_circle(kind, title, subtitle, x, y, idx) for idx, (kind, title, subtitle, x, y, _) in enumerate(nodes))
    barriers = "".join(f"<li>{escape(item)}</li>" for item in profile.barriers)
    levers = "".join(f"<li>{escape(item)}</li>" for item in profile.profit_levers)
    peers = "、".join(profile.peers) if profile.peers else "待补充"
    return f"""
      <div class="chain-layout">
        <svg class="chain-map" viewBox="0 0 660 430" role="img" aria-label="{escape(profile.name)}产业链定位图">
          {lines}
          <circle class="chain-core" cx="330" cy="210" r="68" />
          <text class="chain-text chain-text-light" x="330" y="197">核心驱动</text>
          <text class="chain-text chain-text-light" x="330" y="217">{escape(profile.core_driver[:12])}</text>
          <text class="chain-text chain-text-light" x="330" y="237">{escape(profile.theme[:12])}</text>
          {circles}
        </svg>
        <div class="summary">
          <div class="thesis-card"><b>产业链定位</b>{escape(profile.name)}位于“{escape(profile.node)}”节点，不是产业链中心；中心是“{escape(profile.core_driver)}”。</div>
          <div class="thesis-card"><b>壁垒来源</b><ul>{barriers}</ul></div>
          <div class="thesis-card"><b>利润弹性</b><ul>{levers}</ul></div>
          <div class="thesis-card"><b>同链个股</b>{escape(peers)}</div>
        </div>
      </div>
    """


def _chain_positions(chain_nodes: tuple[tuple[str, str, str], ...]) -> list[tuple[str, str, str, int, int, str]]:
    positions = [(330, 72), (492, 116), (530, 240), (450, 348), (210, 348), (130, 240), (168, 116)]
    result = []
    for idx, item in enumerate(chain_nodes[:7]):
        x, y = positions[idx]
        result.append((*item, x, y, ""))
    return result


def _chain_circle(kind: str, title: str, subtitle: str, x: int, y: int, idx: int) -> str:
    cls = "chain-hot" if kind == "stock" else "chain-peer" if kind in {"peer", "adjacent"} else "chain-node"
    text_cls = " chain-text-light" if cls == "chain-hot" else ""
    radius = 60 if kind == "stock" else 55
    return f"""
      <circle class="{cls}" cx="{x}" cy="{y}" r="{radius}" />
      <text class="chain-text{text_cls}" x="{x}" y="{y - 9}">{escape(title[:12])}</text>
      <text class="chain-text{text_cls}" x="{x}" y="{y + 12}">{escape(subtitle[:12])}</text>
    """


def _day_snapshot(frame: pd.DataFrame, trade_date) -> dict[str, float]:
    if frame.empty:
        return {"open": 0.0, "close": 0.0, "high": 0.0, "low": 0.0, "pct": 0.0, "vol_ratio": 0.0, "ma5": 0.0, "ma10": 0.0}
    frame = frame.sort_values("trade_date").reset_index(drop=True)
    matches = frame.index[frame["trade_date"] == trade_date].tolist()
    if not matches:
        matches = frame.index[frame["trade_date"] >= trade_date].tolist()
    idx = matches[0]
    row = frame.loc[idx]
    history = frame.loc[max(0, idx - 5): idx - 1, "volume"].map(_safe_float).dropna()
    volume = _safe_float(row.get("volume"))
    history_mean = float(history.mean()) if not history.empty else 0.0
    vol_ratio = volume / history_mean if history_mean else 0.0
    return {
        "open": _safe_float(row.get("open")),
        "close": _safe_float(row.get("close")),
        "high": _safe_float(row.get("high")),
        "low": _safe_float(row.get("low")),
        "pct": _safe_float(row.get("pct_chg")),
        "vol_ratio": vol_ratio,
        "ma5": _safe_float(row.get("ma5")),
        "ma10": _safe_float(row.get("ma10")),
    }


def _safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).replace(b"\x00", b"").decode("utf-8", errors="ignore")
    if isinstance(value, str):
        value = value.replace("\x00", "").replace(",", "").strip()
        if not value:
            return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_index_on_or_after(frame: pd.DataFrame, trade_date) -> int | None:
    if frame.empty or "trade_date" not in frame.columns:
        return None
    matches = frame.index[frame["trade_date"] >= trade_date].tolist()
    return matches[0] if matches else None


def _metric_card(label: str, value: str) -> str:
    return f'<div class="metric"><div class="label">{escape(label)}</div><div class="value">{escape(value)}</div></div>'


def _fmt_pct(value: float) -> str:
    return f"{value:.2f}%"


def _fmt_ratio(value: float) -> str:
    return "N/A" if value == 0 else f"{value:.2f}x"


def _fmt_price(value: float) -> str:
    return "N/A" if value == 0 else f"{value:.2f}"


def _premium_page_html(profile: IndustryProfile, analysis: dict, market_html: str, trade_frame: pd.DataFrame) -> str:
    date_label = analysis["first_day"].strftime("%Y-%m-%d")
    generated_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    trade_status = "已闭合" if analysis["is_closed"] else "持仓中"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(profile.name)} {escape(profile.code)} 交易复盘</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #050607;
      --panel: rgba(10, 18, 20, .78);
      --panel-soft: rgba(255, 255, 255, .035);
      --line: rgba(245, 215, 122, .18);
      --line-soft: rgba(255, 255, 255, .08);
      --gold-dark: #8A6A2A;
      --gold-main: #C9A646;
      --gold-light: #F5D77A;
      --gold-pale: #FFF1B8;
      --red: #ff5f56;
      --green: #50d890;
      --text: #f7f1dc;
      --muted: #9fa6a1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at 12% 10%, rgba(201, 166, 70, .13), transparent 26%),
        radial-gradient(circle at 88% 2%, rgba(245, 215, 122, .09), transparent 32%),
        linear-gradient(180deg, #061013 0%, #020405 100%);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    }}
    .page {{ width: min(1160px, calc(100vw - 28px)); margin: 0 auto; padding: 26px 0 46px; }}
    .top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 16px; }}
    h1 {{ margin: 0; font-size: clamp(24px, 4vw, 38px); letter-spacing: -0.02em; }}
    .meta {{ margin-top: 7px; color: var(--muted); font-size: 13px; }}
    .btn {{ border: 1px solid var(--line); color: var(--gold-light); background: rgba(255,255,255,.04); border-radius: 9px; padding: 9px 12px; font-weight: 800; }}
    .grid {{ display: grid; gap: 14px; }}
    .two {{ grid-template-columns: 1.05fr .95fr; }}
    .three {{ grid-template-columns: repeat(3, 1fr); }}
    .six {{ grid-template-columns: repeat(6, 1fr); }}
    .card {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(145deg, rgba(16, 23, 23, .94), rgba(6, 8, 9, .94));
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: 0 18px 55px rgba(0,0,0,.34), inset 0 1px 0 rgba(255,255,255,.04);
      padding: 18px;
      margin-bottom: 14px;
    }}
    .card::before {{
      content: "";
      position: absolute;
      inset: 0;
      pointer-events: none;
      background: radial-gradient(circle at 18% 0%, rgba(245,215,122,.12), transparent 28%);
      opacity: .75;
    }}
    .card > * {{ position: relative; z-index: 1; }}
    .section-title {{ display: flex; align-items: center; gap: 9px; margin: 0 0 14px; font-size: 18px; }}
    .num {{ display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; border: 1px solid var(--gold-main); color: var(--gold-light); font-size: 12px; }}
    .hero {{ grid-template-columns: 320px 1fr 240px; align-items: stretch; }}
    .score-wrap {{ display: grid; place-items: center; gap: 10px; }}
    .score-ring {{
      --score: {int(analysis["score"])};
      width: 190px; height: 190px; border-radius: 50%;
      display: grid; place-items: center;
      background: conic-gradient(var(--gold-light) calc(var(--score) * 1%), rgba(255,255,255,.08) 0);
      box-shadow: 0 0 38px rgba(245, 215, 122, .28);
    }}
    .score-ring-inner {{ width: 150px; height: 150px; border-radius: 50%; background: #071012; border: 1px solid rgba(245,215,122,.2); display: grid; place-items: center; text-align: center; }}
    .score-main {{ color: var(--gold-light); font-size: 54px; font-weight: 900; line-height: 1; }}
    .score-sub {{ color: var(--muted); font-size: 13px; }}
    .rating {{ font-size: 34px; color: var(--gold-light); font-weight: 900; }}
    .summary-title {{ color: var(--gold-light); font-weight: 900; margin: 6px 0 10px; }}
    .summary-text {{ line-height: 1.85; color: #d7d0bd; margin: 0; }}
    .mini-scores {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 16px; }}
    .mini-score, .metric {{
      background: rgba(255,255,255,.045);
      border: 1px solid var(--line-soft);
      border-radius: 10px;
      padding: 12px;
    }}
    .label {{ color: var(--muted); font-size: 13px; }}
    .value {{ margin-top: 6px; font-size: 25px; font-weight: 900; color: var(--gold-light); }}
    .green {{ color: var(--green); }}
    .red {{ color: var(--red); }}
    .chain-flow {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; align-items: stretch; }}
    .flow-card {{ min-height: 128px; padding: 14px; border-radius: 12px; background: rgba(255,255,255,.045); border: 1px solid var(--line-soft); }}
    .flow-card.good {{ border-color: rgba(80,216,144,.3); }}
    .flow-card.warn {{ border-color: rgba(245,215,122,.38); }}
    .flow-card.bad {{ border-color: rgba(255,95,86,.34); }}
    .flow-card b {{ display: block; color: var(--gold-light); margin-bottom: 8px; }}
    .flow-card p {{ margin: 0; color: #c8c0ad; line-height: 1.65; font-size: 13px; }}
    .bar-row {{ margin: 12px 0; }}
    .bar-head {{ display: flex; justify-content: space-between; color: #d9d2c0; font-size: 13px; margin-bottom: 7px; }}
    .bar-track {{ height: 10px; background: rgba(255,255,255,.08); border-radius: 99px; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 99px; background: linear-gradient(90deg, var(--gold-dark), var(--gold-light)); }}
    .mini-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    .mini-table th, .mini-table td {{ padding: 10px 8px; border-bottom: 1px solid var(--line-soft); text-align: right; }}
    .mini-table th:first-child, .mini-table td:first-child {{ text-align: left; }}
    .tag {{ display: inline-flex; padding: 5px 9px; border-radius: 999px; border: 1px solid rgba(245,215,122,.3); color: var(--gold-light); background: rgba(245,215,122,.08); font-size: 12px; font-weight: 800; margin: 0 6px 7px 0; }}
    .radar {{ width: 100%; max-width: 360px; margin: 0 auto; display: block; }}
    .chain {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 16px; }}
    .chain-map {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    .chain-node {{ min-width: 124px; padding: 12px; border-radius: 10px; border: 1px solid var(--line-soft); background: rgba(255,255,255,.045); text-align: center; }}
    .chain-node.core {{ border-color: var(--gold-main); box-shadow: 0 0 22px rgba(201,166,70,.18); }}
    .arrow {{ color: var(--gold-light); font-weight: 900; }}
    .thesis-box, .agent-box {{
      margin: 0 0 12px;
      padding: 13px 14px;
      border-radius: 12px;
      border: 1px solid rgba(245,215,122,.24);
      background: linear-gradient(145deg, rgba(245,215,122,.12), rgba(255,255,255,.035));
      color: #d8cfb9;
      line-height: 1.75;
    }}
    .thesis-box b, .agent-box b {{ display: block; color: var(--gold-light); margin-bottom: 6px; }}
    .thesis-box p, .agent-box p {{ margin: 0; }}
    ul {{ margin: 10px 0 0; padding-left: 18px; color: #c9c0aa; line-height: 1.8; }}
    ol {{ margin: 10px 0 0; padding-left: 20px; color: #c9c0aa; line-height: 1.8; }}
    .advice-list {{ display: grid; gap: 10px; }}
    .advice {{ display: grid; grid-template-columns: 28px 1fr; gap: 10px; align-items: start; color: #d8cfb9; line-height: 1.7; }}
    .advice span {{ display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: rgba(245,215,122,.12); color: var(--gold-light); font-weight: 900; }}
    .uplift {{ display: grid; place-items: center; min-height: 160px; border-radius: 12px; background: linear-gradient(145deg, rgba(245,215,122,.12), rgba(255,255,255,.03)); border: 1px solid var(--line); text-align: center; }}
    .uplift strong {{ font-size: 34px; color: var(--gold-light); }}
    footer {{ color: #6f756f; font-size: 12px; margin-top: 14px; }}
    @media (max-width: 980px) {{ .hero, .two, .three, .six, .chain {{ grid-template-columns: 1fr; }} .mini-scores, .chain-flow {{ grid-template-columns: 1fr 1fr; }} }}
    @media (max-width: 640px) {{ .mini-scores, .chain-flow {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main class="page">
    <header class="top">
      <div>
        <h1>{escape(profile.name)}（{escape(profile.code)}）交易复盘</h1>
        <div class="meta">本次交易已由 AI 深度分析 · 交易日 {date_label} · 生成于 {generated_at} · 状态 {trade_status}</div>
      </div>
      <button class="btn" type="button">分享报告</button>
    </header>

    <section class="card grid hero">
      <div class="score-wrap">
        <div class="score-ring"><div class="score-ring-inner"><div><div class="score-main">{analysis["score"]}</div><div class="score-sub">/100</div><div class="rating">{escape(str(analysis["rating"]))}</div></div></div></div>
      </div>
      <div>
        <div class="summary-title">AI 总结</div>
        <p class="summary-text">{escape(str(analysis["headline"]))}<br>{escape(_one_line_verdict(analysis))}</p>
        <div class="mini-scores">
          {_small_score("逻辑", analysis["logic"])}
          {_small_score("买点", analysis["buy"])}
          {_small_score("卖点", analysis["sell"])}
          {_small_score("风控", analysis["risk"])}
        </div>
      </div>
      <div class="grid">
        {_metric_card("收益率", f"{analysis['return']:.1f}%")}
        {_metric_card("规划收益（可达）", _planned_return(analysis))}
        {_metric_card("少赚收益", _missed_return(analysis))}
        {_metric_card("毛利润", f"{analysis['profit']:.0f}")}
      </div>
    </section>

    <section class="card">
      {_section_title(2, "AI 复盘结论")}
      {_conclusion_flow_html(analysis)}
    </section>

    <section class="grid six">
      {_metric_card("收益率", f"{analysis['return']:.1f}%")}
      {_metric_card("规划收益（可达）", _planned_return(analysis))}
      {_metric_card("少赚收益", _missed_return(analysis))}
      {_metric_card("毛利润", f"{analysis['profit']:.0f}")}
      {_metric_card("交易评级", str(analysis["rating"]))}
      {_metric_card("综合评分", f"{analysis['score']}/100")}
    </section>

    <section class="grid two">
      <div class="card">
        {_section_title(4, "最佳交易路线对比")}
        {_execution_compare_html(analysis, trade_frame)}
      </div>
      <div class="card">
        {_section_title(5, "交易体检")}
        {_trade_radar_html(analysis)}
      </div>
    </section>

    <section class="grid two">
      <div class="card">
        {_section_title(6, "产业链与个股定位")}
        {_premium_industry_chain_html(profile)}
      </div>
      <div class="card">
        {_section_title(7, "市场情绪与行为显微镜")}
        {_psychology_html(analysis)}
      </div>
    </section>

    <section class="card">
      {_section_title(8, "AI 教练总结与建议")}
      {_advice_html(analysis, profile)}
    </section>

    <section class="card">
      {_section_title(9, "大盘、板块与个股共振")}
      {market_html}
    </section>

    <footer>本报告由 AI 自动生成，仅供复盘与交易纪律训练使用，不构成投资建议。</footer>
  </main>
</body>
</html>"""


def _section_title(num: int, text: str) -> str:
    return f'<h2 class="section-title"><span class="num">{num}</span>{escape(text)}</h2>'


def _small_score(label: str, value: float) -> str:
    return f'<div class="mini-score"><div class="label">{escape(label)}</div><div class="value">{value:.0f}<span class="label">/100</span></div></div>'


def _planned_return(analysis: dict) -> str:
    optimal = analysis["optimal"]
    if optimal.get("rule_sell_date"):
        return f"{optimal['rule_sell_return']:.1f}%"
    return f"{optimal.get('peak_return', 0.0):.1f}%"


def _missed_return(analysis: dict) -> str:
    optimal = analysis["optimal"]
    actual = optimal.get("actual_sell_return")
    planned = optimal.get("rule_sell_return") if optimal.get("rule_sell_date") else optimal.get("peak_return", 0.0)
    if actual is None:
        return "未卖出"
    return f"{max(0.0, planned - actual):.1f}%"


def _premium_page_html(profile: IndustryProfile, analysis: dict, market_html: str, trade_frame: pd.DataFrame) -> str:
    """Final workbench report template used by the existing backend call site."""
    date_label = analysis["first_day"].strftime("%Y-%m-%d")
    generated_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    trade_status = "已闭环" if analysis["is_closed"] else "持仓中"
    score = int(analysis.get("score", 0) or 0)
    sector_signal = analysis.get("sector_signal", {}) or {}
    sector_score = int(sector_signal.get("score", 0) or 0)
    industry_score = max(sector_score, min(95, max(55, score + 4)))
    invest_score = min(98, max(45, score))
    stock_pct = float(analysis.get("day_pct", 0.0))
    sector_pct = float(analysis.get("sector_pct", 0.0))
    benchmark_pct = float(analysis.get("benchmark_pct", 0.0))
    max_abs = max(abs(stock_pct), abs(sector_pct), abs(benchmark_pct), 1.0)
    optimal = analysis["optimal"]
    subtitle = f"{profile.code}{_wb_exchange_suffix(profile.code)} · {profile.theme} / {profile.node}"
    flow_html, source_label, target_subtitle = _wb_profit_flow(profile)
    wang_text = profile.wang_investor_report or profile.industry_judgment or "WANG-INVESTOR memo 暂未生成。"
    equity_text = profile.public_equity_report or profile.valuation_odds or "Public Equity memo 暂未生成。"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(profile.name)} AI 复盘分析</title>
  <style>
    :root {{ color-scheme:dark; --bg:#061111; --panel:#111b1a; --line:#29403d; --gold:#ffd966; --cyan:#70d9e6; --text:#fff9e8; --muted:#b5c9c5; --green:#78dd93; --red:#ff746e; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:radial-gradient(circle at 16% 0%,rgba(112,217,230,.16),transparent 28%),radial-gradient(circle at 92% 8%,rgba(255,217,102,.12),transparent 30%),linear-gradient(90deg,rgba(112,217,230,.06) 1px,transparent 1px),linear-gradient(0deg,rgba(112,217,230,.05) 1px,transparent 1px),var(--bg); background-size:auto,auto,48px 48px,48px 48px,auto; color:var(--text); font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif; }}
    .page {{ width:min(1440px,calc(100vw - 32px)); margin:0 auto; padding:32px 0 60px; }}
    .topbar {{ display:flex; justify-content:space-between; gap:16px; align-items:center; color:var(--muted); margin-bottom:26px; }}
    .brand {{ color:var(--cyan); letter-spacing:.12em; font-weight:900; text-transform:uppercase; }}
    .topbar span {{ border:1px solid rgba(255,217,102,.28); border-radius:999px; padding:8px 12px; margin-left:8px; color:#e8d69a; }}
    .hero {{ display:grid; grid-template-columns:1.06fr .94fr; min-height:520px; border-bottom:1px solid rgba(255,217,102,.2); }}
    .hero-left {{ padding:54px 56px 54px 20px; background:linear-gradient(90deg,rgba(112,217,230,.08),transparent); }}
    .kicker {{ color:var(--cyan); font-size:18px; font-weight:900; margin-bottom:22px; }}
    h1 {{ margin:0; font-size:clamp(60px,8vw,112px); line-height:.95; letter-spacing:-.06em; }}
    .subtitle {{ color:#f1d996; font-size:28px; font-weight:900; margin-top:24px; }}
    .rating-row {{ display:flex; flex-wrap:wrap; gap:16px; margin-top:34px; }}
    .rating,.chip {{ border:1px solid rgba(255,217,102,.38); background:rgba(255,217,102,.08); border-radius:8px; padding:16px 22px; font-size:22px; color:var(--gold); font-weight:900; }}
    .chip {{ color:var(--text); font-size:18px; }}
    .hero-card,.section {{ border:1px solid var(--line); border-radius:8px; background:linear-gradient(180deg,rgba(17,27,26,.96),rgba(8,17,17,.96)); box-shadow:0 30px 80px rgba(0,0,0,.26); }}
    .hero-card {{ padding:48px; display:grid; align-content:center; }}
    .hero-card h2,.section h2 {{ margin:0 0 28px; color:var(--gold); font-size:36px; }}
    .bullet-list {{ display:grid; gap:24px; }}
    .bullet {{ display:grid; grid-template-columns:14px 1fr; gap:22px; align-items:start; font-size:29px; line-height:1.35; font-weight:900; }}
    .dot {{ width:13px; height:13px; margin-top:13px; border-radius:50%; background:var(--cyan); box-shadow:0 0 20px rgba(112,217,230,.8); }}
    .hero-note,.section p {{ color:var(--muted); line-height:1.75; font-size:18px; }}
    .section {{ margin-top:28px; padding:34px; }}
    .section-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:20px; margin-bottom:24px; }}
    .pill {{ border:1px solid rgba(112,217,230,.45); color:var(--cyan); border-radius:999px; padding:10px 16px; font-weight:900; white-space:nowrap; }}
    .flow-grid {{ min-height:360px; display:grid; grid-template-columns:230px 1fr 300px; gap:30px; align-items:center; }}
    .source,.target,.mini,.expect-box {{ border:1px solid rgba(112,217,230,.35); background:rgba(112,217,230,.06); border-radius:8px; padding:26px; }}
    .source {{ border-color:rgba(255,217,102,.35); background:rgba(255,217,102,.08); }}
    .source b {{ display:block; color:var(--gold); font-size:34px; margin-bottom:10px; }}
    .target b {{ display:block; color:var(--cyan); font-size:36px; margin-bottom:8px; }}
    .flow-list {{ display:grid; gap:16px; }}
    .flow {{ display:grid; grid-template-columns:140px 1fr 64px; gap:16px; align-items:center; font-size:22px; }}
    .bar {{ height:24px; border-radius:999px; overflow:hidden; background:#263635; }}
    .fill {{ height:100%; border-radius:inherit; background:linear-gradient(90deg,#dfb94d,#ffe590); }}
    .flow.highlight .fill {{ background:linear-gradient(90deg,var(--cyan),#b8f4fb); box-shadow:0 0 24px rgba(112,217,230,.36); }}
    .logic-row {{ display:grid; grid-template-columns:repeat(6,1fr); gap:16px; }}
    .logic-card {{ min-height:154px; border:1px solid rgba(112,217,230,.35); background:rgba(112,217,230,.06); border-radius:8px; padding:22px; }}
    .logic-card h3 {{ margin:0 0 22px; font-size:22px; }}
    .logic-card b {{ color:var(--gold); font-size:38px; }}
    .logic-card span {{ display:block; color:var(--muted); margin-top:10px; line-height:1.5; }}
    .expect-grid {{ display:grid; grid-template-columns:1fr 250px 1fr; gap:24px; align-items:stretch; }}
    .expect-box h3,.mini h3 {{ color:#f1d996; margin:0 0 18px; font-size:26px; }}
    .expect-box ul {{ margin:0; padding-left:24px; color:var(--muted); font-size:22px; line-height:1.65; }}
    .gap-score {{ display:grid; place-items:center; text-align:center; border:1px solid rgba(255,217,102,.45); background:rgba(255,217,102,.09); border-radius:8px; }}
    .gap-score b {{ font-size:64px; color:var(--gold); display:block; }}
    .two {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; }}
    .three {{ display:grid; grid-template-columns:repeat(3,1fr); gap:18px; }}
    .memo {{ white-space:pre-wrap; color:#d7e1df; line-height:1.8; font-size:16px; max-height:520px; overflow:auto; }}
    .list {{ color:#d7e1df; line-height:1.8; font-size:17px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ border-bottom:1px solid rgba(255,217,102,.16); padding:13px 10px; text-align:left; }}
    th {{ color:var(--gold); }}
    .green {{ color:var(--green); }} .red {{ color:var(--red); }}
    footer {{ color:#78908b; margin-top:28px; font-size:13px; }}
    @media (max-width:1100px) {{ .hero,.flow-grid,.expect-grid,.two {{ grid-template-columns:1fr; }} .logic-row,.three {{ grid-template-columns:1fr 1fr; }} }}
    @media (max-width:680px) {{ .logic-row,.three {{ grid-template-columns:1fr; }} .hero-left,.hero-card,.section {{ padding:24px; }} h1 {{ font-size:52px; }} .bullet {{ font-size:22px; }} }}
  </style>
</head>
<body>
  <main class="page">
    <header class="topbar"><div class="brand">Research Workbench</div><div><span>{escape(date_label)}</span><span>{escape(generated_at)}</span><span>{escape(trade_status)}</span></div></header>
    <section class="hero">
      <div class="hero-left">
        <div class="kicker">这家公司值得研究吗?</div>
        <h1>{escape(profile.name)}</h1>
        <div class="subtitle">{escape(subtitle)}</div>
        <div class="rating-row"><span class="rating">产业评级 {_wb_grade(industry_score)}</span><span class="rating">投资评级 {_wb_grade(invest_score)}</span></div>
        <div class="rating-row">{_wb_chips(profile, industry_score)}</div>
      </div>
      <div class="hero-card"><h2>一句话结论</h2><div class="bullet-list">{_wb_conclusion_bullets(profile, analysis)}</div><p class="hero-note">首屏不展示总分，而是先让用户判断：这家公司是否值得进入研究清单。</p></div>
    </section>
    <section class="section"><div class="section-head"><div><h2>利润流向图</h2><p>用资金流和利润池解释“为什么是它”，而不是让用户在财务指标里猜。</p></div><span class="pill">核心模块</span></div><div class="flow-grid"><div class="source"><b>{escape(source_label)}</b><span>价值池 100%</span></div><div class="flow-list">{flow_html}</div><div class="target"><span>高亮位置</span><b>{escape(profile.name)}</b><p>{escape(target_subtitle)}</p></div></div></section>
    <section class="section"><div class="section-head"><div><h2>产业逻辑树</h2><p>把上涨逻辑拆成节点，显示每一步的确定性，暴露逻辑链最脆弱的位置。</p></div><span class="pill">因果链</span></div><div class="logic-row">{_wb_logic_tree(profile, analysis)}</div></section>
    <section class="section"><div class="section-head"><div><h2>市场预期差</h2><p>股票上涨来自“比市场想得更好”，这里直接展示市场叙事和研究员判断之间的差距。</p></div><span class="pill">涨幅来源</span></div>{_wb_expectation_gap(profile, analysis)}</section>
    <section class="section"><div class="section-head"><div><h2>产业壁垒与利润杠杆</h2><p>这里保留 agent 的关键判断，防止图表把研究结论过度压扁。</p></div><span class="pill">moat</span></div><div class="three"><article class="mini"><h3>壁垒</h3><ul class="list">{_rw_list(list(profile.barriers)[:5])}</ul></article><article class="mini"><h3>利润杠杆</h3><ul class="list">{_rw_list(list(profile.profit_levers)[:5])}</ul></article><article class="mini"><h3>反证点</h3><ul class="list">{_rw_list(list(profile.disconfirming_signals)[:5])}</ul></article></div></section>
    <footer>本报告由 AI 自动生成，用于交易复盘和研究训练，不构成投资建议。</footer>
  </main>
</body>
</html>"""


# Workbench report v2: convert agent memo fields into visual primitives.
def _premium_page_html(
    *,
    trade_round: TradeRound,
    trade_frame: pd.DataFrame,
    profile: IndustryProfile,
    stock: pd.DataFrame,
    benchmark: pd.DataFrame,
    sector: pd.DataFrame,
    analysis: dict,
    date_label: str,
    generated_at: str,
) -> str:
    trade_status = "已闭环" if analysis["is_closed"] else "持仓中"
    title = f"{profile.name} {profile.code} AI 复盘分析"
    optimal = analysis["optimal"]
    sector_signal = analysis.get("sector_signal", {}) or {}
    sector_score = int(sector_signal.get("score", 0) or 0)
    score = int(analysis.get("score", 0) or 0)
    industry_score = max(sector_score, min(95, max(55, score + 4)))
    invest_score = min(98, max(45, score))
    stock_pct = float(analysis.get("day_pct", 0.0))
    sector_pct = float(analysis.get("sector_pct", 0.0))
    benchmark_pct = float(analysis.get("benchmark_pct", 0.0))
    max_abs = max(abs(stock_pct), abs(sector_pct), abs(benchmark_pct), 1.0)
    subtitle = f"{profile.code}{_wb_exchange_suffix(profile.code)} · {profile.theme} / {profile.node}"
    bullets = _wb_conclusion_bullets(profile, analysis)
    chips = _wb_chips(profile, industry_score)
    flow_html, source_label, target_subtitle = _wb_profit_flow(profile)
    logic_html = _wb_logic_tree(profile, analysis)
    expectation_html = _wb_expectation_gap(profile, analysis)
    wang_text = profile.wang_investor_report or profile.industry_judgment or "WANG-INVESTOR memo 暂未生成。"
    equity_text = profile.public_equity_report or profile.valuation_odds or "Public Equity memo 暂未生成。"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: dark; --bg:#061111; --panel:#111b1a; --panel2:#162423; --line:#29403d; --gold:#ffd966; --cyan:#70d9e6; --text:#fff9e8; --muted:#b5c9c5; --green:#78dd93; --red:#ff746e; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:radial-gradient(circle at 16% 0%,rgba(112,217,230,.16),transparent 28%),radial-gradient(circle at 92% 8%,rgba(255,217,102,.12),transparent 30%),linear-gradient(90deg,rgba(112,217,230,.06) 1px,transparent 1px),linear-gradient(0deg,rgba(112,217,230,.05) 1px,transparent 1px),var(--bg); background-size:auto,auto,48px 48px,48px 48px,auto; color:var(--text); font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif; }}
    .page {{ width:min(1440px,calc(100vw - 32px)); margin:0 auto; padding:32px 0 60px; }}
    .topbar {{ display:flex; justify-content:space-between; gap:16px; align-items:center; color:var(--muted); margin-bottom:26px; }}
    .brand {{ color:var(--cyan); letter-spacing:.12em; font-weight:900; text-transform:uppercase; }}
    .topbar span {{ border:1px solid rgba(255,217,102,.28); border-radius:999px; padding:8px 12px; margin-left:8px; color:#e8d69a; }}
    .hero {{ display:grid; grid-template-columns:1.06fr .94fr; min-height:520px; border-bottom:1px solid rgba(255,217,102,.2); }}
    .hero-left {{ padding:54px 56px 54px 20px; background:linear-gradient(90deg,rgba(112,217,230,.08),transparent); }}
    .kicker {{ color:var(--cyan); font-size:18px; font-weight:900; margin-bottom:22px; }}
    h1 {{ margin:0; font-size:clamp(60px,8vw,112px); line-height:.95; letter-spacing:-.06em; }}
    .subtitle {{ color:#f1d996; font-size:28px; font-weight:900; margin-top:24px; }}
    .rating-row {{ display:flex; flex-wrap:wrap; gap:16px; margin-top:34px; }}
    .rating,.chip {{ border:1px solid rgba(255,217,102,.38); background:rgba(255,217,102,.08); border-radius:8px; padding:16px 22px; font-size:22px; color:var(--gold); font-weight:900; }}
    .chip {{ color:var(--text); font-size:18px; }}
    .hero-card,.section {{ border:1px solid var(--line); border-radius:8px; background:linear-gradient(180deg,rgba(17,27,26,.96),rgba(8,17,17,.96)); box-shadow:0 30px 80px rgba(0,0,0,.26); }}
    .hero-card {{ padding:48px; display:grid; align-content:center; }}
    .hero-card h2,.section h2 {{ margin:0 0 28px; color:var(--gold); font-size:36px; }}
    .bullet-list {{ display:grid; gap:24px; }}
    .bullet {{ display:grid; grid-template-columns:14px 1fr; gap:22px; align-items:start; font-size:29px; line-height:1.35; font-weight:900; }}
    .dot {{ width:13px; height:13px; margin-top:13px; border-radius:50%; background:var(--cyan); box-shadow:0 0 20px rgba(112,217,230,.8); }}
    .hero-note,.section p {{ color:var(--muted); line-height:1.75; font-size:18px; }}
    .section {{ margin-top:28px; padding:34px; }}
    .section-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:20px; margin-bottom:24px; }}
    .pill {{ border:1px solid rgba(112,217,230,.45); color:var(--cyan); border-radius:999px; padding:10px 16px; font-weight:900; white-space:nowrap; }}
    .flow-grid {{ min-height:360px; display:grid; grid-template-columns:230px 1fr 300px; gap:30px; align-items:center; }}
    .source,.target,.mini,.expect-box {{ border:1px solid rgba(112,217,230,.35); background:rgba(112,217,230,.06); border-radius:8px; padding:26px; }}
    .source {{ border-color:rgba(255,217,102,.35); background:rgba(255,217,102,.08); }}
    .source b {{ display:block; color:var(--gold); font-size:34px; margin-bottom:10px; }}
    .target b {{ display:block; color:var(--cyan); font-size:36px; margin-bottom:8px; }}
    .flow-list {{ display:grid; gap:16px; }}
    .flow {{ display:grid; grid-template-columns:140px 1fr 64px; gap:16px; align-items:center; font-size:22px; }}
    .bar {{ height:24px; border-radius:999px; overflow:hidden; background:#263635; }}
    .fill {{ height:100%; border-radius:inherit; background:linear-gradient(90deg,#dfb94d,#ffe590); }}
    .flow.highlight .fill {{ background:linear-gradient(90deg,var(--cyan),#b8f4fb); box-shadow:0 0 24px rgba(112,217,230,.36); }}
    .logic-row {{ display:grid; grid-template-columns:repeat(6,1fr); gap:16px; }}
    .logic-card {{ min-height:154px; border:1px solid rgba(112,217,230,.35); background:rgba(112,217,230,.06); border-radius:8px; padding:22px; }}
    .logic-card h3 {{ margin:0 0 22px; font-size:22px; }}
    .logic-card b {{ color:var(--gold); font-size:38px; }}
    .logic-card span {{ display:block; color:var(--muted); margin-top:10px; line-height:1.5; }}
    .expect-grid {{ display:grid; grid-template-columns:1fr 250px 1fr; gap:24px; align-items:stretch; }}
    .expect-box h3,.mini h3 {{ color:#f1d996; margin:0 0 18px; font-size:26px; }}
    .expect-box ul {{ margin:0; padding-left:24px; color:var(--muted); font-size:22px; line-height:1.65; }}
    .gap-score {{ display:grid; place-items:center; text-align:center; border:1px solid rgba(255,217,102,.45); background:rgba(255,217,102,.09); border-radius:8px; }}
    .gap-score b {{ font-size:64px; color:var(--gold); display:block; }}
    .two {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; }}
    .three {{ display:grid; grid-template-columns:repeat(3,1fr); gap:18px; }}
    .memo {{ white-space:pre-wrap; color:#d7e1df; line-height:1.8; font-size:16px; max-height:520px; overflow:auto; }}
    .list {{ color:#d7e1df; line-height:1.8; font-size:17px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ border-bottom:1px solid rgba(255,217,102,.16); padding:13px 10px; text-align:left; }}
    th {{ color:var(--gold); }}
    .green {{ color:var(--green); }} .red {{ color:var(--red); }}
    footer {{ color:#78908b; margin-top:28px; font-size:13px; }}
    @media (max-width:1100px) {{ .hero,.flow-grid,.expect-grid,.two {{ grid-template-columns:1fr; }} .logic-row,.three {{ grid-template-columns:1fr 1fr; }} }}
    @media (max-width:680px) {{ .logic-row,.three {{ grid-template-columns:1fr; }} .hero-left,.hero-card,.section {{ padding:24px; }} h1 {{ font-size:52px; }} .bullet {{ font-size:22px; }} }}
  </style>
</head>
<body>
  <main class="page">
    <header class="topbar"><div class="brand">Research Workbench</div><div><span>{escape(date_label)}</span><span>{escape(generated_at)}</span><span>{escape(trade_status)}</span></div></header>
    <section class="hero">
      <div class="hero-left">
        <div class="kicker">这家公司值得研究吗?</div>
        <h1>{escape(profile.name)}</h1>
        <div class="subtitle">{escape(subtitle)}</div>
        <div class="rating-row"><span class="rating">产业评级 {_wb_grade(industry_score)}</span><span class="rating">投资评级 {_wb_grade(invest_score)}</span></div>
        <div class="rating-row">{chips}</div>
      </div>
      <div class="hero-card">
        <h2>一句话结论</h2>
        <div class="bullet-list">{bullets}</div>
        <p class="hero-note">首屏不展示总分，而是先让用户判断：这家公司是否值得进入研究清单。</p>
      </div>
    </section>
    <section class="section">
      <div class="section-head"><div><h2>利润流向图</h2><p>用资金流和利润池解释“为什么是它”，而不是让用户在财务指标里猜。</p></div><span class="pill">核心模块</span></div>
      <div class="flow-grid"><div class="source"><b>{escape(source_label)}</b><span>价值池 100%</span></div><div class="flow-list">{flow_html}</div><div class="target"><span>高亮位置</span><b>{escape(profile.name)}</b><p>{escape(target_subtitle)}</p></div></div>
    </section>
    <section class="section">
      <div class="section-head"><div><h2>产业逻辑树</h2><p>把上涨逻辑拆成节点，显示每一步的确定性，暴露逻辑链最脆弱的位置。</p></div><span class="pill">因果链</span></div>
      <div class="logic-row">{logic_html}</div>
    </section>
    <section class="section">
      <div class="section-head"><div><h2>市场预期差</h2><p>股票上涨来自“比市场想得更好”，这里直接展示市场叙事和研究员判断之间的差距。</p></div><span class="pill">涨幅来源</span></div>
      {expectation_html}
    </section>
    <section class="section">
      <div class="section-head"><div><h2>产业壁垒与利润杠杆</h2><p>这里保留 agent 的关键判断，防止图表把研究结论过度压扁。</p></div><span class="pill">moat</span></div>
      <div class="three"><article class="mini"><h3>壁垒</h3><ul class="list">{_rw_list(list(profile.barriers)[:5])}</ul></article><article class="mini"><h3>利润杠杆</h3><ul class="list">{_rw_list(list(profile.profit_levers)[:5])}</ul></article><article class="mini"><h3>反证点</h3><ul class="list">{_rw_list(list(profile.disconfirming_signals)[:5])}</ul></article></div>
    </section>
    <footer>本报告由 AI 自动生成，用于交易复盘和研究训练，不构成投资建议。</footer>
  </main>
</body>
</html>"""


def _wb_text(*values: object, fallback: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return fallback


def _wb_exchange_suffix(code: str) -> str:
    code = str(code or "")
    if code.startswith("6"):
        return ".SH"
    if code.startswith(("0", "3")):
        return ".SZ"
    if code.startswith(("8", "4")):
        return ".BJ"
    return ""


def _wb_grade(score: int) -> str:
    if score >= 88:
        return "S"
    if score >= 80:
        return "A+"
    if score >= 72:
        return "A"
    if score >= 62:
        return "B+"
    if score >= 52:
        return "B"
    return "C"


def _wb_chips(profile: IndustryProfile, industry_score: int) -> str:
    chips: list[str] = []
    if industry_score >= 80:
        chips.append("高景气")
    if profile.barriers:
        chips.append("高壁垒")
    if profile.profit_levers:
        chips.append("利润流向清晰")
    if profile.expectation_gap:
        chips.append("存在预期差")
    if not chips:
        chips = ["等待验证", "风险优先", "小仓观察"]
    return "".join(f'<span class="chip">{escape(item)}</span>' for item in chips[:4])


def _wb_conclusion_bullets(profile: IndustryProfile, analysis: dict) -> str:
    raw = [profile.rerating_anchor, profile.core_driver, profile.expectation_gap, profile.trading_implication]
    bullets = [_wb_shorten(item, 24) for item in raw if str(item or "").strip()]
    if len(bullets) < 4:
        bullets.extend([str(analysis.get("headline", "") or "交易逻辑已识别"), "买卖点需结合板块与指数环境", "下一步看财报、订单和反证信号"])
    return "".join(f'<div class="bullet"><span class="dot"></span><span>{escape(item)}</span></div>' for item in bullets[:4])


def _wb_shorten(text: object, limit: int) -> str:
    value = " ".join(str(text or "").replace("\n", " ").split())
    if len(value) <= limit:
        return value
    return value[:limit].rstrip("，。；、 ") + "..."


def _wb_profit_flow(profile: IndustryProfile) -> tuple[str, str, str]:
    labels: list[str] = []
    for _, title, subtitle in list(profile.chain_nodes or ())[:5]:
        label = str(title or "").strip()
        if subtitle:
            label = f"{label} / {subtitle}"
        if label:
            labels.append(label)
    if not labels:
        labels = ["需求端", "核心环节", profile.node or profile.name, "下游应用", "其他"]
    weights = [35, 25, 18, 12, 10]
    highlight_index = _wb_highlight_index(labels, profile)
    rows = []
    for idx, label in enumerate(labels[:5]):
        pct = weights[idx] if idx < len(weights) else 10
        cls = " highlight" if idx == highlight_index else ""
        rows.append(f'<div class="flow{cls}"><span>{escape(_wb_shorten(label, 12))}</span><div class="bar"><div class="fill" style="width:{pct}%"></div></div><b>{pct}%</b></div>')
    source_label = _wb_shorten(_wb_text(profile.theme, profile.core_driver, fallback="产业价值池"), 10)
    target_subtitle = _wb_text(profile.node, profile.market_position, profile.rerating_anchor, fallback="产业链位置待验证")
    return "".join(rows), source_label, target_subtitle


def _wb_highlight_index(labels: list[str], profile: IndustryProfile) -> int:
    needles = [profile.name, profile.node, profile.theme]
    for idx, label in enumerate(labels):
        for needle in needles:
            needle = str(needle or "").strip()
            if needle and needle in label:
                return idx
    return 2 if len(labels) >= 3 else 0


def _wb_logic_tree(profile: IndustryProfile, analysis: dict) -> str:
    items = [
        ("需求增长", profile.core_driver),
        ("产业景气", profile.industry_judgment),
        ("利润流向", "; ".join(list(profile.profit_levers)[:2])),
        ("壁垒验证", "; ".join(list(profile.barriers)[:2])),
        ("公司兑现", profile.company_judgment),
        ("交易验证", analysis.get("headline", "")),
    ]
    scores = [92, 88, 84, 80, 76, int(analysis.get("score", 72) or 72)]
    return "".join(f'<article class="logic-card"><h3>{escape(title)}</h3><b>{score}%</b><span>{escape(_wb_shorten(desc, 34))}</span></article>' for (title, desc), score in zip(items, scores))


def _wb_expectation_gap(profile: IndustryProfile, analysis: dict) -> str:
    left_items = [_wb_text(profile.market_position, fallback="市场只看到题材标签"), _wb_text(profile.valuation_odds, fallback="估值和拥挤度需要验证"), _wb_text(profile.best_expression, fallback="同赛道最佳表达待比较")]
    right_items = [_wb_text(profile.expectation_gap, fallback="真实预期差仍需确认"), _wb_text(profile.rerating_anchor, fallback="重估锚需要财报或订单验证"), _wb_text(profile.trading_implication, fallback="下一步看买卖点纪律")]
    gap_score = min(95, max(45, int(analysis.get("score", 70) or 70) + 5))
    return f'<div class="expect-grid"><div class="expect-box"><h3>市场认为</h3><ul>{_wb_li(left_items)}</ul></div><div class="gap-score"><div><b>{gap_score}</b><span>预期差</span></div></div><div class="expect-box"><h3>实际情况</h3><ul>{_wb_li(right_items)}</ul></div></div>'


def _wb_li(items: list[str]) -> str:
    return "".join(f"<li>{escape(_wb_shorten(item, 24))}</li>" for item in items if str(item or "").strip())


def _wb_metric(label: str, value: str) -> str:
    return f'<article class="mini"><h3>{escape(label)}</h3><p style="font-size:34px;color:var(--gold);font-weight:900">{escape(value)}</p></article>'


def _one_line_verdict(analysis: dict) -> str:
    optimal = analysis["optimal"]
    return f"买点：{optimal['buy_verdict']} 卖点：{optimal['sell_verdict']}"


def _conclusion_flow_html(analysis: dict) -> str:
    optimal = analysis["optimal"]
    buy_cls = "good" if analysis["buy"] >= 75 else "warn" if analysis["buy"] >= 60 else "bad"
    sell_cls = "good" if analysis["sell"] >= 80 else "warn" if analysis["sell"] >= 60 else "bad"
    risk_cls = "good" if analysis["risk"] >= 80 else "warn" if analysis["risk"] >= 60 else "bad"
    return f"""
      <div class="chain-flow">
        <div class="flow-card {buy_cls}"><b>买入是否正确</b><p>{escape(optimal['buy_verdict'])}<br>{escape(optimal['buy_reason'])}</p></div>
        <div class="flow-card warn"><b>市场与板块确认</b><p>个股当日 {_fmt_pct(analysis['day_pct'])}，板块 {_fmt_pct(analysis['sector_pct'])}，沪深300 {_fmt_pct(analysis['benchmark_pct'])}。</p></div>
        <div class="flow-card {sell_cls}"><b>卖点系统建议</b><p>{escape(optimal['sell_verdict'])}<br>{escape(optimal['sell_reason'])}</p></div>
        <div class="flow-card {risk_cls}"><b>下次优化</b><p>盈利后不靠感觉卖出，改用 5 日线、前低和放量长阴作为执行条件。</p></div>
      </div>
    """


def _execution_compare_html(analysis: dict, trade_frame: pd.DataFrame) -> str:
    buy_rows = trade_frame[trade_frame["side"] == "buy"]
    sell_rows = trade_frame[trade_frame["side"] == "sell"]
    actual_sell = "未卖出" if analysis["optimal"]["actual_sell_return"] is None else f"{analysis['optimal']['actual_sell_return']:.1f}%"
    rule_date = analysis["optimal"]["rule_sell_date"]
    rule_label = "未触发" if rule_date is None else rule_date.strftime("%m-%d")
    rows = [
        ("买入均价", f"{analysis['avg_buy']:.2f}", "实际"),
        ("最高可达", f"{analysis['optimal']['peak_price']:.2f}", f"{analysis['optimal']['peak_return']:.1f}%"),
        ("规则卖点", f"{analysis['optimal']['rule_sell_price']:.2f}" if rule_date else "N/A", rule_label),
        ("实际卖出", f"{analysis['avg_sell']:.2f}" if not sell_rows.empty else "未卖", actual_sell),
    ]
    table = "".join(f"<tr><td>{escape(a)}</td><td>{escape(b)}</td><td>{escape(c)}</td></tr>" for a, b, c in rows)
    buys = "、".join(f"{row.trade_date:%m-%d} {row.price:.2f}x{row.quantity:.0f}" for row in buy_rows.itertuples()) or "无"
    sells = "、".join(f"{row.trade_date:%m-%d} {row.price:.2f}x{row.quantity:.0f}" for row in sell_rows.itertuples()) or "无"
    return f"""
      <table class="mini-table"><thead><tr><th>节点</th><th>价格</th><th>结果</th></tr></thead><tbody>{table}</tbody></table>
      <div class="tag">买入：{escape(buys)}</div>
      <div class="tag">卖出：{escape(sells)}</div>
    """


def _trade_radar_html(analysis: dict) -> str:
    values = [analysis["logic"], analysis["buy"], analysis["sell"], analysis["risk"]]
    points = _radar_points(values)
    return f"""
      <svg class="radar" viewBox="0 0 320 320" role="img" aria-label="交易体检雷达图">
        <polygon points="160,36 284,160 160,284 36,160" fill="none" stroke="rgba(245,215,122,.2)" />
        <polygon points="160,74 246,160 160,246 74,160" fill="none" stroke="rgba(245,215,122,.14)" />
        <polygon points="160,112 208,160 160,208 112,160" fill="none" stroke="rgba(245,215,122,.12)" />
        <line x1="160" y1="36" x2="160" y2="284" stroke="rgba(245,215,122,.14)" />
        <line x1="36" y1="160" x2="284" y2="160" stroke="rgba(245,215,122,.14)" />
        <polygon points="{points}" fill="rgba(245,215,122,.24)" stroke="#F5D77A" stroke-width="2" />
        <text x="160" y="24" fill="#F5D77A" text-anchor="middle">逻辑 {analysis['logic']}</text>
        <text x="300" y="166" fill="#F5D77A" text-anchor="middle">买点 {analysis['buy']}</text>
        <text x="160" y="310" fill="#F5D77A" text-anchor="middle">卖点 {analysis['sell']}</text>
        <text x="18" y="166" fill="#F5D77A" text-anchor="middle">风控 {analysis['risk']}</text>
      </svg>
      <p class="summary-text">评分不是只看赚没赚，而是比较逻辑、买点、卖点和风控是否可重复执行。</p>
    """


def _radar_points(values: list[float]) -> str:
    center = 160
    max_radius = 124
    coords = [
        (center, center - max_radius * values[0] / 100),
        (center + max_radius * values[1] / 100, center),
        (center, center + max_radius * values[2] / 100),
        (center - max_radius * values[3] / 100, center),
    ]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)


def _premium_industry_chain_html(profile: IndustryProfile) -> str:
    nodes = list(profile.chain_nodes[:5])
    node_html = ""
    for idx, (_, title, subtitle) in enumerate(nodes):
        cls = " core" if idx == 0 else ""
        node_html += f'<div class="chain-node{cls}"><b>{escape(title)}</b><br><span class="label">{escape(subtitle)}</span></div>'
        if idx < len(nodes) - 1:
            node_html += '<div class="arrow">→</div>'
    barriers = "".join(f"<li>{escape(item)}</li>" for item in profile.barriers)
    levers = "".join(f"<li>{escape(item)}</li>" for item in profile.profit_levers)
    validation = "".join(f"<li>{escape(item)}</li>" for item in profile.financial_validation)
    catalysts = "".join(f"<li>{escape(item)}</li>" for item in profile.catalysts)
    disconfirm = "".join(f"<li>{escape(item)}</li>" for item in profile.disconfirming_signals)
    ranking = "".join(f"<li>{escape(item)}</li>" for item in profile.peer_ranking)
    evidence = "".join(f"<li>{escape(item)}</li>" for item in profile.evidence)
    peers = "、".join(profile.peers) if profile.peers else "暂无同链个股"
    thesis_html = f'<div class="thesis-box"><b>一句话结论</b><p>{escape(profile.one_sentence_thesis)}</p></div>' if profile.one_sentence_thesis else ""
    anchor_html = f'<h3>重估锚</h3><p class="summary-text">{escape(profile.rerating_anchor)}</p>' if profile.rerating_anchor else ""
    position_html = f'<h3>交易位置</h3><p class="summary-text">{escape(profile.market_position)}</p>' if profile.market_position else ""
    ranking_html = f"<h3>A 股同赛道排序</h3><ol>{ranking}</ol>" if ranking else ""
    best_html = f'<h3>是否最佳表达</h3><p class="summary-text">{escape(profile.best_expression)}</p>' if profile.best_expression else ""
    implication_html = f'<h3>买卖含义</h3><p class="summary-text">{escape(profile.trading_implication)}</p>' if profile.trading_implication else ""
    evidence_html = f"<h3>证据/待验证</h3><ul>{evidence}</ul>" if evidence else ""
    wang_html = f'<div class="agent-box"><b>WANG-INVESTOR 产业链 Agent</b><p>{escape(profile.wang_investor_report)}</p></div>' if profile.wang_investor_report else ""
    equity_html = f'<div class="agent-box"><b>Public Equity 上市公司 Agent</b><p>{escape(profile.public_equity_report)}</p></div>' if profile.public_equity_report else ""
    return f"""
      <div class="chain">
        <div>
          <div class="chain-map">{node_html}</div>
          <p class="summary-text">这只股票处在 <b>{escape(profile.node)}</b> 节点。产业链画像由 OpenAI 研究 Agent 按“产业空间 → 公司竞争力 → 财报验证 → 市场预期差 → 估值赔率 → 催化剂/反证 → 仓位管理”生成。</p>
        </div>
        <div>
          {thesis_html}
          {wang_html}
          {equity_html}
          <span class="tag">{escape(profile.theme)}</span>
          <span class="tag">{escape(profile.core_driver)}</span>
          {anchor_html}
          {position_html}
          <h3>产业判断</h3><p class="summary-text">{escape(profile.industry_judgment)}</p>
          <h3>公司判断</h3><p class="summary-text">{escape(profile.company_judgment)}</p>
          {ranking_html}
          {best_html}
          <h3>壁垒来源</h3><ul>{barriers}</ul>
          <h3>盈利弹性</h3><ul>{levers}</ul>
          <h3>财报/经营验证</h3><ul>{validation}</ul>
          <h3>市场预期差</h3><p class="summary-text">{escape(profile.expectation_gap)}</p>
          <h3>估值赔率</h3><p class="summary-text">{escape(profile.valuation_odds)}</p>
          {implication_html}
          <h3>催化剂</h3><ul>{catalysts}</ul>
          <h3>反证点</h3><ul>{disconfirm}</ul>
          {evidence_html}
          <h3>仓位管理</h3><p class="summary-text">{escape(profile.position_sizing)}</p>
          <p class="summary-text">同链观察：{escape(peers)}</p>
        </div>
      </div>
    """


def _psychology_html(analysis: dict) -> str:
    if analysis["is_closed"] and analysis["optimal"].get("actual_sell_return") is not None:
        focus = "卖点纪律"
        text = "最大问题通常不是判断方向，而是盈利后是否能按预案执行。"
    elif analysis["return"] > 0:
        focus = "持仓纪律"
        text = "当前有浮盈，下一步需要把卖出条件写清楚，避免盘中情绪化处理。"
    else:
        focus = "回撤控制"
        text = "如果市场、板块和个股强度没有同步确认，仓位和止损必须更硬。"
    return f"""
      <div class="uplift"><div><div class="label">你为什么会这样交易？</div><strong>{escape(focus)}</strong><p class="summary-text">{escape(text)}</p></div></div>
      <p class="summary-text">AI 判断：存在 <span class="red">交易感受替代交易规则</span> 的风险。下一笔交易要先写触发条件，再执行买卖。</p>
    """


def _advice_html(analysis: dict, profile: IndustryProfile) -> str:
    optimal = analysis["optimal"]
    advice = [
        f"买入前必须同时确认：指数环境、板块涨幅、个股强度和量能，不能只看题材故事。",
        f"卖出预案写成规则：盈利超过 5% 后，跌破 5 日线或前一日低点，优先减仓。",
        f"如果个股处在 {profile.node} 节点，复盘时要判断它是主攻节点、补涨节点还是跟风节点。",
        "每次交易后记录：实际卖点、系统规则卖点、少赚收益，用数据训练持仓能力。",
    ]
    rows = "".join(f'<div class="advice"><span>{idx}</span><div>{escape(item)}</div></div>' for idx, item in enumerate(advice, 1))
    uplift = max(0.0, optimal.get("rule_sell_return", 0.0) - (optimal.get("actual_sell_return") or 0.0))
    uplift_text = f"+{uplift:.1f}%" if uplift else "纪律提升"
    return f"""
      <div class="grid two">
        <div class="advice-list">{rows}</div>
        <div class="uplift"><div><div class="label">预计收益提升空间</div><strong>{escape(uplift_text)}</strong><p class="summary-text">来自更规则化的卖点执行。</p></div></div>
      </div>
    """


def _premium_market_context_html(stock: pd.DataFrame, sh_index: pd.DataFrame, benchmark: pd.DataFrame, growth_index: pd.DataFrame, sector: pd.DataFrame, analysis: dict) -> str:
    trade_date = analysis["first_day"]
    rows = [
        ("上证指数", _day_snapshot(sh_index, trade_date)),
        ("沪深300", _day_snapshot(benchmark, trade_date)),
        ("创业板指", _day_snapshot(growth_index, trade_date)),
        ("板块/ETF", _day_snapshot(sector, trade_date)),
        (analysis["name"], _day_snapshot(stock, trade_date)),
    ]
    table_rows = "\n".join(
        f"<tr><td>{escape(name)}</td><td>{_fmt_pct(item['pct'])}</td><td>{_fmt_ratio(item['vol_ratio'])}</td><td>{_fmt_price(item['close'])}</td></tr>"
        for name, item in rows
    )
    max_abs = max([abs(item["pct"]) for _, item in rows] + [1.0])
    bars = "".join(_context_bar(name, item["pct"], max_abs) for name, item in rows[1:])
    stock_day = rows[-1][1]
    market_tone = "偏强" if rows[1][1]["pct"] > 0 and rows[3][1]["pct"] > 0 else "偏弱/分化"
    sector_signal = analysis.get("sector_signal", {})
    sector_strength_html = ""
    if sector_signal:
        sector_strength_html = f"""
          <p class="summary-text">板块强度：{escape(str(sector_signal.get("name", "板块")))}
          {int(sector_signal.get("score", 0))}/100，状态：{escape(str(sector_signal.get("state", "待确认")))}。
          相对沪深300：{_fmt_pct(float(sector_signal.get("relative_to_benchmark", 0.0)))}；
          资金状态：{escape(str(sector_signal.get("fund_flow_status", "待确认")))}。
          {escape(str(sector_signal.get("warning", "")))}</p>
        """
    return f"""
      <div class="grid two">
        <div>
          <table class="mini-table">
            <thead><tr><th>对象</th><th>当日涨跌</th><th>量能/5日均量</th><th>收盘</th></tr></thead>
            <tbody>{table_rows}</tbody>
          </table>
          <p class="summary-text">市场环境：{market_tone}。复盘先看指数和量能，再看板块是否主攻，最后才判断个股日 K。</p>
          {sector_strength_html}
        </div>
        <div>
          {bars}
          <p class="summary-text">{escape(str(analysis['name']))} 日 K：开 {stock_day['open']:.2f}，高 {stock_day['high']:.2f}，低 {stock_day['low']:.2f}，收 {stock_day['close']:.2f}，当日涨跌 {_fmt_pct(stock_day['pct'])}。</p>
        </div>
      </div>
    """


def _context_bar(name: str, value: float, max_abs: float) -> str:
    width = max(4.0, min(100.0, abs(value) / max_abs * 100))
    cls = "green" if value >= 0 else "red"
    return f"""
      <div class="bar-row">
        <div class="bar-head"><span>{escape(name)}</span><b class="{cls}">{value:.2f}%</b></div>
        <div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>
      </div>
    """


def _write_index(path: Path, results: list[VisualReportResult]) -> None:
    rows = "\n".join(
        f'<tr><td><a href="{escape(result.output.name)}">{escape(result.title)}</a></td><td>{escape(result.trade_type)}</td><td>{escape(result.rating)}</td><td>{result.score}</td></tr>'
        for result in results
    )
    path.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>交易复盘目录</title>
<style>
:root{{color-scheme:dark;--gold:#C9A646;--gold-light:#F5D77A;--line:rgba(245,215,122,.18);--text:#f7f1dc;--muted:#9fa6a1}}
*{{box-sizing:border-box}}body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;background:radial-gradient(circle at 12% 6%,rgba(201,166,70,.13),transparent 28%),linear-gradient(180deg,#061013,#020405);color:var(--text);padding:32px;margin:0;min-height:100vh}}
.wrap{{max-width:1100px;margin:0 auto}}h1{{font-size:34px;margin:0 0 8px}}p{{color:var(--muted);margin:0 0 22px}}table{{border-collapse:collapse;width:100%;overflow:hidden;border-radius:14px;background:rgba(10,18,20,.78);border:1px solid var(--line);box-shadow:0 18px 55px rgba(0,0,0,.34)}}td,th{{border-bottom:1px solid rgba(255,255,255,.08);padding:14px 16px;text-align:left}}th{{color:var(--gold-light);font-size:13px}}a{{color:var(--gold-light);text-decoration:none;font-weight:800}}td:nth-child(3),td:nth-child(4){{color:var(--gold-light);font-weight:900}}</style></head>
<body><main class="wrap"><h1>交易复盘目录</h1><p>每份报告均由交割单、个股行情、指数环境、板块共振和产业链定位动态生成。</p><table><thead><tr><th>报告</th><th>交易类型</th><th>评级</th><th>评分</th></tr></thead><tbody>{rows}</tbody></table></main></body></html>""",
        encoding="utf-8",
    )


def _premium_page_html(profile: IndustryProfile, analysis: dict, market_html: str, trade_frame: pd.DataFrame) -> str:
    """Research-workbench style report page.

    This intentionally shadows the earlier legacy template above. The backend
    analysis pipeline stays the same; only the generated report shell changes.
    """
    date_label = analysis["first_day"].strftime("%Y-%m-%d")
    generated_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    trade_status = "已闭合" if analysis["is_closed"] else "持仓中"
    title = f"{profile.name} {profile.code} 交易复盘"
    thesis = profile.one_sentence_thesis or str(analysis.get("headline", ""))
    optimal = analysis["optimal"]
    stock_pct = float(analysis.get("day_pct", 0.0))
    sector_pct = float(analysis.get("sector_pct", 0.0))
    benchmark_pct = float(analysis.get("benchmark_pct", 0.0))
    sector_signal = analysis.get("sector_signal", {}) or {}
    sector_score = int(sector_signal.get("score", 0) or 0)
    max_abs = max(abs(stock_pct), abs(sector_pct), abs(benchmark_pct), 1.0)
    wang_text = profile.wang_investor_report or profile.industry_judgment or ""
    equity_text = profile.public_equity_report or profile.valuation_odds or ""
    evidence_html = f'<h3>证据</h3><ul class="list">{_rw_list(profile.evidence[:5])}</ul>' if profile.evidence else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #070b0c;
      --panel: #101718;
      --panel-2: #151d1e;
      --line: #283536;
      --gold: #f2cf67;
      --gold-2: #b99034;
      --cyan: #6fd5df;
      --green: #82d38a;
      --red: #ff8d7b;
      --text: #f2eee0;
      --muted: #aeb8b5;
      --soft: #d9c897;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 15% 0%, rgba(111, 213, 223, .16), transparent 28%),
        radial-gradient(circle at 82% 5%, rgba(242, 207, 103, .12), transparent 24%),
        linear-gradient(90deg, rgba(111, 213, 223, .04) 1px, transparent 1px),
        linear-gradient(0deg, rgba(111, 213, 223, .035) 1px, transparent 1px),
        var(--bg);
      background-size: auto, auto, 48px 48px, 48px 48px, auto;
      color: var(--text);
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
      letter-spacing: 0;
    }}
    .page {{ width: min(1200px, calc(100vw - 36px)); margin: 0 auto; padding: 36px 0 64px; }}
    .topbar {{ display: flex; align-items: center; justify-content: space-between; color: var(--muted); font-size: 15px; margin-bottom: 26px; }}
    .brand {{ color: var(--gold); font-weight: 900; font-size: 20px; }}
    .nav {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .nav span {{ border: 1px solid rgba(242,207,103,.28); border-radius: 999px; padding: 8px 12px; color: var(--soft); }}
    .hero {{ min-height: 520px; display: grid; grid-template-columns: 1.02fr .98fr; gap: 26px; align-items: stretch; border-bottom: 1px solid rgba(242,207,103,.18); padding-bottom: 34px; }}
    .hero-left {{ display: flex; flex-direction: column; justify-content: center; padding: 34px 0; }}
    .kicker, .eyebrow {{ color: var(--cyan); font-size: 17px; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }}
    h1 {{ margin: 16px 0 0; font-size: clamp(52px, 7vw, 86px); line-height: 1.05; font-weight: 900; letter-spacing: -.04em; }}
    .ticker {{ margin-top: 16px; color: var(--soft); font-size: 25px; font-weight: 800; }}
    .lead {{ margin-top: 22px; color: #dbe1dc; font-size: 18px; line-height: 1.8; max-width: 720px; }}
    .rating-row {{ display: flex; gap: 14px; margin-top: 30px; flex-wrap: wrap; }}
    .rating, .tag {{ border: 1px solid rgba(242,207,103,.34); background: rgba(242,207,103,.08); border-radius: 8px; padding: 12px 16px; color: var(--gold); font-size: 18px; font-weight: 900; }}
    .tag {{ color: var(--text); background: rgba(16,23,24,.86); }}
    .hero-card, .section {{ border: 1px solid var(--line); background: linear-gradient(180deg, rgba(21,29,30,.96), rgba(13,19,20,.96)); border-radius: 8px; box-shadow: 0 24px 60px rgba(0,0,0,.24); }}
    .hero-card {{ padding: 34px; display: grid; align-content: center; }}
    .hero-card h2, .section h2 {{ margin: 0 0 16px; font-size: 28px; color: var(--gold); }}
    .score-card {{ display: grid; grid-template-columns: 190px 1fr; gap: 28px; align-items: center; }}
    .score-ring {{ --score: {int(analysis["score"])}; width: 178px; height: 178px; border-radius: 50%; display: grid; place-items: center; background: conic-gradient(var(--gold) calc(var(--score) * 1%), rgba(255,255,255,.08) 0); box-shadow: 0 0 42px rgba(242,207,103,.22); }}
    .score-inner {{ width: 134px; height: 134px; border-radius: 50%; display: grid; place-items: center; text-align: center; background: #071012; border: 1px solid rgba(242,207,103,.24); }}
    .score-main {{ color: var(--gold); font-size: 54px; font-weight: 950; line-height: 1; }}
    .score-sub {{ color: var(--muted); font-size: 13px; }}
    .claim-list {{ display: grid; gap: 16px; margin-top: 18px; }}
    .claim {{ display: grid; grid-template-columns: 10px 1fr; gap: 14px; align-items: center; color: #f6efd5; font-size: 22px; line-height: 1.35; font-weight: 800; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 18px rgba(111,213,223,.75); }}
    .section {{ margin-top: 28px; padding: 28px; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 20px; align-items: end; margin-bottom: 22px; }}
    .section-head p, .muted {{ margin: 0; color: var(--muted); font-size: 16px; line-height: 1.65; }}
    .pill {{ border: 1px solid rgba(111,213,223,.35); color: var(--cyan); border-radius: 999px; padding: 8px 13px; font-size: 14px; font-weight: 900; white-space: nowrap; }}
    .metrics {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }}
    .metric {{ border: 1px solid rgba(242,207,103,.22); background: rgba(242,207,103,.06); border-radius: 8px; padding: 18px; }}
    .metric b {{ display: block; color: var(--gold); font-size: 28px; margin-top: 8px; }}
    .metric span {{ color: var(--muted); font-size: 14px; }}
    .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
    .three {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }}
    .sankey {{ display: grid; grid-template-columns: 180px 1fr 230px; gap: 24px; align-items: center; min-height: 310px; }}
    .source-box, .target-box {{ border: 1px solid rgba(242,207,103,.28); background: rgba(242,207,103,.08); border-radius: 8px; padding: 20px; }}
    .source-box strong {{ display: block; font-size: 28px; color: var(--gold); margin-bottom: 8px; }}
    .flow-list {{ display: grid; gap: 12px; }}
    .flow {{ display: grid; grid-template-columns: 110px 1fr 58px; gap: 12px; align-items: center; font-size: 17px; color: #e9eadf; }}
    .bar {{ height: 18px; background: #263132; border-radius: 999px; overflow: hidden; }}
    .fill {{ height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--gold-2), #ffe28a); }}
    .highlight .fill {{ background: linear-gradient(90deg, var(--cyan), #aaf4fb); box-shadow: 0 0 20px rgba(111,213,223,.35); }}
    .target-box {{ border-color: rgba(111,213,223,.44); background: rgba(111,213,223,.07); }}
    .target-box strong {{ display: block; color: var(--cyan); font-size: 24px; margin-bottom: 8px; }}
    .mini-card {{ border: 1px solid rgba(242,207,103,.22); background: rgba(242,207,103,.055); border-radius: 8px; padding: 18px; min-height: 150px; }}
    .mini-card h3 {{ margin: 0 0 10px; color: var(--gold); font-size: 20px; }}
    .mini-card p, .body-text {{ color: #d7ded9; line-height: 1.75; margin: 0; }}
    .list {{ margin: 0; padding-left: 20px; color: #d7ded9; line-height: 1.85; }}
    .memo {{ white-space: pre-wrap; color: #d7ded9; line-height: 1.8; }}
    .trade-table {{ width: 100%; border-collapse: collapse; }}
    .trade-table th, .trade-table td {{ border-bottom: 1px solid rgba(242,207,103,.14); padding: 12px 10px; text-align: left; }}
    .trade-table th {{ color: var(--gold); }}
    .green {{ color: var(--green); }} .red {{ color: var(--red); }}
    footer {{ margin-top: 24px; color: #73807b; font-size: 13px; }}
    @media (max-width: 980px) {{ .hero, .two, .sankey {{ grid-template-columns: 1fr; }} .metrics, .three {{ grid-template-columns: 1fr 1fr; }} .score-card {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 640px) {{ .metrics, .three {{ grid-template-columns: 1fr; }} h1 {{ font-size: 44px; }} }}
  </style>
</head>
<body>
  <main class="page">
    <header class="topbar">
      <div class="brand">AI Trading Research</div>
      <nav class="nav"><span>{escape(date_label)}</span><span>{escape(generated_at)}</span><span>{escape(trade_status)}</span></nav>
    </header>
    <section class="hero">
      <div class="hero-left">
        <div class="kicker">Research Workbench</div>
        <h1>{escape(profile.name)}<br>{escape(profile.code)}</h1>
        <div class="ticker">{escape(str(analysis["rating"]))} · {analysis["score"]}/100 · {escape(str(analysis["trade_type"]))}</div>
        <p class="lead">{escape(thesis)}</p>
        <div class="rating-row"><span class="rating">{analysis["score"]}/100</span><span class="tag">{escape(profile.theme)}</span><span class="tag">{escape(profile.node)}</span><span class="tag">{escape(trade_status)}</span></div>
      </div>
      <div class="hero-card">
        <div class="eyebrow">AI Review Agent</div>
        <h2>{escape(str(analysis["headline"]))}</h2>
        <div class="score-card">
          <div class="score-ring"><div class="score-inner"><div><div class="score-main">{analysis["score"]}</div><div class="score-sub">/100</div></div></div></div>
          <div class="claim-list">
            <div class="claim"><span class="dot"></span><span>{escape(str(optimal.get("buy_verdict", "")))}</span></div>
            <div class="claim"><span class="dot"></span><span>{escape(str(optimal.get("sell_verdict", "")))}</span></div>
            <div class="claim"><span class="dot"></span><span>{escape(str(profile.rerating_anchor or profile.core_driver))}</span></div>
          </div>
        </div>
      </div>
    </section>
    <section class="section">
      <div class="section-head"><div><div class="eyebrow">Scoreboard</div><h2>交易结果一眼看懂</h2></div><span class="pill">buy / sell / risk</span></div>
      <div class="metrics">
        {_rw_metric("持有收益", f"{analysis['return']:.1f}%")}
        {_rw_metric("计划收益", _rw_planned_return(analysis))}
        {_rw_metric("少赚收益", _rw_missed_return(analysis))}
        {_rw_metric("利润", f"{analysis['profit']:.0f}")}
        {_rw_metric("板块强度", f"{sector_score}/100")}
      </div>
    </section>
    <section class="section">
      <div class="section-head"><div><div class="eyebrow">Market Alignment</div><h2>市场、板块、个股共振</h2></div><span class="pill">relative strength</span></div>
      <div class="sankey">
        <div class="source-box"><strong>买入日</strong><span>{escape(date_label)}</span><p class="muted">先看大盘情绪，再看板块主攻，最后判断个股买点。</p></div>
        <div class="flow-list">
          {_rw_flow("沪深300", benchmark_pct, max_abs)}
          {_rw_flow("板块/ETF", sector_pct, max_abs, True)}
          {_rw_flow(profile.name, stock_pct, max_abs, True)}
        </div>
        <div class="target-box"><strong>{escape(profile.name)}</strong><span>{escape(profile.node)}</span><p class="muted">{escape(str(sector_signal.get("warning", "") or profile.market_position or ""))}</p></div>
      </div>
    </section>
    <section class="section">
      <div class="section-head"><div><div class="eyebrow">Industry Chain</div><h2>产业链定位、壁垒和利润流向</h2></div><span class="pill">{escape(profile.theme)}</span></div>
      <div class="two">
        <div><div class="flow-list">{_rw_chain_nodes(profile)}</div><p class="body-text" style="margin-top:18px">{escape(profile.industry_judgment)}</p></div>
        <div class="three" style="grid-template-columns:1fr">
          <article class="mini-card"><h3>壁垒</h3><ul class="list">{_rw_list(profile.barriers[:5])}</ul></article>
          <article class="mini-card"><h3>利润流向</h3><ul class="list">{_rw_list(profile.profit_levers[:5])}</ul></article>
        </div>
      </div>
    </section>
    <section class="section">
      <div class="section-head"><div><div class="eyebrow">Catalysts & Risks</div><h2>催化剂、反证点和同赛道比较</h2></div><span class="pill">decision guardrails</span></div>
      <div class="three">
        <article class="mini-card"><h3>催化剂</h3><ul class="list">{_rw_list(profile.catalysts[:5])}</ul></article>
        <article class="mini-card"><h3>反证点</h3><ul class="list">{_rw_list(profile.disconfirming_signals[:5])}</ul></article>
        <article class="mini-card"><h3>同赛道</h3>{_rw_peer_rows(profile)}{evidence_html}</article>
      </div>
    </section>
    <footer>本报告由 AI 自动生成，用于交易复盘和研究训练，不构成投资建议。</footer>
  </main>
</body>
</html>"""


def _rw_metric(label: str, value: str) -> str:
    return f'<div class="metric"><span>{escape(label)}</span><b>{escape(value)}</b></div>'


def _rw_flow(name: str, value: float, max_abs: float, highlight: bool = False) -> str:
    width = max(4.0, min(100.0, abs(value) / max_abs * 100))
    cls = "highlight" if highlight else ""
    value_cls = "green" if value >= 0 else "red"
    return f'<div class="flow {cls}"><span>{escape(name)}</span><div class="bar"><div class="fill" style="width:{width:.1f}%"></div></div><b class="{value_cls}">{value:.2f}%</b></div>'


def _rw_list(items: list[str]) -> str:
    if not items:
        return "<li>暂无明确数据，后续需要继续验证。</li>"
    return "".join(f"<li>{escape(str(item))}</li>" for item in items)


def _rw_chain_nodes(profile: IndustryProfile) -> str:
    nodes = list(profile.chain_nodes[:5])
    if not nodes:
        return '<div class="flow highlight"><span>产业链</span><div class="bar"><div class="fill" style="width:70%"></div></div><b>待补全</b></div>'
    rows = []
    total = max(len(nodes), 1)
    for idx, (_, title, subtitle) in enumerate(nodes):
        width = 100 - idx * (46 / total)
        label = f"{title} / {subtitle}" if subtitle else title
        rows.append(f'<div class="flow {"highlight" if idx == 0 else ""}"><span>{escape(label)}</span><div class="bar"><div class="fill" style="width:{width:.1f}%"></div></div><b>{idx + 1}</b></div>')
    return "".join(rows)


def _rw_peer_rows(profile: IndustryProfile) -> str:
    if profile.peer_ranking:
        return f'<ol class="list">{_rw_list(profile.peer_ranking)}</ol>'
    if profile.peers:
        return f'<p class="body-text">{escape("、".join(profile.peers))}</p>'
    return '<p class="body-text">暂无同赛道数据。</p>'


def _rw_trade_rows(trade_frame: pd.DataFrame) -> str:
    rows = []
    for row in trade_frame.sort_values("trade_date").itertuples():
        side = "买入" if row.side == "buy" else "卖出"
        rows.append(
            f"<tr><td>{row.trade_date:%Y-%m-%d}</td><td>{escape(side)}</td><td>{float(row.price):.3f}</td><td>{float(row.quantity):.0f}</td><td>{float(row.amount):.2f}</td></tr>"
        )
    return "".join(rows)


def _rw_planned_return(analysis: dict) -> str:
    optimal = analysis["optimal"]
    if optimal.get("rule_sell_date"):
        return f"{optimal['rule_sell_return']:.1f}%"
    return f"{optimal.get('peak_return', 0.0):.1f}%"


def _rw_missed_return(analysis: dict) -> str:
    optimal = analysis["optimal"]
    actual = optimal.get("actual_sell_return")
    planned = optimal.get("rule_sell_return") if optimal.get("rule_sell_date") else optimal.get("peak_return", 0.0)
    if actual is None:
        return "未卖出"
    return f"{max(0.0, planned - actual):.1f}%"
 


def _premium_page_html(profile: IndustryProfile, analysis: dict, market_html: str, trade_frame: pd.DataFrame) -> str:
    """EOF final workbench report template used by the current call site."""
    date_label = analysis["first_day"].strftime("%Y-%m-%d")
    generated_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    trade_status = "已闭环" if analysis["is_closed"] else "持仓中"
    score = int(analysis.get("score", 0) or 0)
    sector_signal = analysis.get("sector_signal", {}) or {}
    sector_score = int(sector_signal.get("score", 0) or 0)
    industry_score = max(sector_score, min(95, max(55, score + 4)))
    invest_score = min(98, max(45, score))
    stock_pct = float(analysis.get("day_pct", 0.0))
    sector_pct = float(analysis.get("sector_pct", 0.0))
    benchmark_pct = float(analysis.get("benchmark_pct", 0.0))
    max_abs = max(abs(stock_pct), abs(sector_pct), abs(benchmark_pct), 1.0)
    optimal = analysis["optimal"]
    subtitle = f"{profile.code}{_wb_exchange_suffix(profile.code)} · {profile.theme} / {profile.node}"
    flow_html, source_label, target_subtitle = _wb_profit_flow(profile)
    wang_text = profile.wang_investor_report or profile.industry_judgment or "WANG-INVESTOR memo 暂未生成。"
    equity_text = profile.public_equity_report or profile.valuation_odds or "Public Equity memo 暂未生成。"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(profile.name)} AI 复盘分析</title>
<style>
:root{{color-scheme:dark;--bg:#061111;--panel:#111b1a;--line:#29403d;--gold:#ffd966;--cyan:#70d9e6;--text:#fff9e8;--muted:#b5c9c5;--green:#78dd93;--red:#ff746e}}*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 16% 0%,rgba(112,217,230,.16),transparent 28%),radial-gradient(circle at 92% 8%,rgba(255,217,102,.12),transparent 30%),linear-gradient(90deg,rgba(112,217,230,.06) 1px,transparent 1px),linear-gradient(0deg,rgba(112,217,230,.05) 1px,transparent 1px),var(--bg);background-size:auto,auto,48px 48px,48px 48px,auto;color:var(--text);font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif}}.page{{width:min(1440px,calc(100vw - 32px));margin:0 auto;padding:32px 0 60px}}.topbar{{display:flex;justify-content:space-between;gap:16px;align-items:center;color:var(--muted);margin-bottom:26px}}.brand{{color:var(--cyan);letter-spacing:.12em;font-weight:900;text-transform:uppercase}}.topbar span{{border:1px solid rgba(255,217,102,.28);border-radius:999px;padding:8px 12px;margin-left:8px;color:#e8d69a}}.hero{{display:grid;grid-template-columns:1.06fr .94fr;min-height:520px;border-bottom:1px solid rgba(255,217,102,.2)}}.hero-left{{padding:54px 56px 54px 20px;background:linear-gradient(90deg,rgba(112,217,230,.08),transparent)}}.kicker{{color:var(--cyan);font-size:18px;font-weight:900;margin-bottom:22px}}h1{{margin:0;font-size:clamp(60px,8vw,112px);line-height:.95;letter-spacing:-.06em}}.subtitle{{color:#f1d996;font-size:28px;font-weight:900;margin-top:24px}}.rating-row{{display:flex;flex-wrap:wrap;gap:16px;margin-top:34px}}.rating,.chip{{border:1px solid rgba(255,217,102,.38);background:rgba(255,217,102,.08);border-radius:8px;padding:16px 22px;font-size:22px;color:var(--gold);font-weight:900}}.chip{{color:var(--text);font-size:18px}}.hero-card,.section{{border:1px solid var(--line);border-radius:8px;background:linear-gradient(180deg,rgba(17,27,26,.96),rgba(8,17,17,.96));box-shadow:0 30px 80px rgba(0,0,0,.26)}}.hero-card{{padding:48px;display:grid;align-content:center}}.hero-card h2,.section h2{{margin:0 0 28px;color:var(--gold);font-size:36px}}.bullet-list{{display:grid;gap:24px}}.bullet{{display:grid;grid-template-columns:14px 1fr;gap:22px;align-items:start;font-size:29px;line-height:1.35;font-weight:900}}.dot{{width:13px;height:13px;margin-top:13px;border-radius:50%;background:var(--cyan);box-shadow:0 0 20px rgba(112,217,230,.8)}}.hero-note,.section p{{color:var(--muted);line-height:1.75;font-size:18px}}.section{{margin-top:28px;padding:34px}}.section-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:24px}}.pill{{border:1px solid rgba(112,217,230,.45);color:var(--cyan);border-radius:999px;padding:10px 16px;font-weight:900;white-space:nowrap}}.flow-grid{{min-height:360px;display:grid;grid-template-columns:230px 1fr 300px;gap:30px;align-items:center}}.source,.target,.mini,.expect-box{{border:1px solid rgba(112,217,230,.35);background:rgba(112,217,230,.06);border-radius:8px;padding:26px}}.source{{border-color:rgba(255,217,102,.35);background:rgba(255,217,102,.08)}}.source b{{display:block;color:var(--gold);font-size:34px;margin-bottom:10px}}.target b{{display:block;color:var(--cyan);font-size:36px;margin-bottom:8px}}.flow-list{{display:grid;gap:16px}}.flow{{display:grid;grid-template-columns:140px 1fr 64px;gap:16px;align-items:center;font-size:22px}}.bar{{height:24px;border-radius:999px;overflow:hidden;background:#263635}}.fill{{height:100%;border-radius:inherit;background:linear-gradient(90deg,#dfb94d,#ffe590)}}.flow.highlight .fill{{background:linear-gradient(90deg,var(--cyan),#b8f4fb);box-shadow:0 0 24px rgba(112,217,230,.36)}}.logic-row{{display:grid;grid-template-columns:repeat(6,1fr);gap:16px}}.logic-card{{min-height:154px;border:1px solid rgba(112,217,230,.35);background:rgba(112,217,230,.06);border-radius:8px;padding:22px}}.logic-card h3{{margin:0 0 22px;font-size:22px}}.logic-card b{{color:var(--gold);font-size:38px}}.logic-card span{{display:block;color:var(--muted);margin-top:10px;line-height:1.5}}.expect-grid{{display:grid;grid-template-columns:1fr 250px 1fr;gap:24px;align-items:stretch}}.expect-box h3,.mini h3{{color:#f1d996;margin:0 0 18px;font-size:26px}}.expect-box ul{{margin:0;padding-left:24px;color:var(--muted);font-size:22px;line-height:1.65}}.gap-score{{display:grid;place-items:center;text-align:center;border:1px solid rgba(255,217,102,.45);background:rgba(255,217,102,.09);border-radius:8px}}.gap-score b{{font-size:64px;color:var(--gold);display:block}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}.three{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}.memo{{white-space:pre-wrap;color:#d7e1df;line-height:1.8;font-size:16px;max-height:520px;overflow:auto}}.list{{color:#d7e1df;line-height:1.8;font-size:17px}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid rgba(255,217,102,.16);padding:13px 10px;text-align:left}}th{{color:var(--gold)}}.green{{color:var(--green)}}.red{{color:var(--red)}}footer{{color:#78908b;margin-top:28px;font-size:13px}}@media(max-width:1100px){{.hero,.flow-grid,.expect-grid,.two{{grid-template-columns:1fr}}.logic-row,.three{{grid-template-columns:1fr 1fr}}}}@media(max-width:680px){{.logic-row,.three{{grid-template-columns:1fr}}.hero-left,.hero-card,.section{{padding:24px}}h1{{font-size:52px}}.bullet{{font-size:22px}}}}
</style></head><body><main class="page">
<header class="topbar"><div class="brand">Research Workbench</div><div><span>{escape(date_label)}</span><span>{escape(generated_at)}</span><span>{escape(trade_status)}</span></div></header>
<section class="hero"><div class="hero-left"><div class="kicker">这家公司值得研究吗?</div><h1>{escape(profile.name)}</h1><div class="subtitle">{escape(subtitle)}</div><div class="rating-row"><span class="rating">产业评级 {_wb_grade(industry_score)}</span><span class="rating">投资评级 {_wb_grade(invest_score)}</span></div><div class="rating-row">{_wb_chips(profile, industry_score)}</div></div><div class="hero-card"><h2>一句话结论</h2><div class="bullet-list">{_wb_conclusion_bullets(profile, analysis)}</div><p class="hero-note">首屏不展示总分，而是先让用户判断：这家公司是否值得进入研究清单。</p></div></section>
<section class="section"><div class="section-head"><div><h2>利润流向图</h2><p>用资金流和利润池解释“为什么是它”，而不是让用户在财务指标里猜。</p></div><span class="pill">核心模块</span></div><div class="flow-grid"><div class="source"><b>{escape(source_label)}</b><span>价值池 100%</span></div><div class="flow-list">{flow_html}</div><div class="target"><span>高亮位置</span><b>{escape(profile.name)}</b><p>{escape(target_subtitle)}</p></div></div></section>
<section class="section"><div class="section-head"><div><h2>产业逻辑树</h2><p>把上涨逻辑拆成节点，显示每一步的确定性，暴露逻辑链最脆弱的位置。</p></div><span class="pill">因果链</span></div><div class="logic-row">{_wb_logic_tree(profile, analysis)}</div></section>
<section class="section"><div class="section-head"><div><h2>市场预期差</h2><p>股票上涨来自“比市场想得更好”，这里直接展示市场叙事和研究员判断之间的差距。</p></div><span class="pill">涨幅来源</span></div>{_wb_expectation_gap(profile, analysis)}</section>
<section class="section"><div class="section-head"><div><h2>产业壁垒与利润杠杆</h2><p>这里保留 agent 的关键判断，防止图表把研究结论过度压扁。</p></div><span class="pill">moat</span></div><div class="three"><article class="mini"><h3>壁垒</h3><ul class="list">{_rw_list(list(profile.barriers)[:5])}</ul></article><article class="mini"><h3>利润杠杆</h3><ul class="list">{_rw_list(list(profile.profit_levers)[:5])}</ul></article><article class="mini"><h3>反证点</h3><ul class="list">{_rw_list(list(profile.disconfirming_signals)[:5])}</ul></article></div></section>
<footer>本报告由 AI 自动生成，用于交易复盘和研究训练，不构成投资建议。</footer></main></body></html>"""
