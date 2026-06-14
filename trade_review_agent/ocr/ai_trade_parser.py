from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import pandas as pd

from trade_review_agent.common.config import load_env
from trade_review_agent.market.stock_resolver import resolve_stock_code


BASE_DIR = Path(__file__).resolve().parents[2]

HEADERS = [
    "trade_date",
    "trade_time",
    "code",
    "name",
    "side",
    "quantity",
    "price",
    "amount",
    "fee",
    "market",
    "ocr_text",
]

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_AI_OCR_ATTEMPTS = 3
MAX_RETRY_SLEEP_SECONDS = 8.0


class TradeParsingError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
        user_message: str = "AI 解析服务暂时不可用，请稍后重试",
        code: str = "trade_parsing_failed",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after = retry_after
        self.user_message = user_message
        self.code = code


OpenAITradeParsingError = TradeParsingError


@dataclass(frozen=True)
class TradeIntent:
    name: str
    side: str
    trade_date: str
    trade_time: str
    price: float
    quantity: float
    amount: float = 0.0
    fee: float = 0.0
    code: str = ""
    source_text: str = ""

    def normalized(self) -> "TradeIntent":
        code = _digits(self.code) or resolve_stock_code(self.name)
        amount = self.amount if self.amount else abs(self.price * self.quantity)
        return TradeIntent(
            name=str(self.name or "").strip(),
            code=code.zfill(6)[-6:] if code else "",
            side=_normalize_side(self.side),
            trade_date=_normalize_date(self.trade_date),
            trade_time=_normalize_time(self.trade_time) or "09:30:00",
            price=float(self.price or 0),
            quantity=abs(float(self.quantity or 0)),
            amount=abs(float(amount or 0)),
            fee=abs(float(self.fee or 0)),
            source_text=self.source_text,
        )


