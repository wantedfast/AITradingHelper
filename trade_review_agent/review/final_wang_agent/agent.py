from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .presenter import present_wang_research_result


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARK_MODEL = "doubao-seed-2-0-pro-260215"
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DS_RAW_REPORT_DIR_ENV = "AI_TRADING_HELPER_DS_REPORT_DIR"

USD_CNY = 6.7638
ARK_INPUT_CNY_PER_1M = 3.2
ARK_CACHED_INPUT_CNY_PER_1M = 0.64
ARK_OUTPUT_CNY_PER_1M = 16.0
DEEPSEEK_PRICES_USD_PER_1M = {
    "deepseek-v4-flash": {"input_cache_hit": 0.0028, "input_cache_miss": 0.14, "output": 0.28},
    "deepseek-v4-pro": {"input_cache_hit": 0.003625, "input_cache_miss": 0.435, "output": 0.87},
    "deepseek-chat": {"input_cache_hit": 0.0028, "input_cache_miss": 0.14, "output": 0.28},
}


class FinalWangAgentError(RuntimeError):
    def __init__(self, user_message: str, *, detail: str = "", code: str = "final_wang_agent_error", status_code: int = 0):
        super().__init__(detail or user_message)
        self.user_message = user_message
        self.detail = detail or user_message
        self.code = code
        self.status_code = status_code
        self.retryable = status_code in {429, 500, 502, 503, 504}


def run_final_wang_agent(context: dict[str, Any]) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    started = time.perf_counter()
    ark_key = os.getenv("ARK_API_KEY", "").strip().lstrip("\ufeff")
    judge_provider = wang_judge_provider()
    judge_key_name = "DEEPSEEK_API_KEY"
    judge_key = os.getenv(judge_key_name, "").strip().lstrip("\ufeff")
    if not ark_key:
        raise RuntimeError("ARK_API_KEY missing in .env")
    if not judge_key:
        raise RuntimeError(f"{judge_key_name} missing in .env")

    raw_result = run_wang_research_result(context, ark_key, judge_key, judge_provider)
    return present_wang_research_result(
        raw_result,
        usage_token_summary=usage_token_summary,
        usd_cny=USD_CNY,
        total_started=started,
    )


def run_wang_research_result(context: dict[str, Any], ark_key: str, judge_key: str, judge_provider: str | None = None) -> dict[str, Any]:
    judge_provider = judge_provider or wang_judge_provider()
    trade = trade_input_from_context(context)
    stock_name = trade["stock_name"]
    stock_code = trade["stock_code"]
    buy_date = trade["buy_date"]
    buy_times = trade["buy_times"]

    search_prompt = build_search_prompt(stock_name, stock_code, buy_date, buy_times)
    doubao_started = time.perf_counter()
    doubao_response = call_doubao_search(ark_key, search_prompt)
    doubao_seconds = round(time.perf_counter() - doubao_started, 4)
    search_pack = extract_responses_text(doubao_response)

    judge_prompt = build_judge_prompt(stock_name, stock_code, buy_date, buy_times, search_pack)
    judge_started = time.perf_counter()
    judge_response = call_judge_model(judge_key, judge_prompt, judge_provider)
    judge_seconds = round(time.perf_counter() - judge_started, 4)
    answer = extract_judge_text(judge_response, judge_provider)
    raw_markdown_files = save_deepseek_raw_markdown(answer, context, trade)

    doubao_cost = ark_cost(doubao_response.get("usage", {}))
    judge_cost_result = judge_cost(judge_response.get("usage", {}), judge_provider, judge_model_name(judge_provider))
    return {
        "trade": trade,
        "answer": answer,
        "raw_markdown_files": raw_markdown_files,
        "search_pack": search_pack,
        "doubao_response": doubao_response,
        "judge_response": judge_response,
        "doubao_cost": doubao_cost,
        "judge_cost": judge_cost_result,
        "seconds": {
            "doubao_search": doubao_seconds,
            "judge": judge_seconds,
        },
        "prompts": {
            "doubao_search_prompt": search_prompt,
            "judge_prompt": judge_prompt,
        },
        "models": {
            "doubao": doubao_model_name(),
            "judge": judge_model_name(judge_provider),
            "judge_provider": judge_provider,
        },
    }


