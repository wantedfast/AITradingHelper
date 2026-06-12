# V3 Cross-Agent Coverage Audit

## Remediation Status - 2026-06-12

- **P0 fixed:** Market Scout and Trade Execution now inherit field-level provenance instead of defaulting mixed content to `real_data`.
- **P0 contained:** Public Equity now clears unsupported rating, financial validation, valuation odds, and expectation-gap score when verified inputs are absent. Original LLM text is retained only as an explicit hypothesis.
- **P1 partially fixed:** verified Trade Execution peer returns now feed `peer_snapshot.metrics`; Better Opportunity remains `missing` when no verified peer quote rows exist.
- **Second batch complete:** WANG unsupported numeric fields are now gated and moved to hypotheses; structured catalyst/news facts retain `fact/date/source/source_type`.
- **Still open after batch two:** raw financial/valuation providers, calibrated WANG datasets, industry-specific KPI gates, and end-user provenance display.

Implementation evidence:

- `v3_market_scout.py:23`
- `v3_pipeline.py:93`
- `workbench_agents.py:902-1025`
- `peer_snapshot.py:9`
- `visual_report.py:469-518`
- `validate_v3_contracts.py:364`

审计日期：2026-06-12

范围：Market Scout -> WANG -> Public Equity -> Better Opportunity -> Trade Execution -> Trade Coach -> Presenter/Frontend

性质：只审查当前代码，不假设 Prompt 中要求的数据真实存在。

## Executive Finding

当前链路已经具备 V3 结构，但尚未具备 V3 数据覆盖。

最重要的结论：

1. 真实行情只稳定到达 Trade Execution；没有以结构化行情事实进入 WANG/Public Equity。
2. 财务与估值输入仍是占位值，因此 Public Equity 的财务、估值和评级不是数据验证结论。
3. V3 `peer_snapshot` 没有生产数据源，Better Opportunity 在正常主链中预计长期为 `missing`。
4. 新闻先被旧 Market Catalyst LLM 压缩成文本，再因 V3 只接受对象列表而大量丢失。
5. `source_trace` 存在来源洗白，不能作为当前结论真实性证明。

## End-to-End Coverage

| 数据类型 | 生产源 | 到达 WANG | 到达 Public | 到达 Better | 到达 Coach | 结论 |
|---|---|---:|---:|---:|---:|---|
| 交割单事实 | 上传文件 | 是 | 是 | 否 | 经 Execution 到达 | 可用 |
| 个股日线 | 腾讯/AKShare/cache | 20 日摘要字符串 | 20 日摘要字符串 | 否 | 经 Execution 到达 | 部分可用 |
| 大盘日线 | 腾讯/AKShare/cache | 20 日摘要字符串 | 20 日摘要字符串 | 否 | 经 Execution 到达 | 部分可用 |
| 板块日线 | sector symbol 对应行情 | 20 日摘要字符串 | 20 日摘要字符串 | V3 字段为空 | 经 Execution 到达 | 覆盖不稳定 |
| 新闻/公告 | OpenAI Web Search 摘要 | 是，摘要 | 是，摘要 | V3 转换常丢失 | Market Scout 常只剩主题 | 不可审计到原文 |
| 财务报表 | 无 | 否 | 否 | 否 | 否 | 缺失 |
| PE/PB/估值分位 | 无 | 否 | 否 | 否 | 否 | 缺失 |
| 同行行情 | 仅 profile 或单股票硬编码 | 不进入 WANG 结构输入 | 不进入 Public 结构输入 | 不进入 `peer_snapshot` | Execution 内部可见 | 链路断裂 |
| 同行财务/估值 | 无 | 否 | 否 | 否 | 否 | 缺失 |
| 原始新闻 URL/日期 | 未可靠保存 | 否 | 否 | V3 要求但拿不到 | 否 | 缺失 |

## Agent Coverage

### Market Scout

实际主链在 `visual_report.py:374-387` 只为 Better Opportunity 和 Trade Coach 传入 caller，没有传
`market_scout_caller`。因此 V3 Market Scout 走 `v3_market_scout.py:30-35` 的无 LLM 分支，把输入
直接规范化并标为 `real_data`。

但这些输入来自 `_v3_market_facts()`：

- `market_theme` 可能是旧 Market Catalyst 的 LLM 文本：`visual_report.py:425-443`
- `market_catalyst` 是字符串列表，而 `_fact_list()` 只接受 dict：`v3_market_scout.py:148-164`
- `industry_news` 同样常是字符串列表，因此被丢弃
- `sector_strength` 上游没有构造
- `peer_snapshot` 上游没有构造

预计覆盖：

| 字段 | 正常主链覆盖 |
|---|---|
| `market_theme` | 中，但来源误标风险高 |
| `market_catalyst` | 低/常为空 |
| `industry_news` | 低/常为空 |
| `sector_strength` | 极低/常为 `missing` |
| `peer_snapshot` | 极低/常为空 |

