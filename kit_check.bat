@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Is this scene kit safe to approve?  kit_check.bat <job-id> [map id]
rem   e.g. kit_check.bat 20261109-205640-c3_n3_kit_gas_station-f6be gas_station
rem   pass / warn / fail per line, and check.png in the kit's folder. approve --set runs this first.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "J=%~1"
if "%J%"=="" set /p "J=Kit job id: "
if "%~2"=="" (python -m forge kit check %J% --open) else (python -m forge kit check %J% --map %~2 --open)
pause
