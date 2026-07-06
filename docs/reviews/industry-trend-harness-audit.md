# Industry Trend Harness Audit

Date: 2026-07-06
Branch: `产业选股`
Commit reviewed: `54d4a84`
Scope: `/industry-trend`, `POST /api/industry-trend`, local Stock Analyze bridge, docs, and tests.

## Findings

### P1: Industry trend bypasses the existing credit system

`trade_review_agent/api/simple_api.py` adds `_create_industry_trend_report`, but the route only calls `_require_user()` before running the local Stock Analyze request. Existing paid/gated generation surfaces consume or reserve credits:

- AI review checks `ensure_feature_credit_available(..., feature="review_report")` and charges on ack.
- Market day checks `ensure_feature_credit_available(..., feature="market_day_report")` and charges on ack.
- Watch plan calls `consume_feature_credit(..., feature="watch_plan")`.
- Auction strength checks and charges with `auction_strength_view`.

If industry trend should be part of the paid product, authenticated users can currently generate unlimited long-form Stock Analyze reports without balance checks or usage records. If this is intended to be a free/internal beta, the spec should say so explicitly and the UI should mark it as beta/free to avoid billing ambiguity.

Recommended decision:

- Product choice A: make `industry_trend` consume one credit after successful generation.
- Product choice B: keep it free temporarily, but document the non-billing policy in the PRD and admin usage expectations.

### P2: Long-running generation is synchronous while comparable report flows are queued

`POST /api/industry-trend` blocks until Stock Analyze returns. The API server is threaded, so this does not freeze the whole backend, but each request can occupy a thread for up to `STOCK_ANALYZE_TIMEOUT_SECONDS` seconds. The current default is 620 seconds.

Market-day reports already use a queued/status pattern with `202` and later acknowledgement. Industry trend may be acceptable as an MVP because the frontend waits for the full result, but the operational risk is visible: browser/proxy timeouts, duplicate submits after refresh, and no resumable status URL.

Recommended decision:

- MVP: keep synchronous, cap concurrent calls later if abuse appears.
- Production: move to queued generation with `run_id`, status polling, persisted result, and optional charge-on-success.

### P2: Frontend build/lint was not verified in this workspace

The current workspace has no `frontend/node_modules`, system `npm` is unavailable, and the bundled Node runtime does not include TypeScript. Python compilation and backend client mock checks passed, but Next.js/TypeScript build and lint did not run.

Before merge, run on a machine with frontend dependencies:

```powershell
cd frontend
npm ci
npm run lint
npm run build
```

### P3: Markdown rendering is intentionally shallow

`frontend/app/industry-trend/page.tsx` renders headings, bullets, numbered lines, and table-like rows with a small custom renderer. It is safe enough for local text because it does not inject HTML, but Markdown tables are displayed line-by-line as `<pre>` rather than as real tables. This is acceptable for MVP but will look rough for long stock ranking tables.

Recommended follow-up:

- Add a small table renderer or use an existing Markdown renderer with sanitization if reports become table-heavy.

## Open Questions

- Should industry trend consume one usage credit, be free during beta, or be admin-only?
- Should Stock Analyze failures refund automatically if credit charging is added?
- Should results be persisted so users can revisit generated reports?
- Should the Stock Analyze bridge be launched manually forever, or should the app eventually manage service health?

## Test Gaps

- No API route-level test for `POST /api/industry-trend` auth, validation, and 502 error mapping.
- No frontend build/lint verification in the current workspace.
- No end-to-end test with a real Stock Analyze server, only mocked client behavior.
- No billing/usage test because the billing policy is undecided.

## Review Summary

The implementation is a reasonable synchronous MVP for a local bridge, and the main correctness path is simple: authenticated input becomes a Stock Analyze prompt, and the returned answer is displayed without HTML injection. The largest unresolved risk is product/business consistency around credits. The second risk is operational polish: synchronous long calls are workable locally but weaker than the existing queued report pattern.
