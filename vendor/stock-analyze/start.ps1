param(
  [switch]$Mock,
  [switch]$WorkspaceWrite,
  [switch]$StockSkill,
  [string]$Port = "",
  [string]$SkillName = "",
  [string]$SkillPath = ""
)

$ErrorActionPreference = "Stop"

function Test-Executable($Path) {
  if (-not $Path) { return $false }
  try {
    $out = Join-Path $env:TEMP "codex-version.out"
    $err = Join-Path $env:TEMP "codex-version.err"
    $process = Start-Process -FilePath $Path -ArgumentList "--version" -NoNewWindow -Wait -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    return $process.ExitCode -eq 0
  } catch {
    return $false
  }
}

function Find-Node {
  $bundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
  if (Test-Path -LiteralPath $bundledNode) { return $bundledNode }
  return "node"
}

function Find-Codex {
  if ($env:CODEX_BIN -and (Test-Executable $env:CODEX_BIN)) { return $env:CODEX_BIN }

  $localRoot = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin"
  if (Test-Path -LiteralPath $localRoot) {
    $candidate = Get-ChildItem -LiteralPath $localRoot -Filter "codex.exe" -Recurse -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1
    if ($candidate -and (Test-Executable $candidate.FullName)) { return $candidate.FullName }
  }

  $command = Get-Command codex -ErrorAction SilentlyContinue
  if ($command -and (Test-Executable $command.Source)) { return $command.Source }

  return ""
}

$node = Find-Node

if ($Mock) {
  $env:CODEX_MOCK = "1"
} else {
  $codex = Find-Codex
  if (-not $codex) {
    throw "Could not find a callable codex executable. Open Codex once, or set CODEX_BIN to a user-local codex.exe path."
  }
  $env:CODEX_BIN = $codex
}

if ($Port) { $env:PORT = $Port }
if (-not $env:CODEX_CWD) { $env:CODEX_CWD = $PSScriptRoot }
if (-not $env:CODEX_APPROVAL_POLICY) { $env:CODEX_APPROVAL_POLICY = "never" }
$env:CODEX_SANDBOX = if ($WorkspaceWrite) { "workspaceWrite" } elseif ($env:CODEX_SANDBOX) { $env:CODEX_SANDBOX } else { "readOnly" }

if ($SkillName) { $env:CODEX_SKILL_NAME = $SkillName }
if ($SkillPath) { $env:CODEX_SKILL_PATH = $SkillPath }

$vendoredStockSkill = Join-Path $PSScriptRoot "skills\stock-reverse-engineering\SKILL.md"
if ($StockSkill -and (Test-Path -LiteralPath $vendoredStockSkill)) {
  $env:CODEX_SKILL_NAME = "stock-reverse-engineering"
  $env:CODEX_SKILL_PATH = $vendoredStockSkill
}

& $node (Join-Path $PSScriptRoot "server.mjs")
