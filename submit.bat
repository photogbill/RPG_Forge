@echo off
setlocal
cd /d "%~dp0"
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if "%~1"=="" (
  echo Drag a job file or a batch file onto this .bat, or: submit.bat jobs\templates\scene_card.json
  pause & exit /b 2
)
python -m forge submit %*
pause
