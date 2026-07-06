# Industry Trend Harness Audit

Date: 2026-07-06
Branch: `产业选股`
Scope: `/industry-trend`, `POST /api/industry-trend`, local Stock Analyze bridge, docs, and tests.

## Findings

No open P1/P2 findings remain after the fix loop.

### Fixed: Industry trend now uses the existing credit system

The route now checks available credits before enqueueing a job. The background worker charges one usage credit only after Stock Analyze returns a usable answer. If Stock Analyze fails, returns non-JSON, returns an HTTP error, or returns an empty answer, the task status is `error` and `billing_status` is `not_charged`.

Admin and active membership users follow the existing free-use behavior and receive `admin_free` or `membership_free` billing status.

### Fixed: Long-running generation no longer holds the browser request open

`POST /api/industry-trend` now returns `202` with `run_id/status_url`. Stock Analyze runs in a background thread, writes `report_status.json`, and the frontend polls the status endpoint until `done` or `error`.

### P3: Markdown rendering is intentionally shallow

`frontend/app/industry-trend/page.tsx` renders headings, bullets, numbered lines, and table-like rows with a small custom renderer. It is safe enough for local text because it does not inject HTML, but Markdown tables are displayed line-by-line as `<pre>` rather than as real tables. This is acceptable for MVP but will look rough for long stock ranking tables.

Recommended follow-up:

- Add a small table renderer or use an existing Markdown renderer with sanitization if reports become table-heavy.

## Open Questions

- Should results get a dedicated history page so users can revisit generated reports?
- Should the Stock Analyze bridge be launched manually forever, or should the app eventually manage service health?

## Test Gaps

- No full end-to-end test with a real Stock Analyze server.
- No browser automation test for the polling UI.
- No full billing database integration test for `industry_trend` yet; targeted unit coverage verifies billing status and the mocked charge-on-success path.

## Review Summary

The implementation is now a queued local bridge with explicit charge-on-success behavior. Targeted backend tests and frontend production build pass. Remaining risk is limited to real Stock Analyze end-to-end behavior and deeper billing database integration coverage.
