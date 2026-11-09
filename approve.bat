@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Copy one finished picture into the game, with its provenance. Refuses anything not commercial-OK.
rem   approve.bat <job-id> <wanted-name> [pick-number]
rem   e.g. approve.bat 20261110-031500-01_ribbon-ab12 vignettes/gate_law/01_ribbon 2
rem   Not sure of the name?  wanted.bat --missing   lists them. Add --dry-run at the end to see without copying.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "JOB=%~1"
set "NAME=%~2"
set "PICK=%~3"
if "%JOB%"=="" set /p "JOB=Job id (folder name under out\): "
if "%NAME%"=="" set /p "NAME=Wanted name (e.g. scenes/bills_house): "
if "%PICK%"=="" goto nopick
if /i "%PICK%"=="--dry-run" goto dry
python -m forge approve %JOB% --as %NAME% --pick %PICK% %4
goto end
:dry
python -m forge approve %JOB% --as %NAME% --dry-run
goto end
:nopick
python -m forge approve %JOB% --as %NAME%
:end
pause
