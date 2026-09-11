@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  NavPort launcher
REM  - Verifies Python is installed
REM  - Creates a virtual environment (.venv) if one doesn't exist
REM  - Installs dependencies only if requirements.txt changed
REM  - Starts the Flask server
REM  Safe to double-click from any Windows machine/location.
REM ============================================================

cd /d "%~dp0"

echo ================================================
echo   NavPort - Flight Weather Dashboard
echo ================================================
echo.

REM ---- 1. Locate a Python interpreter -------------------------------
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
    echo [ERROR] Python was not found on this system.
    echo         Install Python 3.9 or newer from https://www.python.org/downloads/
    echo         ^(tick "Add python.exe to PATH" during setup^), then re-run this script.
    echo.
    pause
    exit /b 1
)

echo [OK] Found Python:
%PYTHON_CMD% --version
echo.

REM ---- 2. Create the virtual environment if it doesn't already exist -
set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if exist "%VENV_PY%" (
    echo [OK] Virtual environment already exists - skipping creation.
) else (
    echo [..] Creating virtual environment in .venv ...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        echo         Make sure the "venv" module is available for your Python install.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)
echo.

if not exist "%VENV_PY%" (
    echo [ERROR] Virtual environment python.exe not found at:
    echo         %VENV_PY%
    pause
    exit /b 1
)

REM ---- 3. Install dependencies only if requirements.txt changed ------
set "LOCK_FILE=%VENV_DIR%\requirements.lock"
set "NEED_INSTALL=1"

if exist "%LOCK_FILE%" (
    fc /b "%~dp0requirements.txt" "%LOCK_FILE%" >nul 2>nul
    if not errorlevel 1 set "NEED_INSTALL=0"
)

if "%NEED_INSTALL%"=="0" (
    echo [OK] Dependencies already installed and up to date - skipping.
) else (
    echo [..] Installing dependencies from requirements.txt ...
    "%VENV_PY%" -m pip install --upgrade pip -q
    "%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install dependencies.
        echo         Check your internet connection and try again.
        pause
        exit /b 1
    )
    copy /y "%~dp0requirements.txt" "%LOCK_FILE%" >nul
    echo [OK] Dependencies installed.
)
echo.

REM ---- 4. Start the server --------------------------------------------
echo ================================================
echo   Starting NavPort on http://localhost:5000
echo   Press CTRL+C to stop the server.
echo ================================================
echo.

"%VENV_PY%" "%~dp0run.py"
set "SERVER_EXIT=%errorlevel%"

echo.
if not "%SERVER_EXIT%"=="0" (
    echo [ERROR] NavPort exited with an error ^(code %SERVER_EXIT%^). See the output above for details.
) else (
    echo NavPort server stopped.
)

pause
endlocal
