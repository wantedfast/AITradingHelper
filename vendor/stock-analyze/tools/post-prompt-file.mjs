import { readFile, writeFile } from "node:fs/promises";

const promptPath = process.argv[2];
const outPath = process.argv[3] || "";
const url = process.env.STOCK_ANALYZE_URL || "http://127.0.0.1:3000/api/codex";

if (!promptPath) {
  console.error("usage: node tools/post-prompt-file.mjs PROMPT_PATH [OUT_PATH]");
  process.exit(2);
}

const prompt = await readFile(promptPath, "utf8");
const skillName = process.env.CODEX_SKILL_NAME || "";
const skillPath = process.env.CODEX_SKILL_PATH || "";
const body = { prompt };

if (skillName || skillPath) {
  body.skillName = skillName;
  body.skillPath = skillPath;
}

const response = await fetch(url, {
  method: "POST",
  headers: { "Content-Type": "application/json; charset=utf-8" },
  body: JSON.stringify(body)
});

const text = await response.text();
if (outPath) await writeFile(outPath, text, "utf8");
console.log(text);
if (!response.ok) process.exit(1);
