@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  NavPort launcher (Windows)
REM  - Checks for Python 3.9+
REM  - Creates .venv if it doesn't exist
REM  - Installs the API's dependencies only when they've changed
REM  - Starts the dashboard (port 8080) and the API (port 8000)
REM ============================================================

cd /d "%~dp0"

echo.
echo ================================================
echo   NavPort
echo ================================================
echo.

REM ---- 1. Locate Python -----------------------------------------------
set "PYTHON_CMD="

where python >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_CMD=py -3"
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] Python not found. Install 3.9+ from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [OK] Python
%PYTHON_CMD% --version

REM ---- 2. Virtual environment -----------------------------------------
set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if exist "%VENV_PY%" (
    echo [OK] Virtual environment
) else (
    echo [..] Creating .venv ...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

if not exist "%VENV_PY%" (
    echo [ERROR] .venv\Scripts\python.exe missing
    pause
    exit /b 1
)

REM ---- 3. Dependencies ------------------------------------------------
REM  Only the API has Python dependencies; the dashboard is static files.
set "REQUIREMENTS=%~dp0backend\requirements.txt"
set "LOCK_FILE=%VENV_DIR%\requirements.lock"
set "NEED_INSTALL=1"

if exist "%LOCK_FILE%" (
    fc /b "%REQUIREMENTS%" "%LOCK_FILE%" >nul 2>nul
    if not errorlevel 1 set "NEED_INSTALL=0"
)

if "%NEED_INSTALL%"=="0" (
    echo [OK] Dependencies
) else (
    echo [..] Installing dependencies ...
    "%VENV_PY%" -m pip install --upgrade pip -q
    "%VENV_PY%" -m pip install -r "%REQUIREMENTS%"
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    copy /y "%REQUIREMENTS%" "%LOCK_FILE%" >nul
    echo [OK] Dependencies installed
)

echo.

REM ---- 4. Start -------------------------------------------------------
REM  Development mode is opted into here, explicitly. Every default in
REM  backend\navport\config.py is the production-safe one, so forgetting to
REM  set something can never be what leaves the debugger exposed.
set "NAVPORT_ENV=development"
set "NAVPORT_DEBUG=true"
set "NAVPORT_HOST=0.0.0.0"

REM  Two servers, one window: scripts\dev.py runs both and stops both on Ctrl+C.
"%VENV_PY%" "%~dp0scripts\dev.py"
set "SERVER_EXIT=%errorlevel%"

echo.
if not "%SERVER_EXIT%"=="0" (
    echo [ERROR] NavPort exited with code %SERVER_EXIT%.
) else (
    echo NavPort stopped.
)

pause
endlocal