def build_search_prompt(stock_name: str, stock_code: str, buy_date: str, buy_times: list[str]) -> str:
    # 旧版提示词（已停用）：
    # 你是A股研究资料搜索员。请联网搜索资料，不要做最终投资判断。
    # 请搜索并整理市场主线、个股表现、题材、主营业务、财报验证和相关公司。
    # 输出“搜索资料包”，保留来源名称、日期、URL、原文摘要。
    buy_times_text = "\n".join(f"- {item}" for item in buy_times)
    buy_date_cn = cn_date(buy_date)
    return f"""你是A股资金逻辑研究员。

任务：

请联网搜索资料。

只做资料整理。

不要做投资建议。

不要预测涨跌。

不要推荐股票。

不要输出主观结论。

只输出搜索证据。

---

# 研究对象

股票名称：{stock_name}

股票代码：{stock_code}

买入日期：

{buy_date_cn}

原始日期：

{buy_date}

买入时间：

{buy_times_text}


---

# 核心原则

必须遵循以下顺序：

市场主线
↓
板块
↓
个股
↓
产业链
↓
利润流向
↓
资金验证
↓
资金逻辑
↓
同逻辑公司

禁止：

个股
↓
反推市场主线

必须先确认：

市场在炒什么

然后再分析：

为什么资金炒到该股

---

# 搜索来源优先级

## S级（优先）

市场与资金行为：

- 同花顺
- 财联社
- 证券时报
- 中国证券报
- 上海证券报
- 龙虎榜
- 公司公告
- 交易所公告

---

## A级（补充）

- 东方财富Choice
- Wind引用资料
- 券商研报
- 机构调研纪要
- 公司年报
- 公司季报
- 公司半年报

---

## B级（仅情绪参考）

- 雪球
- 股吧
- 淘股吧

不得单独作为事实依据。

---

# 禁止来源

以下来源禁止作为事实依据：

- 喜娜AI
- 芝麻AI
- 驱动号
- AI摘要站
- 聚合采集站
- 自媒体转载站
- 无法追溯原文的网站

规则：

如果搜索结果来自上述来源：

必须继续向上追溯。

优先追溯：

- 公告
- 年报
- 季报
- 研报
- 财联社
- 同花顺
- 东方财富

无法追溯：

标记：

来源存疑

不得纳入核心证据。

---

# 搜索要求

如果搜索不到：

不要猜测。

统一写：

来源不足

如果证据链不完整：

统一写：

证据不足

---

# 搜索流程

---

# 第一步：市场主线分析

搜索：

{buy_date_cn} A股市场复盘

整理：

## 市场整体情绪

- 涨停家数
- 连板高度
- 跌停家数
- 炸板率

---

## 强势板块

整理：

- 涨幅居前板块
- 涨停家数居前板块
- 成交额居前板块
- 资金流入居前板块

---

## 强势题材

根据搜索结果整理：

- 当日主线
- 主线分支
- 次主线

禁止预设答案。

---

## 资金进攻方向

整理：

- 资金流入方向
- 异动原因

---

## 涨停潮分析

根据搜索结果整理：

- 哪些方向出现涨停潮
- 哪些方向出现连板梯队

如果没有证据：

写：

来源不足

---

# 第二步：板块定位分析

先分析板块。

不要分析个股。

---

## {stock_name}属于哪个板块

整理：

- 所属行业
- 所属概念
- 所属板块

---

## 所属板块是否属于当日主线

整理：

- 板块涨幅
- 板块涨停家数
- 板块成交额变化
- 板块资金流向

---

## 板块核心个股

整理：

- 龙头
- 中军
- 高度板
- 趋势核心

必须给依据。

---

## {stock_name}在板块中的位置

根据搜索结果整理：

- 龙头
- 中军
- 跟风
- 补涨
- 趋势核心
- 情绪标
- 产业链核心

必须给依据。

禁止主观判断。

---

# 第三步：个股市场表现

搜索：

{buy_date_cn}

{stock_name}

整理：

- 涨跌幅
- 换手率
- 成交额
- 成交量
- 主力资金
- 超大单
- 大单
- 龙虎榜
- 异动公告
- 涨停原因
- 融资融券变化

每一项必须保留：

- 来源名称
- 来源等级
- 日期
- URL
- 原文摘要

没有来源：

写：

来源不足

---

# 第四步：市场给该股贴的题材

不要预设结论。

根据搜索结果整理。

---

## 官方概念

来源：

- 同花顺
- 东方财富

---

## 媒体概念

来源：

- 财联社
- 证券时报

---

## 券商概念

来源：

- 券商研报

---

## 情绪概念

来源：

- 雪球
- 股吧
- 淘股吧

必须注明：

情绪观点

不作为事实依据

---

# 第五步：基本面与产业链

整理：

## 主营业务

## 核心产品

## 核心客户

## 应用场景

## 上游

## 下游

## 竞争对手

## 产业链位置

优先引用：

- 年报
- 季报
- 公告
- 机构调研
- 券商研报

---

## 产业链结构图

根据搜索结果绘制：

需求端
↓
终端客户
↓
中游制造
↓
核心材料
↓
研究对象

禁止预设产业链。

---

# 第六步：财报验证

整理：

## 营收

## 净利润

## 毛利率

## 分业务收入

## 经营现金流

## 风险因素

## 业绩变化原因

优先：

- 年报
- 季报
- 半年报

---

# 第七步：产业链利润流向

根据搜索结果整理：

## 需求来自哪里

## 谁拥有定价权

## 利润流向哪个环节

## 哪个环节壁垒最高

## 直接受益公司

## 间接受益公司

每个结论必须给出处。

无法验证：

写：

证据不足

---

# 第八步：资金验证

分别验证：

## 机构资金

## 主力资金

## 游资资金

## 资金是否一致

无法验证：

写：

无法验证

不得猜测。

---

# 第九步：资金逻辑候选

不要直接下结论。

只能整理候选逻辑。

---

## 候选逻辑A

必须同时具备：

- 市场证据
- 板块证据
- 个股证据
- 产业链证据
- 财报证据

---

## 候选逻辑B

必须同时具备：

- 市场证据
- 板块证据
- 个股证据
- 产业链证据
- 财报证据

---

## 候选逻辑C

必须同时具备：

- 市场证据
- 板块证据
- 个股证据
- 产业链证据
- 财报证据

证据不足：

明确标记。

---

# 第十步：同逻辑公司映射

根据搜索结果整理。

不要预设公司。

分类：

## 同主线公司

## 同产业链公司

## 同题材公司

## 同涨停原因公司

## 上游公司

## 下游公司

## 可比公司

每家公司必须说明：

- 关联依据
- 来源名称
- 来源等级
- 日期
- URL
- 原文摘要

数量不限。

如果搜索结果不足：

写：

来源不足

---

# 输出要求

只输出：

# 搜索资料包

不要输出：

- 投资建议
- 买卖建议
- 推荐股票
- 应该买谁
- 应该卖谁
- 确定性结论

要求：

- 中文输出
- 保留来源名称
- 保留来源等级
- 保留日期
- 保留URL
- 保留原文摘要
- 来源不足明确标注
- 来源存疑明确标注
- 所有结论必须有证据链
- 宁可长一些，不要删除关键来源"""


