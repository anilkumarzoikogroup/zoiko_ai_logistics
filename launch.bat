@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set ROOT=%~dp0

echo ============================================================
echo  Zoiko AI Logistics -- Launch
echo ============================================================
echo.

REM ── Pre-flight checks ──────────────────────────────────────
if not exist ".env" (
    echo  ERROR: .env not found. Run setup.bat first.
    pause & exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo  ERROR: .venv not found. Run setup.bat first.
    pause & exit /b 1
)

REM ── Load all .env variables into this process ───────────────
echo  Loading configuration...
.venv\Scripts\python _load_env.py >nul 2>&1
if exist ".env_tmp.bat" ( call ".env_tmp.bat" & del ".env_tmp.bat" >nul 2>&1 )

REM Always set these dev-mode vars (not stored in .env for safety)
set ZOIKO_DEV_MODE=true
set ZOIKO_FF_SC_001_ENABLED=*
set PYTHONIOENCODING=utf-8

echo  Configuration loaded.
echo.

REM ── Test database connection ────────────────────────────────
echo  Checking database connection...
.venv\Scripts\python -c "
import psycopg2, os, sys
url = os.environ.get('DB_URL','').strip()
if not url:
    print('ERROR: DB_URL is empty. Check your .env file.')
    sys.exit(1)
label = 'Neon cloud' if 'neon.tech' in url else 'PostgreSQL'
try:
    conn = psycopg2.connect(url, connect_timeout=10)
    conn.close()
    print(f'[OK] Connected to {label}.')
    sys.exit(0)
except Exception as e:
    print(f'[FAIL] Cannot connect to {label}: {e}')
    sys.exit(1)
" 2>&1

if %errorlevel% neq 0 (
    echo.
    echo  Cannot connect to the database. Check your .env DB_URL.
    echo  If using Neon, make sure you have internet access.
    pause & exit /b 1
)
echo.

REM ── Kill stale processes ────────────────────────────────────
echo  Clearing stale processes...
taskkill /F /IM python.exe /T >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
timeout /t 3 /nobreak >nul
echo  Done.
echo.

REM ── Start Backend (port 8000) using start_phase2.py ─────────
echo  Starting backend on port 8000...
start "Zoiko Backend :8000" cmd /k "cd /d "%ROOT%" && .venv\Scripts\python start_phase2.py"
echo  Waiting for backend to start (20s)...
timeout /t 20 /nobreak >nul

REM ── Start Frontend (port 5173) ─────────────────────────────
echo  Starting frontend on port 5173...
start "Zoiko Frontend :5173" cmd /k "cd /d "%ROOT%zoiko-frontend\frontend" && npm run dev"
timeout /t 8 /nobreak >nul

REM ── Health check ───────────────────────────────────────────
.venv\Scripts\python -c "
import urllib.request, json, sys
try:
    r = urllib.request.urlopen('http://localhost:8000/health', timeout=8)
    d = json.loads(r.read())
    print(f'  Backend: {d.get(\"status\",\"?\").upper()} — {d[\"checks\"][\"database\"][\"cases\"]} cases in DB')
except:
    print('  Backend still starting... check the Zoiko Backend window')
" 2>&1

echo.

REM ── Open browser ────────────────────────────────────────────
start "" "http://localhost:5173/login"

echo ============================================================
echo  ALL SERVICES RUNNING
echo  Frontend : http://localhost:5173
echo  Backend  : http://localhost:8000/docs
echo  Login    : admin@zoiko.com / changeme123
echo ============================================================
echo.
pause >nul
