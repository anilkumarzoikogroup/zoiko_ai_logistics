@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo  Zoiko AI Logistics -- One-Time Setup
echo ============================================================
echo.

REM ── Step 1: Virtual environment ─────────────────────────────
echo [1/5] Creating Python virtual environment...
if exist ".venv\Scripts\activate.bat" (
    echo  Already exists. Skipping.
    goto :step2
)
python -m venv .venv
if errorlevel 1 (
    echo  ERROR: Python 3.10+ required.
    pause & exit /b 1
)
echo  Created.

:step2
echo.

REM ── Step 2: Python packages ──────────────────────────────────
echo [2/5] Installing Python packages...
.venv\Scripts\python -c "import fastapi, uvicorn, psycopg2" 2>nul
if not errorlevel 1 goto :pip_skip

echo  Installing (requires internet)...
.venv\Scripts\pip install -r requirements.txt -q
if errorlevel 1 (
    echo  WARNING: pip had errors ^(no internet?^). Using existing packages.
)
.venv\Scripts\pip install -e phase-0\packages\zoiko-common -q 2>nul
.venv\Scripts\pip install -e phase-1\packages\zoiko-kms -q 2>nul
echo  Done.
goto :step3

:pip_skip
echo  Packages already installed. Skipping.

:step3
echo.

REM ── Step 3: Database connection + migrations ─────────────────
echo [3/5] Running database migrations...
if not exist ".env" (
    echo  ERROR: .env not found. Create it from .env.example
    pause & exit /b 1
)

.venv\Scripts\python _load_env.py >nul 2>&1
if exist ".env_tmp.bat" (
    call ".env_tmp.bat"
    del ".env_tmp.bat" >nul 2>&1
)

.venv\Scripts\python -c "import psycopg2,os,sys; url=os.environ.get('DB_URL','').strip(); conn=psycopg2.connect(url,connect_timeout=10); conn.close()" 2>nul
if errorlevel 1 (
    echo  WARNING: Cannot connect to database. Check DB_URL in .env
    set SKIP_DB=1
    goto :step4
)
echo  Database connected.
.venv\Scripts\python -m alembic -c alembic.ini upgrade head 2>nul
echo  Migrations up to date.
set SKIP_DB=0

:step4
echo.

REM ── Step 4: Seed users ───────────────────────────────────────
echo [4/5] Seeding users...
if "!SKIP_DB!"=="1" (
    echo  SKIPPED ^(database not reachable^).
    goto :step5
)
.venv\Scripts\python seed_users.py 2>nul
echo  Done.

:step5
echo.

REM ── Step 5: Frontend setup ───────────────────────────────────
echo [5/5] Setting up frontend...

REM Check Node.js >= 18
node -e "if(parseInt(process.versions.node)<18){process.exit(1)}" 2>nul
if errorlevel 1 (
    echo  ERROR: Node.js 18+ is required. Install it from https://nodejs.org
    pause & exit /b 1
)

cd zoiko-frontend\frontend
call npm install --silent 2>nul
if errorlevel 1 (
    echo  WARNING: npm install had issues. Check Node.js.
) else (
    echo  npm packages ready.
)
cd ..\..

(
    echo VITE_USE_MOCK=false
    echo VITE_API_BASE=/api
    echo VITE_API3_BASE=/api3
    echo VITE_API4_BASE=/api4
) > "zoiko-frontend\frontend\.env.local"
echo  .env.local written.
echo.

echo ============================================================
if "!SKIP_DB!"=="1" (
    echo  PARTIAL -- database not reached. Fix DB_URL, run again.
) else (
    echo  SETUP COMPLETE. Run: launch.bat
)
echo ============================================================
echo.
pause
