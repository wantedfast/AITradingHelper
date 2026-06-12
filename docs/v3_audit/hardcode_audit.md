# V3 Cross-Agent Hardcode Audit

审计日期：2026-06-12

## Summary

默认 `B/50` 已从主要 Presenter/Schema 路径清除，但影响结论的硬编码仍然存在。
风险最大的硬编码不再是展示默认值，而是同行名单、同行壁垒分、规则阈值和搜索主题偏置。

## P0/P1 Hardcodes

### 1. 单股票同行宇宙

`trade_execution_data.py:37-49` 只有 `002491` 配置了同行和板块：

- 600487
- 600522
- 600498
- 000070
- 600105

其他股票只能依赖 LLM 生成的 profile peers。没有代码、没有可解析同行时，同行行情为空。

影响：

- Trade Execution peer comparison 覆盖极窄
- Frontend 仍可展示同行观察模块
- 该同行数据没有进入 Better Opportunity

### 2. 固定同行壁垒和利润流代理

`trade_execution_agent.py:292-327` 为上述股票写死：

- 固定 proxy score：28/26/22/15/12
- 固定 moat reason
- 固定 profit-flow reason
- 未命中股票默认 proxy score 10

随后使用：

```text
score = day_pct*0.2 + five_day_pct*0.35 + twenty_day_pct*0.25 + hardcoded_proxy
```

证据：`trade_execution_agent.py:273-288`。

这不是行情事实，也不是 LLM 推理，而是行业特例规则。当前 Pipeline 却将整个
Trade Execution 叶子标成 `real_data`，形成严重误标。

### 3. 行情判断阈值

`trade_execution_agent.py:349-377` 使用固定阈值：

- 相对大盘/板块超过 1%：强
- 低于 -1%：弱
- 日内位置 `<= 0.33` 为低位，`>= 0.67` 为高位
- 卖出后高点超过卖价 3%：卖飞

这些是规则模型，不是 AI。规则本身可以使用，但必须标为 `hardcode` 或 `fallback`，
不能标为 `real_data`。

### 4. Market Catalyst 查询偏置

`workbench_news.py:48-55` 固定使用 2026 和以下主题词：

- 电容
- AI
- 机器人
- 新能源
- 同花顺/问财/东方财富/股吧

影响：

- 科技成长行业召回偏高
- 银行、保险、医药、周期、消费等行业查询不匹配
- 当前日期变化后年份会过期

### 5. 少数证券板块覆盖

`industry_agent.py:24-28` 仅对三个代码写死 `512480`：

- 600183
- 600584
- 002185

`trade_execution_data.py:322-330` 在缺少板块 symbol 时回退 `sh000300`。
这会把“大盘”当作“板块”，污染 `stock_vs_sector`。

## Prompt-Enforced Numeric Fabrication Risk

虽然代码不再给默认 50，但 Prompt 强制 LLM 输出大量没有数据基础的数字：

| 字段 | Prompt 位置 | 数据基础 |
|---|---|---|
| `profit_flow.items.share_pct` | `workbench_agents.py:760-765` | 无利润池数据 |
| `moat_radar.company_score` | `workbench_agents.py:766-771` | 无评分模型 |
| `moat_radar.industry_average` | 同上 | 无行业样本 |
| `logic_tree.certainty_pct` | `workbench_agents.py:772` | 无概率校准 |
| `expectation_gap.gap_score` | `workbench_agents.py:797-803` | 无一致预期数据 |
| `risks.impact_pct` | `workbench_agents.py:804-806` | 无情景模型 |

这些值虽然来源是 LLM，不属于字面 hardcode，但结构模板强迫模型“填一个数”，
属于 template-induced pseudo quantification。

## Model and Feature Defaults

| 位置 | 默认值 | 风险 |
|---|---|---|
| `workbench_agents.py:12-13` | `gpt-4.1`, `gpt-5.5` | 模型版本固定 |
| `workbench_agents.py:827-834` | 1400/3200 tokens | 输出深度受固定预算影响 |
| `workbench_news.py:8,37-45` | gpt-4.1 / 900 tokens | 新闻压缩可能截断 |
| `trade_execution_chain.py:95-104` | LLM 增强默认开启 / 1800 tokens | 混合来源默认发生 |
| `presenter_agent.py:759-767` | Presenter LLM 默认关闭 | 当前主要为规则映射 |

## Frontend Template/Fallback

Frontend 不再制造评分，但仍会把同行行情 fallback rows 转换成“同行强者观察”，并补入：

- 推荐理由待补充
- 壁垒理由待补充
- 利润流向理由待补充
- 保守占位风险

证据：`frontend/app/review/report/[id]/page.tsx:1206-1221`。

这些文本明确写“待补充”，风险低于旧版伪结论；但模块标题仍可能让用户把普通行情排名
理解为 Better Opportunity 结论。

## Source Classification Required

| 内容 | 正确 source |
|---|---|
| 腾讯/AKShare 原始价格 | `real_data` |
| 固定 1%/3%/0.33/0.67 判断 | `hardcode` |
| 固定同行 proxy score/reason | `hardcode` |
| cache 行情 | `fallback` 或 `real_data` + stale metadata |
| WANG/Public 输出 | `llm` |
| Market Catalyst Web 摘要 | `llm` |
| Presenter “待验证”文案 | `fallback` |
| 缺失字段 | `missing` |

## Risk Ranking

1. **P0**：固定同行 moat/profit proxy 被 Pipeline 洗成 `real_data`。
2. **P1**：单股票同行硬编码导致少数行业特例实现。
3. **P1**：Prompt 强制无证据数字化评分。
4. **P1**：板块缺失回退沪深大盘，可能产生错误板块结论。
5. **P2**：固定科技主题新闻查询造成行业偏置。
6. **P3**：Presenter/Frontend 的“待验证”展示模板，虽不造结论但需显式标来源。
