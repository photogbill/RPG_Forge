@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Finish the FLUX.2 klein bake-off (flux2_klein_v1: the 8 style_v1 places x 5 styles + the sdxl_v1 prompts, klein 4B base + distilled),
rem then Sarah's sprite pose sheets (sprite_poses_klein_v1), then build both comparison pages. Written 2026-11-11 (BAKEOFF_3_VERDICT.md).
rem   1. parks the rest of flux1_v1 (the photoreal SaMay FLUX.1 model - wrong tool for painted places) in jobs\paused\
rem   2. queues the sprite pose sheets BEHIND the klein jobs (priority -1)
rem   3. starts ComfyUI if it isn't up, runs the GPU worker until the queue is EMPTY, then writes the two reports and opens them
rem Safe to stop at any time: close this window (or Ctrl+C). The picture being made is lost, everything finished is kept;
rem run this .bat again and it carries on from where it stopped.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if not exist "models\diffusion_models\flux-2-klein-4b.safetensors" (echo models\diffusion_models\flux-2-klein-4b.safetensors is missing - run pull_flux.bat first. Nothing was queued. & pause & exit /b 1)
if not exist "models\diffusion_models\flux-2-klein-base-4b.safetensors" (echo models\diffusion_models\flux-2-klein-base-4b.safetensors is missing - run pull_flux.bat first. Nothing was queued. & pause & exit /b 1)
echo.
echo [1/4] Parking the rest of the FLUX.1 run ...
python -m forge pause bakeoff/flux1_v1
echo.
echo [2/4] Queuing Sarah's sprite pose sheets behind the klein jobs ...
python -m forge comfy-paths >nul
python -m forge models scan >nul
python -m forge bakeoff submit games\turing_accords\bakeoff\sprite_poses_klein_v1.json
echo.
echo [3/4] Running the queue until it is empty (klein first, then the sprite sheets) ...
if not exist engines\ComfyUI\main.py (echo ComfyUI is not installed - run install_comfy.bat. & pause & exit /b 1)
python -m forge comfy-up >nul
if not errorlevel 1 goto comfyok
echo Starting ComfyUI in its own minimised window ...
start "ComfyUI" /min "%~dp0start_comfy.bat"
set /a N=0
:waitloop
timeout /t 10 >nul
python -m forge comfy-up >nul
if not errorlevel 1 goto comfyok
set /a N+=1
if %N% lss 30 goto waitloop
echo ComfyUI did not come up in 5 minutes - open its window (taskbar: ComfyUI) and read the last lines. Nothing was run.
pause & exit /b 1
:comfyok
echo ComfyUI is up.
python -m forge worker --gpu --once
echo.
echo [4/4] Building the comparison pages ...
python -m forge bakeoff report flux2_klein_v1
python -m forge bakeoff report sprite_poses_klein_v1
if exist "out\bakeoff\flux2_klein_v1\index.html" start "" "out\bakeoff\flux2_klein_v1\index.html"
if exist "out\bakeoff\sprite_poses_klein_v1\index.html" start "" "out\bakeoff\sprite_poses_klein_v1\index.html"
echo.
echo Done. Tell Claude "the klein run is finished" - it reads the results from the folders.
echo (The parked FLUX.1 jobs stay in jobs\paused\ - resume.bat bakeoff/flux1_v1 brings them back if you ever want them.)
pause
