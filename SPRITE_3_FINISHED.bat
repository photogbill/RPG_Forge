@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
echo.
echo  SPRITE TEST - STEP 3: FINISHED  (only when the sprite test is done)
echo  Puts the old bake-off back in the queue. If the worker is still running it carries straight on.
echo.
pause
python -m forge resume
pause
