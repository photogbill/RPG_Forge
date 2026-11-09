@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem OPTIONAL. Installs comfyui_controlnet_aux (Fannovel16) for depth ControlNet ("control": {"type": "depth"}).
rem Canny control needs none of this - the forge computes canny itself. The forge only ever asks it for the
rem commercial-OK depth weights (Depth Anything V2 Small, Apache-2.0; MiDaS, MIT), which it downloads on first use.
if not exist engines\ComfyUI\venv\Scripts\activate.bat (echo ComfyUI is not installed - run install_comfy.bat first. & pause & exit /b 1)
if not exist engines\ComfyUI\custom_nodes mkdir engines\ComfyUI\custom_nodes
if exist engines\ComfyUI\custom_nodes\comfyui_controlnet_aux goto upd
git clone https://github.com/Fannovel16/comfyui_controlnet_aux engines\ComfyUI\custom_nodes\comfyui_controlnet_aux
goto deps
:upd
pushd engines\ComfyUI\custom_nodes\comfyui_controlnet_aux
git pull
popd
:deps
call engines\ComfyUI\venv\Scripts\activate.bat
pip install -r engines\ComfyUI\custom_nodes\comfyui_controlnet_aux\requirements.txt
echo.
echo Done. Restart ComfyUI (run_worker.bat).
pause