def build_judge_prompt(stock_name: str, stock_code: str, buy_date: str, buy_times: list[str], search_pack: str) -> str:
    return f"""你是A股短线交易复盘研究员，也是用户的交易教练。

下面是一份资料包。
只能基于资料包分析，不要声称自己联网搜索。
任务：
站在{cn_date(buy_date)}当天A股主线资金视角，复盘用户买入{stock_name}（{stock_code}）的交易是否买对。

用户买入时间：
{chr(10).join(f"- {item}" for item in buy_times)}

核心目标：
用户不想看资料总结。
用户想知道：
1. 这笔交易买对了吗？
2. 买对在哪里？
3. 错在哪里？
4. 如果重来一次，应该买{stock_name}，还是同产业链更强标的？

必须回答：
1. 当天市场主线是什么？
2. {stock_name}被交易的真正题材是什么？
3. 它是主线核心、主线支线、边缘跟风，还是独立炒作？
5. 产业链位置在哪里？
6. 壁垒在哪里？
7. 利润流向哪里？
8. 同题材/同主线公司谁更强？
9. 如果重来一次，优先级排序怎么排？
10. 最终一句话结论。

输出顺序必须是：

一、最终判断
直接回答：
- 买对了吗？
- 买点质量如何？
- 属于主线还是跟风？
- 如果重来一次应该如何交易？

给出综合评分：评分基于是否买对，买点质量，是否主线，相关公司比较等因素综合判断，满分100分。

二、交易逻辑
说明资金为什么买它。

三、产业链位置
用箭头画产业链。

四、壁垒和利润流向
说明它凭什么赚钱，利润是不是主要流向它。

五、相关公司比较
基于资料包中Research Agent搜到的相关公司进行判断。
必须排序，不允许只罗列公司。
格式：
第一名：
第二名：
第三名：

六、如果重来一次
给出明确选择：
- 优先买谁
- {stock_name}排第几
- 为什么

七、一句话结论

写作要求：
- 先结论，后依据。
- 语言要像交易复盘，不像年报总结。
- 不要 JSON。
- 不要写“资料包显示”太多次。
- 不要额外联网。
- 不要安全提示。
- 不要只说“无法判断”，资料不足时也要基于已有信息给出倾向判断。
- 不要长篇介绍公司历史。
- 每一段都要回答“这对交易有什么意义”。

资料包：
{search_pack}"""


