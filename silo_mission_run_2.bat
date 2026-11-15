@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The launch-site run, second part (2026-11-13): start this AFTER silo_mission_run.bat says Finished.
rem Tests and the walk in: a T-pose, the survivors years later, lighter crowd bodies, a model comparison,
rem and the things, buildings and people seen on the approach. About three hours on this card.
rem It approves nothing. Every step skips what is already made: safe to close and run again.
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
echo === 1 of 6: tests - T-pose, no helmet, the survivors years later ===
python games\turing_accords\trellis_wait.py
python games\turing_accords\cast_overnight.py games\turing_accords\trellis\silo_tests_1.json
echo.
echo === 2 of 6: the same three people as lighter crowd bodies ===
python games\turing_accords\trellis_wait.py
python games\turing_accords\cast_overnight.py games\turing_accords\trellis\silo_tier_crowd_1.json
echo.
echo === 3 of 6: the trucks and the missile through the building model ===
python games\turing_accords\trellis_wait.py
python games\turing_accords\trellis_trial.py games\turing_accords\trellis\silo_compare_models_1.json
echo.
echo === 4 of 6: things seen on the walk in ===
python games\turing_accords\trellis_wait.py
python games\turing_accords\trellis_trial.py games\turing_accords\trellis\walk_props_1.json
echo.
echo === 5 of 6: buildings seen on the walk in ===
python games\turing_accords\trellis_wait.py
python games\turing_accords\trellis_trial.py games\turing_accords\trellis\walk_buildings_1.json
echo.
echo === 6 of 6: people seen on the walk in ===
python games\turing_accords\trellis_wait.py
python games\turing_accords\cast_overnight.py games\turing_accords\trellis\walk_people_1.json
echo.
echo Finished. Tell Claude "the second launch-site run is finished".
echo Reports: REPORT.txt in out\cast\silo_tests_1, out\cast\silo_tier_crowd_1, out\trellis\silo_compare_models_1,
echo          out\trellis\walk_props_1, out\trellis\walk_buildings_1, out\cast\walk_people_1
pause
