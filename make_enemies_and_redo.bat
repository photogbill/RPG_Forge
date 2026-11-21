@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Makes the game's machines as 3D, and puts back in line the things that did not pass (2026-11-18).
rem   1. The things on the world list that failed or were held back go back in line, each by the forge's own button
rem      (Try again, Make again, Straighten and release, Match and release). It says what it did for each.
rem   2. The world queue then makes everything the list wants and stops when nothing is left.
rem The new list is games\turing_accords\wanted_3d\enemies_game_one.json (23 things; two are held on purpose).
rem 2026-11-19: also humans_animals_game_one.json (28) and cast_game_one.json (15 + Valkyrie's cape). Safe to start while a world queue
rem is running: it asks that one to stop after the item in hand, waits, releases the animals and McKenna, and starts a fresh one.
rem If the world queue is already running it has the new list already: step 2 then says so and starts nothing.
rem It approves nothing: what passes the checks goes to Art - Review and approve; what fails one is held with the reason.
rem Safe to close and run again: what is made is skipped. How long it takes was not measured: 3D - Runs shows the hours left.
rem Do not start it while another art or 3D run is using the graphics card, or while frame rates are being measured.
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
echo === 1 of 2: the things that did not pass go back in line ===
python games\turing_accords\redo_held_1118.py
echo.
echo The running world queue finishes the item in hand and stops, so a fresh one starts with the new picture words:
python games\turing_accords\wait_for_worker_1119.py
if errorlevel 1 (pause & exit /b 1)
echo.
echo The five animals and McKenna (held until a worker with their picture words runs):
python games\turing_accords\release_animals_1119.py
echo.
echo === 2 of 2: the world queue makes what the list wants ===
python -m forge 3d world run --until-empty
echo.
echo Finished. Tell Claude "the enemies run is finished".
echo What it did: 3D - Runs, or out\3d\world\turing_accords\REPORT.txt
pause
