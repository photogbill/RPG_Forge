@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem File what came back from the outside tool: handoff_in.bat <name> ["<tool name version>"]
rem   The results must be in out\handoff\<name>\done, each name still starting with its job id and "__".
rem   Each picture is filed against its job and the kit (depth, normals, glow, layers) is rebuilt from it by the worker.
rem   Missing, extra and wrong-size files are named. If you have recorded only one tool, it is used by default.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "N=%~1"
if "%N%"=="" set /p "N=Hand-off name: "
if "%~2"=="" (python -m forge handoff in %N%) else (python -m forge handoff in %N% --tool "%~2")
pause
