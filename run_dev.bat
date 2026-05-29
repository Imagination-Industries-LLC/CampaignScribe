@echo off
setlocal
title CampaignScribe (dev)

rem Run CampaignScribe directly from source using the project venv.
rem No PyInstaller rebuild needed - edit code, save, relaunch.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [run_dev] ERROR: .venv\Scripts\python.exe not found.
    echo [run_dev] Expected the project virtual environment at:
    echo [run_dev]   %~dp0.venv
    echo.
    pause
    exit /b 1
)

echo [run_dev] Launching CampaignScribe from source...
echo [run_dev] Python: %~dp0.venv\Scripts\python.exe
echo [run_dev] Entry:  %~dp0main.py
echo.

".venv\Scripts\python.exe" main.py %*
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    echo [run_dev] App exited with code %EXITCODE%.
    pause
) else (
    echo [run_dev] App exited cleanly.
)

endlocal & exit /b %EXITCODE%
