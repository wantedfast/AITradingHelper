from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from . import industry_agent
from . import presenter_agent
from . import trade_execution_data
from . import trade_execution_chain
from . import visual_report
from . import watch_agent
from . import workbench_agents
from . import workbench_news
from .ai_trade_parser import OpenAITradeParsingError
from .data_provider import MarketDataProvider
from .execution_structurer import structure_trade_execution_payload
from .industry_profiles import IndustryProfile
from .presenter_agent import build_presenter_fallback_data, _compact_presenter_payload, _memo_conclusion, _merge_presenter_data, _normalize_presenter_data, _presenter_json_schema, _presenter_user_prompt
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
    test_presenter_ignores_pending_hero_placeholders_contract()
    test_presenter_structured_schema_contract()
    test_presenter_agent_disabled_by_default_contract()
    test_presenter_error_visible_contract()
    test_presenter_memo_conclusion_contract()
    test_market_catalyst_context_contract()
    test_market_catalyst_model_isolated()
    test_workbench_market_hype_schema()
    test_research_model_tier_contract()
    test_better_fallback_cache_key_contract()
    test_research_agents_run_concurrently_contract()
    test_research_agents_json_contract()
    test_workbench_research_metrics_contract()
    test_agent_failure_preserves_market_catalyst_context()
    test_bad_json_agent_fallback_contract()
    test_presenter_payload_carries_market_catalyst()
    test_composer_carries_market_hype_fields()
    test_simple_api_manifest_urls()
    test_async_report_status_contract()
    test_openai_429_status_payload_contract()
    test_trade_execution_structurer_bad_types_contract()
    test_trade_execution_agent_missing_data_contract()
    test_trade_execution_advice_normal_contract()
    test_trade_execution_llm_enhancement_contract()
    test_trade_execution_prefetched_quotes_contract()
    test_trade_execution_short_prefetch_falls_back_contract()
    test_build_all_reports_preserves_round_order_with_workers()
    test_trade_execution_tencent_success_contract()
    test_trade_execution_akshare_fallback_contract()
    test_trade_execution_existing_fallback_contract()
    test_watch_plan_fetches_market_frames_concurrently_contract()
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


def test_presenter_ignores_pending_hero_placeholders_contract() -> None:
    workbench = {
        "company": {"name": "通鼎互联", "code": "002491", "theme": "待验证"},
        "hero": {"claims": ["结论待验证"], "tags": ["待验证"], "industry_rating": "B", "investment_rating": "B"},
        "market_hype_reason": "光纤光缆需求增长预期，叠加新能源业务布局。",
        "traded_business_line": "光纤光缆及通信设备",
        "deep_memos": {
            "public_equity": "一句话投资判断：通鼎互联受益于光纤光缆景气与新能源转型预期，但高质押和业绩兑现仍需验证。",
            "wang": "光纤光缆产业链 memo",
        },
    }
    profile = IndustryProfile(
        name="通鼎互联",
        code="002491",
        theme="光纤光缆",
        core_driver="AI算力光通信需求",
        node="通信设备",
        sector_symbol="515880",
        chain_nodes=(),
        barriers=(),
        profit_levers=(),
        peers=(),
        industry_judgment="",
        company_judgment="",
        expectation_gap="",
        valuation_odds="",
        catalysts=(),
        disconfirming_signals=(),
        position_sizing="",
        one_sentence_thesis="",
        financial_validation=(),
        rerating_anchor="",
        market_position="",
        peer_ranking=(),
        best_expression="",
        trading_implication="",
        evidence=(),
        wang_investor_report="",
        public_equity_report="",
    )
    data = build_presenter_fallback_data(workbench=workbench, profile=profile, analysis={}, trade_frame=pd.DataFrame())
    assert data["hero"]["claims"][0] != "结论待验证"
    assert "光纤光缆" in data["hero"]["tags"]


