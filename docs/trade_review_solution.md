# AI 复盘报告解决方案

## 当前生成链路

```text
上传截图/交割单
  -> OCR / AI 识别交易记录
  -> 整理成 TradeRound
  -> 拉行情数据
  -> 并行跑两条主链
       -> Trade Execution 规则层
       -> Workbench 投研链
            -> WANG 研究 agent
            -> Public Equity 研究 agent
  -> Trade Execution LLM 增强层
  -> Workbench 合并统一报告数据
  -> 本地 Presenter Mapper 组装前端展示 JSON
  -> 写入 HTML / JSON
  -> 前端报告页展示
```

## 后端改动

### 1. Presenter AI 默认关闭

文件：

- `trade_review_agent/presenter_agent.py`

之前 Presenter 会再次读取 Workbench 并调用 AI 输出展示 JSON，实测曾单独耗时约 156 秒。

现在默认：

```text
PRESENTER_AGENT_ENABLED=0
```

默认走本地 mapper。需要恢复 AI Presenter 时显式设置：

```powershell
$env:PRESENTER_AGENT_ENABLED="1"
```

### 2. WANG / Public Equity 按档位输出

文件：

- `trade_review_agent/workbench_agents.py`
- `trade_review_agent/workbench_composer.py`
- `trade_review_agent/industry_agent.py`

快速报告：

```text
research_output_mode = json_only
```

只输出前端和 Workbench 需要的结构化 JSON，不输出 `deep_memo`。

更详细的报告：

```text
research_output_mode = json_memo
```

输出结构化 JSON，并附加 `deep_memo`。

Workbench 会记录：

```json
{
  "research_metrics": {
    "wang": {},
    "public_equity": {},
    "wang_output_mode": "json_only",
    "public_equity_output_mode": "json_only"
  }
}
```

其中包含耗时、字符数、估算 token，以及 OpenAI 返回 usage 时的实际 token。

### 3. Trade Execution 增加 LLM 增强层

文件：

- `trade_review_agent/trade_execution_chain.py`
- `trade_review_agent/visual_report.py`

规则层仍然先计算真实事实：

- 买入/卖出日期
- 成交价
- 个股涨跌幅
- 沪深300/ETF 涨跌幅
- 板块涨跌幅
- 相对强弱
- 日内位置
- 卖出后走势

LLM 增强层再结合 Workbench 上下文解释：

- 是否跟随题材
- 是否短线结构合理
- 是否弱势补涨
- 卖点是否偏早
- 下一次确认信号

新增输出：

```text
*.trade_execution_llm_output.json
```

最终增强结果仍写入：

```text
*.trade_execution.json
```

timings 新增：

```json
{
  "trade_execution_llm_seconds": 0
}
```

可通过环境变量关闭：

```powershell
$env:TRADE_EXECUTION_LLM_ENABLED="0"
```

### 4. 复盘生成并行

文件：

- `trade_review_agent/visual_report.py`

已实现：

- Trade Execution 与 Workbench 并行。
- 多个 TradeRound 小并发构建。
- 默认 `REPORT_BUILD_MAX_WORKERS=2`。
- 输出 manifest 顺序保持稳定。
- first aliases 仍指向第一份报告。

### 5. 行情复用与预取

文件：

- `trade_review_agent/trade_execution_chain.py`
- `trade_review_agent/trade_execution_data.py`
- `trade_review_agent/execution_structurer.py`

Trade Execution 可以接收 prefetched stock / benchmark / sector quotes，避免同一轮报告重复拉行情。

prefetch 覆盖不足时会回退到 provider 拉取。

### 6. AI 盯盘行情并行

文件：

- `trade_review_agent/watch_agent.py`

`build_watch_plan` 中并行获取：

- stock
- 沪深300
- 上证指数
- sector

不改变前端调用协议。

## 前端改动

### 1. 报告生成模式选择

文件：

- `frontend/app/review/page.tsx`
- `frontend/app/globals.css`

上传后展示两个按钮：

- 快速报告
- 更详细的报告

提交参数仍是：

```text
research_model_tier=standard | better
```

### 2. 买卖点卡片去重

文件：

- `frontend/app/review/report/[id]/page.tsx`
- `frontend/app/globals.css`

当前展示：

- 买点一块功能卡
- 卖点一块功能卡
- 下次执行规则单独展示

避免重复展示相同的买卖点结论。

### 3. 首屏 fallback 修复

文件：

- `trade_review_agent/presenter_agent.py`

旧 cache 里如果有 `hero.claims=["结论待验证"]` 或 `hero.tags=["待验证"]`，但 memo / market_hype_reason 有有效内容，Presenter 会跳过占位字段，从 memo 和上下文恢复：

- 一句话结论
- 光纤光缆
- 新能源概念
- 高质押风险
- 业绩反转待确认

## 实测数据

同一张本地截图测试：

### 快速报告 JSON-only

```text
完整生成：约 50 秒
Workbench agents：18.11 秒
WANG：7.06 秒，实际 token 3293，输出 token 897
Public Equity：8.42 秒，实际 token 3607，输出 token 1135
deep_memo：无
```

### 更详细报告 JSON+memo

```text
完整生成：约 82 秒
Workbench agents：56.91 秒
WANG：42.97 秒，实际 token 5296，输出 token 2598
Public Equity：47.68 秒，实际 token 5795，输出 token 3022
deep_memo：有
```

### Presenter 优化前后

```text
优化前 Presenter AI：约 156 秒
优化后本地 Presenter：约 0.01 秒
```

## 重要环境变量

```powershell
PRESENTER_AGENT_ENABLED=0
TRADE_EXECUTION_LLM_ENABLED=1
TRADE_EXECUTION_LLM_MAX_OUTPUT_TOKENS=1800
WORKBENCH_FAST_MAX_OUTPUT_TOKENS=1400
WORKBENCH_DETAIL_MAX_OUTPUT_TOKENS=3200
REPORT_BUILD_MAX_WORKERS=2
WORKBENCH_AGENT_REFRESH=1
INDUSTRY_AGENT_REFRESH=1
```

