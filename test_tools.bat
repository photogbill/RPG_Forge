@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The forge tools test: 13 small jobs, one per tool built on Night 2 (scene_paint, the 2560 street, repaint with and
rem without ControlNet, depth, upscale, icon, sleeve x2, a pipeline, normal map, glow mask). About 20 minutes on the GPU.
rem Every job has priority 10, so it runs ahead of anything else in the queue.
rem Usage: test_tools.bat     then run_worker.bat (if it is not running).   Look at it: review.bat tools_v1
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "MISSING="
if not exist "models\upscale_models\RealESRGAN_x4plus.pth" set "MISSING=1"
if not exist "models\controlnet\xinsir-union-sdxl-promax.safetensors" set "MISSING=1"
if not exist "models\ultralytics\bbox\face_yolov8m.pt" set "MISSING=1"
if not exist "engines\ComfyUI\custom_nodes\comfyui-impact-pack" set "MISSING=1"
if defined MISSING (
  echo.
  echo The paint tools are not fully installed yet. Run these two first, then restart run_worker.bat:
  echo     pull_quality.bat            ^(the upscaler, the ControlNet, the face detector - about 3 GB^)
  echo     install_comfy_faces.bat     ^(FaceDetailer^)
  echo Nothing was queued.
  pause & exit /b 1
)
python -m forge submit games\turing_accords\batches\tools_v1.json
echo.
echo Queued. If run_worker.bat is not running, start it now. Progress: doctor.bat.  When done: review.bat tools_v1
pause
