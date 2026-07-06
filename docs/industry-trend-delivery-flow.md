# Industry Trend Delivery Flow

Date: 2026-07-06
Branch: `产业选股`

This document backfills the harness workflow for the industry trend MVP after implementation, so future agents can review and continue the work without reconstructing intent from the diff.

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
5. Frontend calls `POST /api/industry-trend`.
6. Backend wraps the input into a `$stock-reverse-engineering` prompt and posts it to Stock Analyze.
7. Frontend displays the full returned analysis and lets the user copy it.

### Acceptance Criteria

- `/industry-trend` is reachable from the home page and sidebar.
- Unauthenticated users are redirected to login.
- Backend rejects empty input with a clear 400 error.
- Backend defaults to `http://127.0.0.1:8750/api/codex`.
- Backend supports `STOCK_ANALYZE_API_URL`, `STOCK_ANALYZE_TIMEOUT_SECONDS`, and `STOCK_ANALYZE_TOKEN`.
- Stock Analyze connection, HTTP, JSON, and empty-answer failures become clear API errors.
- Returned text is displayed without injecting raw HTML.
- README explains the required local Stock Analyze startup command.

### Non-Goals

- Do not start Stock Analyze as a child process inside AITradingHelper.
- Do not vendor Stock Analyze or the stock skill into AITradingHelper.
- Do not stream partial output in the MVP.
- Do not persist generated industry trend reports in the MVP.

## Task Slices

1. Backend bridge
   - Add an industry trend client module.
   - Normalize input type.
   - Build the Stock Analyze prompt.
   - Map local service failures into `StockAnalyzeError`.

2. API route
   - Add `POST /api/industry-trend`.
   - Require auth.
   - Read JSON payload.
   - Return Stock Analyze result or standardized API error.

3. Frontend route
   - Add `/industry-trend`.
   - Add input form, type toggle, examples, loading state, error state, and result rendering.
   - Add copy-result action.

4. Navigation and docs
   - Add home and sidebar entries.
   - Add `.env.example` knobs.
   - Update README.
   - Add project agent guidance and this delivery record.

5. Verification and review
   - Compile Python changed files.
   - Mock Stock Analyze client call.
   - Review billing, long-running requests, frontend verification, and output rendering risks.

## Role Review

### Product Reviewer

The MVP satisfies the requested local bridge behavior. The unresolved product decision is billing: current implementation requires login but does not consume usage credits.

### Backend Reviewer

The bridge is small and testable. The API error mapping is consistent with local-service failures. The biggest backend tradeoff is the synchronous 620-second request window.

### Frontend Reviewer

The page follows existing visual language and avoids unsafe HTML rendering. The markdown renderer is basic and may not present tables well.

### QA Reviewer

Python compile and mocked client verification passed. Full pytest and frontend build/lint were not available in the current workspace and must be run before merge on a dependency-complete machine.

## Verification Matrix

| Check | Status | Notes |
| --- | --- | --- |
| Python compile | Passed | `python -m py_compile ...` |
| Stock Analyze client mock | Passed | Verified default endpoint and prompt payload |
| `git diff --check` | Passed | No whitespace/conflict-marker errors |
| Pytest | Blocked | Current Python environment lacks `pytest` |
| Frontend lint/build | Blocked | No `frontend/node_modules`, no system `npm`, bundled Node lacks TypeScript |

## Merge Gate

Before merging into `develop`, resolve or explicitly accept:

- Billing policy for industry trend usage.
- Whether synchronous generation is acceptable for the first release.
- Frontend build/lint result on a machine with dependencies installed.
