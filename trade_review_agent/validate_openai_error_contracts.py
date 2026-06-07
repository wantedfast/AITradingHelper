from __future__ import annotations

import os
import urllib.error
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory

from . import ai_trade_parser
from .ai_trade_parser import MAX_OPENAI_ATTEMPTS, OpenAITradeParsingError
from .ocr_trades import trade_file_to_trade_csv
from .simple_api import _api_error_payload, _api_error_status


def main() -> None:
    _assert_csv_upload_still_uses_openai()
    _assert_429_retry_and_payload_contract()
    _assert_non_429_payload_is_sanitized()
    print("openai error contract validation passed")


def _assert_csv_upload_still_uses_openai() -> None:
    calls: list[list[dict]] = []
    original_extract = ai_trade_parser._openai_extract

    def fake_extract(messages: list[dict]) -> list[dict]:
        calls.append(messages)
        return [
            {
                "name": "测试公司",
                "code": "600000",
                "trade_date": "2026-06-01",
                "trade_time": "10:01:02",
                "side": "买入",
                "price": 10.5,
                "quantity": 100,
                "amount": 1050,
                "fee": 1.2,
            }
        ]

    ai_trade_parser._openai_extract = fake_extract
    try:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "trades.csv"
            output = tmp_path / "ai_trades.csv"
            source.write_text("日期,证券代码,证券名称,买卖方向,成交价格,成交数量\n2026-06-01,600000,测试公司,买入,10.5,100\n", encoding="utf-8")
            trade_file_to_trade_csv(source, output)
            assert output.exists()
            text = output.read_text(encoding="utf-8-sig")
            assert "600000" in text
            assert "buy" in text
    finally:
        ai_trade_parser._openai_extract = original_extract

    assert len(calls) == 1
    assert calls[0][0]["role"] == "system"
    assert "rows:" in calls[0][1]["content"]


def _assert_429_retry_and_payload_contract() -> None:
    original_urlopen = ai_trade_parser.urllib.request.urlopen
    original_sleep = ai_trade_parser._sleep_before_retry
    calls = []
    sleeps = []

    def fake_urlopen(request, timeout=90):
        calls.append((request, timeout))
        raise _http_error(429, retry_after="2")

    def fake_sleep(attempt: int, retry_after: float | None) -> None:
        sleeps.append((attempt, retry_after))

    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["OPENAI_BASE_URL"] = "https://example.invalid/v1"
    ai_trade_parser.urllib.request.urlopen = fake_urlopen
    ai_trade_parser._sleep_before_retry = fake_sleep
    try:
        try:
            ai_trade_parser._openai_extract([{"role": "user", "content": "x"}])
            raise AssertionError("expected OpenAITradeParsingError")
        except OpenAITradeParsingError as exc:
            assert exc.status_code == 429
            assert exc.retryable is True
            assert exc.retry_after == 2
            assert exc.code == "openai_rate_limited"
            assert len(calls) == MAX_OPENAI_ATTEMPTS
            assert len(sleeps) == MAX_OPENAI_ATTEMPTS - 1
            payload = _api_error_payload(exc, request_id="req-1", run_id="run-1", stage="ocr_trade_file")
            assert _api_error_status(exc) == 429
            assert payload["code"] == "openai_rate_limited"
            assert payload["retryable"] is True
            assert payload["stage"] == "ocr_trade_file"
            assert payload["request_id"] == "req-1"
            assert payload["run_id"] == "run-1"
            assert payload["error"] == "AI 解析服务暂时繁忙，请稍后重试"
    finally:
        ai_trade_parser.urllib.request.urlopen = original_urlopen
        ai_trade_parser._sleep_before_retry = original_sleep


def _assert_non_429_payload_is_sanitized() -> None:
    original_urlopen = ai_trade_parser.urllib.request.urlopen
    calls = []

    def fake_urlopen(request, timeout=90):
        calls.append((request, timeout))
        raise _http_error(401)

    os.environ["OPENAI_API_KEY"] = "test-openai-key"
    os.environ["OPENAI_BASE_URL"] = "https://sensitive-base-url.invalid/v1"
    ai_trade_parser.urllib.request.urlopen = fake_urlopen
    try:
        try:
            ai_trade_parser._openai_extract([{"role": "user", "content": "x"}])
            raise AssertionError("expected OpenAITradeParsingError")
        except OpenAITradeParsingError as exc:
            assert exc.status_code == 401
            assert exc.retryable is False
            assert len(calls) == 1
            payload = _api_error_payload(exc, request_id="req-2", run_id="run-2", stage="ocr_trade_file")
            assert _api_error_status(exc) == 502
            serialized = repr(payload)
            assert "test-openai-key" not in serialized
            assert "sensitive-base-url" not in serialized
            assert "Traceback" not in serialized
            assert payload["code"] == "openai_request_failed"
    finally:
        ai_trade_parser.urllib.request.urlopen = original_urlopen


def _http_error(status_code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        url="https://example.invalid/v1/chat/completions",
        code=status_code,
        msg="Too Many Requests" if status_code == 429 else "Error",
        hdrs=headers,
        fp=None,
    )


if __name__ == "__main__":
    main()
