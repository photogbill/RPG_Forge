@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Installs ComfyUI-Impact-Pack + ComfyUI-Impact-Subpack (ltdrdata) into engines\ComfyUI\custom_nodes - the FaceDetailer
rem and UltralyticsDetectorProvider nodes behind a job's "face_fix": true. Restart ComfyUI afterwards (run_worker.bat).
rem The face model itself comes from pull_quality.bat.
if not exist engines\ComfyUI\venv\Scripts\activate.bat (echo ComfyUI is not installed - run install_comfy.bat first. & pause & exit /b 1)
if not exist engines\ComfyUI\custom_nodes mkdir engines\ComfyUI\custom_nodes
if exist engines\ComfyUI\custom_nodes\comfyui-impact-pack goto updpack
git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack engines\ComfyUI\custom_nodes\comfyui-impact-pack
goto subpack
:updpack
echo Impact Pack already present - updating ...
pushd engines\ComfyUI\custom_nodes\comfyui-impact-pack
git pull
popd
:subpack
if exist engines\ComfyUI\custom_nodes\comfyui-impact-subpack goto updsub
git clone https://github.com/ltdrdata/ComfyUI-Impact-Subpack engines\ComfyUI\custom_nodes\comfyui-impact-subpack
goto deps
:updsub
echo Impact Subpack already present - updating ...
pushd engines\ComfyUI\custom_nodes\comfyui-impact-subpack
git pull
popd
:deps
call engines\ComfyUI\venv\Scripts\activate.bat
pip install -r engines\ComfyUI\custom_nodes\comfyui-impact-pack\requirements.txt
pip install -r engines\ComfyUI\custom_nodes\comfyui-impact-subpack\requirements.txt
echo.
echo Done. Restart ComfyUI (close the worker window, start run_worker.bat again), then doctor.bat should say face_fix: OK.
pause
