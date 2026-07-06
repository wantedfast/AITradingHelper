from __future__ import annotations

import pytest

from trade_review_agent.industry_trend.stock_analyze_client import (
    IndustryTrendRequest,
    StockAnalyzeError,
    build_industry_trend_prompt,
    run_industry_trend_analysis,
)
from trade_review_agent.api.simple_api import _industry_trend_billing_status, _industry_trend_status_payload
import trade_review_agent.api.simple_api as simple_api


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = "fake"

    def json(self) -> dict:
        return self._payload


def test_build_industry_trend_prompt_mentions_stock_analyze_skill() -> None:
    prompt = build_industry_trend_prompt(IndustryTrendRequest(query="华海清科", input_type="stock"))

    assert "$stock-reverse-engineering" in prompt
    assert "华海清科" in prompt
    assert "三高评分" in prompt
    assert "资金炒作逻辑" in prompt


def test_run_industry_trend_analysis_posts_to_local_stock_analyze(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_post(url: str, **kwargs):
      calls.append({"url": url, **kwargs})
      return FakeResponse({"answer": "产业趋势结果"})

    monkeypatch.delenv("STOCK_ANALYZE_API_URL", raising=False)
    monkeypatch.setattr("trade_review_agent.industry_trend.stock_analyze_client.requests.post", fake_post)

    result = run_industry_trend_analysis(IndustryTrendRequest(query="AI服务器液冷产业链", input_type="chain"))

    assert result["answer"] == "产业趋势结果"
    assert result["input_type"] == "chain"
    assert calls[0]["url"] == "http://127.0.0.1:8750/api/codex"
    assert "AI服务器液冷产业链" in calls[0]["json"]["prompt"]


def test_run_industry_trend_analysis_raises_on_empty_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url: str, **kwargs):
      return FakeResponse({"answer": ""})

    monkeypatch.setattr("trade_review_agent.industry_trend.stock_analyze_client.requests.post", fake_post)

    with pytest.raises(StockAnalyzeError):
        run_industry_trend_analysis(IndustryTrendRequest(query="华海清科"))


def test_industry_trend_status_payload_points_to_polling_endpoint() -> None:
    payload = _industry_trend_status_payload("run123", status="queued", stage="queued", request_id="req1")

    assert payload["status_url"] == "/api/industry-trend/reports/run123/status"
    assert payload["report_url"] == "/api/industry-trend/reports/run123/industry_trend_report.json"
    assert payload["request_id"] == "req1"


def test_industry_trend_billing_status_matches_access_type() -> None:
    assert _industry_trend_billing_status({"role": "admin"}) == "admin_free"
    assert _industry_trend_billing_status({"role": "user", "membership_active": True}) == "membership_free"
    assert _industry_trend_billing_status({"role": "user", "credits": 3}) == "charged"


def test_industry_trend_background_task_charges_after_success(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    def fake_run(request: IndustryTrendRequest) -> dict:
        return {
            "query": request.query,
            "input_type": request.input_type,
            "answer": "产业趋势结果",
            "source": "stock-analyze",
            "endpoint": "mock",
            "elapsed_seconds": 0.1,
        }

    def fake_consume(*args, **kwargs) -> dict:
        return {"id": kwargs["user_id"], "role": "user", "credits": 4}

    monkeypatch.setattr(simple_api, "run_industry_trend_analysis", fake_run)
    monkeypatch.setattr(simple_api, "consume_feature_credit_once", fake_consume)

    simple_api._run_industry_trend_generation_task(
        run_id="run123",
        run_dir=tmp_path,
        query="华海清科",
        input_type="stock",
        request_id="req1",
        user_id=7,
        ip="127.0.0.1",
    )

    payload = simple_api._read_industry_trend_status_payload(tmp_path)
    assert payload is not None
    assert payload["status"] == "done"
    assert payload["billing_status"] == "charged"
    assert payload["answer"] == "产业趋势结果"
    assert payload["user"]["credits"] == 4
