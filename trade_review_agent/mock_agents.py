from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .report_usage import make_llm_call_record, summarize_token_usage
from .v3_pipeline import run_v3_pipeline
from .workbench_report_renderer import render_workbench_report


MOCK_FINAL_ANSWER = {
    "score": 84,
    "verdict": "你买对了行业，但买错了公司。",
    "better_choice": "东方电缆",
    "main_reason": "东方电缆拥有更强海缆壁垒、订单质量更高，盈利弹性更强。",
    "mistake_source": "selection",
    "next_action": "继续关注海风电网高压电缆，避免低壁垒跟风股。",
}


def mock_market_facts() -> dict[str, Any]:
    return {
        "market_theme": "海风电网高压电缆",
        "market_catalyst": [
            {"fact": "海风项目招标节奏改善", "date": "2026-06-01", "source": "mock_news"}
        ],
        "industry_news": [
            {"fact": "电网投资预期上修", "date": "2026-06-02", "source": "mock_news"}
        ],
        "sector_strength": {"value": 6.8, "unit": "pct", "window": "20d", "source": "mock_market"},
        "peer_snapshot": [
            {
                "code": "603606",
                "name": "东方电缆",
                "metrics": {"order_growth_pct": 32, "return_20d_pct": 18},
                "source_trace": {"metrics": {"source": "real_data", "detail": "mock fixture"}},
            },
            {
                "code": "000001",
                "name": "目标公司",
                "metrics": {"order_growth_pct": 8, "return_20d_pct": 6},
                "source_trace": {"metrics": {"source": "real_data", "detail": "mock fixture"}},
            },
        ],
    }


def mock_wang_agent() -> dict[str, Any]:
    return {
        "industry_rating": "A",
        "industry_position": "二线海缆材料/设备链",
        "profit_flow": {
            "value_pool": "海风高压电缆",
            "company_position": "跟随者",
            "items": [{"name": "高压海缆", "share_pct": 42, "highlight": True}],
        },
        "moat_radar": {"company_score": 68},
        "logic_tree": [{"node": "海风招标", "certainty_pct": 82}],
        "research_metrics": {
            "stage": "wang_industry",
            "agent": "Mock WANG Agent",
            "model": "mock-offline",
            "mode": "mock",
            "status": "ok",
            "seconds": 0.01,
            "api_usage": {"input_tokens": 120, "output_tokens": 80, "total_tokens": 200},
        },
    }


def mock_public_equity_agent() -> dict[str, Any]:
    return {
        "investment_rating": "B+",
        "quality_rating": "B+",
        "financial_validation": ["收入弹性待验证", "毛利率低于龙头"],
        "valuation_odds": "龙头赔率更优，目标公司需要更低买入价格。",
        "expectation_gap": {"gap_score": 71},
        "risks": ["订单质量不如龙头", "估值弹性不足"],
        "research_metrics": {
            "stage": "public_equity",
            "agent": "Mock Public Equity Agent",
            "model": "mock-offline",
            "mode": "mock",
            "status": "ok",
            "seconds": 0.01,
            "api_usage": {"input_tokens": 130, "output_tokens": 90, "total_tokens": 220},
        },
    }


def mock_better_opportunity_caller(_system: str, _user: str) -> dict[str, Any]:
    return {
        "better_candidates": [
            {
                "code": "603606",
                "name": "东方电缆",
                "superiority_reason": "订单增速和二级市场强度均高于目标公司。",
                "evidence": ["order_growth_pct 32 > 8", "return_20d_pct 18 > 6"],
            }
        ],
        "superiority_reason": "龙头在海缆壁垒和订单质量上更强。",
        "confidence": 0.82,
        "replacement_thesis": "如果重来一次，优先选择东方电缆。",
        "_report_llm_call": make_llm_call_record(
            stage="v3_better_opportunity",
            agent="Mock Better Opportunity Agent",
            model="mock-offline",
            mode="mock",
            seconds=0.01,
            api_usage={"input_tokens": 100, "output_tokens": 60, "total_tokens": 160},
        ),
    }


def mock_trade_coach_caller(_system: str, _user: str) -> dict[str, Any]:
    return {
        "ai_final_answer": dict(MOCK_FINAL_ANSWER),
        "future_rules": ["先比较同题材龙头和跟随者，再决定买入。"],
        "investment_principles": ["买题材不等于买到最强公司。"],
        "correct_decision": ["行业方向选择正确。"],
        "wrong_decision": ["没有优先选择壁垒更强的公司。"],
        "_report_llm_call": make_llm_call_record(
            stage="v3_trade_coach",
            agent="Mock Trade Coach Agent",
            model="mock-offline",
            mode="mock",
            seconds=0.01,
            api_usage={"input_tokens": 140, "output_tokens": 100, "total_tokens": 240},
        ),
    }


