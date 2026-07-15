from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


CN_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class Quote:
    code: str
    name: str
    price: float
    prev_close: float
    pct_chg: float
    quote_time: str


@dataclass
class AlertPlan:
    plan_id: str
    code: str
    name: str
    action: str
    thesis: str
    buy_date: str = ""
    watch_date: str = ""
    position: str = ""
    buy_price: float | None = None
    reference_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    breakout: float | None = None
    breakdown: float | None = None
    voice_line: str = ""
    agent_response_id: str = ""
    enabled: bool = True
    user_id: int = 0


@dataclass
class AlertEvent:
    plan: AlertPlan
    quote: Quote
    level: str
    message: str
    triggered_key: str


def load_plans(path: str | Path) -> list[AlertPlan]:
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [AlertPlan(**item) for item in data]


def save_plans(path: str | Path, plans: list[AlertPlan]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(plan) for plan in plans], ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_realtime_quote(code: str) -> Quote:
    symbol = _tencent_symbol(code)
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(
            f"https://qt.gtimg.cn/q={symbol}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
    response.raise_for_status()
    response.encoding = "gbk"
    text = response.text.strip()
    if "~" not in text:
        raise ValueError(f"Unexpected Tencent quote response for {code}: {text[:80]}")
    payload = text.split('"', 2)[1]
    fields = payload.split("~")
    name = fields[1] if len(fields) > 1 else code
    price = _to_float(fields[3])
    prev_close = _to_float(fields[4])
    pct_chg = (price / prev_close - 1) * 100 if prev_close else 0.0
    quote_time = _format_quote_time(fields[30] if len(fields) > 30 else "")
    return Quote(code=code, name=name, price=price, prev_close=prev_close, pct_chg=pct_chg, quote_time=quote_time)


def evaluate_plan(plan: AlertPlan, quote: Quote) -> list[AlertEvent]:
    if not plan.enabled:
        return []
    if not _is_watch_session(plan):
        return []
    events: list[AlertEvent] = []
    checks = [
        ("stop_loss", plan.stop_loss, quote.price <= plan.stop_loss if plan.stop_loss else False, "止损执行"),
        ("take_profit", plan.take_profit, quote.price >= plan.take_profit if plan.take_profit else False, "止盈/减仓"),
        ("breakout", plan.breakout, quote.price >= plan.breakout if plan.breakout else False, "突破确认"),
        ("breakdown", plan.breakdown, quote.price <= plan.breakdown if plan.breakdown else False, "跌破失效"),
    ]
    for key, threshold, ok, action_label in checks:
        if not ok or threshold is None:
            continue
        message = (
            f"{quote.name} {quote.code} 现价 {quote.price:.2f}，触发{action_label}预案："
            f"{_condition_text(key)} {threshold:.2f}。建议动作：{plan.action}。"
        )
        events.append(AlertEvent(plan=plan, quote=quote, level=action_label, message=message, triggered_key=key))
    return events


def evaluate_plans(plans: list[AlertPlan]) -> tuple[list[Quote], list[AlertEvent], list[str]]:
    quotes: list[Quote] = []
    events: list[AlertEvent] = []
    errors: list[str] = []
    for plan in plans:
        if not plan.enabled:
            continue
        try:
            quote = fetch_realtime_quote(plan.code)
        except Exception as exc:
            errors.append(f"{plan.code}: {exc}")
            continue
        quotes.append(quote)
        events.extend(evaluate_plan(plan, quote))
    return quotes, events, errors


def event_dedupe_key(event: AlertEvent) -> str:
    now_minute = datetime.now(CN_TZ).strftime("%Y%m%d%H%M")
    return f"{event.plan.plan_id}:{event.triggered_key}:{now_minute}"


def _condition_text(key: str) -> str:
    return {
        "stop_loss": "现价低于/等于止损价",
        "take_profit": "现价高于/等于止盈价",
        "breakout": "现价突破观察价",
        "breakdown": "现价跌破失效价",
    }.get(key, "触发条件")


def _tencent_symbol(code: str) -> str:
    code = str(code).strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        return code
    digits = "".join(ch for ch in code if ch.isdigit()).zfill(6)[-6:]
    if digits.startswith(("6", "5", "9")):
        return f"sh{digits}"
    return f"sz{digits}"


def _to_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _format_quote_time(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 14:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]} {digits[8:10]}:{digits[10:12]}:{digits[12:14]}"
    return datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _is_watch_session(plan: AlertPlan) -> bool:
    now = datetime.now(CN_TZ)
    if plan.watch_date and plan.watch_date != now.strftime("%Y-%m-%d"):
        return False
    hour_minute = now.hour * 100 + now.minute
    in_morning = 930 <= hour_minute <= 1130
    in_afternoon = 1300 <= hour_minute <= 1500
    return in_morning or in_afternoon
