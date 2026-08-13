# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Durable design decisions

- The selected visual direction is “行动仪表盘” (option 3), grounded in the existing 盈航 black/forest-green and muted-gold visual system.
- Primary audience is an ordinary A-share retail investor or beginner. The page must communicate stance, focus, continuation conditions, and invalidation within 30 seconds.
- Professional terms such as 扩散、回流、承接、弱转强、宽度、拥挤度 must not appear in primary decision content. Plain-language explanations belong in a secondary expandable section.
- “今天不操作” is a valid, prominent outcome. The prototype must not contain buy buttons, individual-stock recommendations, or implied entry points.
