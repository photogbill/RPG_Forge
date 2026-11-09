@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Pull everything FLUX needs into .\models (ComfyUI sees these folders through extra_model_paths.yaml).
rem   FLUX.2 [klein] 4B  base + distilled (fp8, ~4 GB each) + Qwen3-4B text encoder (~8 GB) + FLUX.2 VAE   — Apache-2.0
rem   FLUX.1 [schnell]   unet fp8 (~12 GB) + CLIP-L + T5-XXL fp8 (~5 GB) + FLUX.1 VAE                       — Apache-2.0
rem   FLUX.1 [dev]       unet fp8 (~12 GB)  — NON-COMMERCIAL: only if you pass "dev":  pull_flux.bat dev
rem   klein 9B encoder   qwen_3_8b_fp8mixed (~9 GB) for the klein-9B base you downloaded: pull_flux.bat 9b   (or: pull_flux.bat dev 9b)
rem About 34 GB without dev; resumable (files already present are skipped). Then: bakeoff_flux.bat
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge models pull flux2-vae flux2-klein-text-encoder flux2-klein-4b flux1-vae flux1-text-encoders flux1-schnell-fp8
if /i "%~1"=="dev" python -m forge models pull flux1-dev-fp8
if /i "%~1"=="9b" python -m forge models pull flux2-klein-9b-text-encoder
if /i "%~2"=="9b" python -m forge models pull flux2-klein-9b-text-encoder
if /i "%~2"=="dev" python -m forge models pull flux1-dev-fp8
echo.
echo Refreshing ComfyUI's model paths and the inventory ...
python -m forge comfy-paths
python -m forge models scan >nul
echo.
echo Done. If ComfyUI is running, restart it (start_comfy.bat / run_worker.bat) so it sees the new files.
pause
