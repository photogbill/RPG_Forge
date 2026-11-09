@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Installs the ComfyUI-GGUF custom node (city96) into engines\ComfyUI\custom_nodes so .gguf diffusion models load (UnetLoaderGGUF).
rem Optional: only needed for GGUF files such as flux_models\Flux_realistic_SaMay_v2.gguf. Restart ComfyUI (run_worker.bat) afterwards.
if not exist engines\ComfyUI\venv\Scripts\activate.bat (echo ComfyUI is not installed - run install_comfy.bat first. & pause & exit /b 1)
if not exist engines\ComfyUI\custom_nodes mkdir engines\ComfyUI\custom_nodes
if exist engines\ComfyUI\custom_nodes\ComfyUI-GGUF (
  echo ComfyUI-GGUF already present - updating ...
  pushd engines\ComfyUI\custom_nodes\ComfyUI-GGUF && git pull && popd
) else (
  git clone https://github.com/city96/ComfyUI-GGUF engines\ComfyUI\custom_nodes\ComfyUI-GGUF
)
call engines\ComfyUI\venv\Scripts\activate.bat
pip install -r engines\ComfyUI\custom_nodes\ComfyUI-GGUF\requirements.txt
echo.
echo Done. Restart ComfyUI (close the worker window, start run_worker.bat again).
pause
