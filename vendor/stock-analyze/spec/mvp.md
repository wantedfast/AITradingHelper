# Stock Analyze MVP Spec

## Goal

Build a local stock-analysis bridge that accepts a prompt from a web page or script and sends it to Codex through the Codex app-server protocol instead of `codex exec`.

## User Flow

1. User starts the Node server locally.
2. User opens `http://localhost:3000`.
3. User types a prompt.
4. Browser sends `POST /api/codex`.
5. Server starts `codex app-server`, creates a thread, starts a turn, optionally injects a skill, collects agent text, and returns JSON.
6. Browser displays the answer.

## Acceptance Criteria

- No Express or npm dependencies are required.
- `GET /` serves a usable page.
- `POST /api/codex` accepts `{ "prompt": "..." }`.
- `POST /api/codex` accepts optional `skillName` and `skillPath`.
- Turns default to `approvalPolicy: "never"` and read-only sandbox.
- Optional bearer-token authentication is supported with `WEB_TO_CODEX_TOKEN`.
- Mock mode works with `CODEX_MOCK=1`.
- Real mode supports `CODEX_BIN`, `CODEX_CWD`, `CODEX_MODEL`, and `CODEX_TIMEOUT_MS`.
- Long-running Codex processes are terminated after timeout or request close.

## Non-Goals

- Multi-user queueing.
- Persistent Codex threads.
- File upload or image prompts.
- Public deployment.
- Desktop UI automation.
