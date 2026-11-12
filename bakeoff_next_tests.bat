@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The two tests from BAKEOFF_4 (William 2026-11-12), about 40 minutes:
rem   1. ArtUniverse repaints the 8 Klein places at denoise 0.35 / 0.50 / 0.65 (canny keeps the Klein layout) - Klein composition, ArtUniverse paint?
rem   2. Sarah's light form re-prompted (the suit spelled out) + expression grids on Klein base, 4 seeds
rem The queue waits if ComfyUI stops answering. Close this window any time; run it again to carry on.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge housekeeping --prune-comfy >nul
echo.
echo ComfyUI ...
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
echo Queuing the tests ...
python -m forge models scan >nul
python -m forge bakeoff submit games\turing_accords\bakeoff\restyle_klein_to_artuniverse_v1.json
python -m forge bakeoff submit games\turing_accords\bakeoff\sprite_light_klein_v2.json
python -m forge bakeoff submit games\turing_accords\bakeoff\sprite_expressions_klein_base_v1.json
echo.
echo Running until the queue is empty ...
python -m forge worker --gpu --once
echo.
echo Building the comparison pages ...
python -m forge bakeoff report restyle_klein_to_artuniverse_v1
python -m forge bakeoff report sprite_light_klein_v2
python -m forge bakeoff report sprite_expressions_klein_base_v1
if exist "out\bakeoff\restyle_klein_to_artuniverse_v1\index.html" start "" "out\bakeoff\restyle_klein_to_artuniverse_v1\index.html"
echo.
echo Done. Tell Claude "the next tests are finished".
pause