def test_presenter_structured_schema_contract() -> None:
    schema = _presenter_json_schema()
    assert schema["strict"] is True
    root = schema["schema"]
    assert root["additionalProperties"] is False
    for key in ["one_sentence_conclusion", "hero", "profit_flow", "logic_tree", "expectation_gap", "next_action"]:
        assert key in root["required"]
        assert key in root["properties"]


def test_presenter_agent_disabled_by_default_contract() -> None:
    original = os.environ.pop("PRESENTER_AGENT_ENABLED", None)
    try:
        assert presenter_agent._presenter_agent_enabled() is False
        os.environ["PRESENTER_AGENT_ENABLED"] = "1"
        assert presenter_agent._presenter_agent_enabled() is True
        os.environ["PRESENTER_AGENT_ENABLED"] = "true"
        assert presenter_agent._presenter_agent_enabled() is True
        os.environ["PRESENTER_AGENT_ENABLED"] = "0"
        assert presenter_agent._presenter_agent_enabled() is False
    finally:
        if original is None:
            os.environ.pop("PRESENTER_AGENT_ENABLED", None)
        else:
            os.environ["PRESENTER_AGENT_ENABLED"] = original


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


def test_research_agents_json_contract() -> None:
    calls: list[dict[str, object]] = []
    original_call = workbench_agents._call_json_agent
    try:
        def fake_json_agent(system_prompt, user_prompt, **kwargs):
            calls.append(kwargs)
            if "Public Equity" in system_prompt:
                return {
                    "investment_rating": "B",
                    "one_sentence_conclusion": "TestCo 值得观察",
                    "expectation_gap": {"gap_score": 50},
                    "action": {"current_action": "观察"},
                    "reasoning_summary": "估值和业绩仍需验证",
                }
            return {
                "industry_rating": "B",
                "claims": ["产业逻辑待验证"],
                "profit_flow": {"items": [{"name": "segment", "share_pct": 30}]},
                "reasoning_summary": "产业链位置仍需验证",
            }

        workbench_agents._call_json_agent = fake_json_agent
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
        assert wang["research_output_mode"] == "json_only"
        assert public["research_output_mode"] == "json_only"
        assert "deep_memo" not in wang
        assert "deep_memo" not in public
        assert wang["agent_type"] == "wang"
        assert public["agent_type"] == "public_equity"
        assert wang["research_metrics"]["estimated_total_tokens"] > 0
        assert public["research_metrics"]["estimated_total_tokens"] > 0
        assert calls and all(call.get("allow_web") is False for call in calls)

        def fake_detail_json_agent(system_prompt, user_prompt, **kwargs):
            payload = fake_json_agent(system_prompt, user_prompt, **kwargs)
            payload["deep_memo"] = "详细研究 memo"
            return payload

        workbench_agents._call_json_agent = fake_detail_json_agent
        detail_context = dict(context)
        detail_context["research_model_tier"] = "better"
        detail_context["research_model"] = research_model_metadata("better")
        detail_wang = workbench_agents.run_wang_workbench_agent(detail_context)
        assert detail_wang["research_output_mode"] == "json_memo"
        assert detail_wang["deep_memo"] == "详细研究 memo"
    finally:
        workbench_agents._call_json_agent = original_call


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


def test_research_agents_run_concurrently_contract() -> None:
    calls: list[str] = []
    lock = threading.Lock()
    active = 0
    max_active = 0

    def enter(label: str) -> None:
        nonlocal active, max_active
        with lock:
            calls.append(label)
            active += 1
            max_active = max(max_active, active)

    def leave() -> None:
        nonlocal active
        with lock:
            active -= 1

    original_wang = industry_agent.run_wang_workbench_agent
    original_equity = industry_agent.run_public_equity_workbench_agent
    try:
        def fake_wang(context):
            enter("wang")
            try:
                time.sleep(0.05)
                return {"agent_type": "wang", "deep_memo": "wang memo"}
            finally:
                leave()

        def fake_equity(context):
            enter("equity")
            try:
                assert "wang_pre_read" not in context
                time.sleep(0.05)
                return {"agent_type": "public_equity", "deep_memo": "equity memo"}
            finally:
                leave()

        industry_agent.run_wang_workbench_agent = fake_wang
        industry_agent.run_public_equity_workbench_agent = fake_equity
        wang, equity, errors = industry_agent._run_research_agents(
            {
                "company": {"code": "600000", "name": "TestCo"},
                "research_model_tier": "standard",
                "research_model": research_model_metadata("standard"),
            }
        )
    finally:
        industry_agent.run_wang_workbench_agent = original_wang
        industry_agent.run_public_equity_workbench_agent = original_equity

    assert calls == ["wang", "equity"] or calls == ["equity", "wang"]
    assert max_active >= 2
    assert wang["deep_memo"] == "wang memo"
    assert equity["deep_memo"] == "equity memo"
    assert errors == []


