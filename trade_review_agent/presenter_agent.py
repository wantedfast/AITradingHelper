from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd

from .industry_profiles import IndustryProfile
from .workbench_agents import _call_json_agent, _model, _parse_json_object_text, _post_json


def build_presenter_data(
    *,
    workbench: dict[str, Any],
    profile: IndustryProfile,
    analysis: dict[str, Any],
    trade_frame: pd.DataFrame,
) -> dict[str, Any]:
    fallback = build_presenter_fallback_data(
        workbench=workbench,
        profile=profile,
        analysis=analysis,
        trade_frame=trade_frame,
    )
    if not _presenter_agent_enabled():
        return fallback
    agent_data = run_presenter_workbench_agent(fallback=fallback, workbench=workbench, analysis=analysis)
    return _merge_presenter_data(fallback, agent_data)


def build_presenter_fallback_data(
    *,
    workbench: dict[str, Any],
    profile: IndustryProfile,
    analysis: dict[str, Any],
    trade_frame: pd.DataFrame,
) -> dict[str, Any]:
    workbench = _dict(workbench)
    company = _dict(workbench.get("company"))
    hero = _dict(workbench.get("hero"))
    profit = _dict(workbench.get("profit_flow"))
    gap = _dict(workbench.get("expectation_gap"))
    action = _dict(workbench.get("action"))
    trade = _dict(workbench.get("trade_review"))
    memos = _dict(workbench.get("deep_memos"))
    wang_memo = _first(memos.get("wang"), _dict(workbench.get("wang_agent")).get("deep_memo"), profile.wang_investor_report, profile.industry_judgment)
    public_memo = _first(memos.get("public_equity"), _dict(workbench.get("public_equity_agent")).get("deep_memo"), profile.public_equity_report, profile.valuation_odds)
    memo_conclusion = _memo_conclusion(public_memo)

    name = _first(company.get("name"), profile.name, "stock")
    code = _first(company.get("code"), profile.code, "")
    theme = _first_non_pending(company.get("theme"), workbench.get("traded_business_line"), profile.theme, "pending verification")
    node = _first_non_pending(profit.get("company_position"), workbench.get("traded_business_line"), profile.node, company.get("sector"), "pending verification")
    claims = _str_list(hero.get("claims")) or _split_claims(_first(memo_conclusion, profile.one_sentence_thesis, analysis.get("headline"), "research pending"))
    tags = _str_list(hero.get("tags")) or _str_list(action.get("status_tags")) or [theme, node]

    data = {
        "company": {
            "name": name,
            "code": code,
            "subtitle": f"{code} | {theme} / {node}".strip(" |"),
            "theme": theme,
            "node": node,
        },
        "hero": {
            "kicker": "Is this company worth researching?",
            "title": name,
            "industry_rating": _first(hero.get("industry_rating"), "B"),
            "investment_rating": _first(hero.get("investment_rating"), "B"),
            "tags": tags[:5],
            "claims": claims[:4],
            "note": "Start with what is priced, what is verified, and what to check next.",
        },
        "one_sentence_conclusion": _first(
            _dict(workbench.get("public_equity_agent")).get("one_sentence_conclusion"),
            memo_conclusion,
            claims[0] if claims else "",
            profile.one_sentence_thesis,
            "Conclusion pending verification.",
        ),
        "profit_flow": {
            "title": "Profit Flow",
            "description": "Explain why profit pools may flow to this company or segment.",
            "value_pool": _first(profit.get("value_pool"), profile.core_driver, theme),
            "items": _profit_items(profit, profile),
            "company_position": node,
            "why_profit_flows_here": _first(profit.get("why_profit_flows_here"), profile.rerating_anchor, "pending verification"),
        },
        "logic_tree": _logic_tree(workbench, profile),
        "expectation_gap": {
            "market_believes": _str_list(gap.get("market_believes")) or [_first(workbench.get("what_market_is_pricing"), "market consensus pending verification")],
            "analyst_view": _str_list(gap.get("analyst_view")) or [_first(gap.get("underestimated"), profile.expectation_gap, "research view pending verification")],
            "gap_score": _num(gap.get("gap_score"), 50),
            "underestimated": _first(gap.get("underestimated"), profile.rerating_anchor, "pending verification"),
            "overestimated": _first(gap.get("overestimated"), "pending verification"),
        },
        "moat": {
            "summary": _first(_dict(workbench.get("moat_radar")).get("explanation"), "; ".join(profile.barriers), "moat pending verification"),
            "items": _moat_items(workbench, profile),
        },
        "financial_validation": _str_list(_dict(workbench.get("public_equity_agent")).get("financial_validation"))
        or [_validation_text(item) for item in _list(workbench.get("validation_panel"))]
        or ["financial validation pending"],
        "valuation_odds": _first(workbench.get("valuation_odds"), profile.valuation_odds, "valuation odds pending"),
        "catalysts": _event_list(workbench.get("catalysts"), profile.catalysts, workbench.get("recent_catalysts")),
        "disconfirming_signals": _risk_list(workbench.get("risks"), profile.disconfirming_signals, workbench.get("unknowns")),
        "trade_review": {
            "return_pct": _num(trade.get("trade_return_pct"), analysis.get("return", 0)),
            "score": _num(trade.get("trade_score"), analysis.get("score", 0)),
            "buy_verdict": _first(trade.get("buy_verdict"), _dict(analysis.get("optimal")).get("buy_label"), "buy point pending"),
            "sell_verdict": _first(trade.get("sell_verdict"), _dict(analysis.get("optimal")).get("sell_label"), "sell point pending"),
            "execution_lesson": _first(trade.get("execution_lesson"), _dict(analysis.get("optimal")).get("sell_reason"), analysis.get("headline"), "review pending"),
            "rows": _trade_rows(trade_frame),
        },
        "next_action": {
            "current_action": _first(action.get("current_action"), profile.position_sizing, "add to watchlist and verify"),
            "suitable_for": _first(action.get("suitable_for"), profile.best_expression, "investors willing to verify uncertain catalysts"),
            "not_suitable_for": _first(action.get("not_suitable_for"), "not suitable for pure chase without evidence"),
            "recheck_conditions": _str_list(action.get("recheck_conditions")) or _str_list(profile.disconfirming_signals)[:4],
        },
        "deep_memos": {
            "wang": wang_memo,
            "public_equity": public_memo,
        },
        "market_catalyst": _dict(workbench.get("market_catalyst")),
        "market_hype_reason": _first(workbench.get("market_hype_reason"), "recent hype reason pending verification"),
        "recent_catalysts": _str_list(workbench.get("recent_catalysts")),
        "traded_business_line": _first(workbench.get("traded_business_line"), "pending verification"),
        "what_market_is_pricing": _first(workbench.get("what_market_is_pricing"), "pending verification"),
        "evidence_quality": _first(workbench.get("evidence_quality"), "low"),
        "evidence": _str_list(workbench.get("evidence")),
        "news": _str_list(workbench.get("news")),
        "unknowns": _str_list(workbench.get("unknowns")),
        "agent_errors": _str_list(workbench.get("agent_errors")),
    }
    data.update(_expression_layer(data, workbench, analysis))
    return _normalize_presenter_data(data)


