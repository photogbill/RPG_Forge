@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Bake off ONLY the models added after the first run (2026-11-09): the new SDXL LoRAs on the five
rem SDXL checkpoints, same prompts and seed as sdxl_v1, so the new columns join the existing grids.
rem Usage: bakeoff_new_models.bat        then start run_worker.bat (or leave it running); ~1h45m on the 3080 Ti.
rem        When it is done: bakeoff_report.bat   (rebuilds out\bakeoff\sdxl_v1 with the new columns)
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if exist "out\bakeoff\sdxl_v1\plan.json" if not exist "out\bakeoff\sdxl_v1\plan_run1_2026-11-08.json" copy /y "out\bakeoff\sdxl_v1\plan.json" "out\bakeoff\sdxl_v1\plan_run1_2026-11-08.json" >nul
echo Scanning model folders (header-only, fast) ...
python -m forge models scan >nul
python -m forge bakeoff plan games\turing_accords\bakeoff\sdxl_v1_newmodels.json
echo.
python -m forge bakeoff submit games\turing_accords\bakeoff\sdxl_v1_newmodels.json --rescan
echo.
echo Queued. If run_worker.bat is not running, start it now. Progress: doctor.bat. Comparison when done: bakeoff_report.bat
pause
