from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

from trade_review_agent.review.final_wang_agent.agent import (
    DEFAULT_ARK_BASE_URL,
    DEFAULT_ARK_MODEL,
    DEFAULT_DEEPSEEK_MODEL,
    DEEPSEEK_BASE_URL,
    USD_CNY,
    ark_cost,
    deepseek_cost,
    extract_responses_text,
    load_dotenv,
    usage_token_summary,
)


ROOT = Path(__file__).resolve().parents[2]


class MarketDayAgentError(RuntimeError):
    def __init__(self, user_message: str, *, detail: str = "", code: str = "market_day_agent_error", status_code: int = 0):
        super().__init__(detail or user_message)
        self.user_message = user_message
        self.detail = detail or user_message
        self.code = code
        self.status_code = status_code
        self.retryable = status_code in {429, 500, 502, 503, 504}


def run_market_day_agent(market_date: str | None = None) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    started = time.perf_counter()
    ark_key = os.getenv("ARK_API_KEY", "").strip().lstrip("\ufeff")
    judge_key = os.getenv("DEEPSEEK_API_KEY", "").strip().lstrip("\ufeff")
    if not ark_key:
        raise RuntimeError("ARK_API_KEY missing in .env")
    if not judge_key:
        raise RuntimeError("DEEPSEEK_API_KEY missing in .env")

    raw_result = run_market_day_research_result(normalize_market_date(market_date), ark_key, judge_key)
    return present_market_day_result(raw_result, total_started=started)


def run_market_day_research_result(market_date: str, ark_key: str, judge_key: str) -> dict[str, Any]:
    search_prompt = build_market_day_search_prompt(market_date)
    doubao_started = time.perf_counter()
    doubao_response = call_doubao_market_search(ark_key, search_prompt)
    doubao_seconds = round(time.perf_counter() - doubao_started, 4)
    search_pack = extract_responses_text(doubao_response)

    judge_prompt = build_market_day_judge_prompt(market_date, search_pack)
    judge_started = time.perf_counter()
    judge_response = call_market_day_judge(judge_key, judge_prompt)
    judge_seconds = round(time.perf_counter() - judge_started, 4)
    answer = extract_market_day_judge_text(judge_response)
    parsed = parse_market_day_answer(answer)

    return {
        "market_date": market_date,
        "answer": answer,
        "parsed": parsed,
        "search_pack": search_pack,
        "doubao_response": doubao_response,
        "judge_response": judge_response,
        "doubao_cost": ark_cost(doubao_response.get("usage", {})),
        "judge_cost": deepseek_cost(judge_response.get("usage", {}), market_day_judge_model_name()),
        "seconds": {
            "doubao_search": doubao_seconds,
            "judge": judge_seconds,
        },
        "prompts": {
            "doubao_search_prompt": search_prompt,
            "judge_prompt": judge_prompt,
        },
        "models": {
            "doubao": market_day_doubao_model_name(),
            "judge": market_day_judge_model_name(),
            "judge_provider": "deepseek",
        },
    }


def build_market_day_search_prompt(market_date: str) -> str:
    market_date_cn = cn_date(market_date)
    return f"""你是A股全市场当日行情复盘资料搜索员。

任务：
请联网搜索并整理 {market_date_cn} A股市场复盘资料。
只做资料整理，不做投资建议，不预测涨跌，不推荐股票。
只输出搜索证据包。

核心目标：
先确认当天行情主线，再整理板块和个股。
禁止从单一个股反推主线。

搜索优先级：
- 同花顺、财联社、证券时报、中国证券报、上海证券报
- 涨停复盘、龙虎榜、交易所公告、公司公告
- 东方财富 Choice / Wind 引用资料 / 券商研报作为补充
- 雪球、股吧、淘股吧只能作为情绪参考，不能单独作为事实依据

必须搜索并整理：
1. 市场整体情绪：涨停家数、跌停家数、连板高度、炸板率、成交额。
2. 当天行情主线：最强主线、主线分支、次主线、伪主线或退潮方向。
3. 强势板块：涨幅、涨停家数、成交额、资金流入、异动原因。
4. 涨停潮和连板梯队：哪些方向出现涨停潮，哪些个股形成梯队。
5. 主线内核心个股候选：龙头、中军、高度板、趋势核心、情绪标。
6. 每个候选个股的证据：涨跌幅、涨停原因、连板数、成交额、换手率、龙虎榜、资金流。
7. 分歧证据：炸板、回落、后排掉队、主线内部强弱切换。

输出要求：
- 标题只能是：# 搜索证据包
- 中文输出
- 保留来源名称、来源等级、日期、URL、原文摘要
- 来源不足明确标注“来源不足”
- 来源存疑明确标注“来源存疑”
- 所有结论必须有证据链
- 不要输出投资建议、买卖建议、推荐股票或确定性预测"""


