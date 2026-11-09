@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Move failed jobs back to pending so a running worker picks them up again (after a fix).
rem Usage: retry_failed.bat                -> every failed job
rem        retry_failed.bat bakeoff/sdxl_v1 -> only that batch (prefix match)
if not exist venv goto noinstall
call venv\Scripts\activate.bat
python -m forge retry %*
python -m forge status
pause
exit /b
:noinstall
echo Run install.bat first.
pause
