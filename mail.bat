@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The Mail from the command line (the suite's Story side is the easy way: forge.bat).
rem   mail.bat list            your inbox      mail.bat read <id>      a whole thread
rem   mail.bat send --to "Claude Opus" --subject "..." --body "..."    mail.bat reply <id> --body "..."
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge mail %*
pause
