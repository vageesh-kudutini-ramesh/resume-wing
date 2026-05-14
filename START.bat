@echo off
setlocal EnableDelayedExpansion
title ResumeWing — Startup

:: ─────────────────────────────────────────────────────────────────────────────
::  ResumeWing — Start All Services
::
::  What this script does:
::    1. Validates the Python virtual environment and Node modules
::    2. Opens the FastAPI backend  in a new window on http://localhost:8000
::    3. Waits 15 seconds for AI models (sentence-transformers) to warm up
::    4. Opens the Next.js frontend in a new window on http://localhost:3000
::    5. Prints ready URLs + Chrome extension loading instructions
::
::  To stop everything:  run STOP.bat  (or close the two server windows)
::
::  On macOS / Linux:  use  ./start.sh  and  ./stop.sh  instead
:: ─────────────────────────────────────────────────────────────────────────────

:: Resolve the project root (directory where this .bat file lives, no trailing \)
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "BACKEND=%ROOT%\job-app-automation"
set "FRONTEND=%ROOT%\frontend"
set "VENV=%BACKEND%\venv\Scripts"

cls
echo.
echo  ============================================================
echo    ResumeWing   Starting all services...
echo  ============================================================
echo.


:: ── Pre-flight: Python virtual environment ────────────────────────────────────
echo  [1/4] Checking Python virtual environment...
if not exist "%VENV%\uvicorn.exe" (
    echo.
    echo  ERROR: Virtual environment not found or incomplete.
    echo.
    echo  First-time setup - run this once from the repo root:
    echo      .\setup.bat
    echo.
    echo  setup.bat checks your Python/Node versions, creates the venv,
    echo  installs every backend and frontend dependency, and verifies
    echo  the install worked.
    echo.
    pause
    exit /b 1
)
echo         OK
echo.


:: ── Pre-flight: Node modules ──────────────────────────────────────────────────
echo  [2/4] Checking Node modules...
if not exist "%FRONTEND%\node_modules" (
    echo.
    echo  ERROR: Frontend dependencies not installed.
    echo.
    echo  First-time setup - run this once from the repo root:
    echo      .\setup.bat
    echo.
    pause
    exit /b 1
)
echo         OK
echo.


:: ── Write a small helper script for the backend window ───────────────────────
:: Using a temp helper avoids nested-quote issues inside `start "title" cmd /k`.
set "BACKEND_HELPER=%TEMP%\rw_start_backend.bat"
(
    echo @echo off
    echo title ResumeWing — Backend ^(port 8000^)
    echo cd /d "%BACKEND%"
    echo echo.
    echo echo  ResumeWing Backend — FastAPI
    echo echo  http://localhost:8000
    echo echo  ^(First start: AI models load in 10-20 s^)
    echo echo.
    echo "%VENV%\uvicorn.exe" main:app --host 127.0.0.1 --port 8000 --reload
) > "%BACKEND_HELPER%"


:: ── Write a small helper script for the frontend window ──────────────────────
set "FRONTEND_HELPER=%TEMP%\rw_start_frontend.bat"
(
    echo @echo off
    echo title ResumeWing — Frontend ^(port 3000^)
    echo cd /d "%FRONTEND%"
    echo echo.
    echo echo  ResumeWing Frontend — Next.js
    echo echo  http://localhost:3000
    echo echo.
    echo npm run dev
) > "%FRONTEND_HELPER%"


:: ── Launch backend ────────────────────────────────────────────────────────────
echo  [3/4] Starting FastAPI backend...
start "ResumeWing — Backend" cmd /k "%BACKEND_HELPER%"
echo         Backend window opened.
echo.


:: ── Wait for AI models to load ────────────────────────────────────────────────
echo  [4/4] Waiting 15 s for AI models to load before opening frontend...
echo         (sentence-transformers + KeyBERT initialise on first request)
echo.
set /a i=15
:wait_loop
echo          !i! s remaining...
timeout /t 1 /nobreak >nul
set /a i-=1
if !i! GTR 0 goto wait_loop
echo.


:: ── Launch frontend ───────────────────────────────────────────────────────────
start "ResumeWing — Frontend" cmd /k "%FRONTEND_HELPER%"
echo         Frontend window opened.
echo.


:: ── Done — print summary ──────────────────────────────────────────────────────
echo.
echo  ============================================================
echo    ResumeWing is up!
echo  ============================================================
echo.
echo    Dashboard   :  http://localhost:3000
echo    Backend API :  http://localhost:8000
echo    API docs    :  http://localhost:8000/docs
echo.
echo    Chrome Extension (one-time setup):
echo      1. Open  chrome://extensions
echo      2. Enable "Developer mode"  (top-right toggle)
echo      3. Click "Load unpacked"
echo      4. Select the  extension\  folder inside this project
echo.
echo    To stop all services: run  STOP.bat
echo.
echo  ============================================================
echo.
pause
endlocal
