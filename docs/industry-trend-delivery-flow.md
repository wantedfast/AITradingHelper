# Industry Trend Delivery Flow

Date: 2026-07-06
Branch: `产业选股`

This document records the harness workflow for the industry trend MVP and the review fix loop that followed it.

## PRD

### Problem

Users want to enter an industry chain or A-share stock and receive a structured industrial-chain analysis in the web app, using the local Stock Analyze capability that already produces higher-quality Codex App output.

### Target User

An A-share retail or semi-professional trader who wants to identify:

- Where a company sits in the industrial chain.
- Which links capture high profit, high barrier, and high growth.
- Whether a stock is a core asset, emotional exposure, seller of tools, or pseudo-core.
- Which related listed companies deserve further research.

### User Flow

1. User starts Stock Analyze locally on port `8750`.
2. User starts AITradingHelper.
3. User opens `/industry-trend`.
4. User enters an industry chain or stock and selects `auto`, `chain`, or `stock`.
5. Frontend calls `POST /api/industry-trend` to create a background job.
6. Backend checks available credits, writes a status record, wraps the input into a `$stock-reverse-engineering` prompt, and posts it to Stock Analyze in a background thread.
7. Frontend polls `status_url`.
8. Backend charges one credit only after successful generation.
9. Frontend displays the full returned analysis and lets the user copy it.

### Acceptance Criteria

- `/industry-trend` is reachable from the home page and sidebar.
- Unauthenticated users are redirected to login.
- Backend rejects empty input with a clear 400 error.
- Backend defaults to `http://127.0.0.1:8750/api/codex`.
- Backend supports `STOCK_ANALYZE_API_URL`, `STOCK_ANALYZE_TIMEOUT_SECONDS`, and `STOCK_ANALYZE_TOKEN`.
- Stock Analyze connection, HTTP, JSON, and empty-answer failures become clear API errors.
- Successful generation consumes one usage credit; failed generation does not.
- The browser does not hold a multi-minute request open while Stock Analyze runs.
- Returned text is displayed without injecting raw HTML.

### Non-Goals

- Do not start Stock Analyze as a child process inside AITradingHelper.
- Do not vendor Stock Analyze or the stock skill into AITradingHelper.
- Do not stream partial output in the MVP.
- Do not build a report history page in the MVP.

## Task Slices

1. Backend bridge
   - Add an industry trend client module.
   - Normalize input type.
   - Build the Stock Analyze prompt.
   - Map local service failures into `StockAnalyzeError`.

2. API route
   - Add `POST /api/industry-trend`.
   - Require auth.
   - Check available credits before enqueue.
   - Return `202` with `run_id/status_url`.

3. Background generation
   - Persist status under `outputs/industry_trend_reports/`.
   - Run Stock Analyze outside the request thread.
   - Charge one credit only after successful generation.
   - Persist clear error status without charging on failure.

4. Frontend route
   - Add `/industry-trend`.
   - Add input form, type toggle, examples, loading state, error state, and result rendering.
   - Poll status until done or error.
   - Add copy-result action.

5. Navigation and docs
   - Add home and sidebar entries.
   - Add `.env.example` knobs.
   - Update README.
   - Add project agent guidance and this delivery record.

6. Verification and review
   - Compile Python changed files.
   - Mock Stock Analyze client call.
   - Review billing, long-running requests, frontend verification, and output rendering risks.
   - Fix review findings and rerun verification.

## Role Review

### Product Reviewer

The MVP satisfies the requested local bridge behavior. Billing is explicit: successful industry trend generation consumes one usage credit, while failed generation is not charged.

### Backend Reviewer

The bridge is small and testable. Generation now runs as a background task with a status URL, avoiding a multi-minute foreground request.

### Frontend Reviewer

The page follows existing visual language and avoids unsafe HTML rendering. The markdown renderer is basic and may not present tables well.

### QA Reviewer

Python compile, targeted pytest, mocked client verification, mocked background task verification, and frontend production build passed.

## Verification Matrix

| Check | Status | Notes |
| --- | --- | --- |
| Python compile | Passed | `python -m py_compile ...` |
| Stock Analyze client mock | Passed | Verified default endpoint and prompt payload |
| Background task mock | Passed | Verified done status, answer persistence, and charge-on-success billing status |
| `git diff --check` | Passed | No whitespace/conflict-marker errors |
| Pytest | Passed | `python -m pytest tests\test_industry_trend_stock_analyze.py` |
| Frontend build | Passed | `npm run build` with vendored Node/npm on this machine |

## Merge Gate

Before merging into `develop`, resolve or explicitly accept any product follow-ups:

- Dedicated history page for generated industry trend reports.
- Manual Stock Analyze startup versus future managed service health.
