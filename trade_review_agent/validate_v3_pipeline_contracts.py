from __future__ import annotations

from typing import Any

from .v3_better_opportunity_agent import (
    run_better_opportunity_agent,
    validate_better_opportunity_contract,
)
from .v3_market_scout import run_market_scout, validate_market_scout_contract
from .v3_pipeline import run_v3_pipeline, validate_v3_pipeline_contract
from .v3_trade_coach_agent import run_trade_coach_agent, validate_trade_coach_contract


def main() -> None:
    test_market_scout_rejects_conclusions()
    test_market_scout_preserves_real_facts()
    test_better_opportunity_missing_without_peer_data()
    test_better_opportunity_rejects_invented_peer()
    test_trade_coach_has_no_default_score()
    test_full_offline_pipeline_contract()
    print("V3 pipeline contract validation passed")


def test_market_scout_rejects_conclusions() -> None:
    try:
        run_market_scout({}, llm_caller=lambda _system, _user: {"verdict": "buy"})
        raise AssertionError("Market Scout accepted an investment conclusion")
    except ValueError:
        pass


def test_market_scout_preserves_real_facts() -> None:
    result = run_market_scout(_market_facts())
    assert validate_market_scout_contract(result) == []
    assert result["peer_snapshot"][0]["name"] == "Peer A"
    assert result["source_trace"]["peer_snapshot"]["source"] == "real_data"
    assert "verdict" not in result


def test_better_opportunity_missing_without_peer_data() -> None:
    called = False

    def caller(_system: str, _user: str) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    result = run_better_opportunity_agent(
        company={"code": "000001", "name": "Target"},
        market_scout={"market_theme": "Theme", "peer_snapshot": []},
        wang={"industry_position": "midstream"},
        public_equity={},
        llm_caller=caller,
    )
    assert result["status"] == "missing"
    assert result["confidence"] is None
    assert called is False
    assert validate_better_opportunity_contract(result) == []


def test_better_opportunity_rejects_invented_peer() -> None:
    result = run_better_opportunity_agent(
        company={"code": "000001", "name": "Target"},
        market_scout=run_market_scout(_market_facts()),
        wang={"industry_position": "midstream"},
        public_equity={"investment_rating": "A"},
        llm_caller=lambda _system, _user: {
            "better_candidates": [
                {
                    "code": "999999",
                    "name": "Invented",
                    "superiority_reason": "unsupported",
                    "evidence": ["unsupported"],
                }
            ],
            "superiority_reason": "unsupported",
            "confidence": 0.9,
            "replacement_thesis": "unsupported",
        },
    )
    assert result["status"] == "missing"
    assert result["better_candidates"] == []


def test_trade_coach_has_no_default_score() -> None:
    result = run_trade_coach_agent(
        execution={},
        wang={},
        public_equity={},
        better_opportunity={},
    )
    assert result["status"] == "missing"
    assert result["ai_final_answer"]["score"] is None
    assert validate_trade_coach_contract(result) == []


def test_full_offline_pipeline_contract() -> None:
    def scout_caller(_system: str, _user: str) -> dict[str, Any]:
        return _market_facts()

    def better_caller(_system: str, _user: str) -> dict[str, Any]:
        return {
            "better_candidates": [
                {
                    "code": "000002",
                    "name": "Peer A",
                    "superiority_reason": "higher supplied order growth",
                    "evidence": ["order_growth_pct=30"],
                }
            ],
            "superiority_reason": "Peer A has stronger supplied order growth",
            "confidence": 0.78,
            "replacement_thesis": "Prefer the peer with stronger verified order momentum",
        }

    def coach_caller(_system: str, _user: str) -> dict[str, Any]:
        return {
            "ai_final_answer": {
                "score": 82,
                "verdict": "The industry thesis was right, but stock selection was weaker.",
                "better_choice": "Peer A",
                "main_reason": "The peer had stronger comparable order growth.",
                "mistake_source": "selection",
                "next_action": "Compare verified peer operating metrics before entry.",
            },
            "future_rules": ["Compare peers using same-date metrics."],
            "investment_principles": ["Evidence before narrative."],
            "correct_decision": ["Selected the right industry theme."],
            "wrong_decision": ["Did not choose the strongest peer."],
        }

    result = run_v3_pipeline(
        company={"code": "000001", "name": "Target"},
        market_facts=_market_facts(),
        wang={
            "industry_position": "midstream",
            "profit_flow": {"company_position": "midstream"},
            "moat_radar": {"company_score": 60},
        },
        public_equity={"investment_rating": "B", "risks": ["margin pressure"]},
        trade_execution={
            "trade_execution_notes": {
                "buy_verdict": "good",
                "sell_verdict": "average",
                "main_lesson": "selection mattered more than timing",
            }
        },
        market_scout_caller=scout_caller,
        better_opportunity_caller=better_caller,
        trade_coach_caller=coach_caller,
    )
    assert validate_v3_pipeline_contract(result) == []
    assert result["ai_final_answer"]["score"] == 82
    assert result["ai_final_answer"]["better_choice"] == "Peer A"
    assert result["answer_evidence"]["future_rules"]
    assert result["source_trace"]["ai_final_answer.score"]["source"] == "llm"


def _market_facts() -> dict[str, Any]:
    return {
        "market_theme": "Grid investment",
        "market_catalyst": [
            {"fact": "Tender volume increased", "date": "2026-05-30", "source": "exchange notice"}
        ],
        "industry_news": [
            {"fact": "New grid plan published", "date": "2026-05-28", "source": "official plan"}
        ],
        "sector_strength": {
            "value": 4.2,
            "unit": "pct",
            "window": "20d",
            "as_of": "2026-06-01",
            "source": "market data",
        },
        "peer_snapshot": [
            {
                "code": "000002",
                "name": "Peer A",
                "metrics": {"order_growth_pct": 30, "return_20d_pct": 12},
                "as_of": "2026-06-01",
                "source": "market and filing data",
            }
        ],
    }


if __name__ == "__main__":
    main()
