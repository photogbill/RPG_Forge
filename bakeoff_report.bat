@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Build the comparison grids + index.html for a suite and open it. Usage: bakeoff_report.bat [suite-name]
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "SUITE=%~1"
if "%SUITE%"=="" set "SUITE=sdxl_v1"
python -m forge bakeoff report %SUITE%
if exist "out\bakeoff\%SUITE%\index.html" start "" "out\bakeoff\%SUITE%\index.html"
pause
