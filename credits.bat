@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Every model that touched a shipped pixel, its licence and how many files it touched -> out\reports\CREDITS_MODELS.md
rem Any approved file with no provenance or an unknown licence is listed at the top as a PROBLEM.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge credits --open %*
pause
