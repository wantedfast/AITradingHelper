from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import time
from typing import Any


STANDARD_RESEARCH_MODEL = "gpt-4.1"
BETTER_RESEARCH_MODEL = "gpt-5.5"


def run_wang_workbench_agent(context: dict[str, Any]) -> dict[str, Any]:
    model = _research_model(context)
    memo = _call_text_agent(
        _wang_memo_system_prompt(),
        _wang_memo_user_prompt(context),
        model_override=model,
        allow_web=False,
    )
    return _memo_agent_payload("wang", memo, model=model, context=context)


def run_public_equity_workbench_agent(context: dict[str, Any]) -> dict[str, Any]:
    model = _research_model(context)
    memo = _call_text_agent(
        _public_memo_system_prompt(),
        _public_memo_user_prompt(context),
        model_override=model,
        allow_web=False,
    )
    return _memo_agent_payload("public_equity", memo, model=model, context=context)


def _wang_system_prompt() -> str:
    return """
你是 WANG-INVESTOR 风格的产业链研究 Agent，只负责产业链、壁垒、利润流向和预期差来源。
你的核心工作不是复述概念，而是回答：
1. 产业链的钱流向哪里？
2. 哪个环节是瓶颈和高利润池？
3. 公司卡在什么节点？
4. 这个节点的壁垒是否真实？
5. 市场可能低估或误解了什么？

输出必须是合法 JSON，不要 Markdown 包裹。JSON 里既要有结构化字段，也要有 deep_memo 长文。
事实不足时写“待验证”，不要编造。
""".strip()


def _public_system_prompt() -> str:
    return """
你是 Public Equity Investing 风格的上市公司投资判断 Agent，只负责公司质量、财务验证、估值赔率、催化剂、风险和交易含义。
你的核心工作不是说“公司好不好”，而是回答：
1. 这个产业逻辑有没有被财报验证？
2. 市场现在相信什么？
3. 研究员看到的预期差在哪里？
4. 当前估值是否已经透支？
5. 什么催化剂会推动继续重估？
6. 什么反证点说明应该降级？

输出必须是合法 JSON，不要 Markdown 包裹。JSON 里既要有结构化字段，也要有 deep_memo 长文。
事实不足时写“待验证”，不要编造。
""".strip()


def _wang_user_prompt(context: dict[str, Any]) -> str:
    return f"""
基于 stock_context 输出 WANG JSON，字段必须如下：
{{
  "industry_rating": "S/A/B/C",
  "sector": "所属行业或主题方向",
  "theme": "当前市场交易的主线或待验证主题",
  "industry_tags": ["高景气", "高壁垒", "利润集中"],
  "claims": ["3-4 条首屏结论"],
  "profit_flow": {{
    "value_pool": "价值池名称",
    "items": [
      {{"name": "产业环节", "share_pct": 0, "highlight": false}}
    ],
    "company_position": "公司所在位置",
    "why_profit_flows_here": "利润为什么流向这里"
  }},
  "moat_radar": {{
    "company_score": 0,
    "industry_average": 0,
    "dimensions": [
      {{"name": "技术/认证/良率/规模/客户", "company": 0, "average": 0}}
    ],
    "explanation": "壁垒解释"
  }},
  "logic_tree": [
    {{"node": "产业逻辑节点", "certainty_pct": 0}}
  ],
  "weakest_link": "逻辑链最弱处",
  "sector_symbol": "相关 ETF 或指数代码，无法判断则空",
  "peer_ranking": ["同赛道公司排序和理由"],
  "deep_memo": "完整产业链研究 memo。必须包含：一句话产业结论、产业链位置、利润池、壁垒、供需、同链公司比较、市场可能低估什么、证伪点。不要少于 900 字。"
}}

stock_context:
{json.dumps(context, ensure_ascii=False)}
""".strip()


