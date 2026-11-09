@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Download a registered model into .\models (see models\models.json).
rem Usage: pull_model.bat            -> sdxl-base-1.0 (the default checkpoint, ~6.9 GB)
rem        pull_model.bat <name>     -> any name from "python -m forge models list"
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "NAME=%~1"
if "%NAME%"=="" set "NAME=sdxl-base-1.0"
echo Registered models:
python -m forge models list
echo.
echo Pulling %NAME% into models\ ...
python -m forge models pull %NAME%
pause
