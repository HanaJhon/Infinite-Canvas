@echo off
chcp 65001 >nul
rem 2026-11-11：从浏览器下载的压缩包解压后，文件带 Mark-of-the-Web，首次运行会弹
rem 「Windows 已保护你的电脑」。本脚本清除当前目录所有文件的安全锁定标记，然后启动。
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%~dp0' -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue"
start "" "Lochou启动器.exe"
