@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo  Zoiko AI Logistics -- One-Time Setup
echo ============================================================
echo.

REM ── Step 1: Create virtual environment ─────────────────────
echo [1/5] Creating Python virtual environment...
if exist ".venv\Scripts\activate.bat" (
    echo  Already exists. Skipping.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo  ERROR: Python 3.10+ required. Install from python.org
        pause & exit /b 1
    )
)
echo.

REM ── Step 2: Install Python dependencies ────────────────────
echo [2/5] Installing Python packages...
.venv\Scripts\pip install -r requirements.txt -q
.venv\Scripts\pip install -e phase-0\packages\zoiko-common -q
.venv\Scripts\pip install -e phase-1\packages\zoiko-kms -q 2>nul
echo  Done.
echo.

REM ── Step 3: Load .env and run DB migrations ─────────────────
echo [3/5] Running database migrations...
if not exist ".env" (
    echo  ERROR: .env file not found.
    pause & exit /b 1
)
.venv\Scripts\python _load_env.py >nul 2>&1
if exist ".env_tmp.bat" ( call .env_tmp.bat & del .env_tmp.bat >nul 2>&1 )

.venv\Scripts\python -c "import psycopg2,os; psycopg2.connect(os.environ.get('DB_URL',''))" 2>nul
if errorlevel 1 (
    echo  WARNING: PostgreSQL not reachable. Start it then re-run setup.bat.
    set SKIP_DB=1
) else (
    .venv\Scripts\python -m alembic -c alembic.ini upgrade head
    if errorlevel 1 (
        echo  ERROR: Migration failed. Check DB_URL in .env
        pause & exit /b 1
    )
    echo  Migrations up to date.
    set SKIP_DB=0
)
echo.

REM ── Step 4: Seed users ──────────────────────────────────────
echo [4/5] Seeding admin/analyst/manager users...
if "!SKIP_DB!"=="1" (
    echo  SKIPPED. Run again after PostgreSQL starts.
) else (
    .venv\Scripts\python seed_users.py
)
echo.

REM ── Step 5: Install frontend and write .env.local ──────────
echo [5/5] Installing frontend and writing .env.local...
cd zoiko-frontend\frontend
call npm install --silent
if errorlevel 1 (
    echo  ERROR: npm install failed. Install Node.js from nodejs.org
    cd ..\..
    pause & exit /b 1
)
cd ..\..

REM Always write fresh .env.local with correct values
(
    echo VITE_USE_MOCK=false
    echo VITE_API_BASE=/api
    echo VITE_API3_BASE=/api3
    echo VITE_API4_BASE=/api4
) > "zoiko-frontend\frontend\.env.local"
echo  Done.
echo.

echo ============================================================
if "!SKIP_DB!"=="1" (
    echo  Partial setup. Start PostgreSQL then run setup.bat again.
) else (
    echo  Setup complete.
    echo  Run: cmd /c launch.bat
)
echo ============================================================
echo.
pause
