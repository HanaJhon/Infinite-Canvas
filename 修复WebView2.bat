@echo off
chcp 65001 >nul
title Fix WebView2 Runtime

rem Needs admin: relaunch elevated if not
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo ==================================================
echo   Fix WebView2 Runtime  (launcher error 0x800736B1)
echo ==================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\fix-webview2.ps1"

echo.
pause
