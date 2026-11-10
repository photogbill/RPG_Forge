@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
echo.
echo  SPRITE TEST - STEP 1: START  (also use this to RESTART the worker)
echo.
echo  FIRST: if a "Forge worker" window is open, click it, press Ctrl+C, answer Y, close it.
echo  Leave the ComfyUI window alone - it can stay running.
echo.
pause
call venv\Scripts\activate.bat
echo Putting any interrupted job back in the queue ...
python -m forge requeue
start "Forge worker" "%~dp0run_worker.bat"
echo.
echo  Worker started in its own window. Leave it open. Ctrl+C in that window stops it; nothing is lost.
echo.
pause
