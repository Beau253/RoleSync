@echo off
title RoleSync Development Environment

echo Navigating to project directory...
rem Use /d to ensure we change drives if necessary
cd /d "C:\Users\Beau Marchant\Documents\GitHub\Discord-Bots\RoleSync"

echo Checking for virtual environment...
rem Check if the activation script actually exists before we try to run it.
if not exist "venv\Scripts\activate.bat" (
    echo.
    echo ERROR: Virtual environment not found in this directory!
    echo Please run 'python -m venv venv' in this folder first.
    echo.
    pause
    exit
)

echo Activating virtual environment...
call "venv\Scripts\activate.bat"

echo.
echo Environment is ready. Installing/checking requirements...

rem THIS IS THE CORRECTED LINE
python -m pip install -r requirements.txt

echo.
echo Running 'python main.py'...
echo.
python main.py

rem Keep the window open
cmd /k