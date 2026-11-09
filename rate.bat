@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Bring the ratings you exported from a review page back into the forge.
rem   rate.bat <suite-or-batch> [path-to-ratings.json]   (default: Downloads\ratings_<name>.json)
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "T=%~1"
if "%T%"=="" set /p "T=Suite or batch name: "
set "F=%~2"
if "%F%"=="" set "F=%USERPROFILE%\Downloads\ratings_%T%.json"
if not exist "%F%" (echo Could not find %F% - pass the file:  rate.bat %T% "C:\path\ratings.json" & pause & exit /b 1)
python -m forge rate %T% --import "%F%"
pause
