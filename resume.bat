@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Bring paused jobs back to the queue. resume.bat = all; resume.bat bakeoff/style_v1 = one batch.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge resume %1
pause
