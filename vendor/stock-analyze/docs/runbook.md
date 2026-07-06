# Runbook

## Environment Variables

- `PORT`: HTTP port. Default: `3000`.
- `HOST`: HTTP host. Default: `127.0.0.1`.
- `CODEX_BIN`: Codex executable. Default: auto-detected by `start.ps1`; manually set it only if detection fails.
- `CODEX_CWD`: Working directory passed to the Codex turn. Default: this project directory.
- `CODEX_MODEL`: Optional model override for `thread/start`.
- `CODEX_SKILL_NAME`: Optional default skill name injected into every turn.
- `CODEX_SKILL_PATH`: Optional default absolute path to the skill `SKILL.md`.
- `CODEX_APPROVAL_POLICY`: Approval behavior. Default: `never`.
- `CODEX_SANDBOX`: `readOnly`, `workspaceWrite`, or `dangerFullAccess`. Default: `readOnly`.
- `CODEX_TIMEOUT_MS`: Request timeout. Default: `300000`.
- `CODEX_MOCK`: Set to `1` to avoid starting Codex.
- `WEB_TO_CODEX_TOKEN`: Optional bearer token required by `/api/codex`.

## Windows Notes

Microsoft Store apps can live under `C:\Program Files\WindowsApps`, where direct execution may fail with `Access is denied`. Use the callable user-local binary under `AppData\Local\OpenAI\Codex\bin\...\codex.exe`. `start.ps1` tries to find this path automatically.

Use mock mode first to verify Node and the web UI:

```powershell
.\start.ps1 -Mock
```

Use `-StockSkill` to inject the vendored stock skill by default:

```text
.\start.ps1 -StockSkill
```

Then test real mode:

```powershell
$env:CODEX_CWD = "C:\path\to\your\project"
.\start.ps1
```
