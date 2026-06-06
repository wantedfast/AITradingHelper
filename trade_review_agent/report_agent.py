from __future__ import annotations

from datetime import date
from typing import Any

from .openai_agent_api import run_json_agent


def generate_round_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    parsed, response_id = run_json_agent(
        system_prompt=(
            "You are an A-share trade review agent. "
            "You receive structured trade metrics, market context, and an estimated optimal sell path. "
            "Judge the trade quality in Chinese and return JSON only. "
            "Be concrete, data-grounded, and concise. "
            "Required JSON shape: "
            "{"
            "\"trade_type\":\"\","
            "\"rating\":\"A|A-|B+|B|B-|C+|C|C-|D\","
            "\"stance\":\"\","
            "\"headline\":\"\","
            "\"logic\":0,"
            "\"buy\":0,"
            "\"sell\":0,"
            "\"risk\":0,"
            "\"buy_verdict\":\"\","
            "\"buy_reason\":\"\","
            "\"sell_verdict\":\"\","
            "\"sell_reason\":\"\","
            "\"improvement\":\"\""
            "}"
        ),
        user_payload=payload,
        max_output_tokens=1800,
    )
    result = {
        "trade_type": str(parsed.get("trade_type") or "待评估交易"),
        "rating": str(parsed.get("rating") or "C+"),
        "stance": str(parsed.get("stance") or "待验证"),
        "headline": str(parsed.get("headline") or "本次交易需要结合市场环境重新审视。"),
        "logic": _score(parsed.get("logic"), 70),
        "buy": _score(parsed.get("buy"), 60),
        "sell": _score(parsed.get("sell"), 60),
        "risk": _score(parsed.get("risk"), 60),
        "optimal": {
            "buy_verdict": str(parsed.get("buy_verdict") or "买点需要结合当日市场确认。"),
            "buy_reason": str(parsed.get("buy_reason") or "建议结合个股强度、板块共振和量能再判断。"),
            "sell_verdict": str(parsed.get("sell_verdict") or "卖点需要按纪律条件执行。"),
            "sell_reason": str(parsed.get("sell_reason") or "建议用均线、前低和趋势失效条件约束卖出。"),
        },
        "improvement": str(parsed.get("improvement") or "把买卖触发条件提前写成可执行规则。"),
        "agent_response_id": response_id,
    }
    return result


def build_round_payload(
    *,
    code: str,
    name: str,
    first_day: date,
    last_day: date,
    is_closed: bool,
    avg_buy: float,
    avg_sell: float,
    buy_qty: float,
    sell_qty: float,
    buy_amount: float,
    sell_amount: float,
    last_close: float,
    profit: float,
    total_return: float,
    max_gain: float,
    max_drawdown: float,
    day_snapshot: dict[str, float],
    sector_snapshot: dict[str, float],
    benchmark_snapshot: dict[str, float],
    optimal: dict[str, Any],
    profile_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "stock": {
            "code": code,
            "name": name,
            "first_day": first_day.isoformat(),
            "last_day": last_day.isoformat(),
            "is_closed": is_closed,
        },
        "trade_metrics": {
            "avg_buy": round(avg_buy, 4),
            "avg_sell": round(avg_sell, 4),
            "buy_qty": round(buy_qty, 4),
            "sell_qty": round(sell_qty, 4),
            "buy_amount": round(buy_amount, 4),
            "sell_amount": round(sell_amount, 4),
            "last_close": round(last_close, 4),
            "profit": round(profit, 4),
            "return_pct": round(total_return, 4),
            "max_gain_pct": round(max_gain, 4),
            "max_drawdown_pct": round(max_drawdown, 4),
        },
        "market_context": {
            "stock_day": _round_snapshot(day_snapshot),
            "sector_day": _round_snapshot(sector_snapshot),
            "benchmark_day": _round_snapshot(benchmark_snapshot),
        },
        "optimal_path": _serialize_optimal(optimal),
        "profile_context": profile_context,
        "task": "请为这笔交易生成复盘评价、四维评分、买卖判断和一句话结论。",
    }


def _round_snapshot(snapshot: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value or 0.0), 4) for key, value in snapshot.items()}


def _serialize_optimal(optimal: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in optimal.items():
        if hasattr(value, "isoformat"):
            result[key] = value.isoformat()
        elif isinstance(value, float):
            result[key] = round(value, 4)
        else:
            result[key] = value
    return result


def _score(value: Any, default: int) -> int:
    try:
        numeric = int(round(float(value)))
    except Exception:
        numeric = default
    return max(0, min(100, numeric))
