@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem produce.bat - see docs/JOB_TYPES.md (Night 4)
call venv\Scripts\python.exe -m forge produce %*
pause
