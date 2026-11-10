@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Hand pictures to an outside tool that has no command line (it batch-processes a folder).
rem   handoff_out.bat <name> <batch or job ids ...>
rem   e.g. handoff_out.bat upscale_test night3_proof
rem Copies each job's raw render into out\handoff\<name>\in with README.txt saying what size to make and where to save.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "N=%~1"
if "%N%"=="" set /p "N=Name for this hand-off (one word): "
if "%~2"=="" (set /p "R=Batch name or job ids: ") else (set "R=")
if "%~2"=="" (python -m forge handoff out %R% --to out/handoff/%N%/in) else (python -m forge handoff out %2 %3 %4 %5 %6 %7 %8 %9 --to out/handoff/%N%/in)
if exist "out\handoff\%N%\in" start "" "out\handoff\%N%\in"
pause
