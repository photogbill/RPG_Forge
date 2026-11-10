@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem models_report.bat - every model file: loads? licence, used by, verdict, size - and what is safe to delete. REPORT ONLY.
call venv\Scripts\python.exe -m forge models-report %*
pause
