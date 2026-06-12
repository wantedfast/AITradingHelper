from __future__ import annotations

import os
import time
from typing import Any

from .report_usage import estimate_tokens
from .workbench_agents import _call_json_agent

NEWS_CONTEXT_MODEL = "gpt-4.1"
FACT_SOURCE_TYPES = {"llm", "fallback", "missing"}


def build_market_catalyst_context(code: str, name: str) -> dict[str, Any]:
    """Fetch a compact market-catalyst context for WANG/Public agents.

    This is intentionally small: it gives the research agents a current-market
    question to answer without bloating their prompts.
    """
    if os.getenv("WORKBENCH_NEWS_CONTEXT_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return _fallback_market_catalyst(code, name)

    queries = _market_catalyst_queries(code, name)
    started = time.perf_counter()
    system_prompt = _market_catalyst_system_prompt()
    user_prompt = _market_catalyst_user_prompt(code, name, queries)
    max_output_tokens = _news_max_output_tokens()
    model = _news_context_model()
    try:
        raw = _call_json_agent(
            system_prompt,
            user_prompt,
            model_override=model,
            max_output_tokens=max_output_tokens,
            allow_web=True,
        )
        result = _normalize_market_catalyst(raw, code, name, queries)
        result["research_metrics"] = {
            "seconds": round(time.perf_counter() - started, 4),
            "model": model,
            "mode": "market_catalyst",
            "allow_web": True,
            "max_output_tokens": max_output_tokens,
            "estimated_input_tokens": estimate_tokens(system_prompt) + estimate_tokens(user_prompt),
            "estimated_output_tokens": max_output_tokens,
            "api_usage": raw.get("_api_usage") if isinstance(raw, dict) else {},
        }
        return result
    except Exception as exc:
        data = _fallback_market_catalyst(code, name, queries)
        data["agent_error"] = f"market_catalyst_failed: {exc}"
        data["research_metrics"] = {
            "seconds": round(time.perf_counter() - started, 4),
            "model": model,
            "mode": "market_catalyst",
            "allow_web": True,
            "max_output_tokens": max_output_tokens,
            "estimated_input_tokens": estimate_tokens(system_prompt) + estimate_tokens(user_prompt),
            "estimated_output_tokens": max_output_tokens,
            "status": "error",
            "error": str(exc),
            "fallback_used": True,
        }
        data["unknowns"].append("无法稳定获取最新市场催化剂，需要人工复核公告、异动和研报。")
        return data


def _news_max_output_tokens() -> int:
    try:
        return max(300, int(os.getenv("NEWS_CONTEXT_MAX_OUTPUT_TOKENS", "900")))
    except Exception:
        return 900


def _news_context_model() -> str:
    return os.getenv("NEWS_CONTEXT_MODEL") or os.getenv("WORKBENCH_NEWS_CONTEXT_MODEL") or NEWS_CONTEXT_MODEL


def _market_catalyst_queries(code: str, name: str) -> list[str]:
    code = str(code or "").strip()
    name = str(name or code or "").strip()
    return [
        f"{name} {code} 最近上涨 原因 市场炒作 2026",
        f"{name} 涨停 异动 公告 机构 研报 电容 AI 机器人 新能源 2026",
        f"{name} 同花顺 问财 东方财富 股吧 最近催化",
    ]


def _market_catalyst_system_prompt() -> str:
    return """
You are a market catalyst scout for A-share stock research.
Use web search when available. Return strict JSON only.
Do not invent catalysts. If recent evidence is weak, write "最近炒作原因待验证".
Keep the answer short and optimized as context for downstream research agents.
""".strip()


def _market_catalyst_user_prompt(code: str, name: str, queries: list[str]) -> str:
    return f"""
Stock: {name} {code}
Search queries to investigate:
{queries}

Return JSON:
{{
  "market_hype_reason": "最近市场为什么炒它，一句话；证据不足则写最近炒作原因待验证",
  "recent_catalysts": [
    {{
      "fact": "最近公告/新闻/研报/异动催化，最多5条",
      "date": "YYYY-MM-DD or empty when unknown",
      "source": "source name or URL from search, empty when unavailable"
    }}
  ],
  "industry_news": [
    {{
      "fact": "relevant industry news",
      "date": "YYYY-MM-DD or empty when unknown",
      "source": "source name or URL from search, empty when unavailable"
    }}
  ],
  "traded_business_line": "当前股价主要交易的业务线或主题",
  "what_market_is_pricing": "市场正在给什么预期定价",
  "evidence_quality": "high/medium/low",
  "unknowns": ["仍需验证的问题"],
  "evidence": [
    {{
      "fact": "短证据摘要或来源线索",
      "date": "YYYY-MM-DD or empty when unknown",
      "source": "source name or URL from search, empty when unavailable"
    }}
  ],
  "source_queries": ["实际使用的查询"]
}}
""".strip()


def _normalize_market_catalyst(data: Any, code: str, name: str, queries: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _fallback_market_catalyst(code, name, queries)
    fallback = _fallback_market_catalyst(code, name, queries)
    catalyst_facts = _fact_list(data.get("recent_catalysts"), source_type="llm")[:5]
    industry_news = _fact_list(data.get("industry_news") or data.get("news"), source_type="llm")[:8]
    evidence_facts = _fact_list(data.get("evidence"), source_type="llm")[:8]
    result = {
        "market_hype_reason": _string(data.get("market_hype_reason")) or fallback["market_hype_reason"],
        "recent_catalysts": _fact_texts(catalyst_facts),
        "market_catalyst": catalyst_facts,
        "structured_market_catalysts": catalyst_facts,
        "industry_news": industry_news,
        "structured_industry_news": industry_news,
        "traded_business_line": _string(data.get("traded_business_line")) or fallback["traded_business_line"],
        "what_market_is_pricing": _string(data.get("what_market_is_pricing")) or fallback["what_market_is_pricing"],
        "evidence_quality": _quality(data.get("evidence_quality")),
        "unknowns": _str_list(data.get("unknowns"))[:6],
        "evidence": _fact_texts(evidence_facts),
        "evidence_facts": evidence_facts,
        "source_queries": _str_list(data.get("source_queries")) or list(queries or []),
        "source_trace": {
            "market_catalyst": {"source": "llm" if catalyst_facts else "missing"},
            "industry_news": {"source": "llm" if industry_news else "missing"},
            "evidence_facts": {"source": "llm" if evidence_facts else "missing"},
        },
    }
    if not result["recent_catalysts"]:
        result["recent_catalysts"] = fallback["recent_catalysts"]
    if not result["unknowns"]:
        result["unknowns"] = fallback["unknowns"]
    return result


def _fallback_market_catalyst(code: str, name: str, queries: list[str] | None = None) -> dict[str, Any]:
    return {
        "market_hype_reason": "最近炒作原因待验证",
        "recent_catalysts": [],
        "market_catalyst": [],
        "structured_market_catalysts": [],
        "industry_news": [],
        "structured_industry_news": [],
        "traded_business_line": "待验证",
        "what_market_is_pricing": "待验证",
        "evidence_quality": "low",
        "unknowns": ["需要复核最新公告、异动原因、研报摘要和资金交易主线。"],
        "evidence": [],
        "evidence_facts": [],
        "source_queries": list(queries or _market_catalyst_queries(code, name)),
        "source_trace": {
            "market_catalyst": {"source": "missing"},
            "industry_news": {"source": "missing"},
            "evidence_facts": {"source": "missing"},
        },
    }


def _string(value: Any) -> str:
    return str(value).strip() if value not in (None, "", [], {}) else ""


def _str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if item not in (None, "", [], {})]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if item not in (None, "", [], {})]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _fact_list(value: Any, *, source_type: str) -> list[dict[str, str]]:
    items = value if isinstance(value, (list, tuple)) else [value]
    normalized_type = source_type if source_type in FACT_SOURCE_TYPES else "missing"
    result: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            fact = _string(item.get("fact") or item.get("event") or item.get("headline") or item.get("summary"))
            item_source = _string(item.get("source") or item.get("url"))
            item_date = _string(item.get("date") or item.get("as_of") or item.get("published_at"))
        else:
            fact = _string(item)
            item_source = ""
            item_date = ""
        if not fact:
            continue
        result.append(
            {
                "fact": fact,
                "date": item_date,
                "source": item_source or normalized_type,
                "source_type": normalized_type,
            }
        )
    return result


def _fact_texts(value: list[dict[str, str]]) -> list[str]:
    return [item["fact"] for item in value if item.get("fact")]


def _quality(value: Any) -> str:
    text = _string(value).lower()
    if text in {"high", "medium", "low"}:
        return text
    if text in {"高", "强"}:
        return "high"
    if text in {"中", "一般"}:
        return "medium"
    return "low"
