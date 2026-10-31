@echo off
title Tool Lay Link Hop Dong Lao Dong Nhanh - Server
cd /d "%~dp0"

echo ======================================================================
echo    TOOL LAY LINK HOP DONG LAO DONG NHANH (WEB SERVER)
echo ======================================================================
echo.
echo [*] Dang khoi dong may chu tai: http://localhost:5050
echo [*] Dang mo trinh duyet Web...
echo.
echo ======================================================================
echo  Luu y: Cua so den nay la MAY CHU dang chay ngam de phuc vu.
echo  Ban hay vao TRINH DUYET WEB (Chrome/Edge) de nhap CCCD va lay link!
echo  De tat ung dung: Dong cua so den nay lai la xong.
echo ======================================================================
echo.

start http://localhost:5050

python app.py 5050

pause
