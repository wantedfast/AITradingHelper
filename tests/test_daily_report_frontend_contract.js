"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require(path.join(__dirname, "..", "frontend", "node_modules", "typescript"));

const frontend = path.join(__dirname, "..", "frontend");

function read(relativePath) {
  return fs.readFileSync(path.join(frontend, relativePath), "utf8");
}

function loadTypescriptModule(relativePath) {
  const filename = path.join(frontend, relativePath);
  const source = fs.readFileSync(filename, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: filename,
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports, require }, { filename });
  return module.exports;
}

const access = loadTypescriptModule("lib/dated-report-access.ts");

assert.equal(access.canReadDatedReport("free_history"), true, "history must open immediately");
assert.equal(access.canReadDatedReport("charged"), true, "already-paid reports must open immediately");
assert.equal(access.canReadDatedReport("pending_view"), false, "unpaid current reports must stay closed");
assert.equal(access.canReadDatedReport("no_data"), false, "missing reports cannot open");
assert.equal(access.shouldShowDatedReportPayment("pending_view", true), true, "pending report needs payment button");
assert.equal(access.shouldShowDatedReportPayment("pending_view", false), false, "no report means no payment button");
for (const status of ["no_data", "charged", "free_history"]) {
  assert.equal(access.shouldShowDatedReportPayment(status, true), false, `${status} must not show payment button`);
}

const sidebar = read("components/main-sidebar.tsx");
const home = read("app/page.tsx");
const review = read("app/review/page.tsx");
const dailyTop5 = read("app/auction-strength/page.tsx");
assert.match(dailyTop5, /today_open_price\?: number \| null/);
assert.match(dailyTop5, /开盘价 \{formatStockPrice\(stock\.today_open_price\)\}/);
const ticker = read("components/auction-strength-performance-ticker.tsx");

assert.ok(fs.existsSync(path.join(frontend, "app", "auction-strength", "page.tsx")), "old /auction-strength route must remain");
assert.match(sidebar, /href: "\/auction-strength", label: "每日 TOP5"/);
assert.match(home, /href: "\/auction-strength",\s*title: "每日 TOP5",\s*label: "DAILY TOP 5"/);
assert.match(dailyTop5, />DAILY TOP 5<\/span>/);
assert.match(dailyTop5, />每日 TOP5<\/b>/);

const sidebarDaily = sidebar.indexOf('key: "auction-strength"');
const sidebarReview = sidebar.indexOf('key: "review"');
assert.ok(sidebarDaily >= 0 && sidebarDaily < sidebarReview, "Daily TOP5 must be first in sidebar navigation");
const homeDaily = home.indexOf('title: "每日 TOP5"');
const homeReview = home.indexOf('title: "AI 复盘"');
assert.ok(homeDaily >= 0 && homeDaily < homeReview, "Daily TOP5 must be first homepage feature card");

for (const [filename, source] of [
  ["sidebar", sidebar],
  ["homepage", home],
  ["Daily TOP5 page", dailyTop5],
  ["performance ticker", ticker],
]) {
  assert.doesNotMatch(source, /竞价强者|AUCTION STRENGTH/, `${filename} must not expose the old product name`);
}

for (const phrase of ["每天 9:25", "5 只", "回避"]) assert.match(home, new RegExp(phrase), `Daily TOP5 copy needs ${phrase}`);
for (const phrase of ["手动输入", "做对", "需要改", "类似情况"]) assert.match(home, new RegExp(phrase), `review copy needs ${phrase}`);
assert.doesNotMatch(home, /上传交割单/, "homepage must not advertise the removed AI review upload flow");
assert.doesNotMatch(home, /从交割单开始/, "homepage hero must not imply the removed AI review upload flow");
assert.doesNotMatch(review, /type="file"|文件上传|上传交割单|交割单文件说明/, "AI review must not expose file upload controls or copy");
assert.match(review, /手动输入一笔交易/, "AI review must explain the remaining manual-entry flow");
for (const phrase of ["持仓和计划", "明天观察", "买卖", "停手"]) assert.match(home, new RegExp(phrase), `watch copy needs ${phrase}`);
for (const phrase of ["19:00", "市场在炒什么", "板块强弱"]) assert.match(home, new RegExp(phrase), `market copy needs ${phrase}`);
assert.match(home, /第二天(?:关注)?重点/, "market copy needs the next day's focus");
for (const phrase of ["08:30", "国内外", "CPI", "黄金", "原油", "海外", "A 股"]) assert.match(home, new RegExp(phrase), `research copy needs ${phrase}`);
assert.doesNotMatch(home, /automation|webhook|证据链/i, "homepage feature introductions must avoid implementation jargon");

for (const relativePath of ["app/market-day/page.tsx", "app/ai-research/page.tsx"]) {
  const source = read(relativePath);
  assert.match(source, /canReadDatedReport\(nextBillingStatus\)/, `${relativePath} must auto-read history/charged reports`);
  assert.match(source, /shouldShowDatedReportPayment\(billingStatus, Boolean\(summary\)\)/, `${relativePath} must gate payment button on pending data`);
  assert.match(source, /set(?:ReportEnvelope|Report)\(null\);\s*loadedRunIdRef\.current = "";/, `${relativePath} must close an old report when a new run is pending`);
  assert.doesNotMatch(source, /\[confirmed,/, `${relativePath} must not require an extra confirmation before loading list state`);
}

assert.equal((dailyTop5.match(/\/api\/auction-strength\/ack/g) || []).length, 1, "Daily TOP5 must acknowledge only from its explicit payment action");
assert.match(dailyTop5, /shouldShowDatedReportPayment\(billingStatus, Boolean\(selectedReport\)\)/);

console.log("daily report frontend contract: all assertions passed");
