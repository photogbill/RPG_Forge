@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The licence chain of every approved asset -> out\licences_<game>.md (the AI-content / licence record). --game <id> picks a game.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge licences %*
for /f "delims=" %%F in ('dir /b /o-d "out\licences_*.md" 2^>nul') do (start "" "out\%%F" & goto opened)
:opened
pause
