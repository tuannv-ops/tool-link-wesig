@echo off
title Cai Dat Thu Vien Cho Tool Lay Link Hop Dong
cd /d "%~dp0"

echo ======================================================================
echo          DANG CAI DAT CAC THU VIEN PYTHON CAN THIET
echo ======================================================================
echo.
echo [*] Dang cai dat: requests, pandas, openpyxl, pillow...
echo.

pip install -r requirements.txt

if %errorlevel% equ 0 (
    echo.
    echo ======================================================================
    echo  [OK] DA CAI DAT XONG TAT CA THU VIEN THANH CONG!
    echo  Bay gio ban co the chay Chay_Ung_Dung.bat hoac Chay_App_Desktop.bat
    echo ======================================================================
) else (
    echo.
    echo ======================================================================
    echo  [!] Co loi xay ra khi cai dat thu vien.
    echo  Vui long kiem tra lai ket noi Internet hoac phan mem diet virus.
    echo ======================================================================
)

echo.
pause
