@echo off
title Zoiko AI Logistics
cd /d "%~dp0"

echo ============================================================
echo  Zoiko AI Logistics - Starting Services
echo ============================================================
echo.

REM Kill any existing processes on ports 8000 and 5173
echo [1/3] Clearing ports...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
timeout /t 2 /nobreak >nul
echo  Done.

REM Load .env variables
echo [2/3] Loading environment...
.venv\Scripts\python _load_env.py >nul 2>&1
if exist ".env_tmp.bat" ( call .env_tmp.bat & del .env_tmp.bat >nul 2>&1 )
echo  Done.

REM Start backend in new window
echo [3/3] Starting backend and frontend...
start "Zoiko Backend - Port 8000" cmd /k "cd /d %~dp0phase-2 && ..\\.venv\\Scripts\\python.exe -m uvicorn services.api_gateway.app:app --reload --host 0.0.0.0 --port 8000"

timeout /t 4 /nobreak >nul

REM Start frontend in new window
start "Zoiko Frontend - Port 5173" cmd /k "cd /d %~dp0zoiko-frontend\frontend && npm run dev"

timeout /t 6 /nobreak >nul

REM Check backend health
.venv\Scripts\python -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/health',timeout=5); print(' Backend: OK')" 2>nul || echo  Backend: starting (check the backend window)

echo.
echo ============================================================
echo  Services started!
echo  Frontend: http://localhost:5173
echo  Backend:  http://localhost:8000
echo  Login:    admin@zoiko.com / changeme123
echo ============================================================
echo.
start "" "http://localhost:5173"
pause