### WANG

WANG 得到交割单、行情摘要和旧 Market Catalyst 摘要，但没有：

- 结构化行业分类
- 价值链数据库
- 订单、产能、价格、良率等行业 KPI
- 同行结构化指标
- 利润池数据

其 `profit_flow.share_pct`、`moat_radar`、`logic_tree.certainty_pct` 和 `peer_ranking`
均由 Prompt 要求 LLM 填写，见 `workbench_agents.py:744-780`。

行业覆盖不是“所有行业同等有效”，而是“所有行业都能生成 JSON”。对银行、保险、地产、
医药、周期品、航运、公用事业等依赖专用 KPI 的行业，证据覆盖不足。

### Public Equity

`workbench_context.py:58-65` 明确把财务字段写成：

- `revenue_growth = pending fetch`
- `profit_growth = pending fetch`
- `gross_margin = pending fetch`
- `valuation = pending fetch`
- `pe_ttm = None`
- `pb = None`

但 Prompt 仍要求输出投资评级、财务验证、估值赔率、预期差和仓位含义，
见 `workbench_agents.py:784-824`。因此结构覆盖高，事实覆盖低。

### Better Opportunity

Better Agent 的门槛是合理的：必须存在非目标公司的 `peer_snapshot.metrics`，
见 `v3_better_opportunity_agent.py:61-90`。

问题在于生产链从未构造该数据。Trade Execution 虽抓取部分同行涨跌幅，
但没有映射进 V3 Market Scout 的 `peer_snapshot`。所以：

```text
Trade Execution peer quotes
  -X-> V3 market_facts.peer_snapshot
  -> Better Opportunity: missing comparable peer_snapshot
```

`ai_final_answer.better_choice` 因此预计是高频空字段。

### Trade Execution

真实行情覆盖最好：

- 个股、沪深 300 ETF、板块行情：`trade_execution_data.py:52-144`
- 腾讯主源、AKShare fallback、cache fallback：`trade_execution_data.py:158-196`
- 规则化买卖点、相对强弱：`trade_execution_agent.py:7-39`
- 可选 LLM 增强默认开启：`trade_execution_chain.py:50-96`

但同行覆盖依赖 profile peers，另只有 `002491` 的固定同行表，
见 `trade_execution_data.py:37-49,333-349`。

### Trade Coach

Coach 至少要求：

- 可用的 Execution 判断
- WANG/Public 至少一个非空

见 `v3_trade_coach_agent.py:57-75`。它不要求财务真实性、新闻引用完整性或同行覆盖，
因此在 Better 缺失时仍可输出 score/verdict/main_reason/mistake_source/next_action，
只有 `better_choice` 被强制为 `missing`。

## Industry Coverage Audit

| 行业类型 | 覆盖等级 | 主要缺口 |
|---|---:|---|
| 主题成长、半导体、AI、机器人 | 中 | 仍缺订单/良率/产能/估值；新闻查询偏向这些主题 |
| 普通制造业 | 低 | 无产能利用率、订单、价格、成本曲线 |
| 银行/保险/券商 | 极低 | 无息差、不良率、偿付能力、AUM、资本充足率 |
| 医药/医疗 | 极低 | 无临床阶段、适应症、审批、专利、支付数据 |
| 周期/资源 | 极低 | 无商品价格、库存、成本曲线、产量、运价 |
| 消费 | 极低 | 无渠道、同店、库存、价格带、品牌份额 |
| 地产 | 极低 | 无销售、土储、现金流、债务到期 |
| 公用事业 | 极低 | 无利用小时、电价、燃料成本、装机结构 |

## High-Frequency Missing Fields

按生产代码而非测试样例判断：

1. `research_layers.market_scout.peer_snapshot`：上游无生产者。
2. `answer_evidence.better_candidates`：依赖上述字段。
3. `ai_final_answer.better_choice`：Better 缺失时强制 missing。
4. `research_layers.market_scout.sector_strength`：`_v3_market_facts()` 没有可靠来源。
5. `research_layers.market_scout.market_catalyst`：字符串到 dict contract 不兼容。
6. `research_layers.market_scout.industry_news`：同上。
7. 可信的 `financial_validation`：输入财务为空。
8. 可信的 `valuation_odds`：PE/PB 和估值分位为空。

## Coverage Risk Ranking

| 等级 | 风险 |
|---|---|
| P0 | 财务/估值为空但 Public Equity 仍可给评级和估值结论 |
| P0 | `source_trace` 把混合或 LLM 来源标为 `real_data` |
| P1 | `peer_snapshot` 无生产者，Better Choice 基本不可用 |
| P1 | 新闻字符串与 V3 fact contract 不兼容，催化剂在转换中丢失 |
| P1 | Trade Execution 同行逻辑只对极少股票有预设覆盖 |
| P2 | 所有行业共用单一 Prompt，没有行业 KPI gate |
| P2 | sector symbol 默认/推断错误会污染相对强弱 |
