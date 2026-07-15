from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from trade_review_agent.market.data_provider import MarketDataProvider


CN_TZ = ZoneInfo("Asia/Shanghai")
AUCTION_TOP1_REFRESH_HOUR = 16


SEED_TOP1_PERFORMANCE: tuple[dict[str, Any], ...] = (
    {
        "trade_date": "2026-06-16",
        "code": "301176",
        "name": "逸豪新材",
        "buy_date": "2026-06-16",
        "buy_price": 78.41,
        "sell_date": "2026-06-17",
        "sell_price": 79.89,
        "return_pct": 1.89,
        "result": "win",
        "source": "seed",
        "status": "completed",
    },
    {
        "trade_date": "2026-06-17",
        "code": "002741",
        "name": "光华科技",
        "buy_date": "2026-06-17",
        "buy_price": 38.68,
        "sell_date": "2026-06-18",
        "sell_price": 41.30,
        "return_pct": 6.77,
        "result": "win",
        "source": "seed",
        "status": "completed",
    },
    {
        "trade_date": "2026-06-18",
        "code": "600353",
        "name": "旭光电子",
        "buy_date": "2026-06-18",
        "buy_price": 41.50,
        "sell_date": "2026-06-22",
        "sell_price": 46.21,
        "return_pct": 11.35,
        "result": "win",
        "source": "seed",
        "status": "completed",
    },
    {
        "trade_date": "2026-06-22",
        "code": "600397",
        "name": "江钨装备",
        "buy_date": "2026-06-22",
        "buy_price": 21.98,
        "sell_date": "2026-06-23",
        "sell_price": 24.44,
        "return_pct": 11.19,
        "result": "win",
        "source": "seed",
        "status": "completed",
    },
    {
        "trade_date": "2026-06-23",
        "code": "600353",
        "name": "旭光电子",
        "buy_date": "2026-06-23",
        "buy_price": 48.74,
        "sell_date": "2026-06-24",
        "sell_price": 52.90,
        "return_pct": 8.54,
        "result": "win",
        "source": "seed",
        "status": "completed",
    },
    {
        "trade_date": "2026-06-24",
        "code": "000566",
        "name": "海南海药",
        "buy_date": "2026-06-24",
        "buy_price": 4.33,
        "sell_date": "2026-06-25",
        "sell_price": 4.59,
        "return_pct": 6.00,
        "result": "win",
        "source": "seed",
        "status": "completed",
    },
    {
        "trade_date": "2026-06-25",
        "code": "002409",
        "name": "雅克科技",
        "buy_date": "2026-06-25",
        "buy_price": 184.00,
        "sell_date": "2026-06-26",
        "sell_price": 188.60,
        "return_pct": 2.50,
        "result": "win",
        "source": "seed",
        "status": "completed",
    },
)


def auction_top1_next_refresh_at(now: datetime, *, hour: int = AUCTION_TOP1_REFRESH_HOUR) -> datetime:
    local_now = now.astimezone(CN_TZ)
    next_run = local_now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if next_run <= local_now:
        next_run = next_run + timedelta(days=1)
    return next_run


def auction_top1_performance_payload(
    *,
    performance_path: Path,
    auction_reports_path: Path,
    cache_db: Path,
    refresh: bool = True,
) -> dict[str, Any]:
    if refresh:
        refresh_top1_performance(
            auction_reports_path=auction_reports_path,
            performance_path=performance_path,
            cache_db=cache_db,
        )
    reports = read_jsonl(auction_reports_path)
    valid_report_keys = {_record_key(top1) for report in reports if (top1 := top1_from_auction_report(report))}
    records = completed_records(merged_performance_records(performance_path))
    if valid_report_keys:
        records = [
            record
            for record in records
            if str(record.get("source") or "") != "auction_strength_webhook" or _record_key(record) in valid_report_keys
        ]
    rows = [_public_row(record) for record in sorted(records, key=lambda item: item["trade_date"])]
    sample_count = len(records)
    win_count = sum(1 for record in records if float(record.get("return_pct") or 0) > 0)
    win_rate = round(win_count / sample_count * 100, 1) if sample_count else 0.0
    recent_five = sorted(records, key=lambda item: item["trade_date"])[-5:]
    recent_5_avg_return = round(
        sum(float(record.get("return_pct") or 0) for record in recent_five) / len(recent_five),
        2,
    ) if recent_five else 0.0
    best = max(records, key=lambda item: float(item.get("return_pct") or 0), default=None)
    return {
        "sample_count": sample_count,
        "win_count": win_count,
        "loss_count": max(sample_count - win_count, 0),
        "win_rate": win_rate,
        "win_rate_text": _pct_text(win_rate, signed=False, digits=1),
        "recent_5_avg_return": recent_5_avg_return,
        "recent_5_avg_return_text": _pct_text(recent_5_avg_return),
        "best_trade": _public_row(best) if best else None,
        "rows": rows,
        "source": "seed_plus_auction_top1",
    }


