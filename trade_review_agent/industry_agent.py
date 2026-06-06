from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import load_env
from .industry_profiles import IndustryProfile


BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_PATH = BASE_DIR / "work" / "industry_profile_cache.json"


COMPANY_IDENTITY_HINTS = {
    "600183": "身份校验：600183 是生益科技股份有限公司，核心业务与覆铜板/粘结片、电子材料、PCB 上游材料相关。这个提示只用于防止同名/错名检索，不等于预设当前炒作主线。",
    "600172": "身份校验：600172 是黄河旋风，历史业务包括超硬材料、工业金刚石、培育钻石等。这个提示只用于防止同名/错名检索，不等于预设当前炒作主线。",
    "600584": "身份校验：600584 是长电科技，核心业务为集成电路封装测试/先进封装。这个提示只用于防止同名/错名检索，不等于预设当前炒作主线。",
    "000636": "身份校验：000636 是风华高科，核心业务与被动元件、MLCC、电子元器件相关。这个提示只用于防止同名/错名检索，不等于预设当前炒作主线。",
}


# This is not the industry thesis. It only prevents the market-comparison layer
# from falling back to CSI 300 when the researched company is clearly in a
# hardware/electronics chain and needs a closer sector proxy for relative strength.
SECTOR_PROXY_HINTS = {
    "600183": "512480",  # 生益科技: CCL/PCB/electronic materials, use semiconductor/electronics proxy.
    "600584": "512480",  # 长电科技: advanced packaging / semiconductor chain.
    "002185": "512480",  # 华天科技: semiconductor packaging/testing chain.
}


def get_ai_industry_profile(code: str, name: str = "") -> IndustryProfile:
    code = _clean_code(code)
    name = str(name or code).strip()
    cache = _load_cache()
    key = f"{code}:{name}"
    if os.getenv("INDUSTRY_AGENT_REFRESH", "").strip().lower() not in {"1", "true", "yes"}:
        cached = cache.get(key) or cache.get(code)
        if isinstance(cached, dict):
            return _profile_from_payload(cached, code, name)

    payload = _call_research_agent(code, name)
    cache[key] = payload
    cache[code] = payload
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return _profile_from_payload(payload, code, name)


def _call_research_agent(code: str, name: str) -> dict[str, Any]:
    load_env(BASE_DIR / ".env")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or "your-openai-api-key" in api_key:
        raise RuntimeError("OPENAI_API_KEY is required for dynamic industry analysis")

    wang_prompt = _wang_investor_prompt(code, name)
    equity_prompt = _public_equity_prompt(code, name)
    use_web = os.getenv("INDUSTRY_AGENT_WEB_SEARCH", "1").strip().lower() not in {"0", "false", "no"}
    wang_payload: dict[str, Any] = {}
    equity_payload: dict[str, Any] = {}
    if use_web:
        try:
            wang_payload = _call_responses_with_web_search(api_key, _wang_system_prompt(), wang_prompt)
        except Exception as exc:
            print(f"[warn] WANG-INVESTOR web-search agent failed, falling back to plain model: {exc}")
    if not wang_payload:
        wang_payload = _call_chat_json(api_key, _wang_system_prompt(), wang_prompt)

    if use_web:
        try:
            equity_payload = _call_responses_with_web_search(api_key, _public_equity_system_prompt(), equity_prompt)
        except Exception as exc:
            print(f"[warn] Public Equity web-search agent failed, falling back to plain model: {exc}")
    if not equity_payload:
        equity_payload = _call_chat_json(api_key, _public_equity_system_prompt(), equity_prompt)
    retry_note = _equity_quality_issue(equity_payload)
    if retry_note:
        repair_prompt = f"{equity_prompt}\n\n上一次输出存在质量问题：{retry_note}\n请重新输出 JSON，必须修正这些问题。"
        try:
            equity_payload = _call_responses_with_web_search(api_key, _public_equity_system_prompt(), repair_prompt) if use_web else _call_chat_json(api_key, _public_equity_system_prompt(), repair_prompt)
        except Exception as exc:
            print(f"[warn] Public Equity repair retry failed, keeping first result: {exc}")

    return _merge_agent_payloads(code, name, wang_payload, equity_payload)