def build_mock_v3_workbench() -> dict[str, Any]:
    result = run_v3_pipeline(
        company={"code": "000001", "name": "目标公司"},
        market_facts=mock_market_facts(),
        wang=mock_wang_agent(),
        public_equity=mock_public_equity_agent(),
        trade_execution={
            "trade_execution_notes": {
                "buy_verdict": "average",
                "sell_verdict": "unknown",
                "main_lesson": "选股强弱比买点更关键。",
            },
            "execution_advice": {"summary": "执行问题不如选股问题重要。"},
        },
        better_opportunity_caller=mock_better_opportunity_caller,
        trade_coach_caller=mock_trade_coach_caller,
    )
    result["company"] = {"code": "000001", "name": "目标公司", "subtitle": "000001 | mock"}
    result["hero"] = {
        "industry_rating": "A",
        "investment_rating": "B+",
        "tags": ["Mock Agent", "离线测试"],
        "claims": [
            MOCK_FINAL_ANSWER["verdict"],
            MOCK_FINAL_ANSWER["better_choice"],
            MOCK_FINAL_ANSWER["main_reason"],
            MOCK_FINAL_ANSWER["next_action"],
        ],
    }
    result["profit_flow"] = mock_wang_agent()["profit_flow"]
    result["expectation_gap"] = mock_public_equity_agent()["expectation_gap"]
    result["logic_tree"] = mock_wang_agent()["logic_tree"]
    result["trade_review"] = {"rows": []}
    result["generation_diagnostics"] = mock_generation_diagnostics(result)
    return result


def mock_generation_diagnostics(workbench: dict[str, Any]) -> dict[str, Any]:
    layers = workbench.get("research_layers") if isinstance(workbench.get("research_layers"), dict) else {}
    calls = [
        _mock_record(mock_wang_agent()["research_metrics"], "wang_industry", "Mock WANG Agent"),
        _mock_record(mock_public_equity_agent()["research_metrics"], "public_equity", "Mock Public Equity Agent"),
        _mock_record(layers.get("better_opportunity", {}).get("research_metrics", {}), "v3_better_opportunity", "Mock Better Opportunity Agent"),
        _mock_record(layers.get("trade_coach", {}).get("research_metrics", {}), "v3_trade_coach", "Mock Trade Coach Agent"),
        make_llm_call_record(stage="market_catalyst", agent="Mock Market Catalyst", status="not_run", mode="mock"),
        make_llm_call_record(stage="trade_execution_llm", agent="Mock Trade Execution LLM", status="not_run", mode="mock"),
        make_llm_call_record(stage="presenter", agent="Mock Presenter", status="not_run", mode="mock"),
    ]
    return {
        "status": "ok",
        "errors": [],
        "timings": {
            "input_parse_seconds": 0.0,
            "ocr_seconds": 0.0,
            "market_fetch_seconds": 0.01,
            "analysis_seconds": 0.01,
            "workbench_agents_seconds": 0.02,
            "trade_execution_seconds": 0.01,
            "trade_execution_llm_seconds": 0.0,
            "v3_pipeline_seconds": 0.02,
            "presenter_seconds": 0.0,
            "write_artifacts_seconds": 0.01,
            "total_report_generation_seconds": 0.07,
        },
        "llm_calls": calls,
        "token_usage": summarize_token_usage(calls),
        "cache_diagnostics": {"cache_hit": False, "cache_stale": False, "provider": "mock"},
    }


def _mock_record(metrics: dict[str, Any], stage: str, agent: str) -> dict[str, Any]:
    return make_llm_call_record(
        stage=stage,
        agent=str(metrics.get("agent") or agent),
        model=str(metrics.get("model") or "mock-offline"),
        mode=str(metrics.get("mode") or "mock"),
        seconds=float(metrics.get("seconds") or 0.0),
        status=str(metrics.get("status") or "ok"),
        api_usage=metrics.get("api_usage") or metrics,
    )


def write_mock_frontend_report(output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_mock_v3_workbench()
    path.with_suffix(".presenter.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    path.write_text(render_workbench_report(data), encoding="utf-8")
    return path
