# Stock Analyze

本项目用 **Codex App Server** 做本地 A 股产业链分析。网页或脚本发送股票分析 prompt，服务端转给 `codex app-server`，并默认注入仓库内置的 `stock-reverse-engineering` skill。

它不使用 `codex exec`，也不模拟点击 Codex 桌面 App。

## 开箱能力

- 网页输入股票分析请求。
- 通过 Codex App Server 创建 thread/turn。
- 默认注入内置股票分析 skill：`skills/stock-reverse-engineering/SKILL.md`。
- 默认关闭审批弹窗：`approvalPolicy = never`。
- 默认只读沙箱，适合自动化研究任务。
- PowerShell 一键启动。
- 无 npm 第三方依赖。

## 前置条件

另一台电脑需要：

1. Windows + PowerShell。
2. 已安装并登录 Codex App。
3. Node.js 20+，或 Codex runtime 自带 Node。

`start.ps1` 会自动查找可调用的 Codex binary，优先找：

```text
C:\Users\<你>\AppData\Local\OpenAI\Codex\bin\...\codex.exe
```

不要直接用 `C:\Program Files\WindowsApps\...` 里的 Store 应用资源，Windows 可能返回 `Access is denied`。

## 快速启动

```powershell
git clone https://github.com/wantedfast/Stock-Analyze.git
cd Stock-Analyze
.\start.ps1 -StockSkill
```

打开：

```text
http://127.0.0.1:3000
```

`-StockSkill` 会使用仓库内置 skill：

```text
skills/stock-reverse-engineering/SKILL.md
```

网页里的 skill 输入框也已经预填了内置 skill。你可以直接输入：

```text
分析华海清科，从高利润、高壁垒、高增长角度判断产业链地位。
```

## Mock 模式

只测试网页和 API，不调用 Codex：

```powershell
.\start.ps1 -Mock
```

## 指定其他 Skill

如果你想覆盖默认 skill：

```powershell
.\start.ps1 -StockSkill
```

也可以在网页里填写：

```text
skillName: stock-reverse-engineering
skillPath: .\skills\stock-reverse-engineering\SKILL.md
```

## 命令行发送 Prompt

先启动服务：

```powershell
.\start.ps1
```

另开一个 PowerShell：

```powershell
node .\tools\post-prompt-file.mjs .\examples\huahai-qingke.txt .\huahai-result.json
```

如果 `node` 不在 PATH，但 Codex runtime 有 Node：

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" `
  .\tools\post-prompt-file.mjs .\examples\huahai-qingke.txt .\huahai-result.json
```

## 无弹窗自动化

服务端默认给每个 turn 发送：

```json
{
  "approvalPolicy": "never",
  "sandboxPolicy": {
    "type": "readOnly",
    "networkAccess": true
  }
}
```

这意味着自动化任务不会卡在审批弹窗上。

需要写文件时：

```powershell
.\start.ps1 -WorkspaceWrite
```

这会把 `CODEX_CWD` 作为可写根目录。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `3000` | HTTP 端口 |
| `HOST` | `127.0.0.1` | HTTP host |
| `CODEX_BIN` | 自动探测 | 可调用的 `codex.exe` |
| `CODEX_CWD` | 项目目录 | Codex turn 工作目录 |
| `CODEX_MODEL` | 空 | 可选模型覆盖 |
| `CODEX_SKILL_NAME` | 空 | 默认注入 skill 名称；`-StockSkill` 会设置为 `stock-reverse-engineering` |
| `CODEX_SKILL_PATH` | 空 | 默认注入 skill 路径；`-StockSkill` 会设置为内置 skill |
| `CODEX_APPROVAL_POLICY` | `never` | 审批策略 |
| `CODEX_SANDBOX` | `readOnly` | `readOnly` / `workspaceWrite` / `dangerFullAccess` |
| `CODEX_TIMEOUT_MS` | `300000` | 单次请求超时 |
| `WEB_TO_CODEX_TOKEN` | 空 | 可选 Bearer token |

长产业链报告建议：

```powershell
$env:CODEX_TIMEOUT_MS = "600000"
```

## API

```http
POST /api/codex
Content-Type: application/json
```

最简请求：

```json
{
  "prompt": "分析华海清科，从高利润、高壁垒、高增长角度判断产业链地位。"
}
```

覆盖 skill：

```json
{
  "prompt": "分析华海清科",
  "skillName": "stock-reverse-engineering",
  "skillPath": ".\\skills\\stock-reverse-engineering\\SKILL.md"
}
```

返回：

```json
{
  "answer": "..."
}
```

## 目录

```text
.
├─ server.mjs
├─ start.ps1
├─ public/index.html
├─ tools/post-prompt-file.mjs
├─ tools/smoke-test.mjs
├─ examples/
├─ skills/stock-reverse-engineering/
│  ├─ SKILL.md
│  ├─ agents/openai.yaml
│  └─ references/multi-agent-protocol.md
├─ docs/runbook.md
├─ spec/mvp.md
└─ AGENTS.md
```

## 已知限制

- 当前 HTTP 接口是完整回答后一次性返回，不是流式。长报告需要等 `turn/completed`。
- Codex App Server 协议可能随 Codex 版本变化，本项目按本地 `codex-cli 0.142.5` 验证过。
- 如果另一台电脑首次运行找不到 `codex.exe`，先打开一次 Codex App，或手动设置 `CODEX_BIN`。
- 这是研究工具，不构成投资建议。