def _call_responses_with_web_search(api_key: str, system_prompt: str, prompt: str) -> dict[str, Any]:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    body = {
        "model": _research_model(),
        "tools": [{"type": "web_search_preview"}],
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.08,
    }
    data = _post_json(f"{base_url}/responses", api_key, body, timeout=160)
    text = _extract_response_text(data)
    return _loads_json_object(text)


def _call_chat_json(api_key: str, system_prompt: str, prompt: str) -> dict[str, Any]:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    body = {
        "model": _research_model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.08,
        "response_format": {"type": "json_object"},
    }
    data = _post_json(f"{base_url}/chat/completions", api_key, body, timeout=140)
    content = data["choices"][0]["message"]["content"]
    return _loads_json_object(content)


def _research_model() -> str:
    return os.getenv("OPENAI_RESEARCH_MODEL") or "gpt-4.1"


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
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc


def _extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
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
        raise RuntimeError("industry agent returned non-object JSON")
    return parsed


def _wang_system_prompt() -> str:
    return """
你是 WANG-INVESTOR 产业链 Agent。你的工作不是推荐股票，而是像买方科技产业链分析师一样，找到需求冲击、利润池、稀缺瓶颈和产业链排序。

必须遵守：
1. 从需求冲击开始，不从股票涨跌开始。
2. 映射完整产业链：上游材料/设备/工艺，中游制造/模块/零部件，下游客户/应用。
3. 找利润池：价格、产品结构、产能利用率、客户紧迫性、毛利率弹性。
4. 找稀缺瓶颈：技术难度、良率、客户认证、配方/专利、产能、切换成本。
5. 区分“有概念暴露”和“是真正瓶颈”。
6. 如果是 AI 硬件链，必须显式挂到：AI 推理/训练需求 -> GPU/ASIC/HBM -> 服务器/交换机/加速卡 -> 高速 PCB/低损耗 CCL/铜箔/电子布/连接器/电源/散热。
7. 如果公司是 PCB/CCL/覆铜板/电子材料链，必须判断它与 AI 服务器 PCB、高速交换机、高频高速低损耗 CCL 的关系；不能只写 5G、汽车电子、物联网等旧泛应用。
8. 对 PCB/CCL 链要正确区分角色：沪电股份、胜宏科技、深南电路偏 PCB 成品/板厂；生益科技、南亚新材、华正新材偏 CCL/材料；生益电子是 PCB 子公司/同集团相关资产。禁止把 PCB 板厂写成覆铜板龙头。
9. 禁止照抄 schema 占位词，例如“技术/工艺壁垒”“其他壁垒”；每条壁垒必须有具体含义。
10. 只返回 JSON object，不要 markdown。
""".strip()


def _public_equity_system_prompt() -> str:
    return """
你是 Public Equity Investing 上市公司 Agent。你的工作是把产业链结论翻译成可交易的上市公司判断。

必须遵守：
1. 拆业务线，指出当前市场真正重估的是哪条业务线，不要停在宽标签。
2. 比较同市场可投资标的，判断目标公司是不是最佳表达。
3. 判断市场位置：低位补涨、高位核心、主线龙头、拥挤追高、分歧回踩、跟风试错。
4. 输出估值赔率和拥挤风险，不要只说“估值合理/低估”。
5. 给出催化剂、反证点、仓位和买卖含义。
6. 对 PCB/CCL/AI硬件链，必须比较沪电股份、胜宏科技、深南电路、生益科技、南亚新材、华正新材、生益电子等 A 股/H股可观察标的，说明目标公司是核心、补强、弹性票还是跟风。
7. 必须明确判断“低位补涨”还是“高位核心”；如果已经大涨，要写追高风险和等分歧回踩。
8. 对 PCB/CCL 链要正确区分角色：沪电股份、胜宏科技、深南电路偏 PCB 成品/板厂；生益科技、南亚新材、华正新材偏 CCL/材料；生益电子是 PCB 子公司/同集团相关资产。禁止把 PCB 板厂写成覆铜板龙头。
9. best_expression 必须拆成两层：整体 AI PCB 主线谁是最佳表达/最高弹性，CCL 材料细分目标公司是不是最佳表达。不能只在细分赛道里比较后说它是最好。
   - 整体 AI PCB 主线排序要按“AI服务器/高速交换机收入纯度、业绩弹性、市场主攻强度”判断。
   - CCL 材料细分排序要按“高频高速低损耗材料壁垒、客户认证、产能、价格弹性、确定性”判断。
   - 不允许只给一个名字，必须说明排序口径；如果选择深南电路这类稳健标的排第一，必须解释为什么它比沪电/胜宏更强。
10. 如果缺少可靠证据，明确写“待验证”，不要编造财务数字、订单和客户。
11. 禁止照抄 schema 占位词；输出必须像给投资经理看的判断。
12. 只返回 JSON object，不要 markdown。
""".strip()