def refresh_top1_performance(
    *,
    auction_reports_path: Path,
    performance_path: Path,
    cache_db: Path,
    provider: MarketDataProvider | None = None,
) -> list[dict[str, Any]]:
    reports = read_jsonl(auction_reports_path)
    if not reports:
        return []
    existing = merged_performance_records(performance_path)
    recorded_keys = {_record_key(record) for record in completed_records(existing)}
    provider = provider or MarketDataProvider(cache_db=cache_db, adjust="qfq")
    appended: list[dict[str, Any]] = []
    for report in reports:
        top1 = top1_from_auction_report(report)
        if not top1:
            continue
        if _record_key(top1) in recorded_keys:
            continue
        record = resolve_top1_performance(top1, provider=provider)
        if record:
            append_jsonl(performance_path, record)
            appended.append(record)
            recorded_keys.add(_record_key(record))
    return appended


def merged_performance_records(path: Path) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for record in SEED_TOP1_PERFORMANCE:
        by_key[_record_key(record)] = dict(record)
    for record in read_jsonl(path):
        if not isinstance(record, dict):
            continue
        key = _record_key(record)
        if key:
            by_key[key] = normalize_performance_record(record)
    return sorted(by_key.values(), key=lambda item: str(item.get("trade_date") or ""))


def completed_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record.get("status") == "completed" and _float_or_none(record.get("return_pct")) is not None]


def top1_from_auction_report(report: dict[str, Any]) -> dict[str, Any] | None:
    trade_date = str(report.get("trade_date") or "").strip()
    stocks = report.get("top5_strong_stocks")
    if not trade_date or not isinstance(stocks, list) or not stocks:
        return None
    top = stocks[0] if isinstance(stocks[0], dict) else {}
    code = str(top.get("code") or "").strip()
    name = str(top.get("name") or "").strip()
    if not code and not name:
        return None
    return {
        "trade_date": trade_date,
        "code": code,
        "name": name,
        "source": "auction_strength_webhook",
    }


def _strongest_stock_text(report: dict[str, Any]) -> str:
    conclusion = report.get("global_conclusion") if isinstance(report.get("global_conclusion"), dict) else {}
    return str(conclusion.get("strongest_stock_at_925") or "").strip()


def _stock_from_strongest_text(text: str, report: dict[str, Any]) -> dict[str, Any] | None:
    code_match = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
    parsed_code = code_match.group(1) if code_match else ""
    parsed_name = _name_from_strongest_text(text, parsed_code)
    candidates = _stock_candidates_from_report(report)
    if parsed_code:
        matched = next((item for item in candidates if str(item.get("code") or "").strip() == parsed_code), None)
        return {
            "code": parsed_code,
            "name": str((matched or {}).get("name") or parsed_name).strip(),
        }
    if parsed_name:
        matched = next(
            (
                item
                for item in candidates
                if _stock_name_matches(parsed_name, str(item.get("name") or "").strip())
            ),
            None,
        )
        if matched:
            return {"code": str(matched.get("code") or "").strip(), "name": str(matched.get("name") or "").strip()}
        return {"code": "", "name": parsed_name}
    return None


