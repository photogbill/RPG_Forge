@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem What is queued and about how long it will take (from how long recent jobs of each type took).
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge eta
pause
