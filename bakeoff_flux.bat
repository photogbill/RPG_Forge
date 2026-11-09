@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem FLUX bake-offs only (use after new FLUX downloads finish; bakeoff_tonight.bat already includes these two steps).
rem   flux2_klein_v1: every file named *klein* in flux_models\ or models\diffusion_models\ (base: 20 steps cfg 5; distilled: 4 steps cfg 1)
rem   flux1_v1:       every FLUX.1 model in those folders x (no LoRA + every FLUX.1 LoRA in flux_lora\ and lora models\)
rem Reports: bakeoff_report.bat flux2_klein_v1   /   bakeoff_report.bat flux1_v1
rem If ComfyUI was running before the files arrived, close it and start run_worker.bat again so it sees them.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge comfy-paths >nul
python -m forge models scan >nul
python -m forge bakeoff submit games\turing_accords\bakeoff\flux2_klein_v1.json --rescan
echo.
python -m forge bakeoff submit games\turing_accords\bakeoff\flux1_v1.json
echo.
echo If run_worker.bat is not running, start it now.
pause
