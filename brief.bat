@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Write an editable batch DRAFT from the game data: brief.bat maps  ^|  brief.bat sleeves  ^|  brief.bat icons
rem The draft lands in games\turing_accords\batches\draft_*.json and cannot be submitted until its prompts are written
rem and the "_draft" line is deleted (that is Fable's / Claude's job, not the forge's).
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "K=%~1"
if "%K%"=="" set "K=maps"
python -m forge brief %K%
pause
