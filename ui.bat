@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The forge dashboard: the queue, what is rendering, the newest pictures, Retry / Pause / Resume / Approve.
rem Opens in your browser. Only this PC can see it (127.0.0.1). Close this window to stop it.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
start "" http://127.0.0.1:8765/
python -m forge ui
pause
