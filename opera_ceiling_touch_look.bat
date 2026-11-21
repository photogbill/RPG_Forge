@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The painted dome's touch-up: make a picture from cells of the sheet and open it. Nothing goes on the dome.
rem   opera_ceiling_touch_look.bat A2 E3 F1     a part that is not named stays as it is; 0 alone = the painting as it is
if "%~1"=="" (echo Name the cells you want from the sheet, like:  opera_ceiling_touch_look.bat A2 E3 F1 & pause & exit /b 1)
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python games\turing_accords\scenes\opera_ceiling_touch.py --look %*
pause
