@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set ROOT=%~dp0

echo ============================================================
echo  Zoiko AI Logistics -- Launch
echo ============================================================
echo.

if not exist ".env" ( echo  ERROR: .env not found. Run setup.bat first. & pause & exit /b 1 )
if not exist ".venv\Scripts\python.exe" ( echo  ERROR: .venv not found. Run setup.bat first. & pause & exit /b 1 )

REM ── Load .env ───────────────────────────────────────────────
.venv\Scripts\python _load_env.py >nul 2>&1
if exist ".env_tmp.bat" ( call .env_tmp.bat & del .env_tmp.bat >nul 2>&1 )
echo  Configuration loaded.

REM ── Check PostgreSQL ────────────────────────────────────────
echo  Checking PostgreSQL...
.venv\Scripts\python -c "import psycopg2,os; psycopg2.connect(os.environ.get('DB_URL',''))" 2>nul
if %errorlevel%==0 (
    set DB_ONLINE=1
    echo  [OK] PostgreSQL running. Starting in LIVE MODE.
) else (
    set DB_ONLINE=0
    echo  [WARN] PostgreSQL not reachable. Start it and re-run.
    pause & exit /b 1
)
echo.

REM ── Kill any stale services on our ports ─────────────────────
echo  Stopping any stale services on ports 8000 8001 8002 8010 8011 8012 8020 8021 8030 5173...
for %%P in (8000 8001 8002 8010 8011 8012 8020 8021 8030 5173) do (
    for /f "tokens=5" %%A in ('netstat -aon 2^>nul ^| findstr ":%%P " ^| findstr "LISTENING"') do (
        taskkill /PID %%A /F >nul 2>&1
    )
)
timeout /t 2 /nobreak >nul
echo  [OK] Old services cleared.
echo.

REM ── Migrations ──────────────────────────────────────────────
.venv\Scripts\python -m alembic -c alembic.ini upgrade head 2>nul
echo  Migrations up to date.
echo.

REM ════════════════════════════════════════════════════════════
REM  SC-001 (freight invoice overcharge) — gateway/execution/governance
REM ════════════════════════════════════════════════════════════
set SC001=%ROOT%backend\slices\sc-001-freight-invoice-overcharge\spine
set PYPATH_SC001=%SC001%\platform_lib;%SC001%\core_lib\packages\zoiko-common

echo  Starting SC-001 Gateway on port 8000...
start "SC001-Gateway" /d "%SC001%\gateway" cmd /k "call ..\..\..\..\..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "ZOIKO_FF_SC_001_ENABLED=*" && set "ZOIKO_COMPANY_NAME=!ZOIKO_COMPANY_NAME!" && set "ZOIKO_ADMIN_EMAIL=!ZOIKO_ADMIN_EMAIL!" && set "ZOIKO_ADMIN_PASSWORD=!ZOIKO_ADMIN_PASSWORD!" && set "ZOIKO_ADMIN_NAME=!ZOIKO_ADMIN_NAME!" && set "JWT_TTL_SECONDS=!JWT_TTL_SECONDS!" && set "GOOGLE_CLIENT_ID=!GOOGLE_CLIENT_ID!" && set "GOOGLE_CLIENT_SECRET=!GOOGLE_CLIENT_SECRET!" && set "GROQ_API_KEY=!GROQ_API_KEY!" && set "GROQ_MODEL=!GROQ_MODEL!" && set "PYTHONIOENCODING=utf-8" && set "PYTHONPATH=%PYPATH_SC001%" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8000"

echo  Starting SC-001 Governance on port 8002...
start "SC001-Governance" /d "%SC001%\governance" cmd /k "call ..\..\..\..\..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "PYTHONIOENCODING=utf-8" && set "PYTHONPATH=%PYPATH_SC001%" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8002"

echo  Starting SC-001 Execution on port 8001...
start "SC001-Execution" /d "%SC001%\execution" cmd /k "call ..\..\..\..\..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "REDIS_URL=!REDIS_URL!" && set "GROQ_API_KEY=!GROQ_API_KEY!" && set "GROQ_MODEL=!GROQ_MODEL!" && set "TOKEN_TTL_MINUTES=!TOKEN_TTL_MINUTES!" && set "PYTHONIOENCODING=utf-8" && set "PYTHONPATH=%PYPATH_SC001%" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8001"

REM ════════════════════════════════════════════════════════════
REM  SC-002 (carrier claim) — gateway/execution/governance
REM ════════════════════════════════════════════════════════════
set SC002=%ROOT%backend\slices\sc-002-carrier-claim\spine
set PYPATH_SC002=%SC002%\platform_lib;%SC002%\core_lib\packages\zoiko-common

