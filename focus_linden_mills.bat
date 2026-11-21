@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Focus the art on Linden Mills only: holds everything else (resume_all_art.bat puts it back).
call venv\Scripts\python.exe -m forge.focus linden_mills %*
pause
