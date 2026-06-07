from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from types import SimpleNamespace

import pandas as pd

from . import industry_agent
from . import trade_execution_data
from . import workbench_agents
from . import workbench_news
from .ai_trade_parser import OpenAITradeParsingError
from .data_provider import MarketDataProvider
from .execution_structurer import structure_trade_execution_payload
from .presenter_agent import _compact_presenter_payload, _memo_conclusion, _merge_presenter_data, _normalize_presenter_data, _presenter_json_schema, _presenter_user_prompt
from .schema import Trade
from .simple_api import _api_error_payload, _recover_report_manifest, _report_manifest, _report_status_payload, _write_report_status_payload
from .trade_execution_agent import analyze_trade_execution
from .trade_rounds import TradeRound
from .workbench_agents import _loads_json_object, _research_model, research_model_metadata
from .workbench_composer import compose_workbench_data
from .workbench_news import build_market_catalyst_context
from .workbench_schema import merge_default_workbench


def main() -> None:
    test_presenter_compact_payload()
    test_presenter_fallback_full_chinese_schema()
    test_presenter_failed_json_returns_full_schema()
    test_presenter_deep_memos_retained_contract()
    test_presenter_bad_types_fallback()
    test_presenter_structured_schema_contract()
    test_presenter_error_visible_contract()
    test_presenter_memo_conclusion_contract()
    test_market_catalyst_context_contract()
    test_market_catalyst_model_isolated()
    test_workbench_market_hype_schema()
    test_research_model_tier_contract()
    test_better_fallback_cache_key_contract()
    test_memo_first_research_agents_contract()
    test_memo_first_workbench_deep_memos_contract()
    test_agent_failure_preserves_market_catalyst_context()
    test_bad_json_agent_fallback_contract()
    test_presenter_payload_carries_market_catalyst()
    test_composer_carries_market_hype_fields()
    test_simple_api_manifest_urls()
    test_async_report_status_contract()
    test_openai_429_status_payload_contract()
    test_trade_execution_structurer_bad_types_contract()
    test_trade_execution_agent_missing_data_contract()
    test_trade_execution_tencent_success_contract()
    test_trade_execution_akshare_fallback_contract()
    test_trade_execution_existing_fallback_contract()
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
    assert len(payload["deep_memos_summary"]["wang"]) <= 3003
    assert len(payload["deep_memos_summary"]["public_equity"]) <= 3003
    assert len(prompt) < 16000


def test_presenter_fallback_full_chinese_schema() -> None:
    fallback = _normalize_presenter_data(
        {
            "company": {"name": "测试公司", "code": "600000", "theme": "光通信", "node": "光模块"},
            "hero": {"claims": ["公司受益于光通信景气，但收入贡献仍需验证"], "tags": ["光通信"]},
            "profit_flow": {"items": [{"name": "光模块", "share_pct": 40, "highlight": True}]},
            "expectation_gap": {"market_believes": ["市场认为主题弹性较强"], "analyst_view": ["研究认为收入兑现仍需验证"], "gap_score": 55},
            "moat": {"summary": "壁垒待验证"},
            "next_action": {"current_action": "观察", "recheck_conditions": ["复查订单"]},
            "deep_memos": {"wang": "WANG memo 中文内容", "public_equity": "Public memo 中文内容"},
        },
        {},
    )
    for key in [
        "hero",
        "one_sentence_conclusion",
        "newbie_summary",
        "profit_flow",
        "logic_tree",
        "expectation_gap",
        "moat",
        "financial_validation",
        "catalysts",
        "disconfirming_signals",
        "next_action",
        "claim_cards",
        "evidence_blocks",
        "chart_annotations",
        "visual_priority",
        "presenter_copy",
        "frontend_modules",
        "deep_memos",
        "agent_errors",
    ]:
        assert key in fallback
    assert "summary" in fallback["profit_flow"]
    assert "explanation" in fallback["logic_tree"][0]
    assert "dimensions" in fallback["moat"]
    assert "weakest_link" in fallback["moat"]
    pollution = ["should be judged", "Profit Flow", "Conclusion pending", "pending verification", "Claim ", "Validation"]
    text = json.dumps({key: fallback.get(key) for key in ["newbie_summary", "presenter_copy", "profit_flow", "claim_cards", "evidence_blocks"]}, ensure_ascii=False)
    assert not any(term in text for term in pollution)


