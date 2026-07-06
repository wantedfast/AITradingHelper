import http from "node:http";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const host = process.env.HOST || "127.0.0.1";
const port = Number(process.env.PORT || 3000);
const codexBin = process.env.CODEX_BIN || "codex";
const codexCwd = process.env.CODEX_CWD || __dirname;
const codexModel = process.env.CODEX_MODEL || "";
const defaultSkillName = process.env.CODEX_SKILL_NAME || "";
const defaultSkillPath = process.env.CODEX_SKILL_PATH || "";
const approvalPolicy = process.env.CODEX_APPROVAL_POLICY || "never";
const sandboxMode = process.env.CODEX_SANDBOX || "readOnly";
const timeoutMs = Number(process.env.CODEX_TIMEOUT_MS || 300000);
const authToken = process.env.WEB_TO_CODEX_TOKEN || "";
const mockMode = process.env.CODEX_MOCK === "1";

const indexPath = path.join(__dirname, "public", "index.html");

const server = http.createServer(async (request, response) => {
  try {
    if (request.method === "GET" && (request.url === "/" || request.url === "/index.html")) {
      const html = await readFile(indexPath, "utf8");
      send(response, 200, html, "text/html; charset=utf-8");
      return;
    }

    if (request.method === "GET" && request.url === "/healthz") {
      sendJson(response, 200, { ok: true, mockMode });
      return;
    }

    if (request.method === "POST" && request.url === "/api/codex") {
      if (!isAuthorized(request)) {
        sendJson(response, 401, { error: "unauthorized" });
        return;
      }

      const body = await readJsonBody(request);
      const prompt = String(body.prompt || "").trim();
      const skillName = String(body.skillName || defaultSkillName || "").trim();
      const skillPath = normalizeSkillPath(String(body.skillPath || defaultSkillPath || "").trim());
      if (!prompt) {
        sendJson(response, 400, { error: "missing prompt" });
        return;
      }
      if ((skillName && !skillPath) || (!skillName && skillPath)) {
        sendJson(response, 400, { error: "skillName and skillPath must be provided together" });
        return;
      }

      const answer = mockMode
        ? await runMockCodex(prompt, { skillName, skillPath })
        : await runCodexTurn(prompt, { skillName, skillPath });

      sendJson(response, 200, { answer });
      return;
    }

    sendJson(response, 404, { error: "not found" });
  } catch (error) {
    sendJson(response, 500, {
      error: error instanceof Error ? error.message : String(error)
    });
  }
});

server.listen(port, host, () => {
  console.log(`Stock Analyze listening on http://${host}:${port}`);
  console.log(mockMode ? "CODEX_MOCK=1, Codex will not be spawned." : `CODEX_BIN=${codexBin}`);
});

function isAuthorized(request) {
  if (!authToken) return true;
  return request.headers.authorization === `Bearer ${authToken}`;
}

function send(response, statusCode, body, contentType) {
  response.writeHead(statusCode, {
    "Content-Type": contentType,
    "Cache-Control": "no-store"
  });
  response.end(body);
}

function sendJson(response, statusCode, body) {
  send(response, statusCode, JSON.stringify(body, null, 2), "application/json; charset=utf-8");
}

function readJsonBody(request) {
  return new Promise((resolve, reject) => {
    let data = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      data += chunk;
      if (data.length > 1024 * 1024) {
        reject(new Error("request body too large"));
        request.destroy();
      }
    });
    request.on("end", () => {
      try {
        resolve(data ? JSON.parse(data) : {});
      } catch {
        reject(new Error("invalid JSON body"));
      }
    });
    request.on("error", reject);
  });
}

async function runMockCodex(prompt, options = {}) {
  await new Promise((resolve) => setTimeout(resolve, 250));
  const skill = options.skillName ? `\n\nSkill: ${options.skillName}\nPath: ${options.skillPath}` : "";
  return `Mock Codex received:\n\n${prompt}${skill}\n\nSet CODEX_MOCK=0 or unset it to call codex app-server.`;
}

