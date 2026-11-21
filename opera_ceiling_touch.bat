@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The painted dome's touch-up (the game bible, 14.16). William's pick of 2026-11-16 (the first painting of candidate 10,
rem set 20261116-152102) is kept, and only small parts are repainted: his two hands, the marks on him, the storm's edge,
rem and her two hands (lavender nails). Both faces, her hair and everything else stay as they are.
rem   opera_ceiling_touch.bat                  every part's tries (about half an hour), then the sheet opens
rem   opera_ceiling_touch.bat --only E,F       only those parts (the letters are the sheet's columns)
rem   opera_ceiling_touch.bat --more A,B --strengths 0.6,0.7    more tries for those parts, added to the same sheet
rem   opera_ceiling_touch.bat --mask-only      no painting: a picture with the parts that may change outlined
rem Afterwards:  opera_ceiling_touch_look.bat A2 E3 F1    makes a picture from those cells and opens it
rem              opera_ceiling_touch_choose.bat A2 E3 F1  makes it and puts it on the dome (0 = the painting as it is)
rem It waits for the graphics card if something else has it, and starts ComfyUI if it is not running.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python games\turing_accords\scenes\opera_ceiling_touch.py %*
if errorlevel 1 echo Something went wrong or nothing was made. The log: out\3d\places\turing_accords\opera_house\paint\_candidates\ceiling.log
pause
