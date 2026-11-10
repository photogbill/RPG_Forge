@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The prompt library: named blocks such as {{style.house}} that submit expands into every job.
rem   prompts.bat                       list the blocks
rem   prompts.bat show style.house      one block
rem   prompts.bat where-used style.house
rem   prompts.bat check                 the library itself (and the never-list)
rem   prompts.bat ab style.house --on <batch>   a with/without test batch (draft)
rem The blocks live in games\<game>\prompts\*.json ; never.json holds words that may never be in a prompt.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge prompts %*
pause
