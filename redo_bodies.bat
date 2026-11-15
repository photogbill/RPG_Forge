@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The bodies that came out wrong in the second launch-site run, with new words (Fable, 2026-11-14):
rem Kim with one arm (two wordings), the T-pose test, the refugee boy and the teen girl. Five bodies,
rem picture - 3D body - skeleton - motions, about 40 minutes on this card.
rem It approves nothing. Every step skips what is already made: safe to close and run again.
rem Do not start it while another art or 3D run (or the world queue) is using the graphics card.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
if not exist engines\rig\venv (echo Run trellis_rig_install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge comfy-up >nul
if not errorlevel 1 goto comfyok
echo Starting ComfyUI in its own minimised window ...
start "ComfyUI" /min "%~dp0start_comfy.bat"
set /a N=0
:waitloop
timeout /t 10 >nul
python -m forge comfy-up >nul
if not errorlevel 1 goto comfyok
set /a N+=1
if %N% lss 30 goto waitloop
echo ComfyUI did not come up in 5 minutes - open its window (taskbar: ComfyUI) and read the last lines. Nothing was run.
pause & exit /b 1
:comfyok
echo ComfyUI is up.
echo.
python games\turing_accords\trellis_wait.py
if errorlevel 1 (echo Nothing was run. & pause & exit /b 1)
echo.
python games\turing_accords\cast_overnight.py games\turing_accords\trellis\redo_bodies_1.json
echo.
echo Finished. Tell Claude "the redo bodies are finished".
echo Report: out\cast\redo_bodies_1\REPORT.txt    Pictures: out\trellis\redo_bodies_1\pictures
pause
