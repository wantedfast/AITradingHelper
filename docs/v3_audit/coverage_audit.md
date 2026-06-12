# Coverage Audit

## Scope

This audit checks whether current WANG/Public Equity coverage is broad enough for YingHang V3.

## Current Coverage Summary

The current system can generate a report for many A-share trades, but coverage is often syntactic rather than evidence-complete.

It has:

- trade facts
- basic K-line/benchmark/sector quote summaries
- LLM market-catalyst summary
- LLM industry and equity research JSON

It lacks:

- structured financials
- structured valuation data
- peer fundamentals
- peer valuation comparison
- verified industry taxonomy
- sector-specific KPI library
- source-level news/citation storage
- final-answer source trace

## Industry Coverage

### Strongest current coverage

The current flow is best suited to narrative-driven sectors:

- AI themes
- semiconductors
- electronics
- new energy
- robotics
- communication/light communication
- event-driven concept trades

Reason:

- Market Catalyst queries include technology/growth theme hints.
- LLMs can infer narrative logic from company name and catalyst text.

### Weak coverage

The current flow is weak for:

- banks
- insurance
- brokers
- real estate
- utilities
- coal/oil/metals/cyclicals
- pharma with clinical/regulatory data
- consumer staples
- shipping/transport
- agriculture

Reason:

- no sector-specific KPI extraction
- no balance-sheet/valuation model
- no commodity/macro data
- no regulatory/clinical pipeline data
- no consensus expectation data

## Field Coverage

| Field group | Coverage | Notes |
|---|---|---|
| Trade facts | Good | Based on uploaded trades. |
| Buy/sell execution facts | Medium/Good | Quote-driven, separate Trade Execution chain. |
| Market theme | Medium | Web-backed Market Catalyst if available, but compressed. |
| Industry structure | Medium/Low | Mostly LLM inference. |
| Profit flow | Low | No profit-pool data. |
| Moat radar | Low | No objective moat scoring data. |
| Public equity quality | Low | No financial statements. |
| Financial validation | Low | Inputs are `pending fetch`. |
| Valuation odds | Low | No valuation data. |
| Peer ranking | Low | No real peer data in WANG/Public input. |
| Better opportunity | Missing | Dedicated agent not implemented. |
| Trade coaching answer | Missing/Partial | Current execution advice exists, but not V3 final coach. |
| Source trace | Missing | Not implemented. |

## Coverage Failure Modes

1. A report is always generated because fallback/defaults fill gaps.
2. Missing data can become polished research language.
3. Non-growth industries receive generic equity analysis.
4. Sector symbol errors can contaminate market context.
5. Peer recommendations are narrow and sometimes hardcoded in Trade Execution, not research-wide.

## V3 Required Coverage Improvements

### Market Scout Agent

Should output:

- market theme
- catalyst
- industry news
- sector strength
- peer snapshot
- raw source summaries
- source quality

### WANG Industry Agent

Should only reason over Market Scout facts and mark:

- `llm`
- `real_data`
- `missing`

### Public Equity Agent

Needs real inputs:

- revenue growth
- profit growth
- margin
- PE/PB/EV metrics
- valuation percentile
- consensus or market expectation proxy
- company risk data

### Better Opportunity Agent

Needs:

- same-industry peer list
- peer fundamentals
- peer market strength
- peer moat comparison
- confidence and missing-data disclosure

### Trade Coach Agent

Needs:

- Trade Execution facts
- WANG research layer
- Public Equity research layer
- Better Opportunity output

It should produce V3 answer-first fields:

- bought right or wrong
- why made/lost money
- true thesis bought
- better candidate
- mistake source
- future rules

## V3 Coverage Gate

A final answer field should be blocked or marked `missing` if required coverage is absent.

Example:

```json
{
  "ai_final_answer.better_choice": {
    "value": "missing",
    "source": "missing",
    "required_inputs_missing": ["peer_snapshot", "peer_fundamentals", "peer_valuation"]
  }
}
```
