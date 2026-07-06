# Agent Instructions

## Project Purpose

This project is a local stock-analysis bridge. A browser page or script sends a prompt to a local Node.js server, and the server starts `codex app-server`, creates a Codex thread, starts a turn, optionally injects a skill, streams agent message deltas, and returns the final answer.

## Stack

- Node.js 20 or newer.
- No third-party runtime dependencies.
- Codex app-server protocol over stdio JSONL.

## Commands

- Run: `npm start`
- Run without Codex: `npm run mock`
- Windows direct run: `.\start.ps1`
- Windows direct mock run: `.\start.ps1 -Mock`
- Static checks: `npm run check`
- Smoke test: `npm run smoke`

If `node` is not on PATH, use the bundled Node executable from the Codex runtime or set PATH before running commands.

## Directory Map

- `server.mjs`: HTTP server and Codex app-server JSON-RPC bridge.
- `public/`: browser UI served by the MVP.
- `spec/`: requirements and acceptance criteria.
- `docs/`: operational notes and protocol notes.
- `tools/`: deterministic helper scripts.
- `assets/`: reserved for UI or documentation assets.
- `skills/stock-reverse-engineering/`: vendored stock-analysis Codex skill.

## Coding Conventions

- Keep the server dependency-free unless a dependency removes real complexity.
- Keep Codex protocol handling explicit and easy to inspect.
- Prefer environment variables for local machine differences such as `CODEX_BIN`.
- Do not expose this service to the public internet without authentication.

## Testing Policy

- Run `npm run check` after edits.
- Use `CODEX_MOCK=1 npm start` for UI and HTTP testing without starting Codex.
- Use a real Codex run only on localhost and with a non-sensitive prompt first.

## Change Safety

- Do not default to full filesystem access or shelling through user-provided values.
- Never log secrets or bearer tokens.
- Treat prompts received from the web as untrusted input.

## Definition of Done

- The server starts.
- The browser UI can submit a prompt.
- Mock mode returns a deterministic answer.
- Real mode attempts `initialize`, `thread/start`, and `turn/start` against Codex app-server.
- README documents setup, environment variables, and known Windows caveats.
