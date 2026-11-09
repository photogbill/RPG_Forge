@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Park waiting jobs in jobs\paused\ (the running job finishes). pause.bat = all; pause.bat bakeoff/style_v1 = one batch.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge pause %1
pause
