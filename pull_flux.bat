@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Pull everything FLUX needs into .\models (ComfyUI sees these folders through extra_model_paths.yaml).
rem   FLUX.2 klein 4B  base + distilled (about 8 GB each) + Qwen3-4B text encoder (8 GB) + FLUX.2 VAE  - Apache-2.0
rem   FLUX.1 schnell   unet fp8 (12 GB) + CLIP-L + T5-XXL fp8 (5 GB) + FLUX.1 VAE                     - Apache-2.0
rem Both are commercial-OK. Nothing non-commercial is pulled by this file any more (William, 2026-11-09).
rem About 42 GB the first time; resumable - files already here are skipped. Each model is pulled on its own line,
rem so one failed download does not stop the others. Then: bakeoff_flux.bat (or bakeoff_tonight.bat).
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge models pull flux2-vae
python -m forge models pull flux2-klein-text-encoder
python -m forge models pull flux2-klein-4b
python -m forge models pull flux1-vae
python -m forge models pull flux1-text-encoders
python -m forge models pull flux1-schnell-fp8
echo.
echo Refreshing ComfyUI's model paths and the inventory ...
python -m forge comfy-paths >nul
python -m forge models scan >nul
echo.
echo Done. If ComfyUI is running, restart it so it sees the new files (close its window, then run_worker.bat).
pause
