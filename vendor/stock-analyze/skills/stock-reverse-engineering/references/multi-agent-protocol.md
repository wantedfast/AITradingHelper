# Multi-Agent Protocol

## Shared Research Board

Maintain these fields throughout the work:

- `input_stocks`: stock names/tickers.
- `current_catalysts`: verified recent events, policies, price moves, orders, filings, product upgrades, supply-demand changes.
- `product_paths`: stock -> real product/material/equipment -> component/system -> final demand.
- `bom_tree`: final product -> first-level components -> second/third-level materials/processes -> A-share-mappable nodes.
- `bottlenecks`: current bottlenecks, bottleneck type, first price response, expansion difficulty, migration path, A-share mapping.
- `profit_flow`: star-ranked nodes and reasons.
- `conflicts`: mismatches between market logic, product exposure, BOM importance, and profit capture.
- `evidence_confidence`: high/medium/low or 待验证.

## Collaboration Rules

1. Capital Logic Analyst and Product Path Mapper start in parallel for each input stock.
2. BOM Chain Analyst can start once a likely final product path exists, but must revise if Product Path Mapper changes the path.
3. Bottleneck Analyst can start once the candidate chain exists, but must challenge BOM Chain Analyst when a scarce node is missing from the BOM.
4. Profit Flow Analyst can start once the candidate chain and bottleneck map exist, but must challenge Bottleneck Analyst when scarcity does not translate into profit capture.
5. Capital Logic Analyst must challenge cases where the market is trading an emotional label that does not match verified product exposure.
6. Product Path Mapper must challenge cases where the input company has only adjacent or weak exposure.
7. Core Asset Judge reads all five research-role outputs, resolves conflicts, and produces the final fund-manager-style judgment.
8. If there is a material conflict, expose it as `争议点/待验证`.

## Capital Logic Analyst

Purpose: identify why funds are trading the input stock now. Separate event-driven, trend-driven, price-driven, localization-driven, and emotional logic.

Output:

```json
{
  "stock": "",
  "炒作逻辑": "",
  "触发事件": "",
  "核心驱动": "",
  "情绪强度": "",
  "证据置信度": ""
}
```

Must not treat concept tags as proof or jump directly to industry-chain winners.

## Product Path Mapper

Purpose: reverse-map each stock to the real product line and final demand. Prefer narrow product lines over broad concepts.

Output:

```json
{
  "stock": "",
  "真实产品线": "",
  "最终产品": "",
  "产品路径": ["个股", "产品/材料", "部件/系统", "最终需求"],
  "核心/边缘判断": "",
  "证据置信度": ""
}
```

Examples:

```text
宏和科技 -> Low-Dk电子布 -> 高端CCL -> 高速PCB -> AI服务器
中际旭创 -> 800G/1.6T光模块 -> AI集群互联 -> AI服务器/AI数据中心
```

## BOM Chain Analyst

Purpose: build the final product's investable BOM until A-share listed companies can be mapped. Include materials, equipment, precision processing, packaging, testing, connectors, consumables, power, cooling, and enabling infrastructure when relevant.

Output a tree and table:

```text
最终产品
├─ 一级部件
│  ├─ 二级材料/工艺
│  └─ A股对应公司
└─ ...
```

| BOM节点 | 上游/中游/下游 | A股公司 | 价值量/趋势 | 证据置信度 |
| --- | --- | --- | --- | --- |

## Profit Flow Analyst

Purpose: determine where industry profit actually flows. Answer who tightens first, who raises price first, who has pricing power, who has the highest earnings elasticity, and who only gains revenue while margin is squeezed.

Use:

```text
★★★★★ 核心瓶颈：供给紧、定价权、利润率扩张
★★★★  强受益：需求清晰且有一定稀缺
★★★   量增：增长明确但定价权有限
★★    主题跟随：收入相关但利润捕获弱
★     伪核心：概念或情绪溢价大于产业利润
```

Push back when a highly traded stock sits in a low-profit or easily substituted node.

## Bottleneck Analyst

Purpose: identify what the industry chain is currently short of, whether the constraint is temporary or structural, who can raise price first, and where the bottleneck may migrate next.

Must answer:

- What is the current tightest node?
- Is the bottleneck caused by technology, certification, equipment lead time, capacity, raw material, customer qualification, patents, yield, or policy?
- Who raises price first when demand increases?
- Who expands capacity slowest, and why?
- Does the bottleneck create margin expansion or only volume growth?
- Where could the next bottleneck move after the current shortage eases?
- Which A-share companies map to each bottleneck node?

Output:

```json
{
  "当前瓶颈": "",
  "瓶颈类型": "",
  "最先涨价": "",
  "扩产难度": "",
  "利润兑现": "",
  "下一阶段瓶颈": "",
  "A股映射": [],
  "证据置信度": ""
}
```

Classify bottlenecks:

```text
结构性瓶颈：技术/认证/良率/专利/客户锁定导致长期紧缺
产能瓶颈：设备交期、扩产周期、资本开支导致中期紧缺
材料瓶颈：资源、化学品、上游材料供应受限
情绪瓶颈：市场短期交易拥挤，但产业供给并不真正紧张
伪瓶颈：概念上稀缺，实际可替代或利润无法留存
```

Push back when a company is called a bottleneck but lacks pricing power, customer lock-in, or capacity scarcity.

## Core Asset Judge / Fund Manager

Purpose: read all five research-role outputs, resolve conflicts, and give the final fund-manager-style judgment. Decide whether each input stock earns industrial profit or mostly emotional premium, and classify it as 情绪龙头 / 产业龙头 / 容量核心 / 卖铲子 / 高弹性 / 补涨 / 伪核心.

Use Three-High scoring:

```text
Core Score = 0.4 * 壁垒 + 0.3 * 利润 + 0.3 * 增长
```

Score 1-10 and use one decimal place. Explain any score above 9 with concrete evidence.

Company schema:

```json
{
  "company": "",
  "产业环节": "",
  "产品": "",
  "行业地位": "",
  "壁垒": 0,
  "利润": 0,
  "增长": 0,
  "综合": 0,
  "标签": ["龙头", "容量核心", "卖铲子", "高壁垒", "国产替代", "高弹性"]
}
```

## Multi-Stock Handling

For multiple stocks:

1. Run Capital Logic Analyst and Product Path Mapper in parallel per stock.
2. Group stocks by final product or industry chain if they converge.
3. Run BOM Chain Analyst, Bottleneck Analyst, and Profit Flow Analyst per distinct final product/chain, with cross-checks.
4. Force Bottleneck Analyst to identify current and next bottlenecks before Core Asset Judge resolves rankings.
5. Run Core Asset Judge across the input stocks first, then optionally compare discovered same-chain core assets.
6. Produce a cross-stock comparison table that ranks the input stocks by default.
