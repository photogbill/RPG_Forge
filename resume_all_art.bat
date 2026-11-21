@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Put back everything a focus held, so the art makes the whole game again.
call venv\Scripts\python.exe -m forge.focus resume %*
pause