def test_workbench_research_metrics_contract() -> None:
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
    wang = {
        "agent_type": "wang",
        "industry_rating": "B",
        "claims": ["产业逻辑待验证"],
        "research_output_mode": "json_only",
        "research_metrics": {"seconds": 1.2, "estimated_total_tokens": 800},
    }
    equity = {
        "agent_type": "public_equity",
        "investment_rating": "B",
        "one_sentence_conclusion": "TestCo 值得观察",
        "research_output_mode": "json_only",
        "research_metrics": {"seconds": 1.5, "estimated_total_tokens": 900},
    }
    data = compose_workbench_data(context, wang, equity)
    assert data["research_metrics"]["wang"]["estimated_total_tokens"] == 800
    assert data["research_metrics"]["public_equity"]["estimated_total_tokens"] == 900
    assert data["research_metrics"]["wang_output_mode"] == "json_only"
    assert data["market_hype_reason"] == "AI catalyst"
    assert data["evidence_quality"] == "medium"
    assert "source A" in data["evidence"]
    assert "news A" in data["news"]


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
            "execution_advice": {"summary": 123, "next_time_rules": "rule", "confirmation_signals": {"bad": True}},
            "peer_recommendations": {"basis": 456, "items": {"bad": True}},
        },
        data_source_status={"fallback_used": "cache", "errors": "missing quotes"},
    )
    assert isinstance(payload["trade_timing"]["buy_points"], list)
    assert isinstance(payload["trade_timing"]["sell_points"], list)
    assert isinstance(payload["peer_comparison"]["rows"], list)
    assert isinstance(payload["data_source_status"]["fallback_used"], list)
    assert payload["relative_strength"]["stock_vs_benchmark"] == "unknown"
    assert payload["trade_execution_notes"]["buy_verdict"] == "unknown"
    assert isinstance(payload["execution_advice"]["next_time_rules"], list)
    assert isinstance(payload["execution_advice"]["confirmation_signals"], list)
    assert payload["execution_advice"]["summary"] == "123"
    assert isinstance(payload["peer_recommendations"]["items"], list)
    assert payload["peer_recommendations"]["basis"] == "456"
    _assert_no_trade_execution_mojibake(payload)


def test_trade_execution_agent_missing_data_contract() -> None:
    output = analyze_trade_execution({"trade_facts": {"trades": [{"side": "buy", "date": "2026-06-03", "price": 10, "quantity": 100}]}, "market_data": {}})
    assert isinstance(output["trade_timing"]["buy_points"], list)
    assert output["trade_timing"]["buy_points"][0]["intraday_position"] == "unknown"
    assert output["relative_strength"]["stock_vs_benchmark"] in {"similar", "unknown"}
    assert isinstance(output["peer_comparison"]["rows"], list)
    assert output["trade_execution_notes"]["buy_verdict"] == "unknown"
    assert output["execution_advice"]["summary"]
    assert isinstance(output["execution_advice"]["next_time_rules"], list)
    assert isinstance(output["execution_advice"]["confirmation_signals"], list)
    assert isinstance(output["peer_recommendations"]["items"], list)
    final = structure_trade_execution_payload(trade_facts={}, execution_analysis=output, data_source_status={})
    assert final["peer_recommendations"]["items"] == []
    assert final["peer_recommendations"]["basis"]
    _assert_no_trade_execution_mojibake(final)


