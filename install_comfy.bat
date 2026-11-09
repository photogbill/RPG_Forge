@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo == RPG_Forge: install ComfyUI into engines\ComfyUI ==
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
where git >nul 2>nul || (echo git is required: https://git-scm.com/download/win & pause & exit /b 1)
if not exist engines mkdir engines
if not exist engines\ComfyUI (
  git clone https://github.com/comfyanonymous/ComfyUI engines\ComfyUI || (echo clone failed & pause & exit /b 1)
) else (
  echo engines\ComfyUI exists - updating
  pushd engines\ComfyUI && git pull && popd
)
echo Creating ComfyUI's own environment (engines\ComfyUI\venv) ...
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
if not exist engines\ComfyUI\venv %PY% -m venv engines\ComfyUI\venv
call engines\ComfyUI\venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
echo Installing PyTorch with CUDA 12.8 (this is the big download) ...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 || (echo torch install failed & pause & exit /b 1)
pip install -r engines\ComfyUI\requirements.txt || (echo ComfyUI requirements failed & pause & exit /b 1)
call deactivate
for %%d in (checkpoints diffusion_models text_encoders vae loras controlnet upscale_models embeddings) do if not exist models\%%d mkdir models\%%d
echo Pointing ComfyUI at every model folder in forge.json (models\ plus your own collections) ...
call venv\Scripts\activate.bat
python -m forge comfy-paths
echo.
echo ComfyUI installed. Start everything with run_worker.bat
pause