echo  Starting SC-002 Gateway on port 8010...
start "SC002-Gateway" /d "%SC002%\gateway" cmd /k "call ..\..\..\..\..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "GROQ_API_KEY=!GROQ_API_KEY!" && set "GROQ_MODEL=!GROQ_MODEL!" && set "PYTHONIOENCODING=utf-8" && set "PYTHONPATH=%PYPATH_SC002%" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8010"

echo  Starting SC-002 Governance on port 8012...
start "SC002-Governance" /d "%SC002%\governance" cmd /k "call ..\..\..\..\..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "PYTHONIOENCODING=utf-8" && set "PYTHONPATH=%PYPATH_SC002%" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8012"

echo  Starting SC-002 Execution on port 8011...
start "SC002-Execution" /d "%SC002%\execution" cmd /k "call ..\..\..\..\..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "REDIS_URL=!REDIS_URL!" && set "GROQ_API_KEY=!GROQ_API_KEY!" && set "GROQ_MODEL=!GROQ_MODEL!" && set "PYTHONIOENCODING=utf-8" && set "PYTHONPATH=%PYPATH_SC002%" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8011"

REM ════════════════════════════════════════════════════════════
REM  SC-003 (shipment exception / SLA breach) — gateway + execution
REM ════════════════════════════════════════════════════════════
set SC003=%ROOT%backend\slices\sc-003-shipment-exception\spine
set PYPATH_SC003=%SC002%\platform_lib;%SC002%\core_lib\packages\zoiko-common

echo  Starting SC-003 Gateway on port 8020...
start "SC003-Gateway" /d "%SC003%\gateway" cmd /k "call ..\..\..\..\..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "REDIS_URL=!REDIS_URL!" && set "PYTHONIOENCODING=utf-8" && set "PYTHONPATH=%PYPATH_SC003%" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8020"

echo  Starting SC-003 Execution on port 8021...
start "SC003-Execution" /d "%SC003%\execution" cmd /k "call ..\..\..\..\..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "REDIS_URL=!REDIS_URL!" && set "PYTHONIOENCODING=utf-8" && set "PYTHONPATH=%PYPATH_SC003%" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8021"

REM ════════════════════════════════════════════════════════════
REM  SC-004 (supplier scorecard) — gateway only
REM ════════════════════════════════════════════════════════════
set SC004=%ROOT%backend\slices\sc-004-supplier-scorecard\spine
set PYPATH_SC004=%SC002%\platform_lib;%SC002%\core_lib\packages\zoiko-common

echo  Starting SC-004 Scorecard Gateway on port 8030...
start "SC004-Gateway" /d "%SC004%\gateway" cmd /k "call ..\..\..\..\..\.venv\Scripts\activate.bat && set "DB_URL=!DB_URL!" && set "ZOIKO_DEV_MODE=!ZOIKO_DEV_MODE!" && set "ZOIKO_DEV_SECRET=!ZOIKO_DEV_SECRET!" && set "ZOIKO_ISSUER=!ZOIKO_ISSUER!" && set "PYTHONIOENCODING=utf-8" && set "PYTHONPATH=%PYPATH_SC004%" && python -m uvicorn services.api_gateway.app:app --workers 4 --host 0.0.0.0 --port 8030"

REM ── Poll both gateways before starting frontend ─────────────
echo  Waiting for both gateways to be ready...
set RETRIES=0
:wait_gateways
curl -sf http://localhost:8000/health >nul 2>&1 && curl -sf http://localhost:8010/health >nul 2>&1
if %errorlevel%==0 goto :gateways_ready
set /a RETRIES+=1
if %RETRIES% gtr 30 (
    echo  [WARN] Gateways did not respond after 30s. Continuing anyway.
    goto :gateways_ready
)
timeout /t 1 /nobreak >nul
goto :wait_gateways
:gateways_ready
echo  [OK] Gateways ready.
echo.

REM ── Start Frontend (port 5173) — always LIVE ─────────────────
echo  Starting Frontend on port 5173...
start "Zoiko-Frontend" /d "%ROOT%zoiko-frontend\frontend" cmd /k "set VITE_USE_MOCK=false && npm run dev"
echo.

REM ── Open browser after brief Vite startup ────────────────────
timeout /t 3 /nobreak >nul
start "" "http://localhost:5173/login"

echo ============================================================
echo  LIVE MODE
echo  Frontend        :  http://localhost:5173
echo  SC-001 Gateway  :  http://localhost:8000/docs
echo  SC-002 Gateway  :  http://localhost:8010/docs
echo  SC-003 Gateway  :  http://localhost:8020/docs
echo  SC-004 Scorecard:  http://localhost:8030/docs
echo ============================================================
echo.
echo  Press any key to close. Servers keep running.
pause >nul