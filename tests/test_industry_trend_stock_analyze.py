from __future__ import annotations

import pytest

from trade_review_agent.industry_trend.stock_analyze_client import (
    IndustryTrendRequest,
    StockAnalyzeError,
    build_industry_trend_prompt,
    run_industry_trend_analysis,
)


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