function runCodexTurn(prompt, options = {}) {
  return new Promise((resolve, reject) => {
    const proc = spawn(codexBin, ["app-server"], {
      cwd: codexCwd,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true
    });

    const rl = readline.createInterface({ input: proc.stdout });
    let nextId = 0;
    let initializeId = 0;
    let threadStartId = 0;
    let turnStartId = 0;
    let threadId = "";
    let answer = "";
    let stderr = "";
    let settled = false;

    const timer = setTimeout(() => {
      finish(new Error(`Codex timed out after ${timeoutMs}ms`));
    }, timeoutMs);

    const sendRequest = (method, params = {}) => {
      const id = ++nextId;
      proc.stdin.write(`${JSON.stringify({ method, id, params })}\n`);
      return id;
    };

    const sendNotification = (method, params = {}) => {
      proc.stdin.write(`${JSON.stringify({ method, params })}\n`);
    };

    const finish = (error, result = "") => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      rl.close();
      if (!proc.killed) proc.kill();
      if (error) reject(error);
      else resolve(result);
    };

    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    proc.on("error", (error) => {
      finish(new Error(`Failed to start Codex app-server with CODEX_BIN="${codexBin}": ${error.message}`));
    });

    proc.on("close", (code) => {
      if (!settled && code !== 0) {
        finish(new Error(`Codex app-server exited with code ${code}. ${stderr.trim()}`.trim()));
      }
    });

    rl.on("line", (line) => {
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        return;
      }

      if (message.error) {
        finish(new Error(`${message.error.message || "Codex JSON-RPC error"} (${message.error.code || "no-code"})`));
        return;
      }

      if (message.id === initializeId) {
        sendNotification("initialized");
        threadStartId = sendRequest("thread/start", {
          ...(codexModel ? { model: codexModel } : {})
        });
        return;
      }

      if (message.id === threadStartId) {
        threadId = message.result?.thread?.id || "";
        if (!threadId) {
          finish(new Error("Codex did not return a thread id"));
          return;
        }
        const turnParams = {
          threadId,
          input: buildUserInput(prompt, options),
          cwd: codexCwd,
          approvalPolicy,
          sandboxPolicy: buildSandboxPolicy()
        };
        if (codexModel) turnParams.model = codexModel;
        turnStartId = sendRequest("turn/start", {
          ...turnParams
        });
        return;
      }

      if (message.id === turnStartId) {
        return;
      }

      if (message.method === "item/agentMessage/delta") {
        answer += extractDelta(message.params);
        return;
      }

      if (message.method === "item/completed") {
        const completedText = extractCompletedAgentText(message.params);
        if (completedText && !answer) answer += completedText;
        return;
      }

      if (message.method === "turn/completed") {
        finish(null, answer.trim());
      }
    });

    initializeId = sendRequest("initialize", {
      clientInfo: {
        name: "stock_analyze",
        title: "Stock Analyze",
        version: "0.1.0"
      }
    });
  });
}

function buildUserInput(prompt, options = {}) {
  const input = [{ type: "text", text: prompt, text_elements: [] }];
  if (options.skillName && options.skillPath) {
    input.push({ type: "skill", name: options.skillName, path: options.skillPath });
  }
  return input;
}

function normalizeSkillPath(skillPath) {
  if (!skillPath) return "";
  return path.isAbsolute(skillPath) ? skillPath : path.resolve(__dirname, skillPath);
}

function buildSandboxPolicy() {
  if (sandboxMode === "dangerFullAccess") return { type: "dangerFullAccess" };
  if (sandboxMode === "workspaceWrite") {
    return {
      type: "workspaceWrite",
      writableRoots: [codexCwd],
      networkAccess: true,
      excludeTmpdirEnvVar: false,
      excludeSlashTmp: false
    };
  }
  return { type: "readOnly", networkAccess: true };
}

function extractDelta(params) {
  if (!params) return "";
  for (const key of ["delta", "text", "content"]) {
    if (typeof params[key] === "string") return params[key];
  }
  if (typeof params.item?.delta === "string") return params.item.delta;
  if (typeof params.item?.text === "string") return params.item.text;
  return "";
}

function extractCompletedAgentText(params) {
  const item = params?.item;
  if (!item) return "";
  if (item.type !== "agentMessage") return "";
  if (typeof item.text === "string") return item.text;
  if (typeof item.message === "string") return item.message;
  if (Array.isArray(item.content)) {
    return item.content
      .map((part) => part?.text || part?.content || "")
      .filter(Boolean)
      .join("");
  }
  return "";
}
