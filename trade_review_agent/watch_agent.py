from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .alerts import AlertEvent, AlertPlan
from .alert_tts import synthesize_edge_tts
from .data_provider import MarketDataProvider
from .industry_profiles import get_profile
from .openai_agent_api import run_json_agent, synthesize_openai_speech
from .stock_resolver import resolve_stock_code
from .voice_settings import VoiceSettings, default_voice_settings


CN_TZ = ZoneInfo("Asia/Shanghai")


def normalize_buy_date(value: str) -> str:
    text = str(value or "").strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError("买入时间格式应为 DD/MM/YY")


def build_watch_plan(
    *,
    stock_name: str,
    buy_date: str,
    position: str,
    cache_db: str | Path,
    buy_price: float | None = None,
) -> AlertPlan:
    code = resolve_stock_code(stock_name)
    if not code:
        raise ValueError(f"无法识别股票名称：{stock_name}")

    normalized_date = normalize_buy_date(buy_date)
    provider = MarketDataProvider(cache_db=cache_db, adjust="qfq")
    trade_day = pd.to_datetime(normalized_date).date()
    start = trade_day - timedelta(days=20)
    end = trade_day + timedelta(days=20)

    stock = provider.stock_daily(code, start, end)
    benchmark = provider.index_daily("sh000300", start, end)
    index_main = provider.index_daily("sh000001", start, end)
    profile = get_profile(code, stock_name)
    sector = provider.stock_daily(profile.sector_symbol, start, end)

    if stock.empty:
        raise ValueError(f"无法取得 {stock_name} {code} 的历史行情")

    trade_row = _nearest_trade_row(stock, trade_day)
    if trade_row is None:
        raise ValueError("买入日期附近没有可用交易日")
    watch_day = _next_trading_day(stock, trade_row["trade_date"])
    if watch_day is None:
        watch_day = trade_row["trade_date"]

    reference_price = float(buy_price or trade_row["close"] or 0.0)
    payload = {
        "stock": {
            "name": stock_name,
            "code": code,
            "buy_date": normalized_date,
            "watch_date": watch_day.isoformat(),
            "position": position,
            "buy_price": round(float(buy_price or 0.0), 4) if buy_price else None,
            "reference_price": round(reference_price, 4),
        },
        "market_context": {
            "stock_day": _snapshot_from_row(stock, trade_row["trade_date"]),
            "index_day": _snapshot_from_frame(index_main, trade_row["trade_date"]),
            "benchmark_day": _snapshot_from_frame(benchmark, trade_row["trade_date"]),
            "sector_day": _snapshot_from_frame(sector, trade_row["trade_date"]),
        },
        "profile": {
            "theme": profile.theme,
            "core_driver": profile.core_driver,
            "node": profile.node,
            "sector_symbol": profile.sector_symbol,
        },
        "task": "生成次日盯盘预案，返回结构化价格条件、动作、交易假设和一句适合语音提醒的话。",
    }
    parsed, response_id = run_json_agent(
        system_prompt=(
            "You are an A-share next-day watch plan agent. "
            "Return JSON only. "
            "Use the provided trade and market context to create a next-session execution plan. "
            "Required JSON shape: "
            "{"
            "\"watch_date\":\"YYYY-MM-DD\","
            "\"reference_price\":0,"
            "\"stop_loss\":0,"
            "\"take_profit\":0,"
            "\"breakout\":0,"
            "\"breakdown\":0,"
            "\"action\":\"\","
            "\"thesis\":\"\","
            "\"voice_line\":\"\""
            "}"
        ),
        user_payload=payload,
        max_output_tokens=1600,
    )
    final_watch_date = _final_watch_date(parsed.get("watch_date"), watch_day)

    return AlertPlan(
        plan_id=f"{code}-{final_watch_date.strftime('%Y%m%d')}",
        code=code,
        name=stock_name,
        action=str(parsed.get("action") or "按预案执行"),
        thesis=str(parsed.get("thesis") or "按计划观察次日强弱变化。"),
        buy_date=normalized_date,
        watch_date=final_watch_date.isoformat(),
        position=position,
        buy_price=float(buy_price) if buy_price else None,
        reference_price=_price(parsed.get("reference_price"), reference_price),
        stop_loss=_optional_price(parsed.get("stop_loss")),
        take_profit=_optional_price(parsed.get("take_profit")),
        breakout=_optional_price(parsed.get("breakout")),
        breakdown=_optional_price(parsed.get("breakdown")),
        voice_line=str(parsed.get("voice_line") or f"{stock_name} 触发预案，请按计划执行。"),
        agent_response_id=response_id,
        enabled=True,
    )


