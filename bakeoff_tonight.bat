@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Tonight's queue (2026-11-09), in the order it will run:
rem   (1) the tools test - 13 small jobs, ~20 min: proves every Night 2 tool on the real GPU before the long run
rem   (2) the finishing bake-off - 88 paintings at 1920x1080, ~1h45m: refine / FreeU / face repair, per checkpoint
rem   (3) the new SDXL LoRAs on the sdxl_v1 prompts (~1h45m)   (4) the house-style bake-off (~5 h)
rem   (5) FLUX.2 klein and (6) FLUX.1 + its LoRAs - the FLUX suites discover whatever FLUX files are in flux_models\ (0 renders if none yet).
rem (1) and (2) need pull_quality.bat and install_comfy_faces.bat to have been run once; if they have not, those two are
rem skipped with a message and the rest is queued as before.
rem Run this once, then start run_worker.bat (if it is not already running) and go to bed.
rem If ComfyUI was already running before you added model folders or ran the installers, close it and start run_worker.bat again.
rem In the morning:  review.bat tools_v1                (the tools test)
rem                  bakeoff_report.bat finish_v1       (the finishing comparison - look at the "detail" sheets)
rem                  bakeoff_report.bat                 (sdxl_v1 grids, now with the new LoRA columns)
rem                  bakeoff_report.bat style_v1        (the style comparison)
rem                  bakeoff_report.bat flux2_klein_v1  and  bakeoff_report.bat flux1_v1   (if FLUX ran)
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if exist "out\bakeoff\sdxl_v1\plan.json" if not exist "out\bakeoff\sdxl_v1\plan_run1_2026-11-08.json" copy /y "out\bakeoff\sdxl_v1\plan.json" "out\bakeoff\sdxl_v1\plan_run1_2026-11-08.json" >nul
echo Registering model folders with ComfyUI and scanning them (header-only, fast) ...
python -m forge comfy-paths >nul
python -m forge models scan >nul
set "MISSING="
if not exist "models\upscale_models\RealESRGAN_x4plus.pth" set "MISSING=1"
if not exist "models\controlnet\xinsir-union-sdxl-promax.safetensors" set "MISSING=1"
if not exist "models\ultralytics\bbox\face_yolov8m.pt" set "MISSING=1"
if not exist "engines\ComfyUI\custom_nodes\comfyui-impact-pack" set "MISSING=1"
if defined MISSING goto notools
echo.
echo [1/6] The tools test (runs first)
python -m forge submit games\turing_accords\batches\tools_v1.json --skip-done
echo.
echo [2/6] The finishing bake-off
python -m forge bakeoff submit games\turing_accords\bakeoff\finish_v1.json
goto models
:notools
echo.
echo [1/6] [2/6] SKIPPED - the paint tools are not installed yet. To run them later:
echo     pull_quality.bat, then install_comfy_faces.bat, restart run_worker.bat, then test_tools.bat and bakeoff_finish.bat
:models
echo.
echo [3/6] New SDXL LoRAs on the sdxl_v1 prompts
python -m forge bakeoff submit games\turing_accords\bakeoff\sdxl_v1_newmodels.json --rescan
echo.
echo [4/6] House-style bake-off
python -m forge bakeoff submit games\turing_accords\bakeoff\style_v1.json
echo.
echo [5/6] FLUX.2 klein (whatever klein files are in flux_models\ or models\diffusion_models\)
python -m forge bakeoff submit games\turing_accords\bakeoff\flux2_klein_v1.json
echo.
echo [6/6] FLUX.1 models + FLUX.1 LoRAs (whatever FLUX.1 files are in flux_models\, flux_lora\, lora models\)
python -m forge bakeoff submit games\turing_accords\bakeoff\flux1_v1.json
echo.
echo Anything already finished or already queued was skipped (run this twice and the second run adds nothing).
echo.
python -m forge eta
echo.
echo Start run_worker.bat now if it is not running.
echo Progress any time: doctor.bat
pause