def parse_trade_file_to_frame(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return parse_trade_image_to_frame(path)
    return parse_trade_text_to_frame(_file_to_text(path), source=path)


def parse_trade_image_to_frame(image_path: str | Path) -> pd.DataFrame:
    return intents_to_frame(parse_trade_image_to_intents(image_path))


def parse_trade_text_to_frame(text: str, source: str | Path | None = None) -> pd.DataFrame:
    return intents_to_frame(parse_trade_text_to_intents(text, source))


def parse_trade_image_to_intents(image_path: str | Path) -> list[TradeIntent]:
    image_path = Path(image_path)
    mime = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    data_url = f"data:{mime};base64,{encoded}"
    messages = [
        {"role": "system", "content": _system_prompt("image")},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "直接读取这张券商成交/持仓截图，提取真实成交记录。"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]
    return _normalize_intents(_ai_extract(messages), f"vision:{image_path.name}")


def parse_trade_text_to_intents(text: str, source: str | Path | None = None) -> list[TradeIntent]:
    messages = [
        {"role": "system", "content": _system_prompt("text")},
        {"role": "user", "content": f"source={source or ''}\n{text[:16000]}"},
    ]
    return _normalize_intents(_ai_extract(messages), f"text:{source or ''}")


def intents_to_frame(intents: list[TradeIntent]) -> pd.DataFrame:
    rows = [
        {
            "trade_date": item.trade_date,
            "trade_time": item.trade_time,
            "code": item.code,
            "name": item.name,
            "side": item.side,
            "quantity": item.quantity,
            "price": item.price,
            "amount": item.amount,
            "fee": item.fee,
            "market": "",
            "ocr_text": item.source_text,
        }
        for item in intents
    ]
    return pd.DataFrame(rows, columns=HEADERS)


def _system_prompt(mode: str) -> str:
    source_hint = "图片截图" if mode == "image" else "表格/文本内容"
    return (
        "你是 A 股交易事实提取 Agent。"
        f"请读取{source_hint}，不要要求固定券商 CSV 格式。"
        "只提取真实已经成交的交易记录、成交明细、建仓/加仓/减仓/清仓动作。"
        "中文别名：买入/买/建仓/加仓/B 属于 buy；卖出/卖/清仓/减仓/S 属于 sell。"
        "如果截图或表格顶部有股票名称，而具体成交行省略了股票名，要把顶部股票名应用到成交行。"
        "卖出行数量可能显示为负数，输出时 quantity 必须为正数。"
        "如果没有股票代码但能看到股票名称，code 可以留空，后端会根据股票名称解析。"
        "忽略账户盈亏汇总、现价、提示、笔记、BS 点开关，除非它们本身就是交易行。"
        "返回 JSON only，schema："
        "{\"trades\":[{\"name\":\"\",\"code\":\"\",\"trade_date\":\"YYYY-MM-DD\","
        "\"trade_time\":\"HH:MM:SS\",\"side\":\"buy|sell\",\"price\":0,"
        "\"quantity\":0,\"amount\":0,\"fee\":0}]}"
    )


def _ai_extract(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    load_env(BASE_DIR / ".env")
    api_key = _ocr_api_key()
    if not api_key:
        raise TradeParsingError(
            "DeepSeek OCR API key is not configured",
            status_code=503,
            retryable=False,
            user_message="AI 解析服务尚未配置，请检查 DEEPSEEK_API_KEY",
            code="deepseek_not_configured",
        )

    payload = {
        "model": _ocr_model(),
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    base_url = _ocr_base_url()
    parsed: dict[str, Any] | None = None
    last_error: TradeParsingError | None = None

    for attempt in range(1, MAX_AI_OCR_ATTEMPTS + 1):
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            break
        except urllib.error.HTTPError as exc:
            retry_after = _retry_after_seconds(exc)
            retryable = exc.code in RETRYABLE_STATUS_CODES
            last_error = _ai_http_error(exc, retry_after=retry_after, retryable=retryable)
            if not retryable or attempt >= MAX_AI_OCR_ATTEMPTS:
                raise last_error from exc
            _sleep_before_retry(attempt, retry_after)
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = TradeParsingError(
                "DeepSeek trade parsing request failed",
                status_code=503,
                retryable=True,
                user_message="AI 解析服务网络暂时不可用，请稍后重试",
                code="deepseek_unavailable",
            )
            if attempt >= MAX_AI_OCR_ATTEMPTS:
                raise last_error from exc
            _sleep_before_retry(attempt, None)
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise TradeParsingError(
                "DeepSeek trade parsing returned invalid response",
                status_code=502,
                retryable=True,
                user_message="AI 解析服务返回异常，请稍后重试",
                code="deepseek_invalid_response",
            ) from exc

    if parsed is None:
        raise last_error or TradeParsingError("DeepSeek trade parsing failed", status_code=503, retryable=True)

    trades = parsed.get("trades", [])
    if not isinstance(trades, list):
        raise TradeParsingError(
            "DeepSeek trade parsing returned invalid JSON: trades is not a list",
            status_code=502,
            retryable=True,
            user_message="AI 解析服务返回异常，请稍后重试",
            code="deepseek_invalid_response",
        )
    return [item for item in trades if isinstance(item, dict)]


def _ocr_api_key() -> str:
    value = os.getenv("TRADE_OCR_API_KEY", "").strip().lstrip("\ufeff")
    return value or os.getenv("DEEPSEEK_API_KEY", "").strip().lstrip("\ufeff")


def _ocr_base_url() -> str:
    return (
        os.getenv("TRADE_OCR_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com"
    ).strip().rstrip("/")


def _ocr_model() -> str:
    return (
        os.getenv("TRADE_OCR_MODEL")
        or os.getenv("DEEPSEEK_OCR_MODEL")
        or os.getenv("DEEPSEEK_MODEL")
        or "deepseek-chat"
    ).strip()


def _normalize_intents(items: list[dict[str, Any]], source_text: str) -> list[TradeIntent]:
    intents = [
        TradeIntent(
            name=str(item.get("name") or ""),
            code=str(item.get("code") or ""),
            side=str(item.get("side") or ""),
            trade_date=str(item.get("trade_date") or ""),
            trade_time=str(item.get("trade_time") or ""),
            price=_to_float(item.get("price")),
            quantity=_to_float(item.get("quantity")),
            amount=_to_float(item.get("amount")),
            fee=_to_float(item.get("fee")),
            source_text=source_text,
        ).normalized()
        for item in items
    ]
    valid = [item for item in intents if _valid_intent(item)]
    if not valid:
        raise ValueError("未识别到有效成交记录，请上传包含成交日期、代码、买卖方向、数量和价格的明细")
    return valid


def _valid_intent(item: TradeIntent) -> bool:
    return bool(
        item.name
        and item.code
        and item.trade_date
        and item.side in {"buy", "sell"}
        and item.price > 0
        and item.quantity > 0
    )


def _file_to_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        frame = _try_read_excel(path)
        if frame is not None:
            return _frame_to_text(frame, path)
        return _read_delimited_or_text(path)
    if suffix == ".csv":
        return _read_delimited_or_text(path)
    if suffix == ".txt":
        return _read_delimited_or_text(path)
    raise ValueError(f"Unsupported trade file type: {path.suffix}")


def _try_read_excel(path: Path) -> pd.DataFrame | None:
    engines: list[str | None] = [None]
    if path.suffix.lower() == ".xlsx":
        engines.append("openpyxl")
    else:
        engines.extend(["xlrd", "openpyxl"])

    seen: set[str] = set()
    for engine in engines:
        key = str(engine)
        if key in seen:
            continue
        seen.add(key)
        try:
            if engine is None:
                return pd.read_excel(path)
            return pd.read_excel(path, engine=engine)
        except Exception:
            continue
    return None


def _read_delimited_or_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            frame = pd.read_csv(path, encoding=encoding, sep=None, engine="python")
            if len(frame.columns) > 1:
                return _frame_to_text(frame, path)
        except Exception:
            pass
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            pass
    return path.read_bytes().decode("utf-8", errors="ignore")


def _frame_to_text(frame: pd.DataFrame, path: Path) -> str:
    preview = frame.head(200).copy()
    return f"file={path.name}\ncolumns={list(preview.columns)}\nrows:\n{preview.to_csv(index=False)}"


def _normalize_side(value: str) -> str:
    text = str(value).strip().lower()
    if text in {"buy", "b"} or any(word in text for word in ("买入", "买", "建仓", "加仓", "证券买入")):
        return "buy"
    if text in {"sell", "s"} or any(word in text for word in ("卖出", "卖", "清仓", "减仓", "证券卖出")):
        return "sell"
    return text


def _normalize_date(value: str) -> str:
    text = str(value).strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("/", "-")[:10]).strftime("%Y-%m-%d")
    except Exception:
        pass
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return ""


def _normalize_time(value: str) -> str:
    text = str(value).strip()
    if not text:
        return ""
    parts = text.split(":")
    if len(parts) >= 3:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(float(parts[2])):02d}"
    if len(parts) == 2:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
    return ""


def _to_float(value: Any) -> float:
    try:
        text = str(value or "0").strip()
        text = (
            text.replace(",", "")
            .replace("，", "")
            .replace("￥", "")
            .replace("¥", "")
            .replace("元", "")
            .replace("股", "")
            .replace("−", "-")
            .replace("－", "-")
        )
        return float(text)
    except Exception:
        return 0.0


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _ai_http_error(
    exc: urllib.error.HTTPError,
    *,
    retry_after: float | None,
    retryable: bool,
) -> TradeParsingError:
    if exc.code == 429:
        return TradeParsingError(
            "DeepSeek trade parsing rate limited",
            status_code=429,
            retryable=True,
            retry_after=retry_after,
            user_message="AI 解析服务暂时繁忙，请稍后重试",
            code="deepseek_rate_limited",
        )
    if retryable:
        return TradeParsingError(
            f"DeepSeek trade parsing temporary error: HTTP {exc.code}",
            status_code=exc.code,
            retryable=True,
            retry_after=retry_after,
            user_message="AI 解析服务暂时不可用，请稍后重试",
            code="deepseek_temporary_error",
        )
    return TradeParsingError(
        f"DeepSeek trade parsing failed: HTTP {exc.code}",
        status_code=exc.code,
        retryable=False,
        user_message="AI 解析失败，请检查上传内容或稍后重试",
        code="deepseek_request_failed",
    )


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    value = exc.headers.get("Retry-After") if exc.headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(value)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None


def _sleep_before_retry(attempt: int, retry_after: float | None) -> None:
    delay = retry_after if retry_after is not None else 0.75 * (2 ** (attempt - 1))
    time.sleep(min(delay, MAX_RETRY_SLEEP_SECONDS))