def _wang_investor_prompt(code: str, name: str) -> str:
    identity_hint = COMPANY_IDENTITY_HINTS.get(code, "")
    return f"""
请以 WANG-INVESTOR 产业链 Agent 身份分析 A 股公司 {name}（{code}）。

身份校验：
- 必须同时匹配股票代码 {code} 和公司名 {name}。
- {identity_hint or "如公开资料与输入名称/代码冲突，先说明身份待核验。"}

请上网检索公开信息后输出以下 JSON：
质量要求：
- 必须优先解释“当前市场为什么炒它”，而不是历史上它有哪些应用。
- 如果本轮市场主线是 AI PCB / 高速交换机 / 高端 CCL，必须直说；如果证据不足，写“AI PCB 主线待验证”。
- 对 PCB/CCL 链，必须把“PCB 成品端”和“CCL 材料端”分开讲。
- barriers 和 profit_levers 必须写成具体业务语言，不能写模板词。

{{
  "code": "{code}",
  "name": "{name}",
  "theme": "窄主题，必须是最能解释当前交易的产业标签",
  "core_driver": "当前产业需求冲击和市场炒作理由",
  "node": "公司所在精确产业链节点",
  "sector_symbol": "用于板块对比的 A 股 ETF 或指数代码，优先 512480、515790、159995、sh000300 之一",
  "chain_nodes": [
    ["core","核心需求","需求冲击"],
    ["upstream","上游约束","材料/设备/工艺"],
    ["stock","公司节点","公司名称"],
    ["downstream","下游应用","客户/应用"],
    ["peer","同链公司","公司名称"]
  ],
  "industry_judgment": "产业判断：水里有没有鱼，需求是否真实，供给是否有瓶颈",
  "barriers": ["技术/工艺壁垒","客户认证/切换成本","产能/良率/交付壁垒","其他壁垒"],
  "profit_levers": ["价格/ASP","产品结构/高端占比","产能利用率/经营杠杆"],
  "peers": ["同链公司1","同链公司2","同链公司3"],
  "wang_investor_report": "用 5-8 句话写产业链报告：需求冲击、利润池、瓶颈、公司节点、同链公司、风险",
  "evidence": ["来源标题/URL + 事实；没有来源的具体数字不要写","来源标题/URL + 事实","来源标题/URL + 事实"]
}}
""".strip()