def _name_from_strongest_text(text: str, code: str) -> str:
    cleaned = text
    if code:
        cleaned = cleaned.replace(code, " ")
    cleaned = re.sub(r"[，,。；;：:、|/\\()（）【】\[\]{}]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _stock_candidates_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def add_items(value: object) -> None:
        if not isinstance(value, list):
            return
        for item in value:
            if isinstance(item, dict):
                code = str(item.get("code") or "").strip()
                name = str(item.get("name") or "").strip()
                if code or name:
                    candidates.append({"code": code, "name": name})

    add_items(report.get("top5_strong_stocks"))
    add_items(report.get("top5_avoid_stocks"))
    add_items(report.get("emotion_anchors"))
    conclusion = report.get("global_conclusion") if isinstance(report.get("global_conclusion"), dict) else {}
    add_items(conclusion.get("limit_open_emotion_anchors"))
    theme_gate = report.get("theme_gate_result") if isinstance(report.get("theme_gate_result"), dict) else {}
    for theme in theme_gate.get("admitted_themes") or []:
        if isinstance(theme, dict):
            add_items(theme.get("leader_candidates"))
            add_items(theme.get("emotion_anchors"))
    return candidates


def _stock_name_matches(target: str, candidate: str) -> bool:
    return bool(target and candidate and (target in candidate or candidate in target))


def resolve_top1_performance(top1: dict[str, Any], *, provider: MarketDataProvider) -> dict[str, Any] | None:
    trade_date = _parse_date(top1.get("trade_date"))
    code = str(top1.get("code") or "").strip()
    if not trade_date or not code:
        return None
    start = trade_date
    end = trade_date + timedelta(days=12)
    frame = provider.stock_daily(code, start, end)
    if frame.empty:
        return pending_record(top1, "market_data_empty")
    rows = frame.sort_values("trade_date").reset_index(drop=True)
    buy_index = _first_row_index_on_or_after(rows, trade_date)
    if buy_index is None or buy_index + 1 >= len(rows):
        return pending_record(top1, "next_trade_day_missing")
    buy_row = rows.iloc[buy_index]
    sell_row = rows.iloc[buy_index + 1]
    buy_price = _float_or_none(buy_row.get("open"))
    sell_price = _float_or_none(sell_row.get("high"))
    if not buy_price or sell_price is None:
        return pending_record(top1, "price_missing")
    return_pct = round((sell_price - buy_price) / buy_price * 100, 2)
    return normalize_performance_record(
        {
            "trade_date": trade_date.isoformat(),
            "code": code,
            "name": str(top1.get("name") or "").strip(),
            "buy_date": _date_value(buy_row.get("trade_date")).isoformat(),
            "buy_price": round(buy_price, 3),
            "sell_date": _date_value(sell_row.get("trade_date")).isoformat(),
            "sell_price": round(sell_price, 3),
            "return_pct": return_pct,
            "result": "win" if return_pct > 0 else "loss",
            "source": str(top1.get("source") or "auction_strength_webhook"),
            "status": "completed",
        }
    )


def pending_record(top1: dict[str, Any], reason: str) -> dict[str, Any]:
    return normalize_performance_record(
        {
            "trade_date": str(top1.get("trade_date") or ""),
            "code": str(top1.get("code") or ""),
            "name": str(top1.get("name") or ""),
            "source": str(top1.get("source") or "auction_strength_webhook"),
            "status": "pending",
            "pending_reason": reason,
        }
    )


def normalize_performance_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "trade_date": str(record.get("trade_date") or "").strip(),
        "code": str(record.get("code") or "").strip(),
        "name": str(record.get("name") or "").strip(),
        "buy_date": str(record.get("buy_date") or record.get("trade_date") or "").strip(),
        "buy_price": _float_or_none(record.get("buy_price")),
        "sell_date": str(record.get("sell_date") or "").strip(),
        "sell_price": _float_or_none(record.get("sell_price")),
        "return_pct": _float_or_none(record.get("return_pct")),
        "result": str(record.get("result") or "").strip(),
        "source": str(record.get("source") or "").strip(),
        "status": str(record.get("status") or "completed").strip() or "completed",
        "pending_reason": str(record.get("pending_reason") or "").strip(),
        "updated_at": str(record.get("updated_at") or datetime.now().isoformat(timespec="seconds")),
    }
    if not normalized["result"] and normalized["return_pct"] is not None:
        normalized["result"] = "win" if normalized["return_pct"] > 0 else "loss"
    return normalized


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalize_performance_record(record), ensure_ascii=False, sort_keys=True) + "\n")


def _public_row(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    return_pct = float(record.get("return_pct") or 0)
    return {
        "trade_date": str(record.get("trade_date") or ""),
        "code": str(record.get("code") or ""),
        "name": str(record.get("name") or ""),
        "buy_date": str(record.get("buy_date") or ""),
        "buy_price": record.get("buy_price"),
        "sell_date": str(record.get("sell_date") or ""),
        "sell_price": record.get("sell_price"),
        "return_pct": round(return_pct, 2),
        "return_text": _pct_text(return_pct),
        "result": str(record.get("result") or ("win" if return_pct > 0 else "loss")),
        "source": str(record.get("source") or ""),
    }


def _record_key(record: dict[str, Any]) -> str:
    trade_date = str(record.get("trade_date") or "").strip()
    code = str(record.get("code") or "").strip()
    name = str(record.get("name") or "").strip()
    return f"{trade_date}:{code or name}"


def _pct_text(value: float, *, signed: bool = True, digits: int = 2) -> str:
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value:.{digits}f}%"


def _parse_date(value: object) -> date | None:
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _date_value(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    parsed = _parse_date(value)
    if parsed:
        return parsed
    raise ValueError(f"invalid trade date: {value}")


def _first_row_index_on_or_after(rows: pd.DataFrame, target: date) -> int | None:
    for index, row in rows.iterrows():
        if _date_value(row.get("trade_date")) >= target:
            return int(index)
    return None


def _float_or_none(value: object) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if pd.isna(number):
        return None
    return number