def test_presenter_failed_json_returns_full_schema() -> None:
    fallback = {
        "company": {"name": "测试公司", "code": "600000", "theme": "光通信", "node": "光模块"},
        "hero": {"claims": ["收入贡献仍需验证"], "tags": ["光通信"]},
        "profit_flow": {"items": [{"name": "光模块", "share_pct": 30, "highlight": True}]},
        "expectation_gap": {"market_believes": ["题材弹性"], "analyst_view": ["兑现待验证"], "gap_score": 45},
        "moat": {"summary": "壁垒待验证", "items": ["客户认证"]},
        "next_action": {"current_action": "观察", "recheck_conditions": ["复查收入"]},
        "deep_memos": {"wang": "WANG memo", "public_equity": "Public memo"},
        "agent_errors": [],
    }
    result = _merge_presenter_data(fallback, {"_agent_error": "Expecting ',' delimiter", "_raw_text": '{"bad": true'})
    for key in ["profit_flow", "logic_tree", "expectation_gap", "moat", "financial_validation", "catalysts", "next_action"]:
        assert key in result
    assert any("presenter_agent_failed" in item for item in result["agent_errors"])
    assert result["deep_memos"]["wang"] == "WANG memo"


def test_presenter_deep_memos_retained_contract() -> None:
    fallback = {
        "company": {"name": "测试公司", "code": "600000"},
        "hero": {"claims": ["结论待验证"]},
        "deep_memos": {"wang": "WANG 原始 memo 内容", "public_equity": "Public Equity 原始 memo 内容"},
    }
    result = _normalize_presenter_data({"deep_memos": "bad type"}, fallback)
    assert result["deep_memos"]["wang"] == "WANG 原始 memo 内容"
    assert result["deep_memos"]["public_equity"] == "Public Equity 原始 memo 内容"


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


def test_presenter_structured_schema_contract() -> None:
    schema = _presenter_json_schema()
    assert schema["strict"] is True
    root = schema["schema"]
    assert root["additionalProperties"] is False
    for key in ["one_sentence_conclusion", "hero", "profit_flow", "logic_tree", "expectation_gap", "next_action"]:
        assert key in root["required"]
        assert key in root["properties"]


def test_presenter_error_visible_contract() -> None:
    fallback = {
        "company": {"name": "TestCo", "code": "600000"},
        "hero": {"claims": ["real conclusion"], "tags": ["theme"]},
        "one_sentence_conclusion": "real conclusion",
        "profit_flow": {"items": [{"name": "segment", "share_pct": 30, "highlight": True}]},
        "expectation_gap": {"market_believes": ["market"], "analyst_view": ["view"], "gap_score": 50},
        "moat": {"summary": "moat", "items": ["item"]},
        "next_action": {"current_action": "watch", "recheck_conditions": ["condition"]},
        "deep_memos": {"wang": "WANG memo", "public_equity": "Public memo"},
        "agent_errors": [],
    }
    result = _merge_presenter_data(fallback, {"_agent_error": "bad json", "_raw_text": "broken"})
    assert result["one_sentence_conclusion"] == "real conclusion"
    assert any("presenter_agent_failed" in item for item in result["agent_errors"])
    assert result.get("_raw_text") == "broken"


def test_presenter_memo_conclusion_contract() -> None:
    memo = """
通鼎互联（002491）投资判断 Memo

一句话投资判断
当前通鼎互联值得关注但交易需保持谨慎。其主要机会来自光纤光缆主业景气回暖和新能源转型弹性。
"""
    assert _memo_conclusion(memo).startswith("当前通鼎互联值得关注但交易需保持谨慎")