def narrate_alert_event(
    event: AlertEvent,
    audio_dir: str | Path,
    voice_settings: VoiceSettings | None = None,
) -> dict[str, Any]:
    payload = {
        "plan": asdict(event.plan),
        "quote": asdict(event.quote),
        "trigger": {
            "level": event.level,
            "triggered_key": event.triggered_key,
            "message": event.message,
        },
        "task": "基于既有预案，把这次盘中触发事件改写成更自然的提醒文案和语音播报文案。",
    }
    previous_response_id = event.plan.agent_response_id or None
    parsed, response_id = run_json_agent(
        system_prompt=(
            "You are an intraday alert narration agent. "
            "Return JSON only. "
            "Keep language short, concrete, and execution-oriented. "
            "Required JSON shape: "
            "{"
            "\"message\":\"\","
            "\"voice_line\":\"\""
            "}"
        ),
        user_payload=payload,
        previous_response_id=previous_response_id,
        max_output_tokens=800,
    )
    message = str(parsed.get("message") or event.message)
    voice_line = str(parsed.get("voice_line") or event.plan.voice_line or event.message)
    settings = voice_settings or default_voice_settings()
    audio_key = f"{event.plan.plan_id}_{event.triggered_key}_{settings.provider}_{_voice_slug(settings)}.mp3"
    audio_path = _synthesize_watch_audio(voice_line, Path(audio_dir) / audio_key, settings)
    return {
        "message": message,
        "voice_line": voice_line,
        "audio_path": audio_path,
        "agent_response_id": response_id,
    }


def _first_on_or_after(frame: pd.DataFrame, trade_date):
    rows = frame.sort_values("trade_date").reset_index(drop=True)
    matched = rows[rows["trade_date"] >= trade_date]
    if matched.empty:
        return None
    return matched.iloc[0]


def _nearest_trade_row(frame: pd.DataFrame, trade_date):
    exact_or_after = _first_on_or_after(frame, trade_date)
    if exact_or_after is not None:
        return exact_or_after
    rows = frame.sort_values("trade_date").reset_index(drop=True)
    matched = rows[rows["trade_date"] <= trade_date]
    if matched.empty:
        return None
    return matched.iloc[-1]


def _next_trading_day(frame: pd.DataFrame, trade_date):
    rows = frame.sort_values("trade_date").reset_index(drop=True)
    matched = rows[rows["trade_date"] > trade_date]
    if matched.empty:
        return _next_weekday(trade_date)
    return matched.iloc[0]["trade_date"]


def _final_watch_date(value: Any, fallback_date):
    parsed = _parse_date(value)
    if parsed is None or parsed < fallback_date:
        return fallback_date
    return parsed


def _parse_date(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return pd.to_datetime(text).date()
    except Exception:
        return None


def _next_weekday(trade_date):
    candidate = trade_date + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _snapshot_from_frame(frame: pd.DataFrame, trade_date) -> dict[str, float]:
    row = _first_on_or_after(frame, trade_date)
    if row is None:
        return {"close": 0.0, "pct_chg": 0.0, "high": 0.0, "low": 0.0, "open": 0.0}
    return _snapshot_from_row(frame, row["trade_date"])


def _snapshot_from_row(frame: pd.DataFrame, trade_date) -> dict[str, float]:
    rows = frame.sort_values("trade_date").reset_index(drop=True)
    current_idx = rows.index[rows["trade_date"] == trade_date].tolist()
    if not current_idx:
        return {"close": 0.0, "pct_chg": 0.0, "high": 0.0, "low": 0.0, "open": 0.0}
    idx = current_idx[0]
    row = rows.loc[idx]
    history = rows.loc[max(0, idx - 5) : idx - 1, "volume"]
    history_mean = pd.to_numeric(history, errors="coerce").dropna().mean() if idx > 0 else 0.0
    volume = float(row.get("volume") or 0.0)
    return {
        "open": _price(row.get("open"), 0.0),
        "close": _price(row.get("close"), 0.0),
        "high": _price(row.get("high"), 0.0),
        "low": _price(row.get("low"), 0.0),
        "pct_chg": _price(row.get("pct_chg"), 0.0),
        "volume_ratio": round(volume / history_mean, 4) if history_mean else 0.0,
    }


def _optional_price(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if number <= 0:
        return None
    return round(number, 4)


def _price(value: Any, default: float) -> float:
    try:
        return round(float(value), 4)
    except Exception:
        return round(default, 4)


def preview_voice_line(
    text: str,
    audio_dir: str | Path,
    voice_settings: VoiceSettings | None = None,
) -> dict[str, Any]:
    settings = voice_settings or default_voice_settings()
    preview_text = str(text or "").strip() or "请注意，预案已经触发，请按计划执行。"
    audio_key = f"preview_{settings.provider}_{_voice_slug(settings)}.mp3"
    audio_path = _synthesize_watch_audio(preview_text, Path(audio_dir) / audio_key, settings)
    return {
        "voice_line": preview_text,
        "audio_path": audio_path,
        "provider": settings.provider,
        "voice": settings.openai_voice if settings.provider == "openai" else settings.edge_voice,
    }


def _synthesize_watch_audio(text: str, output_path: Path, settings: VoiceSettings) -> Path:
    if settings.provider == "edge":
        return synthesize_edge_tts(text, output_path.parent, voice=settings.edge_voice)
    return synthesize_openai_speech(text, output_path, voice=settings.openai_voice)


def _voice_slug(settings: VoiceSettings) -> str:
    value = settings.openai_voice if settings.provider == "openai" else settings.edge_voice
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or settings.provider
