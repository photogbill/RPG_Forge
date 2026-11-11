@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Copy finished art into the game, with its provenance. Refuses anything not commercial-OK.
rem   approve.bat <job-id> <wanted-name> [pick-number]          one picture
rem   approve.bat <job-id> <wanted-name> --set                  a scene_kit's six files (painting, _n, _e, _back, _over, _depth)
rem   approve.bat <job-id> <wanted-name> --dry-run              look first, copy nothing
rem   approve.bat <job-id> <wanted-name> --set --dry-run        look at the set first
rem   e.g. approve.bat 20261110-031500-town_square-ab12 scenes/town_square --set
rem   Not sure of the name?  wanted.bat --missing   lists them.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "JOB=%~1"
set "NAME=%~2"
set "PICK=%~3"
if "%JOB%"=="" set /p "JOB=Job id (folder name under out\): "
if "%NAME%"=="" set /p "NAME=Wanted name (e.g. scenes/town_square): "
if "%PICK%"=="" goto nopick
if /i "%PICK%"=="--dry-run" goto dry
if /i "%PICK%"=="--set" goto set
python -m forge approve %JOB% --as %NAME% --pick %PICK% %4
goto end
:set
python -m forge approve %JOB% --as %NAME% --set %4
goto end
:dry
python -m forge approve %JOB% --as %NAME% --dry-run
goto end
:nopick
python -m forge approve %JOB% --as %NAME%
:end
pause