def build_market_day_judge_prompt(market_date: str, search_pack: str) -> str:
    return f"""你是A股短线行情复盘 Judge。

下面是一份 Doubao Research 搜索资料包。
只基于资料包判断，不要声称自己联网搜索。

任务：
站在 {cn_date(market_date)} 当天盘后视角，判断 A股全市场当日最强主线，并在主线内选出最强势个股。

核心问题：
1. 当日市场情绪如何？
2. 当日最强主线是什么？
3. 主线内最强势个股是谁？
4. 它为什么强，是龙头、中军、高度板、趋势核心、情绪标，还是跟风后排？
5. 哪些方向只是次主线、伪主线或已经分歧？

输出要求：
- 只输出一个合法 JSON 对象。
- 不要 markdown。
- 不要代码块。
- JSON 外不要输出任何解释。
- 所有判断只能来自资料包；证据不足时写清“证据不足”，但仍要基于已有证据给出倾向判断。
- 不要输出投资建议、买卖建议、明日预测或推荐买入。

JSON 结构必须严格使用以下 key：
{{
  "marketDate": "{market_date}",
  "oneLineConclusion": "30字以内盘后交易员语言结论",
  "marketMood": {{
    "summary": "市场情绪总评",
    "limitUpCount": "涨停家数或证据不足",
    "limitDownCount": "跌停家数或证据不足",
    "heightBoard": "连板高度或证据不足",
    "turnover": "成交额或证据不足",
    "score": 0
  }},
  "mainline": {{
    "name": "当日最强主线",
    "reason": "为什么它是当日最强主线",
    "branches": ["主线分支"],
    "evidence": ["证据1", "证据2"],
    "score": 0
  }},
  "strongestStocks": [
    {{
      "rank": 1,
      "name": "股票名称",
      "code": "股票代码或证据不足",
      "leaderType": "龙头 / 中军 / 高度板 / 趋势核心 / 情绪标 / 跟风 / 后排",
      "theme": "所属主线或分支",
      "strengthReason": "为什么强",
      "evidence": ["涨停、连板、成交额、资金、龙虎榜等证据"],
      "riskOrDivergence": "分歧或风险证据",
      "score": 0
    }}
  ],
  "secondaryLines": [
    {{
      "name": "次主线名称",
      "reason": "为什么不是最强主线",
      "representativeStocks": ["代表个股"],
      "evidence": ["证据"]
    }}
  ],
  "fakeOrWeakLines": [
    {{
      "name": "伪主线或弱方向",
      "reason": "为什么弱或证据不足",
      "evidence": ["证据"]
    }}
  ],
  "watchPoints": ["后续复盘需要观察的客观条件"],
  "audit": {{
    "missingEvidence": ["证据不足的字段"],
    "sourceWarnings": ["来源存疑或冲突"]
  }}
}}

评分要求：
- 所有 score 使用 0-10 分制。
- 10 表示当天最强证据完整，0 表示完全无证据。

写作要求：
- 先结论，后依据。
- 语言像交易复盘，不像新闻摘要。
- 每个最强势个股都要解释“强在哪里”。
- 必须区分龙头、中军、高度板、趋势核心、跟风、后排。

资料包：
{search_pack}"""


