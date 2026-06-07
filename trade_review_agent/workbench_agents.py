from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


STANDARD_RESEARCH_MODEL = "gpt-4.1"
BETTER_RESEARCH_MODEL = "gpt-5.5"


def run_wang_workbench_agent(context: dict[str, Any]) -> dict[str, Any]:
    return _call_json_agent(
        _wang_system_prompt(),
        _wang_user_prompt(context),
        model_override=_research_model(context),
        allow_web=False,
    )


def run_public_equity_workbench_agent(context: dict[str, Any]) -> dict[str, Any]:
    return _call_json_agent(
        _public_system_prompt(),
        _public_user_prompt(context),
        model_override=_research_model(context),
        allow_web=False,
    )


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
    return _call_chat_json(api_key, system_prompt, user_prompt, model_override=model_override, max_output_tokens=max_output_tokens)


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
    return _loads_json_object(_extract_response_text(data))


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
    return _loads_json_object(data["choices"][0]["message"]["content"])


def _max_output_tokens() -> int | None:
    try:
        value = int(os.getenv("WORKBENCH_MAX_OUTPUT_TOKENS", "").strip())
    except Exception:
        return None
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


def _loads_json_object(text: str) -> dict[str, Any]:
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
