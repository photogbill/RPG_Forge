@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The opera house's painted dome: Sarah and Valkyrie, the gap kept (the game bible, 14.16).
rem   opera_ceiling.bat               paints about 8 candidates and opens their contact sheet (about 10 minutes)
rem   opera_ceiling.bat --quick       paints 4
rem   opera_ceiling.bat --forty       paints 52: 40 seeds of the favourite's recipe, 12 'Fibonacci and yin and yang' (about 2 hours)
rem   opera_ceiling.bat --choose 5    puts candidate 5 (its number on the contact sheet) on the dome
rem It waits for the graphics card if something else has it, and starts ComfyUI if it is not running.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python games\turing_accords\scenes\opera_ceiling.py %*
if errorlevel 1 echo Something went wrong. The log: out\3d\places\turing_accords\opera_house\paint\_candidates\ceiling.log
pause