def run_presenter_workbench_agent(*, fallback: dict[str, Any], workbench: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    try:
        return _call_presenter_structured_json(
            _presenter_system_prompt(),
            _presenter_user_prompt(fallback, workbench, analysis),
            max_output_tokens=_presenter_max_output_tokens(),
        )
    except Exception as exc:
        errors.append(f"presenter_structured_output_failed: {exc}")

    try:
        agent_data = _call_json_agent(
            _presenter_system_prompt(),
            _presenter_user_prompt(fallback, workbench, analysis),
            max_output_tokens=_presenter_max_output_tokens(),
            allow_web=False,
        )
    except Exception as exc:
        errors.append(f"presenter_json_fallback_failed: {exc}")
        return _presenter_failed_fallback(fallback, errors)

    if isinstance(agent_data, dict) and agent_data.get("_agent_error"):
        errors.append(f"presenter_json_fallback_failed: {agent_data.get('_agent_error')}")
        return _presenter_failed_fallback(fallback, errors, raw_text=agent_data.get("_raw_text"))

    if errors:
        agent_data = dict(agent_data if isinstance(agent_data, dict) else {})
        agent_data["agent_errors"] = _str_list(agent_data.get("agent_errors")) + errors
    return agent_data


def _presenter_system_prompt() -> str:
    return """
You are the Presenter / Structurer Agent for a stock research workbench.
Read market catalyst context, WANG memo, Public Equity memo, and trade analysis.
Output strict JSON only. Write all user-facing strings in Chinese.
Do not redo research or invent facts.
Keep uncertainty visible. Use "待验证" only when the provided memos or catalyst context do not support a stronger statement.
The JSON must directly drive frontend modules: hero, conclusion, profit flow,
logic tree, expectation gap, moat, validation, catalysts, risks, next action,
claim cards, evidence blocks, chart annotations, visual priority, presenter copy,
frontend modules, deep memos, and agent errors.
""".strip()


def _presenter_user_prompt(fallback: dict[str, Any], workbench: dict[str, Any], analysis: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Convert compact research input into frontend workbench/concept JSON.",
            "compact_payload": _compact_presenter_payload(fallback, workbench, analysis),
            "schema": {
                "company": "dict",
                "hero": "dict with tags and claims",
                "one_sentence_conclusion": "short string",
                "profit_flow": "dict with items",
                "logic_tree": "list of {node, certainty_pct}",
                "expectation_gap": "dict",
                "moat": "dict",
                "financial_validation": "list",
                "catalysts": "list",
                "disconfirming_signals": "list",
                "next_action": "dict",
                "claim_cards": "list",
                "evidence_blocks": "list",
                "chart_annotations": "dict",
                "visual_priority": "list",
                "presenter_copy": "dict",
                "frontend_modules": "dict",
                "deep_memos": "dict summaries",
                "agent_errors": "list",
            },
        },
        ensure_ascii=False,
        default=str,
    )


