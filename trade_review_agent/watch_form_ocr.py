from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .openai_agent_api import run_watch_form_image_agent


def extract_watch_form_from_image(image_path: str | Path) -> dict[str, str]:
    parsed = run_watch_form_image_agent(image_path)

    stock_name = _normalize_stock_name(parsed.get("stock_name"), parsed.get("stock_code"))
    buy_date = _normalize_buy_date(parsed.get("buy_date"))
    position = _normalize_position(parsed.get("position"))
    buy_price = _normalize_buy_price(parsed.get("buy_price"))

    note_parts: list[str] = []
    raw_note = str(parsed.get("notes") or "").strip()
    if raw_note:
        note_parts.append(raw_note)

    missing: list[str] = []
    if not stock_name:
        missing.append("股票名称")
    if not buy_date:
        missing.append("买入时间")
    if not position:
        missing.append("仓位")
    if not buy_price:
        missing.append("买入价")

    if missing:
        note_parts.append(f"以下字段未能稳定识别，请手动补全：{'、'.join(missing)}。")
    else:
        note_parts.append("识别结果已回填，请核对后再生成预案。")

    return {
        "stock_name": stock_name,
        "buy_date": buy_date,
        "position": position,
        "buy_price": buy_price,
        "note": " ".join(part for part in note_parts if part).strip(),
    }


def _normalize_stock_name(name: Any, code: Any) -> str:
    name_text = str(name or "").strip()
    code_text = "".join(ch for ch in str(code or "") if ch.isdigit())[-6:]
    if name_text and code_text:
        return f"{name_text} {code_text}"
    if name_text:
        return name_text
    return code_text


def _normalize_buy_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(text, fmt).strftime("%d/%m/%y")
        except ValueError:
            continue

    digits = re.sub(r"[^\d]", "", text)
    if len(digits) == 8:
        for fmt in ("%Y%m%d", "%d%m%Y"):
            try:
                return datetime.strptime(digits, fmt).strftime("%d/%m/%y")
            except ValueError:
                continue
    return ""


def _normalize_position(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    compact = text.replace(" ", "")
    canonical = [
        ("满仓 (100%)", ("满仓", "全仓", "十成")),
        ("重仓 (80%)", ("重仓", "八成", "8成")),
        ("7成 (70%)", ("七成", "7成")),
        ("半仓 (50%)", ("半仓", "五成", "5成", "中仓")),
        ("3成 (30%)", ("三成", "3成")),
        ("2成 (20%)", ("二成", "2成", "轻仓")),
        ("1成 (10%)", ("一成", "1成", "试仓")),
    ]
    for label, aliases in canonical:
        if any(alias in compact for alias in aliases):
            return label

    percent = _extract_percent_like(compact)
    if percent is not None:
        canonical = _canonical_position_from_percent(percent)
        if canonical:
            return canonical
        if abs(percent - round(percent)) < 1e-6:
            return f"{int(round(percent))}%"
        return f"{percent:.0f}%"
    return text


def _canonical_position_from_percent(percent: float) -> str:
    rounded = int(round(percent))
    mapping = {
        10: "1成 (10%)",
        20: "2成 (20%)",
        30: "3成 (30%)",
        50: "半仓 (50%)",
        70: "7成 (70%)",
        80: "重仓 (80%)",
        100: "满仓 (100%)",
    }
    return mapping.get(rounded, "")


def _extract_percent_like(text: str) -> float | None:
    percent_match = re.search(r"(\d{1,3}(?:\.\d+)?)%", text)
    if percent_match:
        return _clamp_percent(percent_match.group(1))

    ratio_match = re.search(r"(\d(?:\.\d+)?)成", text)
    if ratio_match:
        try:
            return float(ratio_match.group(1)) * 10
        except Exception:
            return None

    warehouse_match = re.search(r"(\d(?:\.\d+)?)仓", text)
    if warehouse_match:
        try:
            raw = float(warehouse_match.group(1))
        except Exception:
            return None
        return raw * 100 if raw <= 1 else raw * 10

    try:
        raw = float(text)
    except Exception:
        return None
    if 0 < raw <= 1:
        return raw * 100
    if 1 < raw <= 10:
        return raw * 10
    if 10 < raw <= 100:
        return raw
    return None


def _clamp_percent(value: str) -> float | None:
    try:
        percent = float(value)
    except Exception:
        return None
    if percent <= 0:
        return None
    return min(percent, 100.0)


def _normalize_buy_price(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return ""
    if number <= 0:
        return ""
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text
