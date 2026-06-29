@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo  Zoiko AI Logistics -- One-Time Setup
echo  Run this ONCE on a fresh machine, then use launch.bat
echo ============================================================
echo.

REM ── Step 1: Virtual environment ─────────────────────────────
echo [1/5] Creating Python virtual environment (.venv)...
if exist ".venv\Scripts\activate.bat" (
    echo  Already exists. Skipping.
    goto :step2
)
python -m venv .venv
if errorlevel 1 (
    echo  ERROR: Python 3.10+ required. Install from https://python.org
    pause & exit /b 1
)
echo  Created.

:step2
echo.

REM ── Step 2: Python packages ──────────────────────────────────
echo [2/5] Installing Python packages...
.venv\Scripts\python -c "import fastapi, uvicorn, psycopg2" 2>nul
if not errorlevel 1 goto :pip_skip

echo  Installing (requires internet ~2 min)...
.venv\Scripts\pip install -r requirements.txt -q
if errorlevel 1 (
    echo  WARNING: pip had errors. Check internet connection and try again.
)
.venv\Scripts\pip install -e backend\slices\sc-001-freight-invoice-overcharge\spine\core_lib\packages\zoiko-common -q 2>nul
.venv\Scripts\pip install -e backend\slices\sc-001-freight-invoice-overcharge\spine\platform_lib\packages\zoiko-kms -q 2>nul
echo  Done.
goto :step3

:pip_skip
echo  Packages already installed. Skipping.

:step3
echo.

REM ── Step 3: Database connection + migrations ─────────────────
echo [3/5] Running database migrations...
if not exist ".env" (
    echo  ERROR: .env not found.
    echo  Copy .env.example to .env and fill in your DB_URL, secrets, etc.
    pause & exit /b 1
)

.venv\Scripts\python _load_env.py >nul 2>&1
if exist ".env_tmp.bat" (
    call ".env_tmp.bat"
    del ".env_tmp.bat" >nul 2>&1
)

.venv\Scripts\python -c "import psycopg2,os; psycopg2.connect(os.environ.get('DB_URL',''),connect_timeout=10).close()" 2>nul
if errorlevel 1 (
    echo  WARNING: Cannot connect to database. Check DB_URL in .env
    echo  PostgreSQL must be running before continuing.
    set SKIP_DB=1
    goto :step4
)
echo  Database connected.
.venv\Scripts\python -m alembic -c alembic.ini upgrade head
if errorlevel 1 (
    echo  WARNING: Alembic migration had issues. Check logs.
) else (
    echo  Migrations up to date.
)
set SKIP_DB=0

:step4
echo.

REM ── Step 4: Seed admin user ──────────────────────────────────
echo [4/5] Seeding users...
if "!SKIP_DB!"=="1" (
    echo  SKIPPED (database not reachable).
    goto :step5
)
.venv\Scripts\python backend\slices\sc-001-freight-invoice-overcharge\spine\core_lib\scripts\seed_users.py 2>nul
echo  Done.

:step5
echo.

REM ── Step 5: Frontend setup ───────────────────────────────────
echo [5/5] Setting up frontend (React + Vite)...

REM Check Node.js >= 18
node -e "if(parseInt(process.versions.node)<18){process.exit(1)}" 2>nul
if errorlevel 1 (
    echo  ERROR: Node.js 18+ is required. Download from https://nodejs.org
    pause & exit /b 1
)

cd zoiko-frontend\frontend
call npm install --silent 2>nul
if errorlevel 1 (
    echo  WARNING: npm install had issues. Check Node.js version.
) else (
    echo  npm packages ready.
)
cd ..\..

REM Write all frontend environment variables
(
    echo VITE_USE_MOCK=false
    echo VITE_API_BASE=/api
    echo VITE_API3_BASE=/api3
    echo VITE_API4_BASE=/api4
    echo VITE_API_CLAIM_BASE=/claimapi
    echo VITE_API_CLAIM3_BASE=/claimapi3
    echo VITE_API_CLAIM4_BASE=/claimapi4
    echo VITE_API_EXC_BASE=/excapi
    echo VITE_API_EXC4_BASE=/excapi4
    echo VITE_API_SCORE_BASE=/scoreapi
    echo VITE_API_SCORE4_BASE=/scoreapi4
    echo VITE_API_ACC_BASE=/accapi
    echo VITE_API_ACC4_BASE=/accapi4
    echo VITE_DEV_TENANT=11111111-1111-1111-1111-111111111111
) > "zoiko-frontend\frontend\.env.local"
echo  .env.local written with all SC-001..005 proxy vars.
echo.

echo ============================================================
if "!SKIP_DB!"=="1" (
    echo  PARTIAL SETUP -- database not reached.
    echo  Fix DB_URL in .env, start PostgreSQL, then run setup.bat again.
) else (
    echo  SETUP COMPLETE.
    echo  Next step: double-click launch.bat to start everything.
)
echo ============================================================
echo.
pause