def _public_equity_prompt(code: str, name: str) -> str:
    identity_hint = COMPANY_IDENTITY_HINTS.get(code, "")
    return f"""
请以 Public Equity Investing Agent 身份分析 A 股公司 {name}（{code}）。

身份校验：
- 必须同时匹配股票代码 {code} 和公司名 {name}。
- {identity_hint or "如公开资料与输入名称/代码冲突，先说明身份待核验。"}

请上网检索公开信息后输出以下 JSON：
质量要求：
- 必须判断它是不是同赛道最好的 A 股表达；如果不是，必须给出排序和原因。
- 必须判断交易位置：低位补涨、高位核心、拥挤追高、分歧回踩，不允许只写“建议关注风险”。
- peer_ranking 必须包含排序理由，不能只列公司名。
- 排序时必须说明每家公司位置：PCB 成品端、CCL 材料端、封装基板、PCB 子公司等。
- best_expression 必须明确回答：目标公司是“整体 AI PCB 主线最佳表达”，还是“CCL 材料细分最佳表达/补强表达”。
- 整体主线优先比较纯度和弹性，材料细分优先比较壁垒和确定性；两种排序不能混为一谈。
- valuation_odds 必须同时写上行逻辑和下行/拥挤风险。

{{
  "code": "{code}",
  "name": "{name}",
  "one_sentence_thesis": "一句话结论：核心性、产业链位置、交易位置都要说清楚",
  "rerating_anchor": "当前重估锚：哪条业务线、什么指标或什么产业变化驱动重估",
  "market_position": "短线交易语义：低位补涨/高位核心/主线龙头/分歧回踩/拥挤追高/跟风试错",
  "peer_ranking": ["A股同赛道排序1：公司 - 排序理由","排序2","排序3","排序4"],
  "best_expression": "分两层回答：整体 AI PCB 主线最佳表达是谁；CCL 材料细分里目标公司是不是最佳表达，为什么",
  "company_judgment": "公司判断：是否是真正受益者，还是宽主题暴露",
  "financial_validation": ["应验证的财报/经营指标1","指标2","指标3"],
  "expectation_gap": "市场低估了什么，或者哪些已经充分定价",
  "valuation_odds": "估值赔率与拥挤风险，不能只写低估/合理",
  "catalysts": ["催化剂1","催化剂2","催化剂3"],
  "disconfirming_signals": ["反证点1","反证点2","反证点3"],
  "position_sizing": "仓位和风险控制建议",
  "trading_implication": "买卖含义：能不能追、是否等分歧、用什么条件减仓/止损",
  "public_equity_report": "用 5-8 句话写上市公司投资判断：重估锚、同赛道排序、估值拥挤、买点含义",
  "evidence": ["来源标题/URL + 事实；没有来源的具体数字不要写","来源标题/URL + 事实","来源标题/URL + 事实"]
}}
""".strip()


def _merge_agent_payloads(code: str, name: str, wang: dict[str, Any], equity: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "code": code,
        "name": name,
        "theme": wang.get("theme") or equity.get("theme"),
        "core_driver": wang.get("core_driver") or equity.get("core_driver"),
        "node": wang.get("node") or equity.get("node"),
        "sector_symbol": wang.get("sector_symbol") or equity.get("sector_symbol"),
        "chain_nodes": wang.get("chain_nodes") or equity.get("chain_nodes"),
        "barriers": wang.get("barriers"),
        "profit_levers": wang.get("profit_levers"),
        "peers": _merge_lists(wang.get("peers"), equity.get("peers")),
        "industry_judgment": wang.get("industry_judgment"),
        "wang_investor_report": wang.get("wang_investor_report"),
        "one_sentence_thesis": equity.get("one_sentence_thesis"),
        "rerating_anchor": equity.get("rerating_anchor"),
        "market_position": equity.get("market_position"),
        "peer_ranking": equity.get("peer_ranking"),
        "best_expression": equity.get("best_expression"),
        "company_judgment": equity.get("company_judgment"),
        "financial_validation": equity.get("financial_validation"),
        "expectation_gap": equity.get("expectation_gap"),
        "valuation_odds": equity.get("valuation_odds"),
        "catalysts": equity.get("catalysts"),
        "disconfirming_signals": equity.get("disconfirming_signals"),
        "position_sizing": equity.get("position_sizing"),
        "trading_implication": equity.get("trading_implication"),
        "public_equity_report": equity.get("public_equity_report"),
        "evidence": _sanitize_evidence(_merge_lists(wang.get("evidence"), equity.get("evidence"))),
    }
    return {key: value for key, value in merged.items() if value not in (None, "", [], {})}


def _merge_lists(*values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list):
            items = value
        elif isinstance(value, tuple):
            items = list(value)
        else:
            items = []
        for item in items:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
    return result


