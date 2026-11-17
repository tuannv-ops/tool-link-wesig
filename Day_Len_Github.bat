@echo off
title Day Code Len GitHub - WeSign Tool
cd /d "%~dp0"

echo ======================================================================
echo    DANG DAY (PUSH) MA NGUON LEN GITHUB REPOSITORY
echo    Repo: https://github.com/tuannv-ops/tool-link-wesig.git
echo ======================================================================
echo.

set GIT_EXE=%LOCALAPPDATA%\Programs\MinGit\cmd\git.exe
if not exist "%GIT_EXE%" set GIT_EXE=git

"%GIT_EXE%" push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo  [OK] DA DAY TOAN BO MA NGUON LEN GITHUB THANH CONG 100%!
    echo ======================================================================
) else (
    echo.
    echo ======================================================================
    echo  [!] Neu GitHub yeu cau xac thuc:
    echo  - Hay dang nhap tai khoan tren cua so trinh duyet bat len.
    echo  - Hoac dung Personal Access Token (PAT) cua GitHub lam mat khau.
    echo ======================================================================
)
echo.
pause
