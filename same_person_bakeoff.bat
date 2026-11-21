@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The same person, changed - the bake-off (BUILD 74 part 4). Twelve cases from pictures that already exist (four poses,
rem four expressions, two ages, two reference sheets into photoreal A-pose pictures), each through every method its change
rem allows (masked, guided, instructed), two seeds; every result checked that nothing else moved. Into
rem out\same_person\<game>\<time>\ with report.md. It uses the graphics card: start it when nothing else is generating.
rem It needs ComfyUI with the models already on this PC (FLUX.2 klein 4B, RealVisXL V5, the xinsir union ControlNet).
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge comfy-up >nul
if errorlevel 1 (echo ComfyUI is not running - start it with start_comfy.bat first, then run this again. & pause & exit /b 1)
python -m forge 3d same-person bakeoff %*
pause
