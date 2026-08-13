# Design QA — 2026-08-13 实际研报预览

- Source visual truth: `C:\Users\wangf\.codex\generated_images\019feabf-4700-76e2-bbc2-d1433070dda6\exec-9afc666e-23b2-4e2f-b2ed-c1ee2009d261.png`
- Implementation: `http://127.0.0.1:4173/`
- Desktop screenshot: `implementation-2026-08-13-desktop.jpg`
- Mobile screenshot: `implementation-2026-08-13-mobile.jpg`
- Source pixels: 1488 × 1055
- Desktop implementation pixels: 1472 × 1055; CSS viewport 1488 × 1055; device density 1; 16 px browser scrollbar excluded from capture width.
- Mobile implementation pixels: 375 × 844; CSS viewport 390 × 844; device density 1; browser scrollbar excluded from capture width.
- State: 2026-08-13 v2 actual-data decision layer, research details and full Markdown expanded for formatting QA.

## Full-view comparison evidence

The source and desktop implementation were opened together at the same desktop height. Both preserve the selected black/forest-green and muted-gold system, fixed left navigation, large stance/focus hero, two-column continue/stop judgment, three-step timeline, backup direction, collapsed research layer and risk disclaimer. The implementation uses the longer validated 2026-08-13 content, so cards are intentionally denser while the hierarchy remains unchanged.

## Focused-region comparison evidence

The hero and paired decision cards were checked separately because they carry the primary 30-second task. Typography remains high contrast, the focus direction is dominant, stop conditions retain red semantics, and the actual longer text wraps inside the cards without clipping or horizontal overflow. No raster imagery is part of this UI; icons use the existing Phosphor icon library and remain crisp.

## Required fidelity surfaces

- Fonts and typography: Chinese system sans-serif hierarchy matches the product; gold headline, white body, muted helper text and red invalidation text remain readable. Actual-data wrapping is clean.
- Spacing and layout rhythm: hero, decision cards, timeline and secondary panels retain the source sequence and consistent 12–14 px section rhythm. Desktop and 390 px mobile have no horizontal overflow.
- Colors and visual tokens: black, forest green, muted gold, cyan backup accent and red stop state match the source semantics.
- Image quality and assets: no source raster assets were replaced. UI symbols use a real icon library; no placeholder or handcrafted SVG is present.
- Copy and content: all visible decisions come from the validated 2026-08-13 JSON. Jargon is absent from the primary layer and appears only in the expanded glossary/professional section.

## Interactions tested

- Initial JSON load.
- Refresh button reloads the actual local JSON.
- Research layer expands and shows 37 sources, 8 evidence rows, 3 institutional research entries, all six glossary terms and the full professional Markdown.
- Full Markdown renders 27 headings, 22 lists and 3 GFM tables; raw `#` heading syntax is not visible.
- Markdown links open safely in a new tab; headings, bold text, quotes, code and tables use the product theme.
- On 390 px mobile, wide tables scroll inside the report (`680 px` table inside a `259 px` scroller) without causing page-level horizontal overflow.
- Desktop and 390 × 844 responsive states.
- No application console errors. The only observed warning originated from the browser host's own telemetry request, not the prototype.

## Findings

- No actionable P0/P1/P2 findings.

## Follow-up polish

- P3: The actual headline and conditions are longer than the visual mock, increasing desktop density. This is acceptable because it preserves factual completeness and remains scannable.

## Comparison history

- Initial capture retained a scrolled position after testing the expanded section; this was capture-state mismatch, not a UI defect. The page was returned to scroll position 0 and recaptured at the source viewport before comparison.
- First mobile Markdown pass allowed a wide table to enlarge the page to 753 px. The table was moved into a contained horizontal scroller and all report/detail containers received explicit `min-width: 0`; post-fix evidence is a 375 px page at a 390 px viewport with no page overflow.

final result: passed
