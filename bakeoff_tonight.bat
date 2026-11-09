@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Tonight's queue (2026-11-09), in order: (1) the new SDXL LoRAs on the sdxl_v1 prompts (~1h45m), (2) the house-style bake-off (~5 h),
rem (3) FLUX.2 klein and (4) FLUX.1 + its LoRAs — the FLUX suites discover whatever FLUX files are in flux_models\ (0 renders if none yet).
rem Run this once, then start run_worker.bat (if it is not already running) and go to bed.
rem If ComfyUI was already running before you added model folders, close it and start run_worker.bat again so it sees them.
rem In the morning:  bakeoff_report.bat                 (sdxl_v1 grids, now with the new LoRA columns)
rem                  bakeoff_report.bat style_v1        (the style comparison)
rem                  bakeoff_report.bat flux2_klein_v1  and  bakeoff_report.bat flux1_v1   (if FLUX ran)
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if exist "out\bakeoff\sdxl_v1\plan.json" if not exist "out\bakeoff\sdxl_v1\plan_run1_2026-11-08.json" copy /y "out\bakeoff\sdxl_v1\plan.json" "out\bakeoff\sdxl_v1\plan_run1_2026-11-08.json" >nul
echo Registering model folders with ComfyUI and scanning them (header-only, fast) ...
python -m forge comfy-paths >nul
python -m forge models scan >nul
echo.
echo [1/4] New SDXL LoRAs on the sdxl_v1 prompts
python -m forge bakeoff submit games\turing_accords\bakeoff\sdxl_v1_newmodels.json --rescan
echo.
echo [2/4] House-style bake-off
python -m forge bakeoff submit games\turing_accords\bakeoff\style_v1.json
echo.
echo [3/4] FLUX.2 klein (whatever klein files are in flux_models\ or models\diffusion_models\)
python -m forge bakeoff submit games\turing_accords\bakeoff\flux2_klein_v1.json
echo.
echo [4/4] FLUX.1 models + FLUX.1 LoRAs (whatever FLUX.1 files are in flux_models\, flux_lora\, lora models\)
python -m forge bakeoff submit games\turing_accords\bakeoff\flux1_v1.json
echo.
echo Queued. About 1,130 SDXL renders (~7 h) plus the FLUX renders listed above. Start run_worker.bat now if it is not running.
echo Progress any time: doctor.bat
pause
