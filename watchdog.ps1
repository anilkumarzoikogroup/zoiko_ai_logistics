# Zoiko Backend Watchdog — aggressive 5-second monitoring
$ROOT   = "c:\Company_Projects_Zoiko\zoiko_ai"
$VENV   = "$ROOT\.venv\Scripts\python.exe"
$PHASE2 = "$ROOT\phase-2"
$HEALTH = "http://localhost:8000/health"
$LOG    = "$ROOT\watchdog.log"

function Log($msg) {
    "$((Get-Date -Format 'HH:mm:ss'))  $msg" | Tee-Object -FilePath $LOG -Append
}

function Is-ZoikoUp {
    try {
        $r = Invoke-RestMethod -Uri $HEALTH -TimeoutSec 2
        return $r.service -eq "api-gateway"
    } catch { return $false }
}

function Kill-Port8000 {
    netstat -ano | Select-String ":8000 " | Select-String "LISTENING" |
    ForEach-Object {
        $p = ($_ -split '\s+')[-1]
        if ($p -match '^\d+$') { taskkill /PID $p /F 2>$null | Out-Null }
    }
}

function Start-ZoikoBackend {
    Kill-Port8000
    Start-Sleep -Seconds 1

    # Load env vars from .env file
    $envFile = "$ROOT\.env"
    if (Test-Path $envFile) {
        Get-Content $envFile | Where-Object { $_ -match '^\s*[^#].*=.*' } | ForEach-Object {
            $parts = $_ -split '=', 2
            if ($parts.Count -eq 2) {
                $k = $parts[0].Trim()
                $v = $parts[1].Trim()
                [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
            }
        }
    }

    $env:PYTHONIOENCODING = "utf-8"

    $proc = Start-Process -FilePath $VENV `
        -ArgumentList "-m uvicorn services.api_gateway.app:app --host 0.0.0.0 --port 8000" `
        -WorkingDirectory $PHASE2 -PassThru -WindowStyle Minimized `
        -EnvironmentBlock ([System.Environment]::GetEnvironmentVariables())
    Log "Started backend PID $($proc.Id)"
    Start-Sleep -Seconds 6
    return (Is-ZoikoUp)
}

Log "=== Watchdog started ==="

if (-not (Is-ZoikoUp)) {
    Log "Starting backend on init..."
    $ok = Start-ZoikoBackend
    Log "Init result: $(if($ok){'OK'}else{'FAILED — will retry'})"
}

$failCount = 0
while ($true) {
    Start-Sleep -Seconds 5      # check every 5 seconds

    if (-not (Is-ZoikoUp)) {
        $failCount++
        Log "Backend down (fail #$failCount) — restarting..."
        $ok = Start-ZoikoBackend
        if ($ok) {
            Log "Backend restored"
            $failCount = 0
        }
    } else {
        $failCount = 0
    }
}
