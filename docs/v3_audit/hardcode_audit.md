# Hardcode Audit

## Scope

This document lists hardcoded logic that affects WANG/Public Equity conclusions or final report presentation.

## Model and Mode Defaults

| Location | Hardcode | Effect |
|---|---|---|
| `workbench_agents.py` | `STANDARD_RESEARCH_MODEL = "gpt-4.1"` | Standard mode fixed unless env override. |
| `workbench_agents.py` | `BETTER_RESEARCH_MODEL = "gpt-5.5"` | Better mode fixed unless env override. |
| `workbench_agents.py` | standard mode `json_only` | Removes `deep_memo`; report may look complete without long reasoning. |
| `workbench_agents.py` | better mode `json_memo` | Adds memo but slower. |
| `workbench_agents.py` | token defaults 1400/3200 | Can shape output depth. |

## Market Catalyst Query Hardcodes

`workbench_news.py` uses fixed query patterns:

- recent rise / market hype / 2026
- limit-up / abnormal movement / announcement / institution / research
- capacitor / AI / robot / new energy / 2026
- Tonghuashun / WenCai / Eastmoney / stock forum

Risk:

- biased toward growth/technology themes
- weak for financials, consumer, pharma, cyclicals, utilities, real estate, insurance, shipping
- can bias downstream WANG and Public Equity conclusions

## Industry and Sector Hardcodes

| Location | Hardcode | Effect |
|---|---|---|
| `industry_agent.py` | `SECTOR_PROXY_HINTS` for `600183`, `600584`, `002185` -> `512480` | Only a few semiconductor-related names get sector override. |
| `industry_profiles.py` | default `sector_symbol = "sh000300"` | Missing sector silently becomes broad benchmark. |
| `trade_execution_data.py` | `PEER_HINTS` only for `002491` | Peer analysis is highly incomplete. |
| `stock_resolver.py` | small `KNOWN_CODES` dictionary | Name resolution coverage depends on AkShare fallback. |

## Schema Defaults That Look Like Judgments

`workbench_schema.py` defines defaults:

- `hero.industry_rating = "B"`
- `hero.investment_rating = "B"`
- `moat_radar.company_score = 50`
- `moat_radar.industry_average = 50`
- `expectation_gap.gap_score = 50`
- `action.current_action = "add to watchlist"`
- `trade_review.trade_score = 0`

V3 task book explicitly forbids default `B`, default `50`, default profit flow, default moat score, default logic tree, default peer ranking, default valuation odds.

## Presenter Fallback Hardcodes

`presenter_agent.py` default mode is local mapper because `PRESENTER_AGENT_ENABLED=0`.

Important hardcoded presentation fallbacks:

- hero kicker: "这家公司值得研究吗？"
- default industry/investment rating: `B`
- profit flow title/summary text
- profit flow item defaults: `40 / 35 / 25`
- logic tree certainty defaults: `85, 75, 65...`
- fallback next action text
- fallback newbie summary
- generated claim card confidence: `80, 72, 64...`
- frontend module order: hero, profit_flow, logic_tree, expectation_gap, moat_validation, decision

These make reports feel complete even when upstream data is missing.

## Keyword Tag Rules

`presenter_agent._derive_tags()` hardcodes tags based on substrings:

- 光纤 / 光缆 / 光通信 -> 光纤光缆
- 新能源 -> 新能源概念
- 质押 -> 高质押风险
- 业绩 / 盈利 -> 业绩反转待确认

Risk:

- narrow industry coverage
- false positives from text
- hides whether tags came from WANG/Public Equity or local keyword rules

## Recommended V3 Action

1. Replace default ratings and scores with `missing`.
2. Add `source_trace` for every displayed field.
3. Separate raw research layer from presenter expression layer.
4. Presenter must not synthesize profit flow, moat score, logic tree, peer ranking, valuation odds, or final score.
5. Hardcoded industry hints should move to explicit data-source modules and be marked as `fallback`.
