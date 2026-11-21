@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The painted dome's touch-up: make a picture from cells of the sheet and put it on the dome.
rem   opera_ceiling_touch_choose.bat A2 E3 F1   a part that is not named stays as it is
rem   opera_ceiling_touch_choose.bat 0          the first painting as it is
rem The painting that was on the dome is kept beside the candidates (replaced_..._ceiling_dome.png).
if "%~1"=="" (echo Name the cells you want from the sheet, like:  opera_ceiling_touch_choose.bat A2 E3 F1   or 0 for the painting as it is & pause & exit /b 1)
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python games\turing_accords\scenes\opera_ceiling_touch.py --choose %*
pause
