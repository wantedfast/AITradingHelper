const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const components = fs.readFileSync(path.join(root, "frontend/app/ai-research/report-components.tsx"), "utf8");
const page = fs.readFileSync(path.join(root, "frontend/app/ai-research/page.tsx"), "utf8");
const detailPage = fs.readFileSync(path.join(root, "frontend/app/ai-research/report/[id]/page.tsx"), "utf8");
const styles = fs.readFileSync(path.join(root, "frontend/app/globals.css"), "utf8");

for (const field of [
  "schema_version", "beginner_decision", "stance", "headline", "primary_focus",
  "continue_conditions", "stop_conditions", "timeline", "backup_focus",
  "avoid_actions", "term_explanations",
]) {
  assert.match(components, new RegExp(field), `AI research types/rendering must include ${field}`);
}

for (const phrase of [
  "继续观察", "立即放弃", "今天不操作", "我该怎么做",
  "研究依据与术语解释", "不是买点提示",
]) {
  assert.match(components, new RegExp(phrase), `beginner dashboard must show ${phrase}`);
}

assert.match(components, /ProfessionalReportBody/, "v1 professional report renderer must remain available");
assert.match(components, /isBeginnerResearchReport/, "v2 report detection must be explicit");
assert.match(page, /isBeginnerResearchReport/, "inline report must suppress the legacy hero for v2");
assert.match(detailPage, /isBeginnerResearchReport/, "detail report must suppress the legacy hero for v2");

for (const className of [
  "ai-beginner-dashboard", "ai-beginner-decision-grid", "ai-beginner-timeline",
  "ai-beginner-backup", "ai-beginner-disclaimer",
]) {
  assert.match(styles, new RegExp(`\\.${className}`), `styles must define ${className}`);
}

console.log("AI research beginner frontend contract OK");
