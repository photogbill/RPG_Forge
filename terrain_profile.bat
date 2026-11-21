@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The ground along a straight line, from DTED Level 0 (BUILD 77): with nothing after it, every line the games own
rem terrain file asks for (its folder: terrain\story.json) - a picture and the numbers into out\terrain\<game>\.
rem   terrain_profile.bat
rem   terrain_profile.bat 38.50,-79.28 --bearing 90 --length 25000 --grade 0.02
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if "%~1"=="" (
  python -m forge terrain profile --story
) else (
  python -m forge terrain profile %*
)
pause