def _call_presenter_structured_json(system_prompt: str, user_prompt: str, *, max_output_tokens: int | None = None) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or "your-openai-api-key" in api_key:
        raise RuntimeError("OPENAI_API_KEY is required for presenter agent")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    model = os.getenv("PRESENTER_AGENT_MODEL") or _model(None)
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_schema", "json_schema": _presenter_json_schema()},
    }
    max_output = max_output_tokens or _presenter_max_output_tokens()
    if max_output:
        body["max_tokens"] = max_output
    data = _post_json(f"{base_url}/chat/completions", api_key, body, timeout=140)
    message = _dict(data.get("choices", [{}])[0].get("message"))
    if message.get("refusal"):
        raise RuntimeError(f"presenter agent refused structured output: {message.get('refusal')}")
    return _parse_json_object_text(str(message.get("content") or ""))


def _presenter_json_schema() -> dict[str, Any]:
    module_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["enabled", "priority"],
        "properties": {"enabled": {"type": "boolean"}, "priority": {"type": "number"}},
    }
    return {
        "name": "workbench_presenter",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "company",
                "hero",
                "one_sentence_conclusion",
                "profit_flow",
                "logic_tree",
                "expectation_gap",
                "moat",
                "financial_validation",
                "valuation_odds",
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
            ],
            "properties": {
                "company": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "code", "subtitle", "theme", "node"],
                    "properties": {key: {"type": "string"} for key in ["name", "code", "subtitle", "theme", "node"]},
                },
                "hero": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kicker", "title", "industry_rating", "investment_rating", "tags", "claims", "note"],
                    "properties": {
                        "kicker": {"type": "string"},
                        "title": {"type": "string"},
                        "industry_rating": {"type": "string"},
                        "investment_rating": {"type": "string"},
                        "tags": _string_array_schema(max_items=5),
                        "claims": _string_array_schema(max_items=4),
                        "note": {"type": "string"},
                    },
                },
                "one_sentence_conclusion": {"type": "string"},
                "profit_flow": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "description", "value_pool", "items", "company_position", "why_profit_flows_here"],
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "value_pool": {"type": "string"},
                        "items": {
                            "type": "array",
                            "maxItems": 6,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "share_pct", "highlight"],
                                "properties": {"name": {"type": "string"}, "share_pct": {"type": "number"}, "highlight": {"type": "boolean"}},
                            },
                        },
                        "company_position": {"type": "string"},
                        "why_profit_flows_here": {"type": "string"},
                    },
                },
                "logic_tree": {
                    "type": "array",
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["node", "certainty_pct"],
                        "properties": {"node": {"type": "string"}, "certainty_pct": {"type": "number"}},
                    },
                },
                "expectation_gap": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["market_believes", "analyst_view", "gap_score", "underestimated", "overestimated"],
                    "properties": {
                        "market_believes": _string_array_schema(max_items=4),
                        "analyst_view": _string_array_schema(max_items=4),
                        "gap_score": {"type": "number"},
                        "underestimated": {"type": "string"},
                        "overestimated": {"type": "string"},
                    },
                },
                "moat": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["summary", "items"],
                    "properties": {"summary": {"type": "string"}, "items": _string_array_schema(max_items=6)},
                },
                "financial_validation": _string_array_schema(max_items=6),
                "valuation_odds": {"type": "string"},
                "catalysts": _string_array_schema(max_items=8),
                "disconfirming_signals": _string_array_schema(max_items=8),
                "next_action": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["current_action", "suitable_for", "not_suitable_for", "recheck_conditions"],
                    "properties": {
                        "current_action": {"type": "string"},
                        "suitable_for": {"type": "string"},
                        "not_suitable_for": {"type": "string"},
                        "recheck_conditions": _string_array_schema(max_items=6),
                    },
                },
                "claim_cards": {
                    "type": "array",
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["title", "claim", "evidence", "confidence_pct", "risk"],
                        "properties": {
                            "title": {"type": "string"},
                            "claim": {"type": "string"},
                            "evidence": {"type": "string"},
                            "confidence_pct": {"type": "number"},
                            "risk": {"type": "string"},
                        },
                    },
                },
                "evidence_blocks": {
                    "type": "array",
                    "maxItems": 12,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["type", "title", "evidence", "status"],
                        "properties": {key: {"type": "string"} for key in ["type", "title", "evidence", "status"]},
                    },
                },
                "chart_annotations": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["profit_flow", "expectation_gap", "trade_review"],
                    "properties": {
                        "profit_flow": _string_array_schema(max_items=4),
                        "expectation_gap": _string_array_schema(max_items=4),
                        "trade_review": _string_array_schema(max_items=4),
                    },
                },
                "visual_priority": _string_array_schema(max_items=8),
                "presenter_copy": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["hero", "decision"],
                    "properties": {"hero": {"type": "string"}, "decision": {"type": "string"}},
                },
                "frontend_modules": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["hero", "profit_flow", "logic_tree", "expectation_gap", "moat_validation", "decision"],
                    "properties": {key: module_schema for key in ["hero", "profit_flow", "logic_tree", "expectation_gap", "moat_validation", "decision"]},
                },
                "deep_memos": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["wang", "public_equity"],
                    "properties": {"wang": {"type": "string"}, "public_equity": {"type": "string"}},
                },
                "agent_errors": _string_array_schema(max_items=8),
            },
        },
    }