def call_doubao_search(api_key: str, prompt: str) -> dict[str, Any]:
    body = {
        "model": doubao_model_name(),
        "input": prompt,
        "tools": [{"type": "web_search"}],
        "thinking": {"type": "enabled"},
        "reasoning": {"effort": "medium"},
    }
    request = urllib.request.Request(
        f"{ark_base_url()}/responses",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = _http_error_body(exc)
        raise FinalWangAgentError(
            "豆包 Research 搜索失败",
            detail=f"Ark HTTP {exc.code}: {exc.reason}. {body_text}".strip(),
            code="doubao_search_http_error",
            status_code=exc.code,
        ) from exc


def call_deepseek(api_key: str, prompt: str) -> dict[str, Any]:
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL).strip().rstrip("/")
    body = {
        "model": judge_model_name("deepseek"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def call_judge_model(api_key: str, prompt: str, provider: str) -> dict[str, Any]:
    if provider == "deepseek":
        return call_deepseek(api_key, prompt)
    raise RuntimeError("Final WANG Agent analysis is configured for DeepSeek only.")


def extract_judge_text(data: dict[str, Any], provider: str) -> str:
    if provider == "deepseek":
        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except Exception:
            return ""
    raise RuntimeError("Final WANG Agent analysis must use DeepSeek.")


def extract_responses_text(data: dict[str, Any]) -> str:
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
    return "\n".join(parts)


def ark_cost(usage: dict[str, Any]) -> dict[str, Any]:
    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    cached_tokens = int(details.get("cached_tokens") or 0)
    billable_input_tokens = max(0, input_tokens - cached_tokens)
    cny = (
        billable_input_tokens * ARK_INPUT_CNY_PER_1M / 1_000_000
        + cached_tokens * ARK_CACHED_INPUT_CNY_PER_1M / 1_000_000
        + output_tokens * ARK_OUTPUT_CNY_PER_1M / 1_000_000
    )
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "billable_input_tokens": billable_input_tokens,
        "output_tokens": output_tokens,
        "cny": round(cny, 6),
    }


def deepseek_cost(usage: dict[str, Any], model: str) -> dict[str, Any]:
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    cached_tokens = int(usage.get("prompt_cache_hit_tokens") or usage.get("input_cache_hit_tokens") or 0)
    billable_input_tokens = max(0, input_tokens - cached_tokens)
    price = DEEPSEEK_PRICES_USD_PER_1M.get(model, DEEPSEEK_PRICES_USD_PER_1M[DEFAULT_DEEPSEEK_MODEL])
    usd = (
        cached_tokens * price["input_cache_hit"] / 1_000_000
        + billable_input_tokens * price["input_cache_miss"] / 1_000_000
        + output_tokens * price["output"] / 1_000_000
    )
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "billable_input_tokens": billable_input_tokens,
        "output_tokens": output_tokens,
        "usd": round(usd, 8),
        "cny": round(usd * USD_CNY, 6),
    }


