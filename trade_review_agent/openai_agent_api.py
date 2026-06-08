from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI


DEFAULT_AGENT_MODEL = "gpt-4.1-mini"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "alloy"

_CLIENT: OpenAI | None = None


class OpenAIAgentError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        code: str = "openai_agent_failed",
        user_message: str = "AI 服务暂时不可用，请稍后重试",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.code = code
        self.user_message = user_message


def get_openai_client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or "your-openai-api-key" in api_key:
            raise OpenAIAgentError(
                "OpenAI API key is not configured",
                status_code=503,
                retryable=False,
                code="openai_not_configured",
                user_message="AI 服务尚未配置，请检查本地环境变量",
            )
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
        proxy_url = _openai_proxy_url()
        timeout_seconds = _openai_timeout_seconds()
        http_client_kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 20.0)),
            "trust_env": False,
            "verify": _openai_ssl_verify(proxy_url),
        }
        if proxy_url:
            http_client_kwargs["proxy"] = proxy_url
        _CLIENT = OpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=_openai_max_retries(),
            http_client=httpx.Client(**http_client_kwargs),
        )
    return _CLIENT


def agent_model() -> str:
    return os.getenv("OPENAI_AGENT_MODEL", os.getenv("OPENAI_MODEL", DEFAULT_AGENT_MODEL)).strip() or DEFAULT_AGENT_MODEL


def tts_model() -> str:
    return os.getenv("OPENAI_TTS_MODEL", DEFAULT_TTS_MODEL).strip() or DEFAULT_TTS_MODEL


def tts_voice(override: str | None = None) -> str:
    if override and str(override).strip():
        return str(override).strip()
    return os.getenv("OPENAI_TTS_VOICE", DEFAULT_TTS_VOICE).strip() or DEFAULT_TTS_VOICE


def run_json_agent(
    *,
    system_prompt: str,
    user_payload: dict[str, Any] | str,
    previous_response_id: str | None = None,
    model: str | None = None,
    max_output_tokens: int = 1400,
) -> tuple[dict[str, Any], str]:
    client = get_openai_client()
    user_text = user_payload if isinstance(user_payload, str) else json.dumps(user_payload, ensure_ascii=False, indent=2)
    try:
        response = client.responses.create(
            model=model or agent_model(),
            previous_response_id=previous_response_id,
            temperature=0.2,
            max_output_tokens=max_output_tokens,
            instructions=system_prompt,
            input=user_text,
        )
        parsed = _parse_json_output(response.output_text)
    except OpenAIAgentError:
        raise
    except Exception as exc:
        raise _coerce_openai_agent_error(exc) from exc
    return parsed, response.id


def run_trade_text_agent(text: str, source: str | None = None) -> list[dict[str, Any]]:
    payload = {
        "source": source or "",
        "text": text[:16000],
    }
    parsed, _ = run_json_agent(
        system_prompt=(
            "You are an A-share trade fact extraction agent. "
            "Read the provided text/table content and extract only actual executed trades, deal records, or position actions. "
            "Chinese aliases: 买入/买/建仓/加仓/B are buy; 卖出/卖/清仓/减仓/S are sell. "
            "If stock code is absent but stock name is visible, leave code empty; the backend will resolve it. "
            "Ignore profit summaries, market commentary, notes, and unrelated table rows. "
            "Return JSON only in this shape: "
            "{\"trades\":[{\"name\":\"\",\"code\":\"\",\"trade_date\":\"YYYY-MM-DD\",\"trade_time\":\"HH:MM:SS\","
            "\"side\":\"buy|sell\",\"price\":0,\"quantity\":0,\"amount\":0,\"fee\":0}]}"
        ),
        user_payload=payload,
        max_output_tokens=1800,
    )
    trades = parsed.get("trades", [])
    if not isinstance(trades, list):
        raise RuntimeError("OpenAI trade parsing returned invalid JSON: trades is not a list")
    return [item for item in trades if isinstance(item, dict)]


def run_trade_image_agent(image_path: str | Path) -> list[dict[str, Any]]:
    image_path = Path(image_path)
    mime = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    data_url = f"data:{mime};base64,{base64.b64encode(image_path.read_bytes()).decode('ascii')}"
    client = get_openai_client()
    response = client.responses.create(
        model=agent_model(),
        temperature=0.2,
        max_output_tokens=1800,
        instructions=(
            "You are an A-share trade fact extraction agent. "
            "Read this brokerage trading screenshot and extract only actual executed trades. "
            "Return JSON only in this shape: "
            "{\"trades\":[{\"name\":\"\",\"code\":\"\",\"trade_date\":\"YYYY-MM-DD\",\"trade_time\":\"HH:MM:SS\","
            "\"side\":\"buy|sell\",\"price\":0,\"quantity\":0,\"amount\":0,\"fee\":0}]}"
        ),
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"source=vision:{image_path.name}"},
                    {"type": "input_image", "image_url": data_url},
                ],
            },
        ],
    )
    parsed = _parse_json_output(response.output_text)
    trades = parsed.get("trades", [])
    if not isinstance(trades, list):
        raise RuntimeError("OpenAI trade parsing returned invalid JSON: trades is not a list")
    return [item for item in trades if isinstance(item, dict)]


