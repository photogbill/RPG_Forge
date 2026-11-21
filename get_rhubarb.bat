@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Rhubarb Lip Sync for the voice bench (BUILD 71): one pinned release (1.14.0, MIT) into tools\rhubarb\, its sum written
rem down the first time and checked every time after. Nothing is written outside this folder.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge voice get rhubarb
pause
