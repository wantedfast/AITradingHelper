# Agent Instructions

## Project Purpose

AITradingHelper is a local web app for A-share trade review, watch plans, market-day reports, auction-strength selection, and industry trend analysis.

## Stack

- Backend: Python HTTP server in `trade_review_agent/api/simple_api.py`.
- Frontend: Next.js app under `frontend/`.
- Tests: pytest under `tests/`.
- Local runner: `start-local.ps1`.

## Commands

- Start locally: `powershell -ExecutionPolicy Bypass -File .\start-local.ps1`
- Backend health: `http://127.0.0.1:8600/api/health`
- Frontend: `http://127.0.0.1:3000/`
- Python tests: `python -m pytest`
- Frontend check: run from `frontend/` with the available Node runtime: `npm run lint` if dependencies are installed.

## Directory Map

- `trade_review_agent/api/`: HTTP API routes.
- `trade_review_agent/industry_trend/`: local Stock Analyze integration.
- `vendor/stock-analyze/`: vendored local Stock Analyze app server and `stock-reverse-engineering` skill used by `/industry-trend`.
- `trade_review_agent/review/`: report generation agents.
- `trade_review_agent/watch/`: watch-plan and alert logic.
- `trade_review_agent/market/`: market data helpers.
- `frontend/app/`: Next.js routes.
- `frontend/components/`: shared UI components.
- `docs/`: operational notes.
- `spec/`: product specs and acceptance criteria.
- `tests/`: regression tests.

## Coding Conventions

- Keep backend route handlers thin; put reusable logic in domain modules.
- Use environment variables for local service URLs and timeouts.
- Keep long-running AI calls explicit and return clear setup errors.
- Do not hardcode user-specific paths.

## Testing Policy

- Add focused pytest coverage for backend integration helpers.
- For frontend-only changes, run TypeScript or lint checks when dependencies are available.
- When local external services are required, document the startup command and test with mocks where possible.

## Definition of Done

- Feature has a reachable UI route.
- Backend API has clear errors and local configuration knobs.
- Tests cover prompt construction and client failure modes.
- README or spec explains how to run required local services.
