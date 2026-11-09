@echo off
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
echo Pointing ComfyUI at .\models ...
(
  echo rpg_forge:
  echo   base_path: %CD%\models
  echo   checkpoints: checkpoints
  echo   diffusion_models: diffusion_models
  echo   text_encoders: text_encoders
  echo   clip: text_encoders
  echo   vae: vae
  echo   loras: loras
  echo   controlnet: controlnet
  echo   upscale_models: upscale_models
) > engines\ComfyUI\extra_model_paths.yaml
for %%d in (checkpoints diffusion_models text_encoders vae loras controlnet upscale_models) do if not exist models\%%d mkdir models\%%d
echo.
echo ComfyUI installed. Models go in .\models\... (python -m forge models list ^| pull ^<name^>)
echo Start everything with run_worker.bat
pause
