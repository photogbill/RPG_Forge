@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Filter Forge from the forge (read-only — filters are used by path, never copied):
rem   filter_forge.bat                 is it set up? (forge.json tools.filter_forge.exe) + licence line
rem   filter_forge.bat list            every filter the forge can see (bundled + your own library)
rem   filter_forge.bat presets Library_242-5     a filter's presets: number, seamless, size, channel
rem Rendering is a job type: "type": "filter_forge" (see docs\JOB_TYPES.md, or filter_forge_proof.bat for an example).
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if "%~1"=="" (python -m forge filter-forge check) else (python -m forge filter-forge %*)
pause
