# Agent Data Sufficiency Audit

## Purpose

This document checks whether the current agent inputs are sufficient to support YingHang V3 final-answer fields.

V3 final answer target:

```json
{
  "ai_score": 84,
  "verdict": "",
  "better_choice": "",
  "main_reason": "",
  "mistake_source": "",
  "next_action": ""
}
```

## Current Data Inventory

| Data category | Available now | Sufficiency |
|---|---|---|
| Uploaded trade facts | Yes | Sufficient for trade reconstruction. |
| Stock daily quotes | Yes | Sufficient for basic execution facts. |
| Benchmark daily quotes | Yes | Sufficient for simple relative strength. |
| Sector quotes | Partial | Depends on correct `sector_symbol`. |
| Market catalyst/news | Partial | LLM summary, not stored raw source set. |
| Financial statements | No | Insufficient. |
| Valuation metrics | No | Insufficient. |
| Peer list | Partial/hardcoded | Insufficient. |
| Peer quotes | Partial in Trade Execution | Not available to WANG/Public as structured input. |
| Peer fundamentals | No | Insufficient. |
| Industry taxonomy | No | Insufficient. |
| Source trace | No | Insufficient. |

## Sufficiency by V3 Question

### 1. "我买对了吗？"

Current data:

- trade return
- buy/sell local execution analysis
- WANG industry hypothesis
- Public Equity investment hypothesis

Status: Partial.

Missing:

- objective thesis correctness criteria
- company quality validation
- better opportunity comparison

### 2. "为什么赚钱？"

Current data:

- buy-day market/sector/stock movement
- Market Catalyst summary
- LLM market narrative

Status: Partial.

Missing:

- attribution across market/sector/company/event
- post-buy catalyst timeline
- volume/liquidity regime

### 3. "为什么亏钱？"

Current data:

- execution facts
- return/drawdown
- LLM risk narrative

Status: Partial.

Missing:

- thesis invalidation timeline
- sector/peer post-trade comparison
- objective mistake taxonomy

### 4. "我真正买到了什么逻辑？"

Current data:

- Market Catalyst summary
- WANG `theme`, `traded_business_line`, `profit_flow`

Status: Medium/Partial.

Risk:

- Mostly LLM inference unless catalyst source is strong.

### 5. "如果重来一次我应该买谁？"

Current data:

- WANG `peer_ranking` from LLM
- Trade Execution peer hints for a very small subset

Status: Insufficient.

Missing:

- Better Opportunity Agent
- peer universe
- peer market strength
- peer financials
- peer valuation
- confidence/source trace

### 6. "我的问题是选股还是执行？"

Current data:

- execution analysis exists
- WANG/Public can infer thesis/company quality

Status: Partial.

Missing:

- explicit decision framework combining thesis quality and execution quality
- Better Opportunity comparison
- source trace for mistake diagnosis

### 7. "下次应该怎么做？"

Current data:

- Trade Execution next-time rules
- Public Equity action suggestions

Status: Partial.

Missing:

- coach-level synthesis
- rule priority
- correct/wrong decision examples
- user-facing concise answer

## Sufficiency by Agent

### Market Scout Agent

Current equivalent: `workbench_news.build_market_catalyst_context`.

Insufficient because it outputs a compact LLM summary, not a structured fact package.

Needs:

- raw source list
- source quality
- event dates
- catalyst confidence
- sector strength
- peer snapshot

### WANG Industry Agent

Current input is sufficient for hypothesis generation, not for verified industry research.

Needs:

- industry taxonomy
- peer universe
- sector-specific KPI facts
- verified value-chain data
- source trace for each conclusion

### Public Equity Agent

Current input is insufficient for company-quality conclusions.

Needs:

- actual financials
- valuation
- consensus/expectation proxy
- debt/balance-sheet risk
- peer valuation/fundamentals

### Better Opportunity Agent

Not implemented.

Needs:

- Market Scout peer snapshot
- WANG peer industry position
- Public Equity quality/valuation
- Trade Execution timing facts

### Trade Coach Agent

Not implemented as V3 final coach.

Needs:

- execution diagnosis
- thesis diagnosis
- better opportunity diagnosis
- final answer schema

## Recommended Source Trace Values

Use the task-book labels strictly:

- `real_data`
- `llm`
- `fallback`
- `hardcode`
- `missing`

Recommended extension:

- `llm_low_confidence`
- `llm_pending_verification`
- `fallback_display_only`

## Blocking Rules for V3

1. Do not produce `better_choice` without peer snapshot.
2. Do not produce `valuation_odds` without valuation data.
3. Do not produce `financial_validation` as verified unless financial data exists.
4. Do not produce `moat_score` without scoring evidence.
5. Do not produce final `ai_score` from default `B/50` fields.
6. Do not let Presenter generate research conclusions.