def test_trade_execution_advice_normal_contract() -> None:
    output = analyze_trade_execution(
        {
            "trade_facts": {
                "stock_name": "通鼎互联",
                "stock_code": "002491",
                "trades": [
                    {"side": "buy", "date": "2026-06-03", "price": 25.4, "quantity": 500},
                    {"side": "sell", "date": "2026-06-04", "price": 25.09, "quantity": 100},
                ],
            },
            "market_data": {
                "stock_quotes": [
                    {"date": "2026-06-03", "open": 25.0, "high": 26.0, "low": 24.8, "close": 24.9, "pct": -2.79},
                    {"date": "2026-06-04", "open": 25.0, "high": 26.2, "low": 24.9, "close": 25.8, "pct": 10.0},
                    {"date": "2026-06-05", "open": 26.0, "high": 27.2, "low": 25.8, "close": 26.5, "pct": 2.0},
                ],
                "benchmark_quotes": [
                    {"date": "2026-06-03", "pct": 0.5},
                    {"date": "2026-06-04", "pct": -0.8},
                ],
                "sector_quotes": [
                    {"date": "2026-06-03", "name": "光通信/光纤光缆", "pct": 4.9},
                    {"date": "2026-06-04", "name": "光通信/光纤光缆", "pct": -0.4},
                ],
                "peers": [
                    {"name": "亨通光电", "code": "600487", "day_pct": 9.9, "five_day_pct": 20, "twenty_day_pct": 10},
                    {"name": "中天科技", "code": "600522", "day_pct": 4.8, "five_day_pct": 10, "twenty_day_pct": 5},
                    {"name": "烽火通信", "code": "600498", "day_pct": 5.0, "five_day_pct": 6, "twenty_day_pct": 2},
                ],
            },
        }
    )
    final = structure_trade_execution_payload(
        trade_facts={"stock_name": "通鼎互联", "stock_code": "002491", "trades": []},
        execution_analysis=output,
        data_source_status={"stock_quote": "ok", "stock_quote_source": "tencent_finance"},
    )
    advice = final["execution_advice"]
    assert advice["summary"]
    assert "买点" in advice["buy_issue"] or "买入" in advice["buy_issue"]
    assert "卖" in advice["sell_issue"]
    assert isinstance(advice["next_time_rules"], list) and advice["next_time_rules"]
    assert isinstance(advice["confirmation_signals"], list) and advice["confirmation_signals"]
    recommendations = final["peer_recommendations"]
    assert recommendations["basis"]
    assert 1 <= len(recommendations["items"]) <= 3
    for index, item in enumerate(recommendations["items"], start=1):
        assert item["rank"] == index
        for key in ["name", "code", "why_strong", "moat_reason", "profit_flow_reason", "risk_note"]:
            assert isinstance(item[key], str)
            assert item[key]
    _assert_no_trade_execution_mojibake(final)


