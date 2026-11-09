@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The finishing bake-off: four pictures x four SDXL checkpoints x six ways of finishing a painting at 1920x1080
rem (upscale only, refine 0.30, refine 0.45, FreeU, face repair at 0.30 and 0.50) = 88 paintings, about 1h45m.
rem It answers: does the refine pass help, how hard should it push, is FreeU worth it, how strong should face repair be.
rem Usage: bakeoff_finish.bat    then run_worker.bat.    Report when done: bakeoff_report.bat finish_v1
rem Open out\bakeoff\finish_v1\index.html - the "detail" sheets at the top are the ones to judge.
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
echo Scanning model folders (header-only, fast) ...
python -m forge models scan >nul
python -m forge bakeoff submit games\turing_accords\bakeoff\finish_v1.json
echo.
echo Queued. If run_worker.bat is not running, start it now. Progress: doctor.bat. Comparison when done: bakeoff_report.bat finish_v1
pause
