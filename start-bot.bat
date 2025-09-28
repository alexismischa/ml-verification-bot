@echo off
title Launching Discord Bot...

REM Ensure we're in the directory where this .bat lives
cd /d "%~dp0"

REM Step 0: Check if Python launcher is available
echo Checking Python launcher...
where py >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python launcher 'py' not found. Please install Python 3.11 and ensure it's on the system PATH.
    pause
    exit /b
)

REM Step 1: Create virtual environment if missing
IF NOT EXIST venv (
    echo Creating virtual environment...
    py -3.11 -m venv venv
)

REM Step 2: Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Step 3: Install dependencies
IF EXIST requirements.txt (
    echo Installing required packages...
    pip install --upgrade pip
    pip install -r requirements.txt
)

REM Step 4: Run the bot
echo Starting bot...
py main.py

REM Step 5: Pause to show output if script exits
pause