def test_trade_execution_llm_enhancement_contract() -> None:
    original_call = trade_execution_chain._call_json_agent
    try:
        def fake_call(system_prompt, user_prompt, **kwargs):
            assert kwargs.get("allow_web") is False
            return {
                "trade_execution_notes": {
                    "buy_verdict": "good",
                    "sell_verdict": "average",
                    "main_lesson": "买点跟随光纤题材，但卖点需要结合板块退潮确认。",
                },
                "trade_timing": {
                    "buy_points": [{"date": "2026-06-03", "judgment": "题材跟随买点较好", "reason": "个股跟随光纤光缆主线，且短线仍有板块热度支撑。"}],
                    "sell_points": [{"date": "2026-06-04", "judgment": "卖点中性", "reason": "卖出保护了回撤，但未确认题材是否退潮。"}],
                },
                "execution_advice": {
                    "summary": "这轮交易不是单纯看涨跌幅，核心是题材跟随和卖出确认不足。",
                    "buy_issue": "买点有题材支撑。",
                    "sell_issue": "卖点缺少板块退潮确认。",
                    "next_time_rules": ["先确认题材仍在主升，再看个股是否强于板块。"],
                    "confirmation_signals": ["光纤光缆板块强于沪深300。"],
                },
            }

        trade_execution_chain._call_json_agent = fake_call
        payload = {
            "trade_timing": {
                "buy_points": [{"date": "2026-06-03", "price": 10.0, "judgment": "rule buy", "reason": "rule reason"}],
                "sell_points": [{"date": "2026-06-04", "price": 11.0, "judgment": "rule sell", "reason": "rule reason"}],
            },
            "trade_execution_notes": {"buy_verdict": "average", "sell_verdict": "average", "main_lesson": "rule"},
            "execution_advice": {"summary": "rule", "buy_issue": "rule", "sell_issue": "rule", "next_time_rules": [], "confirmation_signals": []},
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.html"
            result = trade_execution_chain.enhance_trade_execution_with_llm(
                execution_payload=payload,
                workbench={
                    "company": {"code": "002491", "name": "通鼎互联"},
                    "market_hype_reason": "光纤光缆与新能源题材共振",
                    "traded_business_line": "光纤光缆",
                    "research_model": research_model_metadata("standard"),
                },
                output=output,
                research_model_tier="standard",
            )
            assert result["llm_enhanced"] is True
            assert result["trade_timing"]["buy_points"][0]["judgment"] == "题材跟随买点较好"
            assert result["trade_timing"]["buy_points"][0]["price"] == 10.0
            assert result["execution_advice"]["buy_issue"] == "买点有题材支撑。"
            assert output.with_suffix(".trade_execution_llm_output.json").exists()
    finally:
        trade_execution_chain._call_json_agent = original_call


def test_trade_execution_prefetched_quotes_contract() -> None:
    calls: list[str] = []

    class Provider:
        adjust = "qfq"

        def stock_daily(self, *args, **kwargs):
            calls.append("stock_daily")
            return pd.DataFrame()

        def index_daily(self, *args, **kwargs):
            calls.append("index_daily")
            return pd.DataFrame()

    with tempfile.TemporaryDirectory() as tmp:
        output = trade_execution_chain.build_trade_execution_chain(
            provider=Provider(),
            profile=SimpleNamespace(sector_symbol="515880", theme="光通信"),
            trade_round=TradeRound(
                code="600000",
                name="TestCo",
                round_id=1,
                trades=(
                    Trade("600000", "TestCo", date(2026, 6, 3), "buy", 10.0, 100, 1000),
                    Trade("600000", "TestCo", date(2026, 6, 4), "sell", 10.4, 100, 1040),
                ),
            ),
            output=Path(tmp) / "report.html",
            prefetched_quotes={
                "stock": _sample_daily_frame("600000", days=90),
                "benchmark": _sample_daily_frame("510300", days=90),
                "sector": _sample_daily_frame("515880", days=90),
            },
        )
    assert calls == []
    assert output["trade_timing"]["buy_points"]
    assert output["trade_timing"]["sell_points"]
    assert output["execution_advice"]["next_time_rules"]
    assert output["data_source_status"]["stock_quote_source"] == "prefetched"
    _assert_no_trade_execution_mojibake(output)


def test_trade_execution_short_prefetch_falls_back_contract() -> None:
    calls: list[str] = []

    class Provider:
        adjust = "qfq"

        def _write_cache(self, *args, **kwargs):
            pass

    original_tencent = trade_execution_data._fetch_tencent_daily
    original_stock = trade_execution_data._fetch_akshare_stock_daily
    original_index = trade_execution_data._fetch_akshare_index_daily
    try:
        def fake_tencent(symbol, start, end, adjust, is_index):
            calls.append(f"tencent:{symbol}")
            return _sample_daily_frame(symbol, days=90)

        trade_execution_data._fetch_tencent_daily = fake_tencent
        trade_execution_data._fetch_akshare_stock_daily = lambda *args, **kwargs: pd.DataFrame()
        trade_execution_data._fetch_akshare_index_daily = lambda *args, **kwargs: pd.DataFrame()
        with tempfile.TemporaryDirectory() as tmp:
            output = trade_execution_chain.build_trade_execution_chain(
                provider=Provider(),
                profile=SimpleNamespace(sector_symbol="515880", theme="光通信"),
                trade_round=TradeRound(
                    code="600000",
                    name="TestCo",
                    round_id=1,
                    trades=(Trade("600000", "TestCo", date(2026, 6, 3), "buy", 10.0, 100, 1000),),
                ),
                output=Path(tmp) / "report.html",
                prefetched_quotes={"stock": _sample_daily_frame("600000"), "sector": _sample_daily_frame("515880")},
            )
    finally:
        trade_execution_data._fetch_tencent_daily = original_tencent
        trade_execution_data._fetch_akshare_stock_daily = original_stock
        trade_execution_data._fetch_akshare_index_daily = original_index
    assert "tencent:600000" in calls
    assert "tencent:515880" in calls
    assert output["data_source_status"]["stock_quote_source"] != "prefetched"


def test_build_all_reports_preserves_round_order_with_workers() -> None:
    trades = [
        Trade("600000", "Alpha", date(2026, 6, 1), "buy", 10.0, 100, 1000),
        Trade("600001", "Beta", date(2026, 6, 2), "buy", 20.0, 100, 2000),
    ]
    original_read = visual_report.read_trade_file
    original_build = visual_report.build_round_html
    try:
        visual_report.read_trade_file = lambda path: trades

        def fake_build_round_html(*, trade_round, output, cache_db, benchmark_symbol, research_model_tier):
            return visual_report.VisualReportResult(
                output=output,
                title=f"{trade_round.name} {trade_round.code}",
                rating="B",
                score=70 + trade_round.round_id,
                trade_type="buy",
            )

        visual_report.build_round_html = fake_build_round_html
        with tempfile.TemporaryDirectory() as tmp:
            results = visual_report.build_all_reports(
                "ignored.csv",
                tmp,
                cache_db="cache.sqlite",
                research_model_tier="standard",
                max_workers=2,
            )
        assert [result.title for result in results] == ["Alpha 600000", "Beta 600001"]
    finally:
        visual_report.read_trade_file = original_read
        visual_report.build_round_html = original_build


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


def test_watch_plan_fetches_market_frames_concurrently_contract() -> None:
    calls: list[tuple[str, str]] = []
    lock = threading.Lock()
    active = 0
    max_active = 0
    json_agent_calls = 0

    class FakeProvider:
        def __init__(self, *args, **kwargs):
            pass

        def stock_daily(self, code, start, end):
            return self._fetch("stock", code)

        def index_daily(self, symbol, start, end):
            return self._fetch("index", symbol)

        def _fetch(self, kind, symbol):
            nonlocal active, max_active
            with lock:
                calls.append((kind, symbol))
                active += 1
                max_active = max(max_active, active)
            try:
                time.sleep(0.05)
                return _sample_daily_frame(symbol)
            finally:
                with lock:
                    active -= 1

    def fake_json_agent(*args, **kwargs):
        nonlocal json_agent_calls
        json_agent_calls += 1
        payload = kwargs["user_payload"]
        assert payload["market_context"]["stock_day"]["close"] == 10.1
        assert payload["market_context"]["index_day"]["close"] == 10.1
        assert payload["market_context"]["benchmark_day"]["close"] == 10.1
        assert payload["market_context"]["sector_day"]["close"] == 10.1
        return (
            {
                "watch_date": "2026-06-04",
                "reference_price": 10.1,
                "stop_loss": 9.5,
                "take_profit": 11.2,
                "breakout": 10.8,
                "breakdown": 9.8,
                "action": "watch action",
                "thesis": "watch thesis",
                "voice_line": "watch voice",
            },
            "resp_123",
        )

    original_provider = watch_agent.MarketDataProvider
    original_resolver = watch_agent.resolve_stock_code
    original_profile = watch_agent.get_profile
    original_json_agent = watch_agent.run_json_agent
    try:
        watch_agent.MarketDataProvider = FakeProvider
        watch_agent.resolve_stock_code = lambda stock_name: "600000"
        watch_agent.get_profile = lambda code, stock_name: SimpleNamespace(
            theme="theme",
            core_driver="driver",
            node="node",
            sector_symbol="sh881001",
        )
        watch_agent.run_json_agent = fake_json_agent

        plan = watch_agent.build_watch_plan(
            stock_name="TestCo",
            buy_date="2026-06-03",
            position="half",
            cache_db=":memory:",
            buy_price=10.2,
        )
    finally:
        watch_agent.MarketDataProvider = original_provider
        watch_agent.resolve_stock_code = original_resolver
        watch_agent.get_profile = original_profile
        watch_agent.run_json_agent = original_json_agent

    assert set(calls) == {
        ("stock", "600000"),
        ("index", "sh000300"),
        ("index", "sh000001"),
        ("stock", "sh881001"),
    }
    assert max_active >= 2
    assert json_agent_calls == 1
    assert asdict(plan) == {
        "plan_id": "600000-20260604",
        "code": "600000",
        "name": "TestCo",
        "action": "watch action",
        "thesis": "watch thesis",
        "buy_date": "2026-06-03",
        "watch_date": "2026-06-04",
        "position": "half",
        "buy_price": 10.2,
        "reference_price": 10.1,
        "stop_loss": 9.5,
        "take_profit": 11.2,
        "breakout": 10.8,
        "breakdown": 9.8,
        "voice_line": "watch voice",
        "agent_response_id": "resp_123",
        "enabled": True,
    }


def _sample_daily_frame(symbol: str, days: int = 5) -> pd.DataFrame:
    if days == 5:
        return _legacy_sample_daily_frame(symbol)
    rows = []
    for offset in range(days):
        trade_date = (pd.Timestamp(date(2026, 5, 1)) + pd.Timedelta(days=offset)).date()
        close = 10.2 + offset * 0.1
        rows.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "open": close - 0.1,
                "close": close,
                "high": close + 0.1,
                "low": close - 0.2,
                "volume": 1000 + offset,
                "amount": 10000 + offset,
                "pct_chg": 2.0 if offset == 0 else round(0.1 / max(close - 0.1, 1) * 100, 2),
                "turnover": 1.0,
            }
        )
    return pd.DataFrame(rows)


