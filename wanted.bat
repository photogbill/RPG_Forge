@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem What the game wants vs. what has been approved into it.
rem   wanted.bat                 the table (per kind: wanted / approved / stale / missing)
rem   wanted.bat --refresh       re-read the game folder first (after the game adds maps, records, placeholders)
rem   wanted.bat --missing       list every file that still needs art      wanted.bat --kind scene --missing
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge wanted %*
pause