def _public_user_prompt(context: dict[str, Any]) -> str:
    return f"""
stock_context may include wang_pre_read. Use it as a compact prior for current market hype,
traded_business_line, what_market_is_pricing, evidence_quality, and unknowns. Do not treat it
as verified fact unless stock_context.market_catalyst/evidence supports it.
基于 stock_context 输出 Public Equity JSON，字段必须如下：
{{
  "investment_rating": "A+/A/B/C",
  "one_sentence_conclusion": "一句话投资结论",
  "expectation_gap": {{
    "market_believes": ["市场认为 1", "市场认为 2"],
    "analyst_view": ["研究员判断 1", "研究员判断 2"],
    "gap_score": 0,
    "underestimated": "市场可能低估什么",
    "overestimated": "市场可能高估什么"
  }},
  "validation_panel": [
    {{"status": "已验证/待确认/风险", "item": "验证项", "evidence": "证据或待验证"}}
  ],
  "catalysts": [
    {{"time": "时间", "event": "催化剂", "impact": "高/中/低"}}
  ],
  "risks": [
    {{"name": "风险", "why_it_matters": "为什么重要", "impact_pct": 0, "downgrade_action": "降级动作"}}
  ],
  "action": {{
    "status_tags": ["高质量公司", "高估值", "困境反转", "主题期权", "待验证"],
    "current_action": "加入观察池/谨慎配置/等待回调/规避",
    "suitable_for": "适合谁",
    "not_suitable_for": "不适合谁",
    "recheck_conditions": ["复查条件"]
  }},
  "financial_validation": ["3-5 条财务或经营验证点"],
  "valuation_odds": "估值赔率判断",
  "position_sizing": "仓位/交易含义",
  "trading_implication": "对这笔交易复盘的含义",
  "sources": ["来源或待验证来源"],
  "deep_memo": "完整投资判断 memo。必须包含：一句话投资结论、公司质量、财务验证、市场预期差、估值赔率、情景分析、催化剂、风险反证、交易含义。不要少于 900 字。"
}}

stock_context:
{json.dumps(context, ensure_ascii=False)}
""".strip()


def _call_json_agent(
    system_prompt: str,
    user_prompt: str,
    *,
    model_override: str | None = None,
    max_output_tokens: int | None = None,
    allow_web: bool = True,
) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or "your-openai-api-key" in api_key:
        raise RuntimeError("OPENAI_API_KEY is required for workbench agent")
    if allow_web and _web_enabled():
        try:
            return _call_responses_json(
                api_key,
                system_prompt,
                user_prompt,
                model_override=model_override,
                use_web_tool=True,
                max_output_tokens=max_output_tokens,
            )
        except Exception as exc:
            print(f"[warn] workbench web agent failed, fallback to chat JSON: {exc}")
    else:
        try:
            return _call_responses_json(
                api_key,
                system_prompt,
                user_prompt,
                model_override=model_override,
                use_web_tool=False,
                max_output_tokens=max_output_tokens,
            )
        except Exception as exc:
            print(f"[warn] workbench responses agent failed, fallback to chat JSON: {exc}")
    try:
        return _call_chat_json(api_key, system_prompt, user_prompt, model_override=model_override, max_output_tokens=max_output_tokens)
    except Exception as exc:
        return {"_agent_error": f"workbench chat agent failed: {exc}"}


