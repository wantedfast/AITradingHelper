# Fake-AI Audit

## Definition

Fake-AI risk means the final report appears to contain AI research conclusions, but the value actually came from:

- template text
- default schema values
- hardcoded fallback
- local mapper logic
- keyword rules
- missing data displayed as polished analysis

## Where Fake-AI Risk Appears

### 1. Presenter default mapper

The Presenter Agent is disabled by default. The system uses `build_presenter_fallback_data()` to create final display JSON.

This is acceptable for formatting, but risky when it creates research-looking fields.

High-risk generated fields:

- `profit_flow.items`
- `logic_tree`
- `moat.items`
- `claim_cards`
- `evidence_blocks`
- `newbie_summary`
- `presenter_copy`
- `frontend_modules`

### 2. Default ratings and scores

Schema defaults include:

- industry rating `B`
- investment rating `B`
- moat score `50`
- expectation gap score `50`

These are not missing indicators. They are numeric/letter judgments. V3 should replace them with `missing`.

### 3. Profit flow fallback

If WANG does not produce profit flow items, presenter creates synthetic items with fixed shares.

Risk:

```text
missing profit-flow evidence
  -> presenter fallback
  -> chart with segment names and percentages
  -> user perceives real industry analysis
```

This is the strongest fake-AI risk in the current product.

### 4. Logic tree fallback

If WANG does not produce logic tree, presenter creates nodes from profile/default values with decreasing certainty.

Risk:

```text
missing logic tree
  -> deterministic fallback certainty
  -> user sees structured causal chain
```

### 5. Financial validation without financial data

Public Equity receives financial fields as pending/missing. It can still produce:

- financial validation
- valuation odds
- expectation gap
- investment rating

These are LLM hypotheses, not verified financial conclusions.

### 6. Peer ranking without peer data

WANG can produce `peer_ranking`, but current WANG input does not include a real peer snapshot or peer financials. Any ranking is primarily model prior unless supported by Market Catalyst text.

### 7. Better-choice answer is not yet real

Current system has Trade Execution peer recommendation logic, but WANG/Public Equity do not jointly produce a real "if replayed, buy whom" answer. V3 requires a dedicated Better Opportunity Agent.

## Fake-AI Classification

| Field/group | Current risk | Reason |
|---|---:|---|
| `profit_flow.items/share_pct` | High | Can be LLM-estimated or presenter-generated without data. |
| `logic_tree.certainty_pct` | High | Can be LLM-estimated or fallback-generated. |
| `moat_radar.company_score` | High | No real scoring data. |
| `investment_rating` | High | No financial/valuation engine. |
| `valuation_odds` | High | No valuation inputs. |
| `financial_validation` | High | Financial inputs missing. |
| `peer_ranking` | High | No peer data in WANG input. |
| `claim_cards` | High | Presenter expression layer. |
| `evidence_blocks` | Medium | Built from available lists, not necessarily raw evidence. |
| `market_hype_reason` | Medium | Can be web-backed via Market Catalyst, but is still compressed LLM summary. |
| `trade.return_pct` | Low | Real trade calculation. |
| buy-day stock/sector/benchmark pct | Low/Medium | Real quotes if symbol/source is correct. |

## V3 Rule

Presenter must only format and render. It must not create research conclusions.

Allowed Presenter operations:

- rename fields
- sort modules
- truncate copy
- format lists
- choose layout

Forbidden Presenter operations:

- invent profit-flow items
- invent logic-tree nodes
- invent ratings
- invent score
- invent better choice
- invent valuation odds
- invent peer ranking

Every final-answer field should include source trace:

```json
{
  "ai_final_answer.better_choice": {
    "source": "missing",
    "reason": "Better Opportunity Agent not available"
  }
}
```
