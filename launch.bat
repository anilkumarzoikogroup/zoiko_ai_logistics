@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set ROOT=%~dp0

echo ============================================================
echo  Zoiko AI Logistics -- Launch
echo ============================================================
echo.

REM ── Pre-flight checks ──────────────────────────────────────
if not exist ".env" ( echo  ERROR: .env not found. Run setup.bat first. & pause & exit /b 1 )
if not exist ".venv\Scripts\python.exe" ( echo  ERROR: .venv not found. Run setup.bat first. & pause & exit /b 1 )

REM ── Load .env variables ────────────────────────────────────
echo  Loading configuration...
.venv\Scripts\python _load_env.py >nul 2>&1
if exist ".env_tmp.bat" ( call ".env_tmp.bat" & del ".env_tmp.bat" >nul 2>&1 )
set ZOIKO_DEV_MODE=true
set ZOIKO_FF_SC_001_ENABLED=*
set PYTHONIOENCODING=utf-8
echo  Configuration loaded.
echo.

REM ── Test database connection (single-line — batch can't handle multiline -c)
echo  Checking database connection...
.venv\Scripts\python -c "import psycopg2,os,sys; url=os.environ.get('DB_URL','').strip(); lbl='Neon cloud' if 'neon.tech' in url else 'PostgreSQL'; conn=psycopg2.connect(url,connect_timeout=10); conn.close(); print('[OK] Connected to '+lbl+'.'); sys.exit(0)" 2>nul
if %errorlevel% neq 0 (
    echo  [FAIL] Cannot connect to database.
    echo  Check DB_URL in your .env file and ensure internet access for Neon.
    pause & exit /b 1
)
echo.

REM ── Kill stale Python / frontend processes ─────────────────
echo  Clearing stale processes...
taskkill /F /IM python.exe /T >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
timeout /t 3 /nobreak >nul
echo  Done.
echo.

REM ── Start Backend via start_phase2.py ──────────────────────
echo  Starting backend on port 8000...
start "Zoiko Backend :8000" cmd /k "cd /d %ROOT% && .venv\Scripts\python start_phase2.py"
echo  Waiting for backend to start (20s)...
timeout /t 20 /nobreak >nul

REM ── Start Frontend ─────────────────────────────────────────
echo  Starting frontend on port 5173...
start "Zoiko Frontend :5173" cmd /k "cd /d %ROOT%zoiko-frontend\frontend && npm run dev"
timeout /t 8 /nobreak >nul

REM ── Quick health check (single-line) ───────────────────────
.venv\Scripts\python -c "import urllib.request,json; r=urllib.request.urlopen('http://localhost:8000/health',timeout=8); d=json.loads(r.read()); print('  Backend: OK -- '+str(d['checks']['database']['cases'])+' cases')" 2>nul || echo   Backend still starting -- check Zoiko Backend window

REM ── Open browser ───────────────────────────────────────────
start "" "http://localhost:5173/login"

echo.
echo ============================================================
echo  ALL SERVICES RUNNING
echo  Frontend : http://localhost:5173
echo  Backend  : http://localhost:8000/docs
echo  Login    : admin@zoiko.com / changeme123
echo ============================================================
echo.
pause >nul
