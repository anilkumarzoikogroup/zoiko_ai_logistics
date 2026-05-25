@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set ROOT=%~dp0

echo ============================================================
echo  Zoiko AI Logistics -- Launch
echo ============================================================
echo.

REM ── Check if PostgreSQL is reachable ───────────────────────
echo Checking PostgreSQL connection...
python -c "import psycopg2; psycopg2.connect('postgresql://postgres:1234@localhost/zoiko'); print('DB_OK')" 2>nul | find "DB_OK" >nul
if %errorlevel%==0 (
    set DB_ONLINE=1
    echo  [OK] PostgreSQL is running.
) else (
    set DB_ONLINE=0
    echo  [WARN] PostgreSQL not reachable. Starting in MOCK MODE.
    echo         Frontend will use demo data only.
    echo         Install PostgreSQL to enable live data.
)
echo.

REM ── Backend (only if DB is online) ─────────────────────────
if "%DB_ONLINE%"=="1" (
    echo Starting Zoiko Backend (port 8000^)...
    start "Zoiko Backend" cmd /k "cd /d "%ROOT%phase-2" && call "%ROOT%.venv\Scripts\activate.bat" && set DB_URL=postgresql://postgres:1234@localhost/zoiko && set PYTHONIOENCODING=utf-8 && set ZOIKO_DEV_MODE=true && echo Backend ready at http://localhost:8000 && python -m uvicorn services.api_gateway.app:app --reload --host 0.0.0.0 --port 8000"
    echo  Backend window opened.
    timeout /t 3 /nobreak >nul
) else (
    echo  Skipping backend (no DB).
)
echo.

REM ── Frontend (always starts) ────────────────────────────────
echo Starting Zoiko Frontend (port 5173^)...
if "%DB_ONLINE%"=="1" (
    REM Live mode — talk to real backend
    start "Zoiko Frontend" cmd /k "cd /d "%ROOT%zoiko-frontend\frontend" && set VITE_USE_MOCK=false && echo Frontend ready at http://localhost:5173 && npm run dev"
) else (
    REM Mock mode — demo data, no backend needed
    start "Zoiko Frontend" cmd /k "cd /d "%ROOT%zoiko-frontend\frontend" && echo [MOCK MODE] Frontend ready at http://localhost:5173 && npm run dev"
)
echo  Frontend window opened.
echo.

REM ── Auto-open browser ───────────────────────────────────────
timeout /t 4 /nobreak >nul
start "" "http://localhost:5173"

echo ============================================================
if "%DB_ONLINE%"=="1" (
    echo  LIVE MODE
    echo  Backend  :  http://localhost:8000
    echo  API Docs :  http://localhost:8000/docs
) else (
    echo  MOCK MODE  ^(demo data, no database required^)
)
echo  Frontend :  http://localhost:5173
echo.
echo  To enable live data: install PostgreSQL, create 'zoiko' DB,
echo  run migrations, then re-run this bat file.
echo ============================================================
echo.
pause
