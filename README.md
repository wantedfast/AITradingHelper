# AITradingHelper

Minimal AI trade review app.

## Official Review Flow

```text
/api/reports
-> trade_review_agent.api.simple_api
-> trade_file_to_trade_csv
-> build_minimal_wang_context
-> review.final_wang_agent.run_final_wang_agent(context)
-> render_simple_wang_report
-> frontend /review/report/[id]
```

OCR only extracts trade facts. The final AI review comes from `trade_review_agent.review.final_wang_agent.run_final_wang_agent(context)`.

## Backend Layout

```text
trade_review_agent/
  api/
    simple_api.py
  ocr/
    ai_trade_parser.py
    ocr_trades.py
    ocr_cli.py
  review/
    simple_wang_report.py
    final_wang_agent/
      agent.py
      presenter.py
  watch/
    alerts.py
    alert_tts.py
    voice_settings.py
    watch_agent.py
    watch_form_ocr.py
  market/
    data_provider.py
    industry_profiles.py
    stock_resolver.py
  common/
    cache_policy.py
    config.py
    openai_agent_api.py
```

### File Roles

- `api/simple_api.py`: HTTP API server. Handles `/api/reports`, watch-plan APIs, uploaded files, report status, and static report artifact serving.
- `ocr/ai_trade_parser.py`: OpenAI vision/text parser. Converts screenshots, CSV, Excel, or text into structured trade facts.
- `ocr/ocr_trades.py`: Thin OCR/file parsing facade used by the API. Writes normalized trade facts to CSV.
- `ocr/ocr_cli.py`: Optional command-line OCR helper for local parser checks.
- `review/simple_wang_report.py`: Minimal official report wrapper. Builds the WANG context, calls `run_final_wang_agent(context)`, and writes presenter JSON plus HTML.
- `review/final_wang_agent/agent.py`: Official WANG agent. Contains the Doubao search step and final judge model call.
- `review/final_wang_agent/presenter.py`: Deterministic mapping from the WANG answer into frontend-readable sections.
- `watch/alerts.py`: Watch-plan persistence, real-time quote fetch, trigger evaluation, and alert event models.
- `watch/alert_tts.py`: Edge TTS audio synthesis helper.
- `watch/voice_settings.py`: Voice provider and voice-name settings storage/normalization.
- `watch/watch_agent.py`: Next-day watch plan and intraday alert narration agent.
- `watch/watch_form_ocr.py`: OCR parser for watch-plan form screenshots.
- `market/data_provider.py`: Market data provider used by watch plans for stock/index daily price context.
- `market/industry_profiles.py`: Minimal fallback market profile for watch plans. It does not run industry research.
- `market/stock_resolver.py`: Resolves A-share stock names/codes and caches the code-name table.
- `common/cache_policy.py`: Runtime cache-disable switch.
- `common/config.py`: `.env` loading and basic OpenAI configuration checks.
- `common/openai_agent_api.py`: Shared OpenAI JSON, image, and speech helper used by watch/OCR-adjacent utilities.

## Local Run

In Codex on a fresh machine, pull this branch and run one command from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-local.ps1
```

If `frontend/node_modules` is missing, the script runs `npm install` automatically. If your Node runtime does not expose npm, install frontend dependencies once from `frontend/` or set `NPM_BIN` to npm.

Frontend:

```text
http://127.0.0.1:3000/
```

Backend health:

```text
http://127.0.0.1:8600/api/health
```

Vendored Stock Analyze health:

```text
http://127.0.0.1:8750/healthz
```

Default local admin credentials are created at startup unless `.env` overrides them:

```text
root / 123456
```

## 产业趋势模块

产业趋势页面会调用本仓库内置的 Stock Analyze 服务和 vendored skill。运行 `.\start-local.ps1` 会同时启动：

- Frontend: `http://127.0.0.1:3000/`
- Backend: `http://127.0.0.1:8600/api/health`
- Stock Analyze: `http://127.0.0.1:8750/healthz`

然后打开：

```text
http://127.0.0.1:3000/industry-trend
```

Stock Analyze 已 vendored 在：

```text
vendor/stock-analyze
```

内置的 `stock-reverse-engineering` skill 在：

```text
vendor/stock-analyze/skills/stock-reverse-engineering
```

提交后会创建后台任务，页面自动轮询结果。成功生成后扣除 1 次使用机会；Stock Analyze 失败或返回空结果不会扣次数。

后端默认调用：

```text
http://127.0.0.1:8750/api/codex
```

可以用环境变量覆盖：

```text
STOCK_ANALYZE_API_URL=http://127.0.0.1:8750/api/codex
STOCK_ANALYZE_TIMEOUT_SECONDS=620
STOCK_ANALYZE_TOKEN=
```

## Required Environment

Configure `.env` with the model keys used by OCR and the final WANG agent:

```text
OPENAI_API_KEY=...
ARK_API_KEY=...
DEEPSEEK_API_KEY=...
```

`OPENAI_MODEL` is optional for OCR; if absent, the parser defaults to `gpt-4.1-mini`.