def test_market_catalyst_context_contract() -> None:
    original = os.environ.get("WORKBENCH_NEWS_CONTEXT_ENABLED")
    try:
        os.environ["WORKBENCH_NEWS_CONTEXT_ENABLED"] = "0"
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
    finally:
        if original is None:
            os.environ.pop("WORKBENCH_NEWS_CONTEXT_ENABLED", None)
        else:
            os.environ["WORKBENCH_NEWS_CONTEXT_ENABLED"] = original


def test_market_catalyst_model_isolated() -> None:
    captured: dict[str, object] = {}
    original_call = workbench_news._call_json_agent
    original_env = {key: os.environ.get(key) for key in ["NEWS_CONTEXT_MODEL", "WORKBENCH_NEWS_CONTEXT_MODEL", "OPENAI_RESEARCH_MODEL", "OPENAI_MODEL"]}
    try:
        os.environ.pop("NEWS_CONTEXT_MODEL", None)
        os.environ.pop("WORKBENCH_NEWS_CONTEXT_MODEL", None)
        os.environ["OPENAI_RESEARCH_MODEL"] = "gpt-5.5"
        os.environ["OPENAI_MODEL"] = "gpt-5.5"

        def fake_call(*args, **kwargs):
            captured.update(kwargs)
            return {
                "market_hype_reason": "reason",
                "recent_catalysts": ["catalyst"],
                "traded_business_line": "line",
                "what_market_is_pricing": "pricing",
                "evidence_quality": "medium",
                "unknowns": [],
                "evidence": [],
            }

        workbench_news._call_json_agent = fake_call
        context = workbench_news.build_market_catalyst_context("600000", "TestCo")
        assert context["market_hype_reason"] == "reason"
        assert captured["model_override"] == "gpt-4.1"
        assert captured["allow_web"] is True
    finally:
        workbench_news._call_json_agent = original_call
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
    assert data["requested_research_model"]["tier"] == "standard"
    assert data["company"]["code"] == "600000"


def test_research_model_tier_contract() -> None:
    standard = research_model_metadata("standard")
    better = research_model_metadata("better")
    assert standard["tier"] == "standard"
    assert better["tier"] == "better"
    assert better["wang_model"] == "gpt-5.5"
    assert _research_model({"research_model": better}) == "gpt-5.5"


def test_better_fallback_cache_key_contract() -> None:
    original_cache_path = industry_agent.CACHE_PATH
    original_refresh_enabled = industry_agent._refresh_enabled
    original_build_context = industry_agent.build_stock_context
    original_wang = industry_agent.run_wang_workbench_agent
    original_equity = industry_agent.run_public_equity_workbench_agent
    with tempfile.TemporaryDirectory() as tmp:
        try:
            industry_agent.CACHE_PATH = original_cache_path.__class__(tmp) / "cache.json"
            industry_agent._refresh_enabled = lambda: True
            industry_agent.build_stock_context = lambda **kwargs: {
                "company": {"code": kwargs.get("code"), "name": kwargs.get("name"), "market": "A-share"},
                "trade": {},
                "market": {},
            }

            def fake_wang(context):
                if context.get("research_model_tier") == "better":
                    raise RuntimeError("gpt-5.5 unavailable")
                return {"profit_flow": {"items": []}, "deep_memo": "standard wang"}

            def fake_equity(context):
                assert context.get("research_model_tier") == "standard"
                return {"expectation_gap": {"gap_score": 50}, "deep_memo": "standard equity"}

            industry_agent.run_wang_workbench_agent = fake_wang
            industry_agent.run_public_equity_workbench_agent = fake_equity
            data = industry_agent.get_workbench_profile_data("600000", "TestCo", research_model_tier="better")
            assert data["requested_research_model"]["tier"] == "better"
            assert data["research_model"]["tier"] == "standard"
            assert any("better research model failed" in item for item in data["agent_errors"])
            cache = json.loads(industry_agent.CACHE_PATH.read_text(encoding="utf-8"))
            assert any(":tier:standard" in key for key in cache)
            assert not any(":tier:better" in key for key in cache)
        finally:
            industry_agent.CACHE_PATH = original_cache_path
            industry_agent._refresh_enabled = original_refresh_enabled
            industry_agent.build_stock_context = original_build_context
            industry_agent.run_wang_workbench_agent = original_wang
            industry_agent.run_public_equity_workbench_agent = original_equity