def _call_text_agent(
    system_prompt: str,
    user_prompt: str,
    *,
    model_override: str | None = None,
    max_output_tokens: int | None = None,
    allow_web: bool = False,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or "your-openai-api-key" in api_key:
        raise RuntimeError("OPENAI_API_KEY is required for workbench memo agent")
    if allow_web and _web_enabled():
        try:
            return _call_responses_text(
                api_key,
                system_prompt,
                user_prompt,
                model_override=model_override,
                use_web_tool=True,
                max_output_tokens=max_output_tokens,
            )
        except Exception as exc:
            print(f"[warn] workbench memo web agent failed, fallback to chat text: {exc}")
    else:
        try:
            return _call_responses_text(
                api_key,
                system_prompt,
                user_prompt,
                model_override=model_override,
                use_web_tool=False,
                max_output_tokens=max_output_tokens,
            )
        except Exception as exc:
            print(f"[warn] workbench memo responses agent failed, fallback to chat text: {exc}")
    return _call_chat_text(api_key, system_prompt, user_prompt, model_override=model_override, max_output_tokens=max_output_tokens)


def _model(model_override: str | None = None) -> str:
    return model_override or os.getenv("WORKBENCH_AGENT_MODEL") or os.getenv("OPENAI_RESEARCH_MODEL") or os.getenv("OPENAI_MODEL") or STANDARD_RESEARCH_MODEL


def _research_model(context: dict[str, Any]) -> str:
    metadata = context.get("research_model") if isinstance(context, dict) else {}
    if isinstance(metadata, dict) and metadata.get("model"):
        return str(metadata["model"])
    tier = _research_model_tier(context)
    if tier == "better":
        return os.getenv("WORKBENCH_BETTER_MODEL") or BETTER_RESEARCH_MODEL
    return os.getenv("WORKBENCH_STANDARD_MODEL") or STANDARD_RESEARCH_MODEL


def _research_model_tier(context: dict[str, Any]) -> str:
    metadata = context.get("research_model") if isinstance(context, dict) else {}
    value = metadata.get("tier") if isinstance(metadata, dict) else None
    if value is None and isinstance(context, dict):
        value = context.get("research_model_tier")
    return normalize_research_model_tier(value)


def research_model_metadata(tier: object = "standard") -> dict[str, str]:
    normalized = normalize_research_model_tier(tier)
    model = (os.getenv("WORKBENCH_BETTER_MODEL") or BETTER_RESEARCH_MODEL) if normalized == "better" else (
        os.getenv("WORKBENCH_STANDARD_MODEL") or STANDARD_RESEARCH_MODEL
    )
    return {
        "tier": normalized,
        "model": model,
        "wang_model": model,
        "public_equity_model": model,
    }


def normalize_research_model_tier(value: object) -> str:
    return "better" if str(value or "").strip().lower() in {"better", "gpt-5.5", "premium", "1", "true", "yes", "on"} else "standard"


def _web_enabled() -> bool:
    value = os.getenv("WORKBENCH_WEB_SEARCH", "1").strip().lower()
    return value not in {"0", "false", "no"}


def _call_responses_json(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    model_override: str | None = None,
    use_web_tool: bool = True,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    body: dict[str, Any] = {
        "model": _model(model_override),
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if use_web_tool:
        body["tools"] = [{"type": "web_search_preview"}]
    max_output = max_output_tokens or _max_output_tokens()
    if max_output:
        body["max_output_tokens"] = max_output
    data = _post_json(f"{base_url}/responses", api_key, body, timeout=180)
    parsed = _loads_json_object(
        _extract_response_text(data),
        repair_api_key=api_key,
        model_override=model_override,
        schema_hint=system_prompt,
    )
    _attach_api_usage(parsed, data)
    return parsed


def _call_responses_text(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    model_override: str | None = None,
    use_web_tool: bool = False,
    max_output_tokens: int | None = None,
) -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    body: dict[str, Any] = {
        "model": _model(model_override),
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if use_web_tool:
        body["tools"] = [{"type": "web_search_preview"}]
    max_output = max_output_tokens or _memo_max_output_tokens()
    if max_output:
        body["max_output_tokens"] = max_output
    data = _post_json(f"{base_url}/responses", api_key, body, timeout=180)
    return _extract_response_text(data).strip()


def _call_chat_json(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    model_override: str | None = None,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    body: dict[str, Any] = {
        "model": _model(model_override),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    max_output = max_output_tokens or _max_output_tokens()
    if max_output:
        body["max_tokens"] = max_output
    data = _post_json(f"{base_url}/chat/completions", api_key, body, timeout=140)
    parsed = _loads_json_object(
        data["choices"][0]["message"]["content"],
        repair_api_key=api_key,
        model_override=model_override,
        schema_hint=system_prompt,
    )
    _attach_api_usage(parsed, data)
    return parsed


def _call_chat_text(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    model_override: str | None = None,
    max_output_tokens: int | None = None,
) -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    body: dict[str, Any] = {
        "model": _model(model_override),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    max_output = max_output_tokens or _memo_max_output_tokens()
    if max_output:
        body["max_tokens"] = max_output
    data = _post_json(f"{base_url}/chat/completions", api_key, body, timeout=140)
    return str(data["choices"][0]["message"]["content"] or "").strip()


def _max_output_tokens() -> int | None:
    try:
        value = int(os.getenv("WORKBENCH_MAX_OUTPUT_TOKENS", "").strip())
    except Exception:
        return None
    return value if value > 0 else None


def _memo_max_output_tokens() -> int | None:
    try:
        value = int(os.getenv("WORKBENCH_MEMO_MAX_OUTPUT_TOKENS", "2600").strip())
    except Exception:
        return 2600
    return value if value > 0 else None


def _post_json(url: str, api_key: str, body: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI workbench request failed: HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"OpenAI workbench request failed: {exc}") from exc


def _extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts: list[str] = []
    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("value")
            if isinstance(text, str):
                parts.append(text)
    if parts:
        return "\n".join(parts)
    raise RuntimeError("OpenAI response did not contain text")


def _attach_api_usage(parsed: dict[str, Any], response_data: dict[str, Any]) -> None:
    usage = response_data.get("usage") if isinstance(response_data, dict) else None
    if isinstance(parsed, dict) and isinstance(usage, dict):
        parsed["_api_usage"] = {
            key: usage.get(key)
            for key in ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens")
            if usage.get(key) is not None
        }


def _loads_json_object(
    text: str,
    *,
    repair_api_key: str | None = None,
    model_override: str | None = None,
    schema_hint: str = "",
) -> dict[str, Any]:
    raw = str(text or "").strip()
    try:
        return _parse_json_object_text(raw)
    except Exception as exc:
        parse_error = exc
    if repair_api_key and _json_repair_enabled():
        repaired = _call_json_repair_agent(
            repair_api_key,
            raw,
            schema_hint=schema_hint,
            model_override=model_override,
        )
        if isinstance(repaired, dict) and not repaired.get("_agent_error"):
            return repaired
    return {"_agent_error": f"workbench agent returned invalid JSON: {parse_error}", "_raw_text": raw[:1000]}


def _parse_json_object_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise RuntimeError("workbench agent returned non-object JSON")
    return parsed


def _json_repair_enabled() -> bool:
    value = os.getenv("WORKBENCH_JSON_REPAIR_ENABLED", "1").strip().lower()
    return value not in {"0", "false", "no"}


def _call_json_repair_agent(
    api_key: str,
    raw_text: str,
    *,
    schema_hint: str = "",
    model_override: str | None = None,
) -> dict[str, Any]:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    repair_model = os.getenv("WORKBENCH_JSON_REPAIR_MODEL") or os.getenv("WORKBENCH_STANDARD_MODEL") or STANDARD_RESEARCH_MODEL
    body: dict[str, Any] = {
        "model": repair_model,
        "messages": [
            {
                "role": "system",
                "content": "Repair malformed JSON. Return one valid JSON object only. Do not add markdown or commentary.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "schema_hint": str(schema_hint or "")[:1200],
                        "malformed_json": str(raw_text or "")[:6000],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 900,
    }
    try:
        data = _post_json(f"{base_url}/chat/completions", api_key, body, timeout=80)
        return _parse_json_object_text(data["choices"][0]["message"]["content"])
    except Exception as exc:
        return {"_agent_error": f"json repair failed: {exc}"}


# Final prompt overrides for the research-workbench flow. These are defined at
# the end of the module so runtime uses the stricter, catalyst-aware contracts.
def _wang_system_prompt() -> str:
    return """
你是 WANG-INVESTOR 风格的产业链研究 Agent，只负责产业链、壁垒、利润流向和预期差来源。

必须先回答：最近市场为什么炒它、资金买的主线是什么、对应公司哪条业务线。
如果 stock_context.market_catalyst 证据不足，写“最近炒作原因待验证”，不要用长期基本面替代当前催化剂。

然后回答：
1. 产业链的钱流向哪里？
2. 哪个环节是瓶颈和高利润池？
3. 公司卡在什么节点？
4. 这个节点的壁垒是否真实？
5. 市场可能低估或误解了什么？

输出必须是合法 JSON，不要 Markdown。事实不足时写“待验证”，不要编造。
""".strip()


def _public_system_prompt() -> str:
    return """
你是 Public Equity Investing 风格的上市公司投资判断 Agent，只负责公司质量、财务验证、估值赔率、催化剂、风险和交易含义。

必须先判断：当前股价交易的是哪条业务线或主题，市场正在定价什么预期。
必须区分：公司长期质量、当前市场主题、财报验证、交易拥挤度。

然后回答：
1. 产业链逻辑有没有被财报验证？
2. 市场现在相信什么？
3. 研究员看到的预期差在哪里？
4. 当前估值是否已经透支？
5. 什么催化剂会推动继续重估？
6. 什么反证点说明应该降级？

输出必须是合法 JSON，不要 Markdown。事实不足时写“待验证”，不要编造。
""".strip()


def _wang_user_prompt(context: dict[str, Any]) -> str:
    return f"""
基于 stock_context 输出 WANG JSON，字段必须如下：
{{
  "industry_rating": "S/A/B/C",
  "market_hype_reason": "最近市场为什么炒它/资金买的主线，证据不足写最近炒作原因待验证",
  "recent_catalysts": ["最近催化剂或异动证据"],
  "traded_business_line": "当前被交易的业务线或主题",
  "what_market_is_pricing": "市场正在定价的预期",
  "evidence_quality": "high/medium/low",
  "unknowns": ["仍需验证的关键点"],
  "sector": "所属行业或主题方向",
  "theme": "当前市场交易主线或待验证主题",
  "industry_tags": ["高景气", "高壁垒", "利润集中"],
  "claims": ["3-4 条首屏结论"],
  "profit_flow": {{
    "value_pool": "价值池名称",
    "items": [
      {{"name": "产业环节", "share_pct": 0, "highlight": false}}
    ],
    "company_position": "公司所在位置",
    "why_profit_flows_here": "利润为什么流向这里"
  }},
  "moat_radar": {{
    "company_score": 0,
    "industry_average": 0,
    "dimensions": [
      {{"name": "技术/认证/良率/规模/客户", "company": 0, "average": 0}}
    ],
    "explanation": "壁垒解释"
  }},
  "logic_tree": [
    {{"node": "产业逻辑节点", "certainty_pct": 0}}
  ],
  "weakest_link": "逻辑链最弱处",
  "sector_symbol": "相关 ETF 或指数代码，无法判断则空",
  "peer_ranking": ["同赛道公司排序和理由"],
  "deep_memo": "完整产业链研究 memo。必须包含：最近市场炒作原因、产业链位置、利润池、壁垒、供需、同链公司比较、市场可能低估什么、证伪点。不少于 700 字。"
}}

stock_context:
{json.dumps(context, ensure_ascii=False)}
""".strip()


def _public_user_prompt(context: dict[str, Any]) -> str:
    return f"""
基于 stock_context 输出 Public Equity JSON，字段必须如下：
{{
  "investment_rating": "A+/A/B/C",
  "market_hype_reason": "最近市场为什么炒它/资金买的主线，证据不足写最近炒作原因待验证",
  "recent_catalysts": ["最近催化剂或异动证据"],
  "traded_business_line": "当前股价交易的是哪条业务线或主题",
  "what_market_is_pricing": "市场正在定价的预期",
  "evidence_quality": "high/medium/low",
  "unknowns": ["仍需验证的关键点"],
  "one_sentence_conclusion": "一句话投资结论",
  "expectation_gap": {{
    "market_believes": ["市场认为 1", "市场认为 2"],
    "analyst_view": ["研究员判断 1", "研究员判断 2"],
    "gap_score": 0,
    "underestimated": "市场可能低估什么",
    "overestimated": "市场可能高估什么"
  }},
  "validation_panel": [
    {{"status": "已验证/待确认/风险", "item": "验证项", "evidence": "证据或待验证"}}
  ],
  "catalysts": [
    {{"time": "时间", "event": "催化剂", "impact": "高/中/低"}}
  ],
  "risks": [
    {{"name": "风险", "why_it_matters": "为什么重要", "impact_pct": 0, "downgrade_action": "降级动作"}}
  ],
  "action": {{
    "status_tags": ["高质量公司", "高估值", "困境反转", "主题期权", "待验证"],
    "current_action": "加入观察池/谨慎配置/等待回调/规避",
    "suitable_for": "适合谁",
    "not_suitable_for": "不适合谁",
    "recheck_conditions": ["复查条件"]
  }},
  "financial_validation": ["3-5 条财务或经营验证点"],
  "valuation_odds": "估值赔率判断",
  "position_sizing": "仓位/交易含义",
  "trading_implication": "对这笔交易复盘的含义",
  "sources": ["来源或待验证来源"],
  "deep_memo": "完整投资判断 memo。必须包含：当前市场主题、公司长期质量、财报验证、交易拥挤度、预期差、估值赔率、催化剂、风险反证、交易含义。不少于 700 字。"
}}

stock_context:
{json.dumps(context, ensure_ascii=False)}
""".strip()


_runtime_public_user_prompt_base = _public_user_prompt


def _public_user_prompt(context: dict[str, Any]) -> str:
    note = (
        "stock_context may include wang_pre_read. Use it as a compact prior for current market hype, "
        "traded_business_line, what_market_is_pricing, evidence_quality, and unknowns. Do not treat it "
        "as verified fact unless stock_context.market_catalyst/evidence supports it."
    )
    prompt = _runtime_public_user_prompt_base(context)
    if note in prompt:
        return prompt
    return f"{note}\n{prompt}"


# Research agents return the workbench contract directly. Standard mode keeps the
# payload short for fast report generation; better mode adds a longer deep_memo.
def run_wang_workbench_agent(context: dict[str, Any]) -> dict[str, Any]:
    model = _research_model(context)
    include_memo = _research_model_tier(context) == "better"
    system_prompt = _research_json_system_prompt("WANG industry-chain", include_memo=include_memo)
    user_prompt = _wang_research_json_user_prompt(context, include_memo=include_memo)
    started = time.perf_counter()
    payload = _call_json_agent(
        system_prompt,
        user_prompt,
        model_override=model,
        max_output_tokens=_research_json_max_output_tokens(include_memo),
        allow_web=False,
    )
    return _research_agent_payload(
        "wang",
        payload,
        model=model,
        context=context,
        include_memo=include_memo,
        input_text=f"{system_prompt}\n{user_prompt}",
        seconds=time.perf_counter() - started,
    )


def run_public_equity_workbench_agent(context: dict[str, Any]) -> dict[str, Any]:
    model = _research_model(context)
    include_memo = _research_model_tier(context) == "better"
    system_prompt = _research_json_system_prompt("Public Equity", include_memo=include_memo)
    user_prompt = _public_research_json_user_prompt(context, include_memo=include_memo)
    started = time.perf_counter()
    payload = _call_json_agent(
        system_prompt,
        user_prompt,
        model_override=model,
        max_output_tokens=_research_json_max_output_tokens(include_memo),
        allow_web=False,
    )
    return _research_agent_payload(
        "public_equity",
        payload,
        model=model,
        context=context,
        include_memo=include_memo,
        input_text=f"{system_prompt}\n{user_prompt}",
        seconds=time.perf_counter() - started,
    )


def _research_json_system_prompt(agent_name: str, *, include_memo: bool) -> str:
    memo_rule = (
        "Also include deep_memo, 700-1000 Chinese characters, explaining the full reasoning."
        if include_memo
        else "Do not include deep_memo or long memo text. Keep reasoning_summary within 180 Chinese characters."
    )
    return f"""
You are the {agent_name} research agent for an A-share trade review product.
Return valid JSON only. Do not use Markdown. Use Chinese values.
Use only stock_context facts, market_catalyst, evidence, news, and trade context. If evidence is insufficient, write "待验证".
{memo_rule}
""".strip()


def _wang_research_json_user_prompt(context: dict[str, Any], *, include_memo: bool) -> str:
    memo_field = ',\n  "deep_memo": "700-1000字产业链研究长文"' if include_memo else ""
    return f"""
Return this exact WANG JSON contract:
{{
  "industry_rating": "S/A/B/C",
  "sector": "行业或主题方向",
  "theme": "市场交易主线或待验证主题",
  "market_hype_reason": "最近市场为什么交易这家公司",
  "recent_catalysts": ["催化或异动证据"],
  "traded_business_line": "被交易的业务线或主题",
  "what_market_is_pricing": "市场正在定价的预期",
  "evidence_quality": "high/medium/low",
  "unknowns": ["仍需验证的关键点"],
  "industry_tags": ["标签"],
  "claims": ["3-4条首页结论"],
  "profit_flow": {{
    "value_pool": "价值池名称",
    "items": [{{"name": "产业环节", "share_pct": 0, "highlight": false}}],
    "company_position": "公司所处位置",
    "why_profit_flows_here": "利润为什么可能流向这里"
  }},
  "moat_radar": {{
    "company_score": 0,
    "industry_average": 0,
    "dimensions": [{{"name": "技术/认证/良率/规模/客户", "company": 0, "average": 0}}],
    "explanation": "壁垒解释"
  }},
  "logic_tree": [{{"node": "产业逻辑节点", "certainty_pct": 0}}],
  "weakest_link": "最弱逻辑链",
  "sector_symbol": "相关ETF或指数代码，无法判断则空",
  "peer_ranking": ["同赛道公司排序和理由"],
  "reasoning_summary": "180字以内依据摘要"{memo_field}
}}

stock_context:
{json.dumps(context, ensure_ascii=False)}
""".strip()


def _public_research_json_user_prompt(context: dict[str, Any], *, include_memo: bool) -> str:
    memo_field = ',\n  "deep_memo": "700-1000字投资判断长文"' if include_memo else ""
    return f"""
Return this exact Public Equity JSON contract:
{{
  "investment_rating": "A+/A/B/C",
  "one_sentence_conclusion": "一句话投资结论",
  "market_hype_reason": "最近市场为什么交易这家公司",
  "recent_catalysts": ["催化或异动证据"],
  "traded_business_line": "当前股价交易的业务线或主题",
  "what_market_is_pricing": "市场正在定价的预期",
  "evidence_quality": "high/medium/low",
  "unknowns": ["仍需验证的关键点"],
  "expectation_gap": {{
    "market_believes": ["市场认为"],
    "analyst_view": ["研究判断"],
    "gap_score": 0,
    "underestimated": "市场可能低估什么",
    "overestimated": "市场可能高估什么"
  }},
  "validation_panel": [{{"status": "已验证/待确认/风险", "item": "验证项", "evidence": "证据或待验证"}}],
  "catalysts": [{{"time": "时间", "event": "催化剂", "impact": "高/中/低"}}],
  "risks": [{{"name": "风险", "why_it_matters": "为什么重要", "impact_pct": 0, "downgrade_action": "降级动作"}}],
  "action": {{
    "status_tags": ["状态标签"],
    "current_action": "加入观察池/谨慎配置/等待回调/规避",
    "suitable_for": "适合谁",
    "not_suitable_for": "不适合谁",
    "recheck_conditions": ["复查条件"]
  }},
  "financial_validation": ["财务或经营验证点"],
  "valuation_odds": "估值赔率判断",
  "position_sizing": "仓位/交易含义",
  "trading_implication": "对本次交易复盘的含义",
  "sources": ["来源或待验证来源"],
  "reasoning_summary": "180字以内依据摘要"{memo_field}
}}

stock_context:
{json.dumps(context, ensure_ascii=False)}
""".strip()


def _research_json_max_output_tokens(include_memo: bool) -> int:
    env_name = "WORKBENCH_DETAIL_MAX_OUTPUT_TOKENS" if include_memo else "WORKBENCH_FAST_MAX_OUTPUT_TOKENS"
    default = 3200 if include_memo else 1400
    try:
        value = int(os.getenv(env_name, str(default)).strip())
    except Exception:
        return default
    return value if value > 0 else default


def _research_agent_payload(
    agent_type: str,
    payload: object,
    *,
    model: str,
    context: dict[str, Any],
    include_memo: bool,
    input_text: str,
    seconds: float,
) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    if data.get("_agent_error"):
        return data
    data = dict(data)
    api_usage = data.pop("_api_usage", None)
    output_text = json.dumps(data, ensure_ascii=False, default=str)
    data["agent_type"] = agent_type
    data["model"] = model
    data["research_model_tier"] = _research_model_tier(context)
    data["research_output_mode"] = "json_memo" if include_memo else "json_only"
    data["research_metrics"] = _research_metrics(input_text, output_text, seconds=seconds, api_usage=api_usage)
    if not include_memo:
        data.pop("deep_memo", None)
        data.pop("memo", None)
        data.pop("raw_text", None)
    elif isinstance(data.get("deep_memo"), str):
        data["memo"] = data["deep_memo"]
        data["raw_text"] = data["deep_memo"]
    return data


def _research_metrics(input_text: str, output_text: str, *, seconds: float, api_usage: object = None) -> dict[str, Any]:
    input_chars = len(input_text or "")
    output_chars = len(output_text or "")
    input_tokens = _estimate_tokens(input_text)
    output_tokens = _estimate_tokens(output_text)
    metrics = {
        "seconds": round(max(0.0, seconds), 4),
        "input_chars": input_chars,
        "output_chars": output_chars,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_total_tokens": input_tokens + output_tokens,
    }
    if isinstance(api_usage, dict):
        metrics["api_usage"] = api_usage
        actual_input = api_usage.get("input_tokens", api_usage.get("prompt_tokens"))
        actual_output = api_usage.get("output_tokens", api_usage.get("completion_tokens"))
        actual_total = api_usage.get("total_tokens")
        if actual_input is not None:
            metrics["actual_input_tokens"] = actual_input
        if actual_output is not None:
            metrics["actual_output_tokens"] = actual_output
        if actual_total is not None:
            metrics["actual_total_tokens"] = actual_total
    return metrics


def _estimate_tokens(text: str) -> int:
    return max(1, round(len(text or "") / 2))


def _wang_memo_system_prompt() -> str:
    return """
你是 WANG-INVESTOR 风格的产业链研究 Agent。
你只输出研究 memo 文本，不输出 JSON，不输出 Markdown 大表格，不上网。
你只能使用 stock_context 里的交易事实、市场催化剂、evidence/news 和行情上下文。
必须区分“题材叙事”和“已验证收入/利润贡献”；证据不足就写“待验证”。
""".strip()


def _public_memo_system_prompt() -> str:
    return """
你是 Public Equity Investing 风格的上市公司投资判断 Agent。
你只输出研究 memo 文本，不输出 JSON，不输出 Markdown 大表格，不上网。
你只能使用 stock_context、WANG memo 摘要、market_catalyst/evidence/news 和交易复盘上下文。
必须区分公司长期质量、当前市场主题、财报验证、估值赔率和反证风险。
""".strip()


def _wang_memo_user_prompt(context: dict[str, Any]) -> str:
    return f"""
请写一份产业链研究 memo，结构用短标题和段落即可，不要 JSON。

必须覆盖：
1. 最近市场为什么炒这家公司：资金主线、对应业务线、证据质量、待验证点。
2. 公司在产业链的位置：上游/中游/下游、利润池在哪里、利润为什么可能流向这里。
3. 壁垒与瓶颈：技术、认证、良率、规模、客户、产能、供需。
4. 竞争格局：同链公司对比，谁更可能吃到利润。
5. 市场可能低估/误解了什么。
6. 最弱逻辑链和需要下一步验证的事实。

写作要求：
- 500-1200 中文字。
- 使用明确判断，但不要编造事实。
- 如果 stock_context.market_catalyst/evidence 不足，必须写“最近炒作原因待验证”。

stock_context:
{json.dumps(context, ensure_ascii=False)}
""".strip()


def _public_memo_user_prompt(context: dict[str, Any]) -> str:
    return f"""
请写一份上市公司/投资判断 memo，结构用短标题和段落即可，不要 JSON。

必须覆盖：
1. 一句话投资判断：现在是否值得研究，为什么。
2. 当前股价交易的是什么：业务线/主题/预期。
3. 财务和经营验证：哪些已验证，哪些只是题材。
4. 市场预期差：市场相信什么，研究判断认为哪里可能错。
5. 估值赔率：当前是否透支，什么条件下赔率改善。
6. 催化剂、反证点、下一步复查条件。
7. 对本次交易复盘的含义：买点/卖点/持有难度。

写作要求：
- 500-1200 中文字。
- 只能基于输入上下文，不上网，不编造财务数字。
- 对未验证事项明确写“待验证”。

stock_context:
{json.dumps(context, ensure_ascii=False)}
""".strip()
