@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The world queue (BUILD 39): makes what the game's world list wants, the thing that appears first in the story
rem first, checks each one and reports it - then the next, until you stop it. The list is games\<game>\wanted_3d\.
rem Anyone may add to the list while this runs; it reads the list again before every thing. You never edit this file.
rem It waits whenever the graphics card is someone else's (another run, the art worker, ComfyUI busy).
rem It approves nothing: what passes its checks goes to Art - Review and approve; what fails one is held back with
rem the reason and a picture of what the check saw (3D - World list).
rem To stop: close this window (at most the thing in hand is lost; it is taken up first next time), or choose
rem "Stop after this one" in 3D - Runs.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
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
echo ComfyUI did not come up in 5 minutes - open its window (taskbar: ComfyUI) and read the last lines. Nothing was made.
pause & exit /b 1
:comfyok
echo ComfyUI is up.
echo.
python -m forge 3d world run
echo.
echo The world queue has stopped. What it did: 3D - Runs, or out\3d\world\^<game^>\REPORT.txt
pause
