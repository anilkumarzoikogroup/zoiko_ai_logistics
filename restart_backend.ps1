# ============================================================
#  Zoiko AI — Backend Restart Script
#  Double-click this file OR run: pwsh restart_backend.ps1
#  This script: kills stale processes → reads .env → starts
#  a single clean backend on port 8000 → confirms it's up
# ============================================================

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON = "$ROOT\.venv\Scripts\python.exe"
$PHASE2 = "$ROOT\phase-2"
$ENV_FILE = "$ROOT\.env"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Zoiko AI - Backend Restart" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# --- Step 1: Kill ALL existing Python / uvicorn processes --------------------
Write-Host ""
Write-Host "[1/3] Stopping existing processes..." -ForegroundColor Yellow
Get-Process python* -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3

# Double-check port 8000 is free
netstat -ano | Select-String ":8000 " | Select-String "LISTEN" | ForEach-Object {
    $parts = ($_ -split "\s+"); $p = $parts[-1].Trim()
    if ($p -match "^\d+$" -and [int]$p -gt 0) { taskkill /PID $p /F 2>$null | Out-Null }
}
Start-Sleep -Seconds 2
Write-Host "  Done — port 8000 is free." -ForegroundColor Green

# --- Step 2: Read .env file --------------------------------------------------
Write-Host "[2/3] Loading environment from .env..." -ForegroundColor Yellow

$envVars = @{
    "ZOIKO_DEV_MODE"           = "true"
    "ZOIKO_FF_SC_001_ENABLED"  = "*"
    "PYTHONIOENCODING"         = "utf-8"
}

if (Test-Path $ENV_FILE) {
    Get-Content $ENV_FILE | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line -match "^([^=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim()
            if ($key -and $val) { $envVars[$key] = $val }
        }
    }
    Write-Host "  .env loaded ($(($envVars.Keys).Count) variables)." -ForegroundColor Green
} else {
    Write-Host "  WARNING: .env not found — using defaults." -ForegroundColor Red
}

# --- Step 3: Start backend ---------------------------------------------------
Write-Host "[3/3] Starting backend on port 8000..." -ForegroundColor Yellow

# Use start_phase2.py which loads .env and sets all vars correctly
$proc = Start-Process -FilePath $PYTHON `
    -ArgumentList "$ROOT\start_phase2.py" `
    -WorkingDirectory $ROOT `
    -PassThru -WindowStyle Normal
Write-Host "  Backend PID: $($proc.Id)" -ForegroundColor Green

# --- Wait and health-check ---------------------------------------------------
Write-Host ""
Write-Host "Waiting for backend to start (up to 40s)..." -ForegroundColor Yellow
$up = $false
for ($i = 1; $i -le 8; $i++) {
    Start-Sleep -Seconds 5
    try {
        $h = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 4
        if ($h.status -eq "ok") {
            Write-Host ""
            Write-Host "============================================================" -ForegroundColor Green
            Write-Host "  BACKEND IS UP!" -ForegroundColor Green
            Write-Host "  URL:    http://localhost:8000" -ForegroundColor Green
            Write-Host "  Cases:  $($h.checks.database.cases)" -ForegroundColor Green
            Write-Host "  DB:     $($h.checks.database.status)" -ForegroundColor Green
            Write-Host "============================================================" -ForegroundColor Green
            $up = $true
            break
        }
    } catch {
        Write-Host "  Still starting... ($($i*5)s)" -ForegroundColor Gray
    }
}

if (-not $up) {
    Write-Host ""
    Write-Host "  Backend did not start in time. Check the backend window for errors." -ForegroundColor Red
}

Write-Host ""
Write-Host "Press any key to exit this window (backend keeps running)..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