def test_memo_first_research_agents_contract() -> None:
    calls: list[dict[str, object]] = []
    original_call = workbench_agents._call_text_agent
    try:
        def fake_text_agent(system_prompt, user_prompt, **kwargs):
            calls.append(kwargs)
            return "这是普通中文研究 memo，不是 JSON。包含产业链、利润流向、证据待验证和下一步。"

        workbench_agents._call_text_agent = fake_text_agent
        context = {
            "company": {"code": "600000", "name": "TestCo", "market": "A-share"},
            "research_model_tier": "standard",
            "research_model": research_model_metadata("standard"),
            "market_catalyst": {"market_hype_reason": "AI catalyst"},
            "evidence": ["source A"],
            "news": ["news A"],
        }
        wang = workbench_agents.run_wang_workbench_agent(context)
        public = workbench_agents.run_public_equity_workbench_agent(context)
        assert "deep_memo" in wang
        assert "deep_memo" in public
        assert wang["agent_type"] == "wang"
        assert public["agent_type"] == "public_equity"
        assert "_agent_error" not in wang
        assert "_agent_error" not in public
        assert calls and all(call.get("allow_web") is False for call in calls)
    finally:
        workbench_agents._call_text_agent = original_call


def test_memo_first_workbench_deep_memos_contract() -> None:
    context = {
        "company": {"code": "600000", "name": "TestCo", "market": "A-share"},
        "market_hype_reason": "AI catalyst",
        "recent_catalysts": ["order rumor"],
        "traded_business_line": "optical module",
        "what_market_is_pricing": "AI capex demand",
        "evidence_quality": "medium",
        "unknowns": [],
        "evidence": ["source A"],
        "news": ["news A"],
        "research_model": research_model_metadata("standard"),
    }
    wang = {"agent_type": "wang", "deep_memo": "WANG 普通 memo 文本"}
    equity = {"agent_type": "public_equity", "deep_memo": "Public 普通 memo 文本"}
    data = compose_workbench_data(context, wang, equity)
    assert data["deep_memos"]["wang"] == "WANG 普通 memo 文本"
    assert data["deep_memos"]["public_equity"] == "Public 普通 memo 文本"
    assert data["market_hype_reason"] == "AI catalyst"
    assert data["evidence_quality"] == "medium"
    assert "source A" in data["evidence"]
    assert "news A" in data["news"]


