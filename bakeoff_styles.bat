@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The house-style bake-off: five candidate styles x five SDXL checkpoints x (none + 3 LoRAs) x ten Game I pictures = 800 renders (~5 h).
rem Usage: bakeoff_styles.bat     then run_worker.bat.   Report when done: bakeoff_report.bat style_v1
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
echo Scanning model folders (header-only, fast) ...
python -m forge models scan >nul
python -m forge bakeoff plan games\turing_accords\bakeoff\style_v1.json
echo.
python -m forge bakeoff submit games\turing_accords\bakeoff\style_v1.json --rescan
echo.
echo Queued. If run_worker.bat is not running, start it now. Progress: doctor.bat. Comparison when done: bakeoff_report.bat style_v1
pause
