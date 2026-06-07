from __future__ import annotations

from types import SimpleNamespace

from .presenter_agent import _compact_presenter_payload, _normalize_presenter_data, _presenter_user_prompt
from .simple_api import _report_manifest
from .workbench_agents import _research_model, research_model_metadata
from .workbench_composer import compose_workbench_data
from .workbench_news import build_market_catalyst_context
from .workbench_schema import merge_default_workbench


def main() -> None:
    test_presenter_compact_payload()
    test_presenter_bad_types_fallback()
    test_market_catalyst_context_contract()
    test_workbench_market_hype_schema()
    test_research_model_tier_contract()
    test_composer_carries_market_hype_fields()
    test_simple_api_manifest_urls()
    print("workbench contract validation passed")


def test_presenter_compact_payload() -> None:
    long_memo = "LONG_MEMO_" * 800
    fallback = {
        "company": {"name": "TestCo", "code": "600000"},
        "hero": {"claims": ["claim"]},
        "profit_flow": {"items": [{"name": "segment", "share_pct": 30}]},
        "expectation_gap": {"gap_score": 60},
        "next_action": {"current_action": "watch"},
    }
    workbench = {
        "deep_memos": {"wang": long_memo, "public_equity": long_memo},
        "market_hype_reason": "theme pending verification",
        "recent_catalysts": ["catalyst"],
        "agent_errors": ["agent failed"],
    }
    payload = _compact_presenter_payload(fallback, workbench, {"score": 70, "optimal": {"buy_label": "ok"}})
    prompt = _presenter_user_prompt(fallback, workbench, {"score": 70})
    assert "fallback_contract" not in prompt
    assert "research_workbench" not in prompt
    assert len(payload["deep_memos_summary"]["wang"]) <= 903
    assert len(payload["deep_memos_summary"]["public_equity"]) <= 903
    assert len(prompt) < 9000


def test_presenter_bad_types_fallback() -> None:
    fallback = {
        "company": {"name": "TestCo", "code": "600000"},
        "profit_flow": {"items": [{"name": "fallback", "share_pct": 20}]},
        "expectation_gap": {"market_believes": ["fallback"], "analyst_view": ["fallback"], "gap_score": 40},
        "next_action": {"current_action": "watch", "recheck_conditions": ["condition"]},
    }
    bad = {
        "profit_flow": "bad",
        "expectation_gap": [],
        "next_action": "observe",
        "logic_tree": "bad",
        "claim_cards": "bad",
    }
    normalized = _normalize_presenter_data(bad, fallback)
    assert isinstance(normalized["profit_flow"], dict)
    assert isinstance(normalized["expectation_gap"], dict)
    assert isinstance(normalized["next_action"], dict)
    assert isinstance(normalized["logic_tree"], list)
    assert isinstance(normalized["claim_cards"], list)


def test_market_catalyst_context_contract() -> None:
    context = build_market_catalyst_context("002484", "Jianghai")
    for key in [
        "market_hype_reason",
        "recent_catalysts",
        "traded_business_line",
        "what_market_is_pricing",
        "evidence_quality",
        "unknowns",
        "evidence",
        "source_queries",
    ]:
        assert key in context


def test_workbench_market_hype_schema() -> None:
    data = merge_default_workbench(
        {
            "market_hype_reason": 123,
            "recent_catalysts": "single catalyst",
            "traded_business_line": 456,
            "what_market_is_pricing": None,
            "evidence_quality": "medium",
            "unknowns": "unknown",
            "profit_flow": "bad",
            "expectation_gap": [],
            "action": "bad",
            "research_model": {"tier": "better", "model": "gpt-5.5"},
        },
        code="600000",
        name="TestCo",
    )
    assert isinstance(data["profit_flow"], dict)
    assert isinstance(data["expectation_gap"], dict)
    assert isinstance(data["action"], dict)
    assert isinstance(data["recent_catalysts"], list)
    assert isinstance(data["unknowns"], list)
    assert data["research_model"]["tier"] == "better"
    assert data["company"]["code"] == "600000"


def test_research_model_tier_contract() -> None:
    standard = research_model_metadata("standard")
    better = research_model_metadata("better")
    assert standard["tier"] == "standard"
    assert better["tier"] == "better"
    assert better["wang_model"] == "gpt-5.5"
    assert _research_model({"research_model": better}) == "gpt-5.5"


def test_composer_carries_market_hype_fields() -> None:
    context = {
        "company": {"code": "600000", "name": "TestCo", "market": "A-share"},
        "market_hype_reason": "context reason",
        "recent_catalysts": ["context catalyst"],
        "traded_business_line": "context line",
        "what_market_is_pricing": "context pricing",
        "evidence_quality": "low",
        "unknowns": ["context unknown"],
        "research_model": {"tier": "better", "model": "gpt-5.5", "wang_model": "gpt-5.5", "public_equity_model": "gpt-5.5"},
    }
    wang = {
        "market_hype_reason": "wang reason",
        "recent_catalysts": ["wang catalyst"],
        "traded_business_line": "wang line",
        "what_market_is_pricing": "wang pricing",
        "evidence_quality": "medium",
        "unknowns": ["wang unknown"],
    }
    equity = {
        "traded_business_line": "equity line",
        "what_market_is_pricing": "equity pricing",
        "evidence_quality": "high",
        "unknowns": ["equity unknown"],
    }
    data = compose_workbench_data(context, wang, equity)
    assert data["market_hype_reason"] == "wang reason"
    assert "wang catalyst" in data["recent_catalysts"]
    assert data["traded_business_line"] == "equity line"
    assert data["what_market_is_pricing"] == "equity pricing"
    assert data["evidence_quality"] == "high"
    assert data["research_model"]["tier"] == "better"


def test_simple_api_manifest_urls() -> None:
    result = SimpleNamespace(
        output=SimpleNamespace(name="600000_20260601_r1.html", with_suffix=lambda suffix: SimpleNamespace(name=f"600000_20260601_r1{suffix}")),
        title="TestCo 600000",
        rating="B",
        score=70,
        trade_type="buy",
        requested_research_model_tier="better",
        research_model_tier="better",
        wang_model="gpt-5.5",
        public_equity_model="gpt-5.5",
    )
    manifest = _report_manifest("run123", [result])
    report = manifest["reports"][0]
    assert report["html_url"].endswith(".html")
    assert report["workbench_url"].endswith(".workbench.json")
    assert report["presenter_url"].endswith(".presenter.json")
    assert manifest["research_model_tier"] == "better"
    assert report["wang_model"] == "gpt-5.5"


if __name__ == "__main__":
    main()