def test_agent_failure_preserves_market_catalyst_context() -> None:
    original_cache_path = industry_agent.CACHE_PATH
    original_refresh_enabled = industry_agent._refresh_enabled
    original_build_context = industry_agent.build_stock_context
    original_wang = industry_agent.run_wang_workbench_agent
    original_equity = industry_agent.run_public_equity_workbench_agent
    with tempfile.TemporaryDirectory() as tmp:
        try:
            industry_agent.CACHE_PATH = original_cache_path.__class__(tmp) / "cache.json"
            industry_agent._refresh_enabled = lambda: True
            industry_agent.build_stock_context = lambda **kwargs: {
                "company": {"code": kwargs.get("code"), "name": kwargs.get("name"), "market": "A-share"},
                "trade": {},
                "market": {},
                "market_catalyst": {"market_hype_reason": "AI catalyst", "recent_catalysts": ["order rumor"]},
                "market_hype_reason": "AI catalyst",
                "recent_catalysts": ["order rumor"],
                "traded_business_line": "optical module",
                "what_market_is_pricing": "AI capex demand",
                "evidence_quality": "medium",
                "unknowns": ["revenue contribution unknown"],
                "evidence": ["source A"],
                "news": ["news A"],
            }
            industry_agent.run_wang_workbench_agent = lambda context: {"_agent_error": "bad json"}
            industry_agent.run_public_equity_workbench_agent = lambda context: (_ for _ in ()).throw(RuntimeError("bad json"))
            data = industry_agent.get_workbench_profile_data("002491", "TestCo", research_model_tier="standard")
            assert data["market_hype_reason"] == "AI catalyst"
            assert "order rumor" in data["recent_catalysts"]
            assert data["traded_business_line"] == "optical module"
            assert data["what_market_is_pricing"] == "AI capex demand"
            assert data["evidence_quality"] == "medium"
            assert "source A" in data["evidence"]
            assert "news A" in data["news"]
            assert data["wang_agent"] == {}
            assert data["public_equity_agent"] == {}
            assert any("WANG agent failed" in item for item in data["agent_errors"])
            assert any("Public Equity agent failed" in item for item in data["agent_errors"])
        finally:
            industry_agent.CACHE_PATH = original_cache_path
            industry_agent._refresh_enabled = original_refresh_enabled
            industry_agent.build_stock_context = original_build_context
            industry_agent.run_wang_workbench_agent = original_wang
            industry_agent.run_public_equity_workbench_agent = original_equity


def test_bad_json_agent_fallback_contract() -> None:
    extracted = _loads_json_object('```json\n{"ok": true}\n```')
    assert extracted["ok"] is True
    bad = _loads_json_object('{"profit_flow": {"items": []} "missing_comma": true}', repair_api_key=None)
    assert isinstance(bad, dict)
    assert "_agent_error" in bad
    assert "invalid JSON" in bad["_agent_error"]


def test_presenter_payload_carries_market_catalyst() -> None:
    fallback = {"company": {"name": "TestCo", "code": "600000"}}
    workbench = {
        "company": {"name": "TestCo", "code": "600000"},
        "market_catalyst": {"market_hype_reason": "AI catalyst", "evidence_quality": "medium"},
        "market_hype_reason": "AI catalyst",
        "recent_catalysts": ["order rumor"],
        "traded_business_line": "optical module",
        "what_market_is_pricing": "AI capex demand",
        "evidence_quality": "medium",
        "evidence": ["source A"],
        "news": ["news A"],
        "deep_memos": {"wang": "WANG memo", "public_equity": "Public memo"},
    }
    payload = _compact_presenter_payload(fallback, workbench, {"score": 70})
    assert payload["market_catalyst"]["market_hype_reason"] == "AI catalyst"
    assert "source A" in payload["evidence"]
    assert "news A" in payload["news"]
    assert payload["deep_memos_summary"]["wang"] == "WANG memo"


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
        research_model_tier="standard",
        wang_model="gpt-4.1",
        public_equity_model="gpt-4.1",
    )
    manifest = _report_manifest("run123", [result])
    report = manifest["reports"][0]
    assert report["html_url"].endswith(".html")
    assert report["workbench_url"].endswith(".workbench.json")
    assert report["presenter_url"].endswith(".presenter.json")
    assert report["trade_execution_url"].endswith(".trade_execution.json")
    assert manifest["trade_execution_url"].endswith(".trade_execution.json")
    assert manifest["requested_research_model_tier"] == "better"
    assert manifest["research_model_tier"] == "standard"
    assert manifest["actual_research_model_tier"] == "standard"
    assert report["requested_research_model_tier"] == "better"
    assert report["actual_research_model_tier"] == "standard"
    assert report["wang_model"] == "gpt-4.1"


