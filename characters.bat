@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem characters.bat [list | show <id> | check [<id>] | stubs | set <id> [variant]]  - the character registry
call venv\Scripts\python.exe -m forge characters %*
pause
