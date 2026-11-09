@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Models for painted backgrounds - every one commercial-OK:
rem   RealESRGAN_x4plus (BSD-3, 67 MB)          the upscaler
rem   face_yolov8m (Apache-2.0, 52 MB)          the face finder FaceDetailer uses (it only finds faces; your checkpoint repaints them)
rem   ControlNet union SDXL promax (Apache-2.0, ~2.5 GB)   layout lock for repaints (canny / depth / lineart ...)
rem Resumable. Then restart ComfyUI (close the worker window, run run_worker.bat).
rem FaceDetailer also needs its add-on: install_comfy_faces.bat.  Depth control (optional): install_comfy_aux.bat.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge models pull realesrgan-x4plus face-yolov8m controlnet-union-sdxl-promax
echo.
echo Refreshing ComfyUI's model paths ...
python -m forge comfy-paths >nul
echo Done. Restart run_worker.bat so ComfyUI sees the new files.
pause
