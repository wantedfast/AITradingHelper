const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const sample = JSON.parse(fs.readFileSync(path.join(root, "samples/market-day/2026-08-12-v2.json"), "utf8"));
const view = fs.readFileSync(path.join(root, "frontend/components/market-day-report-view.tsx"), "utf8");
const page = fs.readFileSync(path.join(root, "frontend/app/market-day/page.tsx"), "utf8");
const detailPage = fs.readFileSync(path.join(root, "frontend/app/market-day/report/[id]/page.tsx"), "utf8");

assert.equal(sample.schema_version, 2, "market-day sample must stay on the v2 beginner schema");
assert.equal(sample.run_id, "market-day-2026-08-12", "market-day sample must keep the dated v2 run id");
assert.ok(sample.report && sample.report.beginner_decision, "market-day sample must include report.beginner_decision");

const decision = sample.report.beginner_decision;
assert.ok(decision.stance && decision.headline, "sample must answer tomorrow's stance");
assert.ok(Array.isArray(decision.what_changed) && decision.what_changed.length >= 1, "sample must answer what changed today");
assert.ok(Array.isArray(decision.continue_conditions), "sample must expose continue conditions even when stand_aside");
assert.ok(Array.isArray(decision.stop_conditions) && decision.stop_conditions.length >= 1, "sample must answer when to stop");
assert.deepEqual(decision.timeline.map((item) => item.time), ["09:25", "09:35", "10:30"], "sample must answer the three market-day time anchors");
assert.ok(Array.isArray(decision.avoid_actions) && decision.avoid_actions.length >= 1, "sample must answer what to avoid tomorrow");
assert.equal(decision.primary_focus, null, "stand_aside sample must allow no primary focus");
assert.equal(decision.backup_focus, null, "stand_aside sample must allow no backup focus");

for (const field of [
  "schema_version", "beginner_decision", "what_changed", "primary_focus",
  "continue_conditions", "stop_conditions", "timeline", "backup_focus",
  "avoid_actions", "term_explanations",
]) {
  assert.match(view, new RegExp(field), `market-day view must include ${field}`);
}

assert.match(
  view,
  /decision\.what_changed\.map\(\(item\) => <li key=\{item\}>\{item\}<\/li>\)/,
  "market-day beginner dashboard must actually render decision.what_changed items",
);

for (const phrase of [
  "继续观察", "立即停止", "明天开盘后怎么观察", "今天发生了什么",
  "市场强弱依据", "持续性依据", "证据把握说明", "研究依据与术语解释", "不是买点提示",
]) {
  assert.match(view, new RegExp(phrase), `market-day beginner dashboard must show ${phrase}`);
}

for (const sourceField of ["publisher", "publishedAt", "accessedAt", "sourceType", "supports"]) {
  assert.match(view, new RegExp(sourceField), `market-day professional source formatter must preserve ${sourceField}`);
}

assert.match(view, /hasBeginnerMarketDayDashboard/, "market-day view must detect the beginner dashboard explicitly");
assert.match(view, /review-workbench-hero market-day-report-hero/, "market-day legacy professional hero must remain available");
assert.match(page, /MarketDayReportView/, "market-day landing page must render the shared report view");
assert.match(detailPage, /MarketDayReportView/, "market-day detail page must render the shared report view");

console.log("Market Day v2 beginner contract OK");
