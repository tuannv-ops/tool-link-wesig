@echo off
chcp 65001 >nul
title Tool Lay Link Hop Dong Lao Dong Nhanh - Server
cd /d "%~dp0"

echo ======================================================================
echo    TOOL LAY LINK HOP DONG LAO DONG NHANH (WEB SERVER)
echo ======================================================================
echo.

:: Kiem tra va cai dat thu vien neu thieu
python -c "import requests, pandas, openpyxl, PIL" >nul 2>&1
if errorlevel 1 (
    echo [*] Dang tu dong cai dat thu vien can thiet: requests, pandas, openpyxl, pillow...
    pip install requests pandas openpyxl pillow
    echo.
)

echo [*] Dang khoi dong may chu tai: http://localhost:5050
echo [*] Trinh duyet web se tu dong bat len trong giay lat...
echo.
echo ======================================================================
echo  Luu y: Cua so den nay la MAY CHU dang chay ngam de phuc vu.
echo  Ban hay vao TRINH DUYET WEB (Chrome/Edge) de nhap CCCD va lay link!
echo  De tat ung dung: Dong cua so den nay lai la xong.
echo ======================================================================
echo.

python app.py 5050

if errorlevel 1 (
    echo.
    echo [!] Khong the khoi dong may chu.
    echo.
)

pause