def test_async_report_status_contract() -> None:
    queued = _report_status_payload("run123", status="queued", stage="queued", request_id="req123")
    assert queued["status"] == "queued"
    assert queued["status_url"].endswith("/api/reports/run123/status")
    assert queued["manifest_url"].endswith("/api/reports/run123/report_manifest.json")

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = industry_agent.CACHE_PATH.__class__(tmp)
        (run_dir / "600000_20260601_r1.html").write_text("<html></html>", encoding="utf-8")
        (run_dir / "600000_20260601_r1.presenter.json").write_text("{}", encoding="utf-8")
        (run_dir / "600000_20260601_r1.workbench.json").write_text(
            json.dumps(
                {
                    "requested_research_model": {"tier": "better", "model": "gpt-5.5"},
                    "research_model": {"tier": "standard", "model": "gpt-4.1"},
                }
            ),
            encoding="utf-8",
        )
        recovered = _recover_report_manifest("run123", run_dir)
        assert recovered is not None
        assert recovered["research_model_tier"] == "standard"
        assert recovered["requested_research_model_tier"] == "better"
        done = dict(recovered)
        done["status"] = "done"
        _write_report_status_payload(run_dir, done)
        status = json.loads((run_dir / "report_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "done"
        assert status["reports"][0]["presenter_url"].endswith(".presenter.json")
        assert status["reports"][0]["trade_execution_url"].endswith(".trade_execution.json")


def test_openai_429_status_payload_contract() -> None:
    exc = OpenAITradeParsingError(
        "OpenAI trade parsing rate limited",
        status_code=429,
        retryable=True,
        retry_after=2.0,
        code="openai_rate_limited",
        user_message="OpenAI 请求过于频繁，请稍后重试。",
    )
    payload = _api_error_payload(exc, request_id="req123", run_id="run123", stage="ocr_trade_file")
    payload["status"] = "error"
    assert payload["status"] == "error"
    assert payload["stage"] == "ocr_trade_file"
    assert payload["code"] == "openai_rate_limited"
    assert payload["retryable"] is True
    assert payload["retry_after"] == 2.0


def test_trade_execution_structurer_bad_types_contract() -> None:
    payload = structure_trade_execution_payload(
        trade_facts={"stock_name": "TestCo", "stock_code": "600000", "trades": "bad"},
        execution_analysis={
            "trade_timing": {"buy_points": "bad", "sell_points": None},
            "relative_strength": {"stock_vs_benchmark": "bad"},
            "peer_comparison": {"rows": "bad"},
            "trade_execution_notes": {"buy_verdict": "bad"},
        },
        data_source_status={"fallback_used": "cache", "errors": "missing quotes"},
    )
    assert isinstance(payload["trade_timing"]["buy_points"], list)
    assert isinstance(payload["trade_timing"]["sell_points"], list)
    assert isinstance(payload["peer_comparison"]["rows"], list)
    assert isinstance(payload["data_source_status"]["fallback_used"], list)
    assert payload["relative_strength"]["stock_vs_benchmark"] == "unknown"
    assert payload["trade_execution_notes"]["buy_verdict"] == "unknown"


def test_trade_execution_agent_missing_data_contract() -> None:
    output = analyze_trade_execution({"trade_facts": {"trades": [{"side": "buy", "date": "2026-06-03", "price": 10, "quantity": 100}]}, "market_data": {}})
    assert isinstance(output["trade_timing"]["buy_points"], list)
    assert output["trade_timing"]["buy_points"][0]["intraday_position"] == "unknown"
    assert output["relative_strength"]["stock_vs_benchmark"] in {"similar", "unknown"}
    assert isinstance(output["peer_comparison"]["rows"], list)
    assert output["trade_execution_notes"]["buy_verdict"] == "unknown"


def test_trade_execution_tencent_success_contract() -> None:
    original_tencent = trade_execution_data._fetch_tencent_daily
    original_stock = trade_execution_data._fetch_akshare_stock_daily
    try:
        trade_execution_data._fetch_tencent_daily = lambda *args, **kwargs: _sample_daily_frame(args[0] if args else "600000")
        trade_execution_data._fetch_akshare_stock_daily = lambda *args, **kwargs: pd.DataFrame()
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as handle:
            cache_db = handle.name
        try:
            provider = MarketDataProvider(cache_db)
            fetch = trade_execution_data.fetch_daily_with_source(
                provider=provider,
                table="stock_daily",
                symbol="600000",
                start=date(2026, 6, 1),
                end=date(2026, 6, 5),
                kind="stock",
            )
            assert fetch.source == "tencent_finance"
            assert fetch.status == "ok"
        finally:
            _remove_if_possible(cache_db)
    finally:
        trade_execution_data._fetch_tencent_daily = original_tencent
        trade_execution_data._fetch_akshare_stock_daily = original_stock


def test_trade_execution_akshare_fallback_contract() -> None:
    original_tencent = trade_execution_data._fetch_tencent_daily
    original_stock = trade_execution_data._fetch_akshare_stock_daily
    try:
        trade_execution_data._fetch_tencent_daily = lambda *args, **kwargs: pd.DataFrame()
        trade_execution_data._fetch_akshare_stock_daily = lambda *args, **kwargs: _sample_daily_frame(args[0] if args else "600000")
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as handle:
            cache_db = handle.name
        try:
            provider = MarketDataProvider(cache_db)
            fetch = trade_execution_data.fetch_daily_with_source(
                provider=provider,
                table="stock_daily",
                symbol="600000",
                start=date(2026, 6, 1),
                end=date(2026, 6, 5),
                kind="stock",
            )
            assert fetch.source == "akshare"
            assert fetch.status == "fallback"
        finally:
            _remove_if_possible(cache_db)
    finally:
        trade_execution_data._fetch_tencent_daily = original_tencent
        trade_execution_data._fetch_akshare_stock_daily = original_stock


def test_trade_execution_existing_fallback_contract() -> None:
    original_tencent = trade_execution_data._fetch_tencent_daily
    original_stock = trade_execution_data._fetch_akshare_stock_daily
    try:
        trade_execution_data._fetch_tencent_daily = lambda *args, **kwargs: pd.DataFrame()
        trade_execution_data._fetch_akshare_stock_daily = lambda *args, **kwargs: pd.DataFrame()
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as handle:
            cache_db = handle.name
        try:
            provider = MarketDataProvider(cache_db)
            provider._write_cache("stock_daily", _sample_daily_frame("600000"))
            fetch = trade_execution_data.fetch_daily_with_source(
                provider=provider,
                table="stock_daily",
                symbol="600000",
                start=date(2026, 6, 1),
                end=date(2026, 6, 5),
                kind="stock",
            )
            assert fetch.source == "fallback_existing"
            assert fetch.status == "fallback"
            assert not fetch.frame.empty
        finally:
            _remove_if_possible(cache_db)
    finally:
        trade_execution_data._fetch_tencent_daily = original_tencent
        trade_execution_data._fetch_akshare_stock_daily = original_stock


def _sample_daily_frame(symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": symbol, "trade_date": date(2026, 6, 1), "open": 10.0, "close": 10.2, "high": 10.3, "low": 9.9, "volume": 1000, "amount": 10000, "pct_chg": 2.0, "turnover": 1.0},
            {"symbol": symbol, "trade_date": date(2026, 6, 2), "open": 10.2, "close": 10.5, "high": 10.8, "low": 10.1, "volume": 1100, "amount": 11000, "pct_chg": 2.94, "turnover": 1.1},
            {"symbol": symbol, "trade_date": date(2026, 6, 3), "open": 10.5, "close": 10.1, "high": 10.7, "low": 10.0, "volume": 1200, "amount": 12000, "pct_chg": -3.81, "turnover": 1.2},
            {"symbol": symbol, "trade_date": date(2026, 6, 4), "open": 10.1, "close": 10.4, "high": 10.6, "low": 10.0, "volume": 1300, "amount": 13000, "pct_chg": 2.97, "turnover": 1.3},
            {"symbol": symbol, "trade_date": date(2026, 6, 5), "open": 10.4, "close": 10.3, "high": 10.5, "low": 10.2, "volume": 900, "amount": 9000, "pct_chg": -0.96, "turnover": 0.9},
        ]
    )


def _remove_if_possible(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


if __name__ == "__main__":
    main()
