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

REM ── Kill stale processes on used ports ──────────────────────
echo  Clearing stale processes on ports 8000, 8001, 8002, 5173...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8001 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8002 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
echo  Ports cleared.
echo.

REM ── Migrations ──────────────────────────────────────────────
.venv\Scripts\python -m alembic -c alembic.ini upgrade head 2>nul
echo  Migrations up to date.
echo.

REM ── Start Phase 2 (port 8000) ───────────────────────────────
echo  Starting Phase 2 on port 8000...
start "Zoiko-Phase2" /d "%ROOT%phase-2" cmd /k "call ..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "ZOIKO_FF_SC_001_ENABLED=*" && set "ZOIKO_COMPANY_NAME=!ZOIKO_COMPANY_NAME!" && set "ZOIKO_ADMIN_EMAIL=!ZOIKO_ADMIN_EMAIL!" && set "ZOIKO_ADMIN_PASSWORD=!ZOIKO_ADMIN_PASSWORD!" && set "ZOIKO_ADMIN_NAME=!ZOIKO_ADMIN_NAME!" && set "JWT_TTL_SECONDS=!JWT_TTL_SECONDS!" && set "GOOGLE_CLIENT_ID=!GOOGLE_CLIENT_ID!" && set "GOOGLE_CLIENT_SECRET=!GOOGLE_CLIENT_SECRET!" && set "PYTHONIOENCODING=utf-8" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8000"

REM ── Start Phase 3 (port 8002) ───────────────────────────────
echo  Starting Phase 3 on port 8002...
start "Zoiko-Phase3" /d "%ROOT%phase-3" cmd /k "call ..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "PYTHONIOENCODING=utf-8" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8002"

REM ── Start Phase 4 (port 8001) ───────────────────────────────
echo  Starting Phase 4 on port 8001...
start "Zoiko-Phase4" /d "%ROOT%phase-4" cmd /k "call ..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "PYTHONIOENCODING=utf-8" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8001"

REM ── Poll Phase 2 health before starting frontend ─────────────
echo  Waiting for Phase 2 to be ready...
set RETRIES=0
:wait_phase2
curl -sf http://localhost:8000/health >nul 2>&1
if %errorlevel%==0 goto :phase2_ready
set /a RETRIES+=1
if %RETRIES% gtr 30 (
    echo  [WARN] Phase 2 did not respond after 30s. Continuing anyway.
    goto :phase2_ready
)
timeout /t 1 /nobreak >nul
goto :wait_phase2
:phase2_ready
echo  [OK] Phase 2 ready.
echo.

REM ── Start Frontend (port 5173) ───────────────────────────────
echo  Starting Frontend on port 5173...
start "Zoiko-Frontend" /d "%ROOT%zoiko-frontend\frontend" cmd /k "set VITE_USE_MOCK=false && npm run dev"
timeout /t 8 /nobreak >nul

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
