@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo == RPG_Forge install ==
echo Everything stays in this folder: %CD%
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>nul || (
  echo Python 3.10+ is required. Install it from https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH".
  pause & exit /b 1
)
if not exist venv (
  echo Creating virtual environment in .\venv ...
  %PY% -m venv venv || (echo venv failed & pause & exit /b 1)
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
echo Installing requirements (Pillow, numpy, huggingface_hub) ...
pip install -r requirements.txt || (echo pip install failed & pause & exit /b 1)
python -m forge docs >nul
echo.
python -m forge doctor
echo.
echo Done. Next:
echo   install_comfy.bat   - installs ComfyUI into engines\ComfyUI (GPU generation; ~3 GB download)
echo   run_cpu_worker.bat  - run palette/pixelize/pack jobs now (no GPU needed)
echo   run_worker.bat      - run everything (starts ComfyUI)
pause
