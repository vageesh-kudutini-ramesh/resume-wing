@echo off
title ResumeWing — Stop All Services

echo.
echo  ============================================================
echo    ResumeWing ^| Stopping all services...
echo  ============================================================
echo.

:: Kill uvicorn (FastAPI backend)
echo  Stopping FastAPI backend (uvicorn)...
taskkill /F /IM uvicorn.exe >nul 2>&1
if errorlevel 1 (
    echo         Not running or already stopped.
) else (
    echo         Stopped.
)
echo.

:: Kill Node.js (Next.js frontend)
:: We only kill node processes that have "next" in their command line
echo  Stopping Next.js frontend (node)...
for /f "tokens=2" %%p in ('wmic process where "name='node.exe' and commandline like '%%next%%'" get processid ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%p >nul 2>&1
)
:: Fallback: if the above finds nothing, notify the user
wmic process where "name='node.exe' and commandline like '%next%'" get processid 2>nul | findstr /r "[0-9]" >nul
if errorlevel 1 (
    echo         Not running or already stopped.
) else (
    echo         Stopped.
)
echo.

echo  ============================================================
echo    All ResumeWing services have been stopped.
echo  ============================================================
echo.
pause
