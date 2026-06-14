# YingHang V3 Integration Checklist

This checklist is the Integration QA gate for the V3 answer-first contract. It is
deliberately independent of network access, OpenAI credentials, pandas, and market
data providers.

## Runbook

Run validator self-tests only:

```powershell
python -m trade_review_agent.validate_v3_contracts --self-test --skip-source-audit
```

Run static production guards:

```powershell
python -m trade_review_agent.validate_v3_contracts
```

Validate a generated V3 workbench artifact:

```powershell
python -m trade_review_agent.validate_v3_contracts `
  --payload path\to\research_workbench_data.json
```

Compare a Presenter artifact with its upstream workbench artifact:

```powershell
python -m trade_review_agent.validate_v3_contracts `
  --payload path\to\research_workbench_data.json `
  --presenter-payload path\to\research_presenter_data.json
```

Exit code `0` means all enabled checks passed. Exit code `1` means at least one
contract violation was found.

## Four-Layer Schema

- [ ] Top-level `ai_final_answer` exists and is an object.
- [ ] Top-level `answer_evidence` exists and is an object.
- [ ] Top-level `research_layers` exists and is an object.
- [ ] Top-level `source_trace` exists and is an object.
- [ ] `ai_final_answer` contains `score`, `verdict`, `better_choice`,
      `main_reason`, `mistake_source`, and `next_action`.
- [ ] `answer_evidence` contains `why_stock_moved`, `investment_thesis`,
      `better_candidates`, `mistake_diagnosis`, and `future_rules`.
- [ ] `research_layers` contains `market_scout`, `wang_industry`,
      `public_equity`, and `trade_execution`.
- [ ] Missing agents retain their layer as an empty object instead of deleting
      the layer or substituting a fabricated report.

## Source Trace

- [ ] Every trace entry is an object with a `source` property.
- [ ] `source` is exactly one of `llm`, `real_data`, `fallback`, `hardcode`, or
      `missing`.
- [ ] Every final-answer field has a trace entry.
- [ ] Every answer-evidence section has a trace entry.
- [ ] Every research layer has a trace entry.
- [ ] Every populated leaf emitted by a research agent has a trace entry.
- [ ] Presenter preserves upstream provenance and never upgrades `missing` or
      `fallback` to `llm` or `real_data`.
- [ ] Optional trace `detail` explains material limitations, such as missing
      structured financial statements or unverified peer data.

## Missing Behavior

- [ ] Missing scalar conclusions use `null`, `missing`, or
      `pending verification`.
- [ ] Missing collections use empty objects/lists.
- [ ] A trace marked `missing` never accompanies a concrete-looking conclusion.
- [ ] A trace marked `llm` or `real_data` never accompanies an empty value.
- [ ] Missing WANG data does not create a profit-flow graph, moat score, logic
      tree, peer ranking, or industry rating.
- [ ] Missing Public Equity data does not create valuation odds, quality score,
      expectation-gap score, or financial conclusions.
- [ ] Missing Better Opportunity data leaves `better_choice` and
      `better_candidates` missing/empty.
- [ ] Missing Trade Coach data leaves final score, verdict, diagnosis, and next
      action missing.

## Forbidden Defaults

- [ ] No schema, composer, Presenter, renderer, or adapter defaults a rating to
      `B`.
- [ ] No schema, composer, Presenter, renderer, or adapter defaults a score to
      `50`.
- [ ] No deterministic fallback creates profit-flow percentages.
- [ ] No deterministic fallback creates moat scores or moat dimensions.
- [ ] No deterministic fallback creates logic-tree nodes or certainty scores.
- [ ] No deterministic fallback creates peer rankings.
- [ ] No deterministic fallback creates valuation odds.
- [ ] A genuine model/data value of `B` or `50` is accepted only when its exact
      field path has `llm` or `real_data` provenance.

## Presenter Boundary

- [ ] Presenter accepts completed upstream contracts and only formats,
      aggregates, orders, and renders them.
- [ ] Presenter does not call an LLM to produce investment conclusions.
- [ ] Presenter does not derive ratings, scores, confidence percentages, claims,
      actions, or recommendations.
- [ ] Presenter does not generate profit-flow items.
- [ ] Presenter does not generate logic-tree nodes.
- [ ] Presenter does not generate moat dimensions.
- [ ] Presenter does not rewrite `source_trace`.
- [ ] Upstream and Presenter artifacts pass `--presenter-payload` comparison for
      protected fields.

## Pipeline Integration

- [ ] Market Scout emits facts only and never emits an investment verdict.
- [ ] WANG consumes Market Scout output and writes only
      `research_layers.wang_industry`.
- [ ] Public Equity consumes WANG output and writes only
      `research_layers.public_equity`.
- [ ] Better Opportunity consumes Scout/WANG/Public Equity and populates
      `answer_evidence.better_candidates`.
- [ ] Trade Coach consumes Trade Execution and all research outputs, then owns
      `ai_final_answer`.
- [ ] The pipeline order is Scout -> WANG -> Public Equity -> Better Opportunity
      -> Trade Coach -> Presenter.
- [ ] Agent failures are visible in errors/trace and do not silently become
      polished conclusions.

## Expected Failures Before V3 Completion

The current pre-integration implementation is expected to fail the static source
audit in `presenter_agent.py` because it still:

- defaults industry and investment ratings to `B`;
- defaults expectation-gap and logic-tree values to `50`;
- creates fixed profit-flow shares such as `40/35/25`;
- creates fallback logic-tree nodes and certainty percentages;
- derives moat and presentation conclusions when upstream research is absent.

During staged integration, `ai_final_answer` may legitimately remain `missing`
until Better Opportunity and Trade Coach are connected. That state is valid only
when the matching `source_trace` entries are also `missing`.

## Release Gate

- [ ] Validator self-tests pass.
- [ ] Static source audit passes with no suppression.
- [ ] At least one complete real report passes payload validation.
- [ ] One missing-news fixture passes without fabricated catalyst conclusions.
- [ ] One missing-financials fixture passes without valuation/quality fabrication.
- [ ] One failed-agent fixture passes with explicit `missing` provenance.
- [ ] One Presenter comparison passes without protected-field differences.
- [ ] A reviewer can answer the five homepage questions from Screen 1 within
      30 seconds.
