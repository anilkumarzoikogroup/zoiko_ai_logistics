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
    echo  Created.
)
echo.

REM ── Step 2: Install Python dependencies ────────────────────
echo [2/5] Installing Python packages...
.venv\Scripts\python -c "import fastapi, uvicorn, psycopg2" 2>nul
if %errorlevel%==0 (
    echo  Packages already installed. Skipping pip.
) else (
    echo  Installing (requires internet)...
    .venv\Scripts\pip install -r requirements.txt -q 2>&1
    if errorlevel 1 (
        echo  WARNING: pip install had errors. Some packages may be missing.
        echo  If you have no internet, packages from a previous install will be used.
    ) else (
        echo  Done.
    )
    .venv\Scripts\pip install -e phase-0\packages\zoiko-common -q 2>nul
    .venv\Scripts\pip install -e phase-1\packages\zoiko-kms -q 2>nul
)
echo.

REM ── Step 3: Load .env and run DB migrations ─────────────────
echo [3/5] Running database migrations...
if not exist ".env" (
    echo  ERROR: .env file not found.
    echo  Create .env from .env.example and fill in your Neon DB_URL.
    pause & exit /b 1
)

.venv\Scripts\python _load_env.py >nul 2>&1
if exist ".env_tmp.bat" ( call ".env_tmp.bat" & del ".env_tmp.bat" >nul 2>&1 )

REM Test DB connection
.venv\Scripts\python -c "
import psycopg2, os, sys
url = os.environ.get('DB_URL','').strip()
if not url:
    print('  ERROR: DB_URL empty in .env')
    sys.exit(1)
try:
    conn = psycopg2.connect(url, connect_timeout=10)
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f'  Cannot connect: {e}')
    sys.exit(1)
" 2>&1

if %errorlevel% neq 0 (
    echo  WARNING: Database not reachable. Check DB_URL in .env and internet access.
    set SKIP_DB=1
) else (
    echo  Database connected. Running migrations...
    .venv\Scripts\python -m alembic -c alembic.ini upgrade head 2>&1
    if errorlevel 1 (
        echo  WARNING: Migrations failed. DB may already be up to date.
    ) else (
        echo  Migrations up to date.
    )
    set SKIP_DB=0
)
echo.

REM ── Step 4: Seed users ──────────────────────────────────────
echo [4/5] Seeding admin/analyst/manager users...
if "!SKIP_DB!"=="1" (
    echo  SKIPPED (database not reachable).
) else (
    .venv\Scripts\python seed_users.py 2>&1
    if errorlevel 1 (
        echo  Users may already exist (OK to ignore).
    ) else (
        echo  Done.
    )
)
echo.

REM ── Step 5: Install frontend and write .env.local ──────────
echo [5/5] Setting up frontend...
cd zoiko-frontend\frontend
call npm install --silent 2>nul
if errorlevel 1 (
    echo  WARNING: npm install failed. Check Node.js installation.
) else (
    echo  npm packages installed.
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
    echo  PARTIAL SETUP — database not reached.
    echo  Fix DB_URL in .env, then run setup.bat again.
) else (
    echo  SETUP COMPLETE.
    echo  Run launch.bat to start all services.
)
echo ============================================================
echo.
pause