def judge_cost(usage: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
    if provider == "deepseek":
        return deepseek_cost(usage, model)
    raise RuntimeError("Final WANG Agent analysis must use DeepSeek.")


def cn_date(date_text: str) -> str:
    parsed = datetime.strptime(date_text, "%Y-%m-%d").date()
    return f"{parsed:%Y年%m月%d日}"


def date_window(date_text: str) -> str:
    base = datetime.strptime(date_text, "%Y-%m-%d").date()
    start = base - timedelta(days=2)
    end = base + timedelta(days=2)
    return f"{start:%Y年%m月%d日}至{end:%m月%d日}"


def wang_judge_provider() -> str:
    provider = os.getenv("WANG_JUDGE_PROVIDER", "deepseek").strip().lower()
    if provider != "deepseek":
        raise RuntimeError("Final WANG Agent analysis must use DeepSeek. Set WANG_JUDGE_PROVIDER=deepseek.")
    return "deepseek"


def doubao_model_name() -> str:
    return os.getenv("WANG_DOUBAO_MODEL") or os.getenv("ARK_MODEL") or DEFAULT_ARK_MODEL


def ark_base_url() -> str:
    return (os.getenv("ARK_BASE_URL") or DEFAULT_ARK_BASE_URL).strip().rstrip("/")


def judge_model_name(provider: str) -> str:
    if provider == "deepseek":
        return os.getenv("WANG_JUDGE_MODEL") or os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL
    raise RuntimeError("Final WANG Agent analysis must use DeepSeek.")


def _http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        payload = exc.read().decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""
    return payload[:1200]


def save_deepseek_raw_markdown(answer: str, context: dict[str, Any], trade: dict[str, Any]) -> dict[str, str]:
    run_id = _safe_slug(context.get("_run_id") or datetime.now().strftime("%H%M%S"))
    stock_code = _safe_slug(trade.get("stock_code") or "unknown")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{stamp}_{stock_code}_{run_id}_ds_raw.md"

    desktop_dir = Path(os.getenv(DS_RAW_REPORT_DIR_ENV, "") or (Path.home() / "Desktop" / "AITradingHelper_DS_Reports"))
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_path = desktop_dir / filename
    desktop_path.write_text(answer or "", encoding="utf-8")

    files = {"desktop": str(desktop_path)}
    run_dir_text = str(context.get("_run_dir") or "").strip()
    if run_dir_text:
        run_dir = Path(run_dir_text)
        run_dir.mkdir(parents=True, exist_ok=True)
        ds_path = run_dir / "ds_raw.md"
        agent_path = run_dir / "agent_raw.md"
        ds_path.write_text(answer or "", encoding="utf-8")
        agent_path.write_text(answer or "", encoding="utf-8")
        files["run_dir_ds_raw"] = str(ds_path)
        files["run_dir_agent_raw"] = str(agent_path)
    return files


def _safe_slug(value: Any) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_.-]+", "_", str(value or "").strip())
    return text.strip("_") or "unknown"

def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def trade_input_from_context(context: dict[str, Any]) -> dict[str, Any]:
    company = context.get("company") if isinstance(context.get("company"), dict) else {}
    trade = context.get("trade") if isinstance(context.get("trade"), dict) else {}
    stock_code = str(company.get("code") or "").strip()
    stock_name = str(company.get("name") or stock_code).strip()
    trades = trade.get("trades") if isinstance(trade.get("trades"), list) else []
    buys = [item for item in trades if isinstance(item, dict) and str(item.get("side") or "").lower() == "buy"]
    buy_date = str(trade.get("buy_date") or "").strip()
    buy_times: list[str] = []
    for item in buys:
        date_text = str(item.get("trade_date") or buy_date or "").strip()
        time_text = str(item.get("trade_time") or item.get("time") or "").strip()
        if date_text and time_text:
            buy_times.append(f"{date_text} {time_text}")
        elif date_text:
            buy_times.append(date_text)
    if not buy_date and buy_times:
        buy_date = buy_times[0].split()[0]
    if not buy_times and buy_date:
        buy_times = [buy_date]
    if not stock_code:
        raise RuntimeError("company.code is required for Final WANG Agent")
    if not stock_name:
        stock_name = stock_code
    if not buy_date:
        raise RuntimeError("trade.buy_date or buy trade_date is required for Final WANG Agent")
    return {"stock_name": stock_name, "stock_code": stock_code, "buy_date": buy_date, "buy_times": buy_times}


def usage_token_summary(usage: Any) -> dict[str, int]:
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    return {"input": input_tokens, "output": output_tokens, "total": int(usage.get("total_tokens") or input_tokens + output_tokens)}