def _sanitize_evidence(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    source_words = ("http", "www.", "公告", "年报", "季报", "研报", "点评", "交易所", "互动", "公司", "券商", "东方财富", "同花顺", "Wind")
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        if "公开证据或待验证事实" in text or "证据1" in text or "证据2" in text or "证据3" in text:
            continue
        has_number = bool(re.search(r"\d", text))
        has_source = any(word in text for word in source_words)
        if has_number and not has_source:
            continue
        cleaned.append(text)
    return cleaned[:6]


def _equity_quality_issue(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False)
    issues: list[str] = []
    if re.search(r"沪电股份[^，。；\n]*(覆铜板|CCL)", text):
        issues.append("沪电股份/胜宏/深南是 PCB 成品端，不是覆铜板/CCL 材料龙头；必须纠正同赛道角色。")
    if re.search(r"胜宏科技[^，。；\n]*(覆铜板|CCL)", text):
        issues.append("胜宏科技偏 PCB 成品端，不能写成覆铜板/CCL 材料公司。")
    if re.search(r"深南电路[^，。；\n]*(覆铜板|CCL)", text):
        issues.append("深南电路偏 PCB/封装基板，不能写成覆铜板/CCL 材料公司。")
    rerating = str(payload.get("rerating_anchor") or payload.get("public_equity_report") or payload.get("one_sentence_thesis") or "")
    if "AI" not in rerating and ("5G" in rerating or "汽车电子" in rerating or "物联网" in rerating):
        issues.append("当前重估锚不能退回 5G/汽车电子/物联网泛应用；必须核验 AI PCB、高速交换机、高端 CCL 是否是当前主线。")
    ranking = payload.get("peer_ranking")
    if not isinstance(ranking, list) or len(ranking) < 4:
        issues.append("peer_ranking 不足，必须给出至少 4 个 A 股同赛道标的及排序理由。")
    return "；".join(issues)


def _system_prompt() -> str:
    return """
你是 A 股交易复盘系统里的投研 Agent。你的任务不是用行情接口猜产业链，而是像 Codex 里的 WANG-INVESTOR + Public Equity Investing 一样，先检索公开信息，再形成投资研究判断。

硬规则：
1. 腾讯财经、AKShare 等行情源只用于 K 线、指数、成交量、涨跌幅等市场事实；不能把它们当作产业链研究来源。
2. 产业链、壁垒、利润池、公司定位、催化剂、反证点，必须来自公开检索后的综合判断：公司公告、年报/半年报、交易所互动、券商研报标题、新闻、产业资料、客户/产品/订单线索。
3. 第一问题永远是：当前市场为什么炒它？不要默认它属于 AI，不要默认旧主业就是本轮交易主线。
4. 如果证据不足，明确写“待验证”，并说明需要验证什么；不要编造客户、订单、财报数字。
5. 财报验证字段优先写“应该验证哪些指标”，不要随口给具体营收、利润、毛利率数字；只有在检索证据明确支持时才可写具体数值。

WANG-INVESTOR 分析骨架：
- 定义需求冲击：需求增长、供给瓶颈、利润池迁移、政策/技术变化、主题轮动。
- 映射产业链：上游材料/设备/工艺，中游制造/模块/零部件，下游客户/应用。
- 找利润池：价格、产品结构、产能利用率、客户紧迫性、毛利率弹性。
- 找稀缺和瓶颈：技术难度、良率、客户认证、专利/配方、设备长交期、产能、切换成本。
- 判断盈利弹性：需求变化时，谁的利润弹性大于收入弹性。
- 区分“有概念暴露”和“是真正瓶颈”。

Public Equity Investing 骨架：
产业空间 -> 公司竞争力 -> 财报/经营验证 -> 市场预期差 -> 估值赔率 -> 催化剂/反证 -> 仓位管理。

单股精度要求：
- 必须说明公司所在的精确节点，而不是只写 PCB、半导体、AI、钻石等宽标签。
- 必须说明这条主线是主攻、补涨、材料节点、设备节点、制造节点、下游应用节点，还是弱相关暴露。
- 对 PCB/CCL/半导体硬件链，如证据指向 AI 基建，要显式挂到：
  AI 推理/训练需求 -> GPU/ASIC/HBM -> 服务器/交换机/加速卡 -> 高速 PCB/低损耗 CCL/铜箔/电子布/连接器/电源/散热。
- 对超硬材料/人造金刚石公司，必须区分：
  培育钻石消费品、工业金刚石工具、金刚石热沉/金刚石-铜/金刚石-碳化硅复合材料、AI 芯片或高功率半导体热管理。

只返回 JSON，不要 markdown。
""".strip()


def _user_prompt(code: str, name: str) -> str:
    identity_hint = COMPANY_IDENTITY_HINTS.get(code, "")
    return f"""
请对 A 股上市公司 {name}（{code}）生成交易复盘用的动态产业画像。

标的身份硬校验：
- 检索和分析必须同时匹配股票代码 {code} 和公司名 {name}，不得引用同名、错名、其他市场或其他代码的公司资料。
- {identity_hint or "如公开资料与输入名称/代码冲突，先说明身份待核验，不要套用不匹配公司的产业链。"}
- 身份提示不是结论，当前交易主线仍必须由近期市场证据和产业证据判断。

请先上网检索并判断：
1. 近期市场为什么炒它，或为什么交易关注度上升？
2. 本轮交易主线到底是产业逻辑、财报逻辑、价格逻辑、政策逻辑、指数/资金逻辑，还是纯情绪补涨？
3. 公司在产业链的精确位置、壁垒、利润弹性、验证指标是什么？
4. 市场预期差在哪里？哪些证据会证伪？
5. 财报验证请输出指标和验证方向，除非你能从检索证据确认具体数字，否则不要写具体数值。
6. 必须比较 A 股同赛道可投资标的，判断目标公司是不是最佳表达；如果不是，说明谁更强。
7. 必须判断短线交易语义：低位补涨、高位核心、主线龙头、分歧回踩、拥挤追高、跟风试错等。

输出 JSON schema：
{{
  "code": "{code}",
  "name": "{name}",
  "one_sentence_thesis": "一句话结论：核心性、产业链位置、交易位置都要说清楚",
  "theme": "窄主题，不要宽标签",
  "core_driver": "当前市场炒作理由和产业核心驱动",
  "node": "公司所在精确产业链节点",
  "rerating_anchor": "当前市场重估锚：是哪条业务线、什么指标或什么产业变化驱动重估",
  "market_position": "短线交易语义：低位补涨/高位核心/主线龙头/分歧回踩/拥挤追高/跟风试错等",
  "sector_symbol": "用于板块对比的 A 股 ETF 或指数代码，优先 512480、515790、159995、sh000300 之一",
  "chain_nodes": [
    ["core","核心需求","需求冲击"],
    ["upstream","上游约束","材料/设备/工艺"],
    ["stock","公司节点","公司名称"],
    ["downstream","下游应用","客户/应用"],
    ["peer","同链公司","公司名称"]
  ],
  "barriers": ["壁垒1","壁垒2","壁垒3","壁垒4"],
  "profit_levers": ["盈利弹性1","盈利弹性2","盈利弹性3"],
  "peers": ["同链公司1","同链公司2"],
  "peer_ranking": ["A股同赛道排序1：公司 - 排序理由","排序2","排序3","排序4"],
  "best_expression": "目标公司是不是这条产业链最好的 A 股交易表达？如果不是，谁更好，为什么",
  "industry_judgment": "产业判断：水里有没有鱼",
  "company_judgment": "公司判断：是不是这条产业链里真正受益的鱼",
  "financial_validation": ["财报验证指标1","财报验证指标2","经营KPI"],
  "expectation_gap": "市场可能低估或已经充分定价的点",
  "valuation_odds": "估值赔率如何判断，不写具体目标价",
  "catalysts": ["催化剂1","催化剂2"],
  "disconfirming_signals": ["反证点1","反证点2"],
  "position_sizing": "仓位和风险控制建议",
  "trading_implication": "结合交易位置给买点/卖点建议：能不能追、是否等分歧、用什么条件减仓",
  "evidence": ["证据1：公开资料或需要核验的事实","证据2","证据3"]
}}
""".strip()


def _profile_from_payload(payload: dict[str, Any], code: str, name: str) -> IndustryProfile:
    theme = _text(payload.get("theme"), "产业主题待验证")
    node = _text(payload.get("node"), "产业链节点待识别")
    core_driver = _text(payload.get("core_driver"), "市场主线待识别")
    return IndustryProfile(
        code=_clean_code(str(payload.get("code") or code)),
        name=_text(payload.get("name"), name or code),
        theme=theme,
        core_driver=core_driver,
        node=node,
        sector_symbol=_normalize_sector_symbol(payload, code, name, theme, node, core_driver),
        chain_nodes=_normalize_chain_nodes(payload.get("chain_nodes")),
        barriers=_tuple_text(payload.get("barriers"), ("壁垒待验证",)),
        profit_levers=_tuple_text(payload.get("profit_levers"), ("盈利弹性待验证",)),
        peers=_tuple_text(payload.get("peers"), ()),
        industry_judgment=_text(payload.get("industry_judgment"), "产业判断待生成。"),
        company_judgment=_text(payload.get("company_judgment"), "公司判断待生成。"),
        financial_validation=_tuple_text(payload.get("financial_validation"), ("收入结构", "毛利率", "订单/产能利用率")),
        expectation_gap=_text(payload.get("expectation_gap"), "预期差待验证。"),
        valuation_odds=_text(payload.get("valuation_odds"), "估值赔率待验证。"),
        catalysts=_tuple_text(payload.get("catalysts"), ("订单/客户验证", "财报兑现")),
        disconfirming_signals=_tuple_text(payload.get("disconfirming_signals"), ("逻辑未被财报验证", "竞争加剧")),
        position_sizing=_text(payload.get("position_sizing"), "根据波动、流动性和反证点控制仓位。"),
        one_sentence_thesis=_text(payload.get("one_sentence_thesis"), ""),
        rerating_anchor=_text(payload.get("rerating_anchor"), ""),
        market_position=_text(payload.get("market_position"), ""),
        peer_ranking=_tuple_text(payload.get("peer_ranking"), ()),
        best_expression=_text(payload.get("best_expression"), ""),
        trading_implication=_text(payload.get("trading_implication"), ""),
        evidence=_tuple_text(payload.get("evidence"), ()),
        wang_investor_report=_text(payload.get("wang_investor_report"), ""),
        public_equity_report=_text(payload.get("public_equity_report"), ""),
    )


def _normalize_chain_nodes(value: Any) -> tuple[tuple[str, str, str], ...]:
    result: list[tuple[str, str, str]] = []
    if isinstance(value, list):
        for item in value[:7]:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                result.append((str(item[0])[:24], str(item[1])[:24], str(item[2])[:36]))
            elif isinstance(item, dict):
                result.append(
                    (
                        str(item.get("kind") or item.get("id") or "node")[:24],
                        str(item.get("title") or item.get("label") or "节点")[:24],
                        str(item.get("subtitle") or item.get("description") or "")[:36],
                    )
                )
    if not result:
        result = [
            ("core", "核心需求", "待识别"),
            ("upstream", "上游约束", "待识别"),
            ("stock", "公司节点", "待识别"),
            ("downstream", "下游应用", "待识别"),
            ("peer", "同链公司", "待识别"),
        ]
    return tuple(result)


def _tuple_text(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return tuple(items) if items else default
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return default


def _text(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _normalize_symbol(value: str) -> str:
    text = value.strip()
    if text.startswith(("sh", "sz")):
        return text
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 6:
        return digits
    return "sh000300"


def _normalize_sector_symbol(
    payload: dict[str, Any],
    code: str,
    name: str,
    theme: str,
    node: str,
    core_driver: str,
) -> str:
    symbol = _normalize_symbol(str(payload.get("sector_symbol") or ""))
    code = _clean_code(code)
    broad_index = symbol in {"sh000300", "000300", "sh000001", "sz399001"}
    context = " ".join([name, theme, node, core_driver])
    hardware_chain = any(
        keyword in context
        for keyword in (
            "PCB",
            "CCL",
            "覆铜板",
            "电子材料",
            "半导体",
            "封装",
            "先进封装",
            "MLCC",
            "被动元件",
            "算力",
            "AI基础设施",
            "AI算力",
        )
    )
    if broad_index and code in SECTOR_PROXY_HINTS and hardware_chain:
        return SECTOR_PROXY_HINTS[code]
    return symbol or SECTOR_PROXY_HINTS.get(code, "sh000300")


def _clean_code(code: str) -> str:
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else ""


def _load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
