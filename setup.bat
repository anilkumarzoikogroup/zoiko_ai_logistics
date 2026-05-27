@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo  Zoiko AI Logistics -- One-Time Setup
echo ============================================================
echo.

REM ── Load .env ───────────────────────────────────────────────
if not exist ".env" (
    echo  ERROR: .env file not found. Create it from .env.example
    pause
    exit /b 1
)
for /f "usebackq tokens=* delims=" %%l in (".env") do (
    set "line=%%l"
    if not "!line:~0,1!"=="#" if not "!line!"=="" set "%%l"
)
echo  Loaded configuration from .env
echo.

REM ── Step 0: Check PostgreSQL ────────────────────────────────
echo [0/6] Checking PostgreSQL connection...
python -c "import psycopg2; psycopg2.connect('%DB_URL%')" 2>nul
if errorlevel 1 (
    echo.
    echo  WARNING: PostgreSQL is not reachable.
    echo  Steps [3] and [4] will be skipped.
    echo  Start PostgreSQL, then re-run setup.bat to complete them.
    echo.
    set SKIP_DB=1
) else (
    echo  PostgreSQL OK.
    set SKIP_DB=0
)
echo.

REM ── Step 1: Create virtual environment ─────────────────────
echo [1/6] Creating Python virtual environment (.venv)...
if exist ".venv\Scripts\activate.bat" (
    echo  .venv already exists -- skipping creation.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo  ERROR: Could not create venv. Make sure Python 3.10+ is on your PATH.
        pause
        exit /b 1
    )
    echo  Created .venv
)
echo.

REM ── Step 2: Install Python dependencies ────────────────────
echo [2/6] Installing Python dependencies into .venv...
.venv\Scripts\pip install -r requirements.txt -q
if errorlevel 1 (
    echo  ERROR: pip install failed. See errors above.
    pause
    exit /b 1
)
.venv\Scripts\pip install -e phase-0\packages\zoiko-common -q
.venv\Scripts\pip install -e phase-1\packages\zoiko-kms -q 2>nul
echo  Done.
echo.

REM ── Step 3: Run Alembic migrations ─────────────────────────
echo [3/6] Running Alembic database migrations...
if "%SKIP_DB%"=="1" (
    echo  SKIPPED -- PostgreSQL not available.
) else (
    cd phase-0\db
    ..\..\\.venv\Scripts\python -m alembic upgrade head
    if errorlevel 1 (
        echo  ERROR: Alembic migration failed. Check PostgreSQL is running.
        cd ..\..
        pause
        exit /b 1
    )
    cd ..\..
    echo  Done.
)
echo.

REM ── Step 4: Seed contract rates ────────────────────────────
echo [4/6] Seeding contract rates...
if "%SKIP_DB%"=="1" (
    echo  SKIPPED -- PostgreSQL not available.
) else (
    cd phase-2
    ..\.venv\Scripts\python seed_contract_rates.py
    if errorlevel 1 (
        echo  WARNING: Seeding skipped -- rates may already exist.
    ) else (
        echo  Seeded.
    )
    cd ..
)
echo.

REM ── Step 5: Install npm dependencies ───────────────────────
echo [5/6] Installing frontend npm dependencies...
cd zoiko-frontend\frontend
call npm install --silent
if errorlevel 1 (
    echo  ERROR: npm install failed. Make sure Node.js is installed.
    cd ..\..
    pause
    exit /b 1
)
cd ..\..
echo  Done.
echo.

REM ── Step 6: Create frontend .env.local ─────────────────────
echo [6/6] Creating frontend .env.local...
if not exist "zoiko-frontend\frontend\.env.local" (
    (
        echo VITE_USE_MOCK=false
        echo VITE_API_BASE=http://localhost:8000
        echo VITE_DEV_JWT=dev-token
        echo VITE_DEV_TENANT=amazon-india
    ) > "zoiko-frontend\frontend\.env.local"
    echo  Created .env.local
) else (
    echo  .env.local already exists -- skipping.
)
echo.

if "%SKIP_DB%"=="1" (
    echo ============================================================
    echo  Partial setup complete.
    echo  Start PostgreSQL, then run setup.bat again to finish
    echo  database migrations and contract rate seeding.
    echo ============================================================
) else (
    echo ============================================================
    echo  Setup complete! Run launch.bat to start the app.
    echo ============================================================
)
echo.
pause
