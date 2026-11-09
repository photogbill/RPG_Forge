@echo off
setlocal
cd /d "%~dp0"
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
if exist engines\ComfyUI\main.py (
  echo Starting ComfyUI (minimised) ...
  start "ComfyUI" /min cmd /c "cd /d "%CD%\engines\ComfyUI" && call venv\Scripts\activate.bat && python main.py --listen 127.0.0.1 --port 8188 --output-directory "%CD%\out\_comfy" --input-directory "%CD%\out\_comfy_in" --disable-auto-launch"
  timeout /t 8 >nul
) else (
  echo ComfyUI is not installed (install_comfy.bat) - GPU jobs will fail, CPU jobs still run.
)
call venv\Scripts\activate.bat
echo GPU worker running. Drop jobs into jobs\pending\ - Ctrl+C stops it. Log: logs\
python -m forge worker --gpu
pause
