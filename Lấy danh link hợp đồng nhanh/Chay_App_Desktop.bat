@echo off
title Tool Lay Link Hop Dong Lao Dong Nhanh
cd /d "%~dp0"

start "" pythonw gui_app.py
if %errorlevel% neq 0 (
    python gui_app.py
)
exit
