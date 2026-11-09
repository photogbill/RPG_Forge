@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
echo CPU worker running (palette, pixelize, pack, sheets). Ctrl+C stops it. Log: logs\
python -m forge worker
pause
