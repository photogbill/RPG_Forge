@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist venv goto noinstall
call venv\Scripts\activate.bat
if not exist engines\ComfyUI\main.py goto nocomfy
rem refresh ComfyUI's model folders from forge.json (models\ plus your own collections) every start
python -m forge comfy-paths >nul
python -m forge comfy-up >nul
if not errorlevel 1 goto already
echo Starting ComfyUI in its own minimised window ...
start "ComfyUI" /min "%~dp0start_comfy.bat"
echo Waiting 15 s for ComfyUI to come up ...
timeout /t 15 >nul
goto worker
:already
echo ComfyUI is already running - using it.
goto worker
:nocomfy
echo ComfyUI is not installed (install_comfy.bat) - GPU jobs will fail, CPU jobs still run.
:worker
echo.
echo GPU worker running. Drop jobs into jobs\pending\ - Ctrl+C stops it. Log: logs\
python -m forge worker --gpu
pause
exit /b
:noinstall
echo Run install.bat first.
pause