def run_watch_form_image_agent(image_path: str | Path) -> dict[str, Any]:
    image_path = Path(image_path)
    mime = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    data_url = f"data:{mime};base64,{base64.b64encode(image_path.read_bytes()).decode('ascii')}"
    client = get_openai_client()
    response = client.responses.create(
        model=agent_model(),
        temperature=0.2,
        max_output_tokens=900,
        instructions=(
            "You are an A-share watch-form OCR extraction agent. "
            "Read the screenshot and extract only four fields if visible: stock_name, stock_code, buy_date, position, buy_price. "
            "buy_date should stay as visible date text if uncertain. "
            "position may be values like 半仓, 50%, 5成, 重仓, 满仓. "
            "buy_price must be numeric. "
            "Return JSON only in this shape: "
            "{"
            "\"stock_name\":\"\","
            "\"stock_code\":\"\","
            "\"buy_date\":\"\","
            "\"position\":\"\","
            "\"buy_price\":0,"
            "\"notes\":\"\""
            "}"
        ),
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"source=vision:{image_path.name}"},
                    {"type": "input_image", "image_url": data_url},
                ],
            },
        ],
    )
    parsed = _parse_json_output(response.output_text)
    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI watch form OCR returned invalid JSON object")
    return parsed


def synthesize_openai_speech(text: str, output_path: str | Path, voice: str | None = None) -> Path:
    client = get_openai_client()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path

    with client.audio.speech.with_streaming_response.create(
        model=tts_model(),
        voice=tts_voice(voice),
        input=text,
        response_format="mp3",
    ) as response:
        response.stream_to_file(output_path)
    return output_path


def _openai_proxy_url() -> str | None:
    for key in (
        "OPENAI_PROXY_URL",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return None


def _openai_ssl_verify(proxy_url: str | None) -> bool:
    raw = os.getenv("OPENAI_SSL_VERIFY", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return not bool(proxy_url)


def _openai_timeout_seconds() -> float:
    raw = os.getenv("OPENAI_TIMEOUT_SECONDS", "").strip()
    try:
        return max(10.0, float(raw))
    except Exception:
        return 90.0


def _openai_max_retries() -> int:
    raw = os.getenv("OPENAI_MAX_RETRIES", "").strip()
    try:
        return max(0, int(raw))
    except Exception:
        return 1


def _parse_json_output(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise OpenAIAgentError(
            "OpenAI returned empty output",
            status_code=502,
            retryable=True,
            code="openai_invalid_response",
            user_message="AI 服务返回空结果，请稍后重试",
        )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise OpenAIAgentError(
                "OpenAI returned invalid JSON output",
                status_code=502,
                retryable=True,
                code="openai_invalid_response",
                user_message="AI 服务返回格式异常，请稍后重试",
            ) from exc
    raise OpenAIAgentError(
        "OpenAI returned non-JSON output",
        status_code=502,
        retryable=True,
        code="openai_invalid_response",
        user_message="AI 服务返回格式异常，请稍后重试",
    )


def _coerce_openai_agent_error(exc: Exception) -> OpenAIAgentError:
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)

    if status_code == 429:
        return OpenAIAgentError(
            "OpenAI agent request was rate limited",
            status_code=429,
            retryable=True,
            code="openai_rate_limited",
            user_message="AI 服务请求过于频繁，请稍后重试",
        )
    if status_code in {500, 502, 503, 504}:
        return OpenAIAgentError(
            f"OpenAI agent request failed with HTTP {status_code}",
            status_code=status_code,
            retryable=True,
            code="openai_unavailable",
            user_message="AI 服务临时异常，请稍后重试",
        )
    if status_code:
        return OpenAIAgentError(
            f"OpenAI agent request failed with HTTP {status_code}",
            status_code=status_code,
            retryable=False,
            code="openai_request_failed",
            user_message="AI 服务请求失败，请检查模型、网络或服务配置",
        )
    return OpenAIAgentError(
        "OpenAI agent request failed",
        status_code=503,
        retryable=True,
        code="openai_unavailable",
        user_message="AI 服务网络暂时不可用，请稍后重试",
    )
