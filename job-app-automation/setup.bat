@echo off
echo ============================================
echo   ResumeWing — Job Application Automation
echo   One-time Setup Script
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

echo [1/5] Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

echo [2/5] Activating virtual environment...
call venv\Scripts\activate.bat

echo [3/5] Installing Python dependencies...
pip install --upgrade pip --quiet
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: pip install failed. Check your internet connection.
    pause
    exit /b 1
)

echo [4/5] Installing Playwright browsers (Chromium)...
playwright install chromium
if %errorlevel% neq 0 (
    echo WARNING: Playwright browser install failed.
    echo Web scrapers (Indeed, Glassdoor, etc.) may not work.
    echo You can run manually: playwright install chromium
)

echo [5/5] Creating .env file from template...
if not exist .env (
    copy .env.example .env >nul
    echo .env created. Edit it to add your Adzuna API credentials.
) else (
    echo .env already exists — skipping.
)

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo Next steps:
echo   1. Edit .env  — add your Adzuna App ID and API Key (or other board keys)
echo   2. Start the FastAPI backend:
echo.
echo      venv\Scripts\activate.bat
echo      uvicorn main:app --reload --port 8000
echo.
echo   3. In a second terminal, start the Next.js frontend:
echo.
echo      cd ..\frontend
echo      npm install        (one-time)
echo      npm run dev
echo.
echo Then open http://localhost:3000 in your browser.
echo.
pause
