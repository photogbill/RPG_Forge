@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem concur.bat - give your OK for Claude Opus to approve/deliver for 30 minutes.  concur.bat close / concur.bat status
call venv\Scripts\python.exe -m forge.concur %*
pause
