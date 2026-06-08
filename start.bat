@echo off
title Zoiko AI Logistics
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================================
echo  Zoiko AI Logistics - Start Everything
echo ============================================================
echo.

REM ── Step 1: Kill ALL stale Python / uvicorn processes ──────────────────────
echo [1/4] Clearing stale processes...
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul
REM Also free specific ports
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul
echo  Done.

REM ── Step 2: Load .env variables ────────────────────────────────────────────
echo [2/4] Loading environment...
.venv\Scripts\python _load_env.py >nul 2>&1
if exist ".env_tmp.bat" (
    call .env_tmp.bat
    del .env_tmp.bat >nul 2>&1
)
REM ZOIKO_DEV_MODE must always be true in dev (not stored in .env for safety)
set ZOIKO_DEV_MODE=true
set ZOIKO_FF_SC_001_ENABLED=*
set PYTHONIOENCODING=utf-8
echo  Done.

REM ── Step 3: Start backend (no --reload so long requests are never killed) ──
echo [3/4] Starting backend on port 8000...
start "Zoiko Backend :8000" cmd /k "cd /d "%~dp0phase-2" && set ZOIKO_DEV_MODE=true && set ZOIKO_FF_SC_001_ENABLED=* && set PYTHONIOENCODING=utf-8 && "%~dp0.venv\Scripts\python.exe" -m uvicorn services.api_gateway.app:app --host 0.0.0.0 --port 8000"
timeout /t 20 /nobreak >nul

REM ── Step 4: Start frontend ─────────────────────────────────────────────────
echo [4/4] Starting frontend on port 5173...
start "Zoiko Frontend :5173" cmd /k "cd /d "%~dp0zoiko-frontend\frontend" && npm run dev"
timeout /t 8 /nobreak >nul

REM ── Health check ───────────────────────────────────────────────────────────
.venv\Scripts\python -c "import urllib.request,sys; r=urllib.request.urlopen('http://localhost:8000/health',timeout=10); print(' Backend: OK'); sys.exit(0)" 2>nul && goto :ok
echo  Backend still starting — check the 'Zoiko Backend :8000' window for errors.
goto :done

:ok
echo.
echo ============================================================
echo  ALL SERVICES RUNNING
echo  Frontend : http://localhost:5173
echo  Backend  : http://localhost:8000
echo  Login    : admin@zoiko.com / changeme123
echo ============================================================
:done
echo.
start "" "http://localhost:5173"
pause
