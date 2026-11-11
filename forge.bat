@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem RPG_Forge - the suite: pick a game, then Art or Story. Opens in your browser at http://127.0.0.1:8770/
rem Only this PC can see it. Close this window to stop the suite; the art worker is separate and is not touched.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
echo Starting the RPG_Forge suite - your browser opens in a moment. Log: logs\
python -m forge suite
pause
