@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Runs the forge's tests and says how many passed. They work on the example game and temp folders,
rem so it is fine to run them while the art worker renders.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m pytest -q -p no:cacheprovider %*
pause
