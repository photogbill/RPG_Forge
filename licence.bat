@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Record a model licence you have checked yourself (a Civitai checkpoint or LoRA). The forge never guesses one.
rem   licence.bat "ArtUniverseSDXL_v8.safetensors" "CreativeML Open RAIL++-M" yes "civitai page: Sell images = allowed"
rem   yes = commercial use of generated images is allowed; no = it is not (then it can never ship).
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if "%~3"=="" (echo usage: licence.bat "file" "licence name" yes^|no "where you checked" & pause & exit /b 2)
python -m forge models licence "%~1" "%~2" %~3 "%~4"
pause
