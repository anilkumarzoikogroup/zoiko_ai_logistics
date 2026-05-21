@echo off
setlocal EnableDelayedExpansion

REM Always run from the folder where this bat file lives
cd /d "%~dp0"

echo ============================================================
echo  Zoiko AI Logistics -- Launch
echo ============================================================
echo.

REM ── Check venv exists ──────────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo  ERROR: .venv not found. Run setup.bat first.
    pause
    exit /b 1
)

REM ── Environment ────────────────────────────────────────────
set DB_URL=postgresql://postgres:1234@localhost/zoiko
set PYTHONIOENCODING=utf-8
set ZOIKO_DEV_MODE=true
set ROOT=%~dp0

REM ── Backend ────────────────────────────────────────────────
echo Starting Zoiko Backend (port 8000)...
start "Zoiko Backend" cmd /k "cd /d "%ROOT%phase-2" && call "%ROOT%.venv\Scripts\activate.bat" && set DB_URL=postgresql://postgres:1234@localhost/zoiko && set PYTHONIOENCODING=utf-8 && set ZOIKO_DEV_MODE=true && echo Backend starting at http://localhost:8000 && python -m uvicorn services.api_gateway.app:app --reload --host 0.0.0.0 --port 8000"
echo  Backend window opened.
echo.

REM ── Give backend a moment to bind ──────────────────────────
timeout /t 3 /nobreak >nul

REM ── Frontend ───────────────────────────────────────────────
echo Starting Zoiko Frontend...
start "Zoiko Frontend" cmd /k "cd /d "%ROOT%zoiko-frontend\frontend" && echo Frontend starting at http://localhost:5173 && npm run dev"
echo  Frontend window opened.
echo.

echo ============================================================
echo  Services are starting in separate windows.
echo.
echo  Backend  :  http://localhost:8000
echo  Frontend :  http://localhost:5173
echo  API Docs :  http://localhost:8000/docs
echo.
echo  Close those windows (or Ctrl+C in each) to stop.
echo ============================================================
echo.
pause
