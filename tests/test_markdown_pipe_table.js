"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require(path.join(__dirname, "..", "frontend", "node_modules", "typescript"));

function loadParser() {
  return loadTypescriptModule("markdown-pipe-table.ts");
}

function loadTypescriptModule(relativePath) {
  const filename = path.join(__dirname, "..", "frontend", "lib", relativePath);
  const source = fs.readFileSync(filename, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: filename,
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports, require }, { filename });
  return module.exports;
}

const { containsMarkdownPipeTable, parseMarkdownPipeTables } = loadParser();
const { evidenceReportText, namedReportText, watchPointReportText } = loadTypescriptModule("market-day-report-content.ts");

function tableFrom(markdown) {
  const segments = parseMarkdownPipeTables(markdown.split(/\r?\n/));
  return segments.find((segment) => segment.type === "table")?.table;
}

{
  const markdown = [
    "| 主题 | 涨跌幅 | 来源 |",
    "| :--- | ---: | :---: |",
    "| 黄金 | +3.25% | [交易所](https://example.com/gold) |",
    "| 原油 | -1.8% | [数据](https://example.com/oil) |",
  ].join("\n");
  const table = tableFrom(markdown);
  assert.ok(table, "Chinese/percentage/link table should be recognized");
  assert.deepEqual(Array.from(table.headers), ["主题", "涨跌幅", "来源"]);
  assert.deepEqual(Array.from(table.alignments), ["left", "right", "center"]);
  assert.deepEqual(Array.from(table.rows[0]), ["黄金", "+3.25%", "[交易所](https://example.com/gold)"]);
  assert.equal(containsMarkdownPipeTable(markdown), true);
}

{
  const table = "| 字段 | 数值 |\n| --- | --- |\n| CPI | 利空 |";
  const named = namedReportText("宏观", table);
  assert.equal(named[0].label, "宏观：");
  assert.equal(named[0].value, table);
  assert.equal(containsMarkdownPipeTable(named[0].value), true, "named reason must remain independently detectable");

  const evidence = evidenceReportText({ type: "数据", content: table });
  assert.equal(evidence[0].label, "数据：");
  assert.equal(evidence[0].value, table);
  assert.equal(containsMarkdownPipeTable(evidence[0].value), true, "evidence content must remain independently detectable");

  const watch = watchPointReportText({
    object: table,
    condition: table,
    positiveSignal: table,
    negativeSignal: table,
    meaning: table,
  });
  assert.deepEqual(Array.from(watch, (part) => part.label), ["", "条件：", "正向：", "负向：", "含义："]);
  assert.equal(watch.every((part) => part.value === table && containsMarkdownPipeTable(part.value)), true, "every watch-point field must remain independently detectable");
}

{
  const markdown = [
    "| A | B | C | D | E | F |",
    "| --- | :--- | :---: | ---: | --- | --- |",
    "|  | 很长的中文单元格内容用于验证宽表不会被解析器截断 | 0% | [链接](https://example.com) | \u7a7a | 尾列 |",
  ].join("\n");
  const table = tableFrom(markdown);
  assert.ok(table, "wide table should be recognized");
  assert.equal(table.headers.length, 6);
  assert.equal(table.rows[0][0], "");
  assert.equal(table.rows[0][1], "很长的中文单元格内容用于验证宽表不会被解析器截断");
  assert.deepEqual(Array.from(table.alignments), [null, "left", "center", "right", null, null]);
}

{
  const malformedCases = [
    "| 标题 | 数值 |\n| -- | --- |\n| A | 1 |",
    "| 标题 | 数值 |\n| --- | --- |",
    "标题 | 数值\n--- | ---\nA | 1",
    "| 标题 | 数值 |\n| --- | --- |\n| 只有一列 |",
  ];
  for (const markdown of malformedCases) {
    const segments = parseMarkdownPipeTables(markdown.split(/\r?\n/));
    assert.equal(segments.some((segment) => segment.type === "table"), false, markdown);
    assert.equal(segments.every((segment) => segment.type === "text"), true, markdown);
  }
}

{
  const lines = ["普通段落", "- 第一项", "* 第二项", "", "结尾文字"];
  const segments = parseMarkdownPipeTables(lines);
  assert.equal(segments.length, 1);
  assert.equal(segments[0].type, "text");
  assert.deepEqual(Array.from(segments[0].lines), lines);
  assert.equal(containsMarkdownPipeTable(lines.join("\n")), false);
}

{
  // There is no React test runner in this frontend. Keep the security contract
  // executable by checking the small table-cell renderer alongside the pure parser.
  const renderer = fs.readFileSync(
    path.join(__dirname, "..", "frontend", "components", "report-pipe-table.tsx"),
    "utf8",
  );
  assert.match(renderer, /https\?:\\\/\\\//, "table-cell links must only recognize HTTP(S) URLs");
  assert.match(renderer, /href=\{match\[2\]\}/, "validated link URL must be used as href");
  assert.match(renderer, /target="_blank"/, "external report links must open separately");
  assert.match(renderer, /rel="noopener noreferrer"/, "external report links must isolate the opener");
}

console.log("markdown pipe table parser: all assertions passed");
