$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$RuntimeRoot = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies"
$BundledNode = Join-Path $RuntimeRoot "node\bin\node.exe"
$BundledPython = Join-Path $RuntimeRoot "python\python.exe"
$Node = $null
$Python = $null
$BackendBase = "http://127.0.0.1:8600"

if (Test-Path $BundledNode) {
  $Node = $BundledNode
} else {
  $NodeCommand = Get-Command node -ErrorAction SilentlyContinue
  if ($NodeCommand) {
    $Node = $NodeCommand.Source
  }
}

if (-not $Node -or -not (Test-Path $Node)) {
  throw "Node runtime not found. Checked bundled runtime and system node."
}

if (Test-Path $BundledPython) {
  $Python = $BundledPython
} elseif (Test-Path "D:\an\python.exe") {
  $Python = "D:\an\python.exe"
} else {
  $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($PythonCommand) {
    $Python = $PythonCommand.Source
  } else {
    $Python = "python"
  }
}

function Stop-PortListeners {
  param([int]$Port)

  for ($attempt = 0; $attempt -lt 10; $attempt++) {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) {
      return
    }
    foreach ($listener in $listeners) {
      if ($listener.OwningProcess -gt 0) {
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
      }
    }
    Start-Sleep -Milliseconds 350
  }

  $remaining = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
  if ($remaining.Count -gt 0) {
    throw "Port $Port is still occupied after cleanup."
  }
}

function Import-DotEnv {
  param([string]$Path)

  if (-not (Test-Path $Path)) {
    return
  }

  foreach ($rawLine in [System.IO.File]::ReadAllLines($Path, [System.Text.Encoding]::UTF8)) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
      continue
    }
    $parts = $line.Split("=", 2)
    $key = $parts[0].Trim().TrimStart([char]0xFEFF)
    $value = $parts[1].Trim().Trim('"').Trim("'")
    if ($key) {
      [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
  }
}

function Wait-HttpOk {
  param(
    [string]$Url,
    [System.Diagnostics.Process]$Process,
    [int]$TimeoutSeconds = 60
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    if ($Process -and $Process.HasExited) {
      throw "Backend process exited before health check succeeded. ExitCode=$($Process.ExitCode)"
    }
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
        return
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)

  throw "Timed out waiting for backend health check: $Url"
}

foreach ($port in 3000, 8600) {
  Stop-PortListeners -Port $port
}

Start-Sleep -Milliseconds 600

$NextBin = Join-Path $Frontend "node_modules\next\dist\bin\next"
if (-not (Test-Path $NextBin)) {
  throw "Next.js binary not found. Check frontend/node_modules: $NextBin"
}

$NextCache = Join-Path $Frontend ".next"
if ((Test-Path $NextCache) -and ($NextCache -like "$Frontend*")) {
  Remove-Item -LiteralPath $NextCache -Recurse -Force
}

$EnvPath = Join-Path $Root ".env"
Import-DotEnv -Path $EnvPath

if (-not $env:NEXT_PUBLIC_API_BASE) {
  $env:NEXT_PUBLIC_API_BASE = $BackendBase
}
if (-not $env:INTERNAL_API_BASE) {
  $env:INTERNAL_API_BASE = $BackendBase
}

$BackendProcess = Start-Process -FilePath $Python `
  -ArgumentList @("-m", "trade_review_agent.simple_api") `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -PassThru

Wait-HttpOk -Url "$BackendBase/api/health" -Process $BackendProcess -TimeoutSeconds 60

Start-Process -FilePath $Node `
  -ArgumentList @($NextBin, "dev", "--hostname", "127.0.0.1", "--port", "3000") `
  -WorkingDirectory $Frontend `
  -WindowStyle Hidden

Write-Host "Started backend:  $BackendBase/api/health"
Write-Host "Started frontend: http://127.0.0.1:3000/"
Write-Host "Frontend API:     $env:NEXT_PUBLIC_API_BASE"
Write-Host "Project: $Root"
