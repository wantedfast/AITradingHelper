from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

from .data_provider import MarketDataProvider
from .execution_structurer import structure_trade_execution_payload
from .industry_profiles import IndustryProfile
from .trade_execution_agent import analyze_trade_execution
from .trade_execution_data import build_trade_execution_data_context
from .trade_rounds import TradeRound
from .workbench_agents import _call_json_agent, _research_model


def build_trade_execution_chain(
    *,
    provider: MarketDataProvider,
    profile: IndustryProfile,
    trade_round: TradeRound,
    output: str | Path,
    prefetched_quotes: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """Run the independent execution chain and persist its debug artifacts."""

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    data_context = build_trade_execution_data_context(
        provider=provider,
        profile=profile,
        trade_round=trade_round,
        prefetched_quotes=prefetched_quotes,
    )
    agent_output = analyze_trade_execution(data_context)
    final_payload = structure_trade_execution_payload(
        trade_facts=data_context.get("trade_facts"),
        execution_analysis=agent_output,
        data_source_status=data_context.get("data_source_status"),
    )
    _write_json(output.with_suffix(".execution_data_context.json"), data_context)
    _write_json(output.with_suffix(".trade_execution_agent_output.json"), agent_output)
    _write_json(output.with_suffix(".trade_execution.json"), final_payload)
    return final_payload


def enhance_trade_execution_with_llm(
    *,
    execution_payload: dict[str, Any],
    workbench: dict[str, Any],
    output: str | Path,
    research_model_tier: str = "standard",
) -> dict[str, Any]:
    if not _trade_execution_llm_enabled():
        return execution_payload

    output = Path(output)
    started = time.perf_counter()
    context = _compact_execution_llm_context(execution_payload, workbench)
    model_context = {"research_model_tier": research_model_tier, "research_model": _dict(workbench.get("research_model"))}
    model = os.getenv("TRADE_EXECUTION_LLM_MODEL") or _research_model(model_context)
    try:
        llm_output = _call_json_agent(
            _trade_execution_llm_system_prompt(),
            _trade_execution_llm_user_prompt(context),
            model_override=model,
            max_output_tokens=_trade_execution_llm_max_output_tokens(),
            allow_web=False,
        )
        llm_output["research_metrics"] = {
            "seconds": round(time.perf_counter() - started, 4),
            "model": model,
            "mode": "trade_execution_llm",
        }
        enhanced = _merge_trade_execution_llm_output(execution_payload, llm_output)
        _write_json(output.with_suffix(".trade_execution_llm_output.json"), llm_output)
        _write_json(output.with_suffix(".trade_execution.json"), enhanced)
        return enhanced
    except Exception as exc:
        error_payload = {
            "_agent_error": f"trade_execution_llm_failed: {exc}",
            "research_metrics": {"seconds": round(time.perf_counter() - started, 4), "model": model},
        }
        _write_json(output.with_suffix(".trade_execution_llm_output.json"), error_payload)
        return execution_payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _trade_execution_llm_enabled() -> bool:
    return os.getenv("TRADE_EXECUTION_LLM_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def _trade_execution_llm_max_output_tokens() -> int:
    try:
        value = int(os.getenv("TRADE_EXECUTION_LLM_MAX_OUTPUT_TOKENS", "1800").strip())
    except Exception:
        return 1800
    return value if value > 0 else 1800


def _trade_execution_llm_system_prompt() -> str:
    return """
你是交易执行复盘 Agent。你只基于输入里的交易事实、行情相对强弱、同概念比较和投研上下文判断买卖点质量。
不要编造行情、财务数据或新闻；证据不足时明确写“待验证”。
你的任务不是重复涨跌幅，而是解释：买点/卖点为什么好或不好，是否跟随题材，是否有短线确认，是否偏离板块核心。
输出合法 JSON，不要 Markdown。
""".strip()


def _trade_execution_llm_user_prompt(context: dict[str, Any]) -> str:
    return f"""
请输出以下 JSON 字段：
{{
  "trade_execution_notes": {{
    "buy_verdict": "good/average/poor/unknown",
    "sell_verdict": "good/average/poor/unknown",
    "main_lesson": "这轮交易最重要的执行教训"
  }},
  "trade_timing": {{
    "buy_points": [{{"date": "YYYY-MM-DD", "judgment": "买点判断", "reason": "结合题材/板块/个股短线结构的原因"}}],
    "sell_points": [{{"date": "YYYY-MM-DD", "judgment": "卖点判断", "reason": "结合题材/板块/个股短线结构的原因"}}]
  }},
  "execution_advice": {{
    "summary": "总体执行复盘结论",
    "buy_issue": "买点是否更好以及原因",
    "sell_issue": "卖点是否更好以及原因",
    "next_time_rules": ["下一次可执行规则"],
    "confirmation_signals": ["下一次确认信号"]
  }}
}}

输入上下文：
{json.dumps(context, ensure_ascii=False, default=str)}
""".strip()


def _compact_execution_llm_context(execution_payload: dict[str, Any], workbench: dict[str, Any]) -> dict[str, Any]:
    workbench = _dict(workbench)
    return {
        "execution_rule_result": execution_payload,
        "company": workbench.get("company"),
        "market_hype_reason": workbench.get("market_hype_reason"),
        "traded_business_line": workbench.get("traded_business_line"),
        "what_market_is_pricing": workbench.get("what_market_is_pricing"),
        "evidence_quality": workbench.get("evidence_quality"),
        "hero": workbench.get("hero"),
        "profit_flow": workbench.get("profit_flow"),
        "expectation_gap": workbench.get("expectation_gap"),
        "action": workbench.get("action"),
        "deep_memos_summary": {
            "wang": _truncate(_dict(workbench.get("deep_memos")).get("wang"), 900),
            "public_equity": _truncate(_dict(workbench.get("deep_memos")).get("public_equity"), 900),
        },
    }


def _merge_trade_execution_llm_output(payload: dict[str, Any], llm_output: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    notes = _dict(llm_output.get("trade_execution_notes"))
    if notes:
        merged.setdefault("trade_execution_notes", {}).update({key: value for key, value in notes.items() if value})
    advice = _dict(llm_output.get("execution_advice"))
    if advice:
        merged.setdefault("execution_advice", {}).update({key: value for key, value in advice.items() if value not in (None, "", [], {})})
    timing = _dict(llm_output.get("trade_timing"))
    for side in ("buy_points", "sell_points"):
        updates = timing.get(side)
        existing = _dict(merged.get("trade_timing")).get(side)
        if isinstance(updates, list) and isinstance(existing, list):
            _merge_trade_points(existing, updates)
    merged["llm_enhanced"] = True
    metrics = _dict(llm_output.get("research_metrics"))
    if metrics:
        merged["llm_metrics"] = metrics
    return merged


def _merge_trade_points(existing: list[Any], updates: list[Any]) -> None:
    by_date = {str(_dict(item).get("date") or ""): _dict(item) for item in updates if isinstance(item, dict)}
    for item in existing:
        if not isinstance(item, dict):
            continue
        update = by_date.get(str(item.get("date") or ""))
        if not update:
            continue
        if update.get("judgment"):
            item["judgment"] = update["judgment"]
        if update.get("reason"):
            item["reason"] = update["reason"]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."
