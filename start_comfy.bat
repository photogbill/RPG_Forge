@echo off
chcp 65001 >nul
rem Starts ComfyUI from its own environment, output folders inside the repo. Used by run_worker.bat;
rem double-click it alone to watch ComfyUI's console.
cd /d "%~dp0engines\ComfyUI"
if not exist venv\Scripts\activate.bat goto missing
call venv\Scripts\activate.bat
python main.py --listen 127.0.0.1 --port 8188 --output-directory "%~dp0out\_comfy" --input-directory "%~dp0out\_comfy_in" --disable-auto-launch
echo.
echo ComfyUI exited. Scroll up for the reason.
pause
exit /b
:missing
echo ComfyUI is not installed - run install_comfy.bat
pause
