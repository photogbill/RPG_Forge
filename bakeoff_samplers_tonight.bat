@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Tonight's sampler round (William 2026-11-11): samplers judged as sampler x steps, on pictures the game needs
rem (the Tucson Boneyard scene, Sarah's Guardian dialogue portrait, Sarah's Guardian turnaround sheet) - a cell that nails it is done.
rem   SDXL ArtUniverse: 14 samplers x 4..48 steps (336) - FLUX.1 FusionV2: 7 recipes x 8..32 (147) - schnell: 2..8 (75)
rem   klein base: 5 samplers x 8..32 (105) - klein distilled: 2..8 (75)
rem It also re-runs what failed when ComfyUI crashed at 19:17: the rest of the klein bake-off and Sarah's 84 pose sheets.
rem The queue now WAITS if ComfyUI stops answering (it used to fail every job). Close this window any time; run it again to carry on.
rem Disk: step 0 deletes only true duplicates (ComfyUI's own copy of each picture, out\_comfy) and links the bake-off copies.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
echo.
echo [0/4] Freeing disk: ComfyUI's duplicate copies, and the bake-off copies turned into links (no picture is lost) ...
python -m forge housekeeping --prune-comfy --dedupe
echo.
echo [1/4] ComfyUI ...
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
echo.
echo [2/4] Putting back what failed while ComfyUI was down ...
python -m forge retry bakeoff/flux2_klein_v1
python -m forge retry bakeoff/sprite_poses_klein_v1
echo.
echo [3/4] Queuing the sampler grids ...
python -m forge models scan >nul
python -m forge bakeoff submit games\turing_accords\bakeoff\sampler_grid_sdxl_v1.json
python -m forge bakeoff submit games\turing_accords\bakeoff\sampler_grid_flux1_v1.json
python -m forge bakeoff submit games\turing_accords\bakeoff\sampler_grid_schnell_v1.json
python -m forge bakeoff submit games\turing_accords\bakeoff\sampler_grid_klein_base_v1.json
python -m forge bakeoff submit games\turing_accords\bakeoff\sampler_grid_klein_distilled_v1.json
echo.
echo [4/4] Running until the queue is empty (klein first, then the pose sheets, then the grids) ...
python -m forge worker --gpu --once
echo.
echo Building the comparison pages ...
for %%S in (flux2_klein_v1 sprite_poses_klein_v1 sampler_grid_sdxl_v1 sampler_grid_flux1_v1 sampler_grid_schnell_v1 sampler_grid_klein_base_v1 sampler_grid_klein_distilled_v1) do python -m forge bakeoff report %%S
if exist "out\bakeoff\sampler_grid_sdxl_v1\index.html" start "" "out\bakeoff\sampler_grid_sdxl_v1\index.html"
echo.
echo Done. Tell Claude "the sampler round is finished" - it reads everything from the folders.
pause
