from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests


DEFAULT_STOCK_ANALYZE_API = "http://127.0.0.1:8750/api/codex"
DEFAULT_TIMEOUT_SECONDS = 620


class StockAnalyzeError(RuntimeError):
    """Raised when the local Stock Analyze bridge cannot return a usable result."""


@dataclass(frozen=True)
class IndustryTrendRequest:
    query: str
    input_type: str = "auto"


def build_industry_trend_prompt(request: IndustryTrendRequest) -> str:
    query = request.query.strip()
    input_type = _normalize_input_type(request.input_type)
    subject_label = {
        "stock": "个股",
        "chain": "产业链",
        "auto": "产业链或个股",
    }[input_type]
    return f"""请使用 $stock-reverse-engineering 技能，围绕用户输入的{subject_label}做产业趋势和产业选股分析。

用户输入：{query}
输入类型：{input_type}

请输出：
1. 资金为什么关注：事件、政策、业绩、供需、国产替代或情绪催化。
2. 产业链位置：从最终需求倒推到产品、材料、设备、服务和 A 股映射。
3. 瓶颈分析：当前最稀缺节点、瓶颈类型、谁先涨价、扩产难度和瓶颈迁移。
4. 利润流向：高利润、高壁垒、高增长分别在哪些环节。
5. 产业选股：列出核心受益、弹性受益、卖铲子、情绪跟随、伪核心，并说明理由。
6. 三高评分：壁垒、利润、增长，各 1-10 分，综合分 = 0.4*壁垒 + 0.3*利润 + 0.3*增长。
7. 反证风险：哪些信号会推翻当前判断。

要求：
- 明确区分资金炒作逻辑和产业利润逻辑。
- 不构成投资建议。
- 若资料不足，标注“待验证”，不要把概念标签当证据。
"""


def run_industry_trend_analysis(request: IndustryTrendRequest) -> dict:
    query = request.query.strip()
    if not query:
        raise ValueError("请输入产业链或个股")
    input_type = _normalize_input_type(request.input_type)
    endpoint = os.getenv("STOCK_ANALYZE_API_URL", DEFAULT_STOCK_ANALYZE_API).strip() or DEFAULT_STOCK_ANALYZE_API
    timeout = _timeout_seconds()
    prompt = build_industry_trend_prompt(IndustryTrendRequest(query=query, input_type=input_type))
    headers = _auth_headers()
    started = time.perf_counter()
    try:
        response = requests.post(
            endpoint,
            json={"prompt": prompt},
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise StockAnalyzeError(
            f"Stock Analyze 服务不可用，请先启动：.\\start.ps1 -StockSkill -Port 8750。详细错误：{exc}"
        ) from exc

    elapsed = round(time.perf_counter() - started, 3)
    try:
        payload = response.json()
    except ValueError as exc:
        raise StockAnalyzeError(f"Stock Analyze 返回了非 JSON 响应：{response.text[:300]}") from exc

    if response.status_code >= 400:
        message = payload.get("error") if isinstance(payload, dict) else ""
        raise StockAnalyzeError(str(message or f"Stock Analyze 请求失败：HTTP {response.status_code}"))

    answer = str(payload.get("answer") or "").strip() if isinstance(payload, dict) else ""
    if not answer:
        raise StockAnalyzeError("Stock Analyze 没有返回分析正文")

    return {
        "query": query,
        "input_type": input_type,
        "answer": answer,
        "source": "stock-analyze",
        "endpoint": endpoint,
        "elapsed_seconds": elapsed,
    }


def _normalize_input_type(value: object) -> str:
    text = str(value or "auto").strip().lower()
    if text in {"stock", "chain", "auto"}:
        return text
    return "auto"


def _timeout_seconds() -> int:
    raw = os.getenv("STOCK_ANALYZE_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return max(30, int(float(raw)))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _auth_headers() -> dict[str, str]:
    token = os.getenv("STOCK_ANALYZE_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}