def _string_array_schema(*, max_items: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if max_items:
        schema["maxItems"] = max_items
    return schema


def _presenter_failed_fallback(fallback: dict[str, Any], errors: list[str], *, raw_text: Any = None) -> dict[str, Any]:
    deterministic = dict(fallback if isinstance(fallback, dict) else {})
    merged_errors = _str_list(deterministic.get("agent_errors")) + [str(item) for item in errors if str(item).strip()]
    deterministic["agent_errors"] = _dedupe(merged_errors)
    if raw_text:
        deterministic["_raw_text"] = str(raw_text)[:1000]
    return _normalize_presenter_data(deterministic, fallback)


def _compact_presenter_payload(fallback: dict[str, Any], workbench: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    fallback = _dict(fallback)
    workbench = _dict(workbench)
    return {
        "company": _dict(fallback.get("company")) or _dict(workbench.get("company")),
        "hero": _dict(fallback.get("hero")) or _dict(workbench.get("hero")),
        "profit_flow": _dict(fallback.get("profit_flow")) or _dict(workbench.get("profit_flow")),
        "expectation_gap": _dict(fallback.get("expectation_gap")) or _dict(workbench.get("expectation_gap")),
        "action": _dict(fallback.get("next_action")) or _dict(fallback.get("action")) or _dict(workbench.get("action")),
        "risks": _list(fallback.get("disconfirming_signals")) or _list(workbench.get("risks")),
        "validation": _list(fallback.get("financial_validation")) or _list(workbench.get("validation_panel")),
        "market_catalyst": _dict(workbench.get("market_catalyst")),
        "market_hype_reason": _first(workbench.get("market_hype_reason"), fallback.get("market_hype_reason"), "recent hype reason pending verification"),
        "recent_catalysts": _str_list(workbench.get("recent_catalysts")) or _str_list(fallback.get("recent_catalysts")),
        "traded_business_line": _first(workbench.get("traded_business_line"), fallback.get("traded_business_line"), "pending verification"),
        "what_market_is_pricing": _first(workbench.get("what_market_is_pricing"), fallback.get("what_market_is_pricing"), "pending verification"),
        "evidence_quality": _first(workbench.get("evidence_quality"), fallback.get("evidence_quality"), "low"),
        "evidence": _str_list(workbench.get("evidence")),
        "news": _str_list(workbench.get("news")),
        "unknowns": _str_list(workbench.get("unknowns")) or _str_list(fallback.get("unknowns")),
        "deep_memos_summary": _compact_deep_memos(workbench),
        "trade_analysis": _compact_trade_analysis(analysis),
        "agent_errors": _str_list(workbench.get("agent_errors")) or _str_list(fallback.get("agent_errors")),
    }


def _merge_presenter_data(fallback: dict[str, Any], agent_data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(agent_data, dict) and agent_data.get("_agent_error"):
        return _presenter_failed_fallback(fallback, [f"presenter_agent_failed: {agent_data.get('_agent_error')}"], raw_text=agent_data.get("_raw_text"))
    merged = _deep_merge(_dict(fallback), _dict(agent_data))
    return _normalize_presenter_data(merged, fallback)


def _normalize_presenter_data(data: dict[str, Any], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = _dict(fallback)
    normalized = _deep_merge(fallback, _dict(data))
    for key in ["company", "hero", "profit_flow", "expectation_gap", "moat", "trade_review", "next_action", "deep_memos", "chart_annotations", "presenter_copy", "frontend_modules"]:
        if not isinstance(normalized.get(key), dict):
            normalized[key] = _dict(fallback.get(key))
    for key in ["logic_tree", "financial_validation", "catalysts", "disconfirming_signals", "claim_cards", "evidence_blocks", "visual_priority", "agent_errors", "recent_catalysts", "evidence", "news", "unknowns"]:
        normalized[key] = _list(normalized.get(key)) or _list(fallback.get(key))

    company = normalized["company"]
    company["name"] = _first(company.get("name"), _dict(fallback.get("company")).get("name"), "stock")
    company["code"] = _first(company.get("code"), _dict(fallback.get("company")).get("code"), "")
    company["theme"] = _first(company.get("theme"), _dict(fallback.get("company")).get("theme"), "pending verification")
    company["node"] = _first(company.get("node"), _dict(fallback.get("company")).get("node"), "pending verification")
    company["subtitle"] = _first(company.get("subtitle"), f"{company['code']} | {company['theme']} / {company['node']}".strip(" |"))

    hero = normalized["hero"]
    hero["tags"] = _str_list(hero.get("tags"))[:5] or _str_list(_dict(fallback.get("hero")).get("tags"))[:5] or ["pending verification"]
    hero["claims"] = _str_list(hero.get("claims"))[:4] or _str_list(_dict(fallback.get("hero")).get("claims"))[:4] or ["conclusion pending verification"]
    hero["industry_rating"] = _first(hero.get("industry_rating"), "B")
    hero["investment_rating"] = _first(hero.get("investment_rating"), "B")
    hero["title"] = _first(hero.get("title"), company["name"])
    hero["kicker"] = _first(hero.get("kicker"), "Is this company worth researching?")
    hero["note"] = _first(hero.get("note"), "Verify the market story before acting.")

    normalized["one_sentence_conclusion"] = _first(normalized.get("one_sentence_conclusion"), hero["claims"][0])
    normalized["logic_tree"] = _normalize_logic_tree(normalized.get("logic_tree"))
    normalized["profit_flow"]["items"] = _normalize_profit_items(normalized["profit_flow"].get("items"))
    normalized["expectation_gap"]["market_believes"] = _str_list(normalized["expectation_gap"].get("market_believes")) or ["pending verification"]
    normalized["expectation_gap"]["analyst_view"] = _str_list(normalized["expectation_gap"].get("analyst_view")) or ["pending verification"]
    normalized["expectation_gap"]["gap_score"] = _num(normalized["expectation_gap"].get("gap_score"), 50)
    normalized["market_catalyst"] = _dict(normalized.get("market_catalyst"))
    normalized["market_hype_reason"] = _first(normalized.get("market_hype_reason"), "recent hype reason pending verification")
    normalized.update(_expression_layer(normalized, {}, {}))
    return normalized


def _expression_layer(data: dict[str, Any], workbench: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    company = _dict(data.get("company"))
    claims = _str_list(_dict(data.get("hero")).get("claims"))
    profit = _dict(data.get("profit_flow"))
    logic = _list(data.get("logic_tree"))
    gap = _dict(data.get("expectation_gap"))
    moat = _dict(data.get("moat"))
    financial = _str_list(data.get("financial_validation"))
    risks = _str_list(data.get("disconfirming_signals"))
    catalysts = _str_list(data.get("catalysts"))
    next_action = _dict(data.get("next_action"))

    claim_cards = []
    for idx, claim in enumerate(claims[:4]):
        claim_cards.append(
            {
                "title": f"Claim {idx + 1}",
                "claim": claim,
                "evidence": _first(financial[idx] if idx < len(financial) else "", "pending verification"),
                "confidence_pct": max(35, 80 - idx * 8),
                "risk": _first(risks[idx] if idx < len(risks) else "", "pending verification"),
            }
        )
    evidence_blocks = [{"type": "financial", "title": "Validation", "evidence": item, "status": "check"} for item in financial[:5]]
    evidence_blocks += [{"type": "risk", "title": "Disconfirming Signal", "evidence": item, "status": "risk"} for item in risks[:4]]
    evidence_blocks += [{"type": "catalyst", "title": "Catalyst", "evidence": item, "status": "watch"} for item in catalysts[:4]]

    return {
        "newbie_summary": f"{company.get('name', 'This company')} should be judged through market story, verified business contribution, valuation odds, and disconfirming signals.",
        "section_narrative": {
            "hero": _first("; ".join(claims), "Conclusion pending verification"),
            "profit_flow": _first(profit.get("why_profit_flows_here"), "Profit flow pending verification"),
            "logic_tree": " -> ".join(str(_dict(item).get("node", item)) for item in logic[:4]) or "Logic chain pending verification",
            "expectation_gap": _first(gap.get("underestimated"), "Expectation gap pending verification"),
            "moat_validation": _first(moat.get("summary"), "Moat pending verification"),
            "decision": _first(next_action.get("current_action"), "Next action pending verification"),
        },
        "claim_cards": claim_cards,
        "evidence_blocks": evidence_blocks,
        "chart_annotations": {
            "profit_flow": [_first(profit.get("why_profit_flows_here"), "Profit flow pending verification")],
            "expectation_gap": _str_list(gap.get("analyst_view"))[:3],
            "trade_review": [_first(_dict(data.get("trade_review")).get("execution_lesson"), analysis.get("headline"), "Trade review pending")],
        },
        "visual_priority": ["hero", "profit_flow", "logic_tree", "expectation_gap", "moat_validation", "decision"],
        "presenter_copy": {
            "hero": _first("; ".join(claims), "Conclusion pending verification"),
            "decision": _first(next_action.get("current_action"), "Next action pending verification"),
        },
        "frontend_modules": {
            name: {"enabled": True, "priority": idx + 1}
            for idx, name in enumerate(["hero", "profit_flow", "logic_tree", "expectation_gap", "moat_validation", "decision"])
        },
    }


def _compact_deep_memos(workbench: dict[str, Any], limit: int = 900) -> dict[str, str]:
    memos = _dict(workbench.get("deep_memos"))
    wang = _first(memos.get("wang"), _dict(workbench.get("wang_agent")).get("deep_memo"), _dict(workbench.get("wang_agent")).get("memo"))
    public = _first(memos.get("public_equity"), _dict(workbench.get("public_equity_agent")).get("deep_memo"), _dict(workbench.get("public_equity_agent")).get("memo"))
    return {"wang": _truncate(wang, limit), "public_equity": _truncate(public, limit)}


def _compact_trade_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    analysis = _dict(analysis)
    keys = ["name", "code", "trade_date", "side", "price", "quantity", "amount", "headline", "score", "return"]
    return {key: analysis.get(key) for key in keys if key in analysis}


def _presenter_agent_enabled() -> bool:
    return os.getenv("PRESENTER_AGENT_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def _presenter_max_output_tokens() -> int:
    try:
        return max(1600, int(os.getenv("PRESENTER_MAX_OUTPUT_TOKENS", "3200")))
    except Exception:
        return 3200


def _profit_items(profit: dict[str, Any], profile: IndustryProfile) -> list[dict[str, Any]]:
    items = _normalize_profit_items(profit.get("items"))
    if items:
        return items
    labels = [profile.core_driver, profile.node, "financial verification"]
    defaults = [40, 35, 25]
    return [{"name": _first(label, f"segment {idx + 1}"), "share_pct": defaults[idx], "highlight": idx == 1} for idx, label in enumerate(labels[:3])]


def _normalize_profit_items(value: Any) -> list[dict[str, Any]]:
    items = []
    for item in _list(value):
        item = _dict(item)
        if item:
            items.append({"name": _first(item.get("name"), "segment"), "share_pct": _num(item.get("share_pct"), 0), "highlight": bool(item.get("highlight"))})
    return items


def _logic_tree(workbench: dict[str, Any], profile: IndustryProfile) -> list[dict[str, Any]]:
    items = _normalize_logic_tree(workbench.get("logic_tree"))
    if items:
        return items
    labels = [title for _, title, _ in profile.chain_nodes] or [profile.core_driver, profile.node, "financial verification"]
    return [{"node": _first(label, "logic node"), "certainty_pct": max(40, 85 - idx * 10)} for idx, label in enumerate(labels[:5])]


def _normalize_logic_tree(value: Any) -> list[dict[str, Any]]:
    items = []
    for item in _list(value):
        item = _dict(item)
        if item:
            items.append({"node": _first(item.get("node"), "logic node"), "certainty_pct": _num(item.get("certainty_pct"), 50)})
    return items[:6]


def _moat_items(workbench: dict[str, Any], profile: IndustryProfile) -> list[str]:
    moat = _dict(workbench.get("moat_radar"))
    dimensions = _list(moat.get("dimensions"))
    rows = []
    for item in dimensions:
        item = _dict(item)
        if item:
            rows.append(f"{_first(item.get('name'), 'moat')}: company {item.get('company', 'pending')} / industry {item.get('average', 'pending')}")
    return rows or _str_list(profile.barriers)[:5] or ["moat pending verification"]


def _event_list(value: Any, profile_items: Any, recent: Any = None) -> list[str]:
    rows = [_event_text(item) for item in _list(value)]
    rows += _str_list(profile_items)
    rows += _str_list(recent)
    return _dedupe(rows)[:8]


def _risk_list(value: Any, profile_items: Any, unknowns: Any = None) -> list[str]:
    rows = [_risk_text(item) for item in _list(value)]
    rows += _str_list(profile_items)
    rows += _str_list(unknowns)
    return _dedupe(rows)[:8]


def _event_text(item: Any) -> str:
    item_dict = _dict(item)
    if item_dict:
        return ": ".join(part for part in [_first(item_dict.get("time")), _first(item_dict.get("event")), _first(item_dict.get("impact"))] if part)
    return str(item)


def _risk_text(item: Any) -> str:
    item_dict = _dict(item)
    if item_dict:
        return ": ".join(part for part in [_first(item_dict.get("name")), _first(item_dict.get("why_it_matters")), _first(item_dict.get("downgrade_action"))] if part)
    return str(item)


def _validation_text(item: Any) -> str:
    item_dict = _dict(item)
    if item_dict:
        return ": ".join(part for part in [_first(item_dict.get("status")), _first(item_dict.get("item")), _first(item_dict.get("evidence"))] if part)
    return str(item)


def _trade_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    rows = []
    for item in frame.tail(12).to_dict("records"):
        rows.append({key: _jsonable(value) for key, value in item.items()})
    return rows


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        elif value not in (None, "", [], {}):
            result[key] = value
    return result


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in (None, "", [], {})]
    if isinstance(value, tuple):
        return [item for item in value if item not in (None, "", [], {})]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _str_list(value: Any) -> list[str]:
    return [str(item) for item in _list(value)]


def _first(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value not in (None, "", [], {}):
            return str(value)
    return ""


def _first_non_pending(*values: Any) -> str:
    for value in values:
        text = _first(value)
        if text and not _is_pending_text(text):
            return text
    return _first(*values)


def _is_pending_text(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return normalized in {"待验证", "pending", "pending verification", "research pending", "conclusion pending verification."}


def _memo_conclusion(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    lines = [line.strip(" 　-*#") for line in raw.splitlines() if line.strip(" 　-*#")]
    skip_terms = {"memo", "一句话投资判断", "总结", "结论", "当前股价交易的是什么"}
    for line in lines:
        compact = line.lower().replace(" ", "")
        if any(term.lower().replace(" ", "") == compact for term in skip_terms):
            continue
        if len(line) >= 18 and any(term in line for term in ["值得", "谨慎", "关注", "交易", "估值", "风险", "待验证"]):
            return _truncate(line, 120)
    for line in lines:
        if len(line) >= 18:
            return _truncate(line, 120)
    return _truncate(raw, 120)


def _split_claims(text: str) -> list[str]:
    parts = [part.strip(" -;；。.\n\t") for part in str(text or "").replace("；", ";").replace("。", ";").split(";")]
    return [part for part in parts if part][:4]


def _num(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _truncate(text: Any, limit: int) -> str:
    raw = str(text or "").strip()
    return raw if len(raw) <= limit else raw[:limit] + "..."


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    rows = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            rows.append(text)
    return rows


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
