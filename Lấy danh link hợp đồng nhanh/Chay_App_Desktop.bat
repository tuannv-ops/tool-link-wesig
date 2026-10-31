@echo off
chcp 65001 >nul
title Tool Lay Link Hop Dong Lao Dong Nhanh
cd /d "%~dp0"

:: Kiem tra va cai dat thu vien neu thieu
python -c "import requests, pandas, openpyxl, PIL" >nul 2>&1
if errorlevel 1 (
    echo [*] Dang tu dong cai dat thu vien can thiet: requests, pandas, openpyxl, pillow...
    pip install requests pandas openpyxl pillow
    echo.
)

start "" pythonw gui_app.py
if errorlevel 1 (
    python gui_app.py
)
exit
