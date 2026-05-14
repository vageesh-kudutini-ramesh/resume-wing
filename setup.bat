@echo off
setlocal EnableDelayedExpansion
title ResumeWing - One-time Setup

:: ─────────────────────────────────────────────────────────────────────────────
::  ResumeWing - One-time Setup (Windows)
::
::  Run this once after cloning the repo. It:
::    1. Verifies Python 3.10+ and Node 18+ are installed
::    2. Creates a clean Python venv and installs every backend dep
::    3. Installs every frontend dep with npm
::    4. Verifies the install actually worked (uvicorn + node_modules present)
::
::  Then run START.bat to launch the app.
:: ─────────────────────────────────────────────────────────────────────────────

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND=%ROOT%\job-app-automation"
set "FRONTEND=%ROOT%\frontend"

cls
echo.
echo  ============================================================
echo    ResumeWing - One-time Setup
echo  ============================================================
echo.


:: ── [1/5] Python ──────────────────────────────────────────────────────────────
echo  [1/5] Checking Python...

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  ERROR: 'python' not found in PATH.
    echo.
    echo  Install Python 3.10 or higher from:
    echo      https://www.python.org/downloads/windows/
    echo.
    echo  IMPORTANT: during the installer, tick "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VERSION=%%v"
for /f "tokens=1,2 delims=." %%a in ("!PY_VERSION!") do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)

if !PY_MAJOR! LSS 3 (
    echo.
    echo  ERROR: Python 3.10 or higher required - found !PY_VERSION!.
    echo  Install from https://www.python.org/downloads/windows/
    pause
    exit /b 1
)
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 10 (
    echo.
    echo  ERROR: Python 3.10 or higher required - found !PY_VERSION!.
    echo  Install from https://www.python.org/downloads/windows/
    pause
    exit /b 1
)
echo         OK - Python !PY_VERSION!
echo.


:: ── [2/5] Node.js ─────────────────────────────────────────────────────────────
echo  [2/5] Checking Node.js...

where node >nul 2>nul
if errorlevel 1 (
    echo.
    echo  ERROR: 'node' not found in PATH.
    echo  Install Node.js 18 or higher from https://nodejs.org/
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('node -v') do set "NODE_VERSION=%%v"
set "NODE_VERSION=!NODE_VERSION:v=!"
for /f "tokens=1 delims=." %%a in ("!NODE_VERSION!") do set "NODE_MAJOR=%%a"

if !NODE_MAJOR! LSS 18 (
    echo.
    echo  ERROR: Node.js 18 or higher required - found v!NODE_VERSION!.
    echo  Install from https://nodejs.org/
    pause
    exit /b 1
)
echo         OK - Node v!NODE_VERSION!
echo.


:: ── [3/5] Python venv ─────────────────────────────────────────────────────────
echo  [3/5] Creating Python virtual environment...

pushd "%BACKEND%"

if exist venv (
    echo         Removing existing venv...
    rmdir /s /q venv
)

python -m venv venv
if errorlevel 1 (
    echo.
    echo  ERROR: venv creation failed. Try reinstalling Python from python.org
    echo  ^(the Windows Store version of Python is known to have venv issues^).
    popd
    pause
    exit /b 1
)
echo         OK
echo.


:: ── [4/5] Backend dependencies ────────────────────────────────────────────────
echo  [4/5] Installing backend dependencies ^(2-3 minutes^)...
echo.

call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo  ERROR: pip upgrade failed.
    popd
    pause
    exit /b 1
)

pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  ERROR: pip install failed. Most common cause on Windows:
    echo  Missing "Microsoft Visual C++ 14.0 or greater" - download from:
    echo      https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo  Install the "Desktop development with C++" workload, then re-run setup.bat.
    popd
    pause
    exit /b 1
)

if not exist "venv\Scripts\uvicorn.exe" (
    echo.
    echo  ERROR: uvicorn did not install. Check the pip output above for errors.
    popd
    pause
    exit /b 1
)
echo         OK - uvicorn + all backend deps installed
echo.
popd


:: ── [5/5] Frontend dependencies ───────────────────────────────────────────────
echo  [5/5] Installing frontend dependencies ^(1-2 minutes^)...
echo.

pushd "%FRONTEND%"
call npm install
if errorlevel 1 (
    echo.
    echo  ERROR: npm install failed. Check the output above for errors.
    popd
    pause
    exit /b 1
)
if not exist "node_modules" (
    echo.
    echo  ERROR: npm install ran but node_modules folder is missing.
    popd
    pause
    exit /b 1
)
echo         OK - node_modules installed
echo.
popd


:: ── Success ───────────────────────────────────────────────────────────────────
echo.
echo  ============================================================
echo    Setup complete!
echo  ============================================================
echo.
echo    To start ResumeWing, run:
echo        .\START.bat
echo.
echo    Then open  http://localhost:3000  in your browser.
echo.
echo    Optional - load the browser extension once:
echo        1. Open  edge://extensions  ^(or chrome://extensions^)
echo        2. Toggle "Developer mode" on
echo        3. Click "Load unpacked" -^> select the  extension\  folder
echo.
echo  ============================================================
echo.
pause
endlocal
