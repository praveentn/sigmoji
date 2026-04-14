@echo off
:: ============================================================
::  Sigmoji Discord Bot — Windows startup script
::  Usage:
::    start.bat            (reads PORT from .env, default 8080)
::    set PORT=9090 && start.bat
:: ============================================================
setlocal enabledelayedexpansion
title Sigmoji Discord Bot

echo.
echo   ==========================================
echo     🎮  Sigmoji Discord Bot
echo   ==========================================
echo.

:: ── Change to script directory ────────────────────────────────────────────────
cd /d "%~dp0"

:: ── Read PORT from .env (env var takes precedence) ────────────────────────────
if not defined PORT (
    if exist ".env" (
        for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
            set "_key=%%A"
            set "_key=!_key: =!"
            if /i "!_key!"=="PORT" (
                set "_val=%%B"
                set "_val=!_val: =!"
                set "_val=!_val:"=!"
                if not "!_val!"=="" set PORT=!_val!
            )
        )
    )
)
if not defined PORT set PORT=8080
echo   [sigmoji] Port   : %PORT%

:: ── Detect Python (3.10+) ─────────────────────────────────────────────────────
set PYTHON_CMD=
where python  >nul 2>&1 && python  -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 && set PYTHON_CMD=python
if not defined PYTHON_CMD (
    where python3 >nul 2>&1 && python3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 && set PYTHON_CMD=python3
)
if not defined PYTHON_CMD (
    where py >nul 2>&1 && py -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 && set PYTHON_CMD=py
)
if not defined PYTHON_CMD (
    echo   [sigmoji] ERROR: Python 3.10+ not found in PATH.
    echo   Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do echo   [sigmoji] Python : %%v
echo.

:: ── Check / free the port ─────────────────────────────────────────────────────
echo   [sigmoji] Checking port %PORT%...
set FOUND_PID=
for /f "skip=4 tokens=1,2,3,4,5" %%A in ('netstat -ano 2^>nul') do (
    set "_local=%%B"
    set "_state=%%D"
    set "_pid=%%E"
    if "!_local!"=="0.0.0.0:%PORT%" if /i "!_state!"=="LISTENING" set FOUND_PID=!_pid!
    if "!_local!"=="[::]:%PORT%"    if /i "!_state!"=="LISTENING" set FOUND_PID=!_pid!
)
if defined FOUND_PID (
    if not "%FOUND_PID%"=="0" (
        echo   [sigmoji] WARNING: Port %PORT% in use by PID %FOUND_PID% - killing...
        taskkill /f /pid %FOUND_PID% >nul 2>&1
        timeout /t 1 /nobreak >nul
        echo   [sigmoji] OK: Port %PORT% freed.
    )
) else (
    echo   [sigmoji] OK: Port %PORT% is free.
)
echo.

:: ── Virtual environment ───────────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo   [sigmoji] Creating virtual environment...
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo   [sigmoji] ERROR: Failed to create venv.
        pause & exit /b 1
    )
    echo   [sigmoji] OK: venv created.
)
echo   [sigmoji] Activating venv...
call venv\Scripts\activate.bat
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   [sigmoji] venv   : %%v

:: ── Install / sync requirements ───────────────────────────────────────────────
echo.
echo   [sigmoji] Checking requirements...
pip install -r requirements.txt -q --disable-pip-version-check
if errorlevel 1 (
    echo   [sigmoji] ERROR: pip install failed.
    pause & exit /b 1
)
echo   [sigmoji] OK: Dependencies up to date.

:: ── Token check ───────────────────────────────────────────────────────────────
echo.
set TOKEN_VAL=
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        set "_key=%%A"
        set "_key=!_key: =!"
        if /i "!_key!"=="DISCORD_TOKEN" (
            set TOKEN_VAL=%%B
            set TOKEN_VAL=!TOKEN_VAL: =!
            set TOKEN_VAL=!TOKEN_VAL:"=!
        )
    )
)
if not defined TOKEN_VAL (
    echo   [sigmoji] WARNING: DISCORD_TOKEN is not set in .env
    echo   [sigmoji]          Bot will start in local-only mode.
    echo   [sigmoji]          Open http://localhost:%PORT%/ for setup instructions.
) else if "%TOKEN_VAL%"=="your_bot_token_here" (
    echo   [sigmoji] WARNING: DISCORD_TOKEN still has the placeholder value.
    echo   [sigmoji]          Bot will start in local-only mode.
    echo   [sigmoji]          Open http://localhost:%PORT%/ for setup instructions.
) else (
    echo   [sigmoji] OK: Discord token found.
)

:: ── Launch ────────────────────────────────────────────────────────────────────
echo.
echo   [sigmoji] Starting bot  --^>  http://localhost:%PORT%/
echo   [sigmoji] Press Ctrl+C to stop.
echo.

python bot.py

echo.
echo   [sigmoji] Bot stopped.
pause
endlocal
