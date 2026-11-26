@echo off
rem Start PyTPS from source on Windows. The first start creates a private Python environment (.venv)
rem in this folder and installs everything PyTPS needs (internet needed once); later starts are quick.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating the Python environment .venv ...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo Python 3.10 or newer was not found. Install it from https://www.python.org and tick "Add python.exe to PATH".
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
".venv\Scripts\python.exe" run_pytps.py %*
if errorlevel 1 pause