def _legacy_sample_daily_frame(symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": symbol, "trade_date": date(2026, 6, 1), "open": 10.0, "close": 10.2, "high": 10.3, "low": 9.9, "volume": 1000, "amount": 10000, "pct_chg": 2.0, "turnover": 1.0},
            {"symbol": symbol, "trade_date": date(2026, 6, 2), "open": 10.2, "close": 10.5, "high": 10.8, "low": 10.1, "volume": 1100, "amount": 11000, "pct_chg": 2.94, "turnover": 1.1},
            {"symbol": symbol, "trade_date": date(2026, 6, 3), "open": 10.5, "close": 10.1, "high": 10.7, "low": 10.0, "volume": 1200, "amount": 12000, "pct_chg": -3.81, "turnover": 1.2},
            {"symbol": symbol, "trade_date": date(2026, 6, 4), "open": 10.1, "close": 10.4, "high": 10.6, "low": 10.0, "volume": 1300, "amount": 13000, "pct_chg": 2.97, "turnover": 1.3},
            {"symbol": symbol, "trade_date": date(2026, 6, 5), "open": 10.4, "close": 10.3, "high": 10.5, "low": 10.2, "volume": 900, "amount": 9000, "pct_chg": -0.96, "turnover": 0.9},
        ]
    )


def _assert_no_trade_execution_mojibake(value) -> None:
    bad_fragments = ["涔", "鏉", "鍗", "杩", "璐", "鏃", "鐐", "�"]
    text = json.dumps(value, ensure_ascii=False, default=str)
    assert not any(fragment in text for fragment in bad_fragments), text


def _remove_if_possible(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


if __name__ == "__main__":
    main()
