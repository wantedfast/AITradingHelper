# AI Watch Formal Fix Report - 2026-06-28

## Scope

- Stabilize AI watch-plan generation so it does not inherit the AI review judge model.
- Remove the OCR entry mode from the AI watch-plan frontend input.

## Root Cause

`run_deepseek_json_agent()` used this model fallback order:

`WATCH_DEEPSEEK_MODEL -> WANG_JUDGE_MODEL -> DEEPSEEK_MODEL -> DEFAULT_DEEPSEEK_MODEL`

When `WATCH_DEEPSEEK_MODEL` was unset, AI watch-plan generation used `WANG_JUDGE_MODEL=deepseek-v4-pro`. In local reproduction, that model returned empty or non-JSON output for watch-plan JSON generation, causing `/api/watch/plans` failures.

## Fix

- Changed the DeepSeek JSON agent fallback order to:

`WATCH_DEEPSEEK_MODEL -> DEEPSEEK_MODEL -> DEFAULT_DEEPSEEK_MODEL`

- Changed the default DeepSeek JSON model to `deepseek-chat`.
- Added `.env.example` documentation for `WATCH_DEEPSEEK_MODEL=deepseek-chat`.
- Removed AI watch frontend OCR mode state, upload UI, OCR validation, OCR handler, and related props.

## Verification

- `.\.venv\Scripts\python.exe -m unittest tests.test_watch_deepseek_agent`
  - Result: passed, 2 tests.
- `npm run build` in `frontend`
  - Result: passed, Next.js production build completed.
- Actual local API check:
  - Input: `stock_name=冰轮环境`, `buy_date=23/06/26`, `position=2 成 (20%)`, `buy_price=45.7`
  - Result: generated `plan_id=000811-20260624`, `code=000811`, `name=冰轮环境`, `watch_date=2026-06-24`.

## Notes

Current date parsing treats `23/06/26` as `DD/MM/YY`, which becomes `2026-06-23`.
