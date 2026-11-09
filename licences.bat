@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The licence chain of every approved asset -> out\licences_turing_accords.md (the AI-content / licence record).
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge licences %*
if exist "out\licences_turing_accords.md" start "" "out\licences_turing_accords.md"
pause