def call_doubao_market_search(api_key: str, prompt: str) -> dict[str, Any]:
    body = {
        "model": market_day_doubao_model_name(),
        "input": prompt,
        "tools": [{"type": "web_search"}],
        "thinking": {"type": "enabled"},
        "reasoning": {"effort": "medium"},
    }
    request = urllib.request.Request(
        f"{market_day_ark_base_url()}/responses",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = _http_error_body(exc)
        raise MarketDayAgentError(
            "豆包当日行情 Research 搜索失败",
            detail=f"Ark HTTP {exc.code}: {exc.reason}. {body_text}".strip(),
            code="market_day_doubao_search_http_error",
            status_code=exc.code,
        ) from exc


def call_market_day_judge(api_key: str, prompt: str) -> dict[str, Any]:
    body = {
        "model": market_day_judge_model_name(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        f"{market_day_deepseek_base_url()}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_market_day_judge_text(data: dict[str, Any]) -> str:
    try:
        return str(data["choices"][0]["message"]["content"] or "")
    except Exception:
        return ""


def parse_market_day_answer(answer: str) -> dict[str, Any]:
    raw = (answer or "").strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").strip()
        raw = raw.removesuffix("```").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise MarketDayAgentError(
                "当日行情 Judge 返回格式异常",
                detail="Judge response did not contain a JSON object.",
                code="market_day_judge_invalid_json",
                status_code=502,
            )
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise MarketDayAgentError(
            "当日行情 Judge 返回格式异常",
            detail="Judge response JSON was not an object.",
            code="market_day_judge_invalid_json",
            status_code=502,
        )
    return data


def present_market_day_result(raw_result: dict[str, Any], *, total_started: float) -> dict[str, Any]:
    doubao_response = raw_result.get("doubao_response") if isinstance(raw_result.get("doubao_response"), dict) else {}
    judge_response = raw_result.get("judge_response") if isinstance(raw_result.get("judge_response"), dict) else {}
    doubao_cost = raw_result.get("doubao_cost") or {}
    judge_cost = raw_result.get("judge_cost") or {}
    total_cny = round(float(doubao_cost.get("cny") or 0) + float(judge_cost.get("cny") or 0), 6)
    seconds = raw_result.get("seconds") if isinstance(raw_result.get("seconds"), dict) else {}
    models = raw_result.get("models") if isinstance(raw_result.get("models"), dict) else {}
    parsed = raw_result.get("parsed") if isinstance(raw_result.get("parsed"), dict) else {}
    return {
        "agent_type": "market_day",
        "agent_name": "Market Day Agent",
        "market_date": raw_result.get("market_date"),
        "report": parsed,
        "judge_answer": raw_result.get("answer") or "",
        "doubao_search_pack": raw_result.get("search_pack") or "",
        "research_pipeline": "market_day_agent:doubao_search_deepseek_judge",
        "prompts": raw_result.get("prompts") or {},
        "models": models,
        "doubao_search_metrics": {
            "model": models.get("doubao"),
            "seconds": seconds.get("doubao_search"),
            "tokens": usage_token_summary(doubao_response.get("usage", {})),
            "cost_cny": doubao_cost.get("cny"),
            "raw_usage": doubao_response.get("usage", {}),
        },
        "research_metrics": {
            "agent": "Market Day Agent",
            "provider": "deepseek",
            "model": models.get("judge"),
            "allow_web": False,
            "seconds": round(float(seconds.get("doubao_search") or 0) + float(seconds.get("judge") or 0), 4),
            "status": "ok",
            "api_usage": judge_response.get("usage", {}),
            "estimated_cost_cny": judge_cost.get("cny"),
            "doubao_search_seconds": seconds.get("doubao_search"),
            "judge_seconds": seconds.get("judge"),
        },
        "cost": {
            "doubao": doubao_cost,
            "judge": judge_cost,
            "total_cny": total_cny,
            "total_usd_equivalent": round(total_cny / USD_CNY, 8) if USD_CNY else None,
        },
        "seconds": {
            "doubao_search": seconds.get("doubao_search"),
            "judge": seconds.get("judge"),
            "total": round(time.perf_counter() - total_started, 4),
        },
    }


def normalize_market_date(value: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return date.today().isoformat()
    return datetime.strptime(text, "%Y-%m-%d").date().isoformat()


def cn_date(date_text: str) -> str:
    parsed = datetime.strptime(date_text, "%Y-%m-%d").date()
    return f"{parsed:%Y年%m月%d日}"


def market_day_doubao_model_name() -> str:
    return os.getenv("MARKET_DAY_DOUBAO_MODEL") or os.getenv("WANG_DOUBAO_MODEL") or os.getenv("ARK_MODEL") or DEFAULT_ARK_MODEL


def market_day_judge_model_name() -> str:
    return os.getenv("MARKET_DAY_JUDGE_MODEL") or os.getenv("WANG_JUDGE_MODEL") or os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL


def market_day_ark_base_url() -> str:
    return (os.getenv("ARK_BASE_URL") or DEFAULT_ARK_BASE_URL).strip().rstrip("/")


def market_day_deepseek_base_url() -> str:
    return (os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL).strip().rstrip("/")


def _http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        payload = exc.read().decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""
    return payload[:1200]
