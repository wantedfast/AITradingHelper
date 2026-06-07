$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$Node = "C:\Users\wantedfast\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$Python = "D:\an\python.exe"

if (-not (Test-Path $Node)) {
  throw "Node runtime not found: $Node"
}

if (-not (Test-Path $Python)) {
  $Python = "python"
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

Start-Process -FilePath $Python `
  -ArgumentList @("-m", "trade_review_agent.simple_api") `
  -WorkingDirectory $Root `
  -WindowStyle Hidden

Start-Sleep -Seconds 2

$backendListeners = @(Get-NetTCPConnection -LocalPort 8600 -State Listen -ErrorAction SilentlyContinue)
if ($backendListeners.Count -ne 1) {
  throw "Expected exactly one backend listener on port 8600, found $($backendListeners.Count)."
}

Start-Process -FilePath $Node `
  -ArgumentList @($NextBin, "dev", "--hostname", "127.0.0.1", "--port", "3000") `
  -WorkingDirectory $Frontend `
  -WindowStyle Hidden

Write-Host "Started backend:  http://127.0.0.1:8600/api/health"
Write-Host "Started frontend: http://127.0.0.1:3000/"
Write-Host "Project: $Root"
