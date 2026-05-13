@echo off
setlocal

:: ─────────────────────────────────────────────────────────────────────────────
::  ResumeWing — Run Daily Digest Email
::
::  Wrapper invoked by Windows Task Scheduler. Activates the project venv and
::  runs digest_email.py, capturing the exit code so the scheduler can show
::  the run as successful or failed.
::
::  Register the task once (replace <REPO_PATH> with your local path):
::    schtasks /Create /TN ResumeWingDigest
::            /TR "<REPO_PATH>\job-app-automation\run_digest.bat"
::            /SC DAILY /ST 08:00 /F
::
::  Delete it with:
::    schtasks /Delete /TN ResumeWingDigest /F
:: ─────────────────────────────────────────────────────────────────────────────

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "VENV=%ROOT%\venv\Scripts"

if not exist "%VENV%\python.exe" (
    echo ERROR: Python venv not found at "%VENV%".
    echo Run:   cd job-app-automation ^&^& python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
    exit /b 1
)

cd /d "%ROOT%"
"%VENV%\python.exe" digest_email.py
set "EXITCODE=%ERRORLEVEL%"

endlocal & exit /b %EXITCODE%
