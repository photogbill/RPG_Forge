@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The launch-site run (2026-11-13): everything the opening mission needs, made as 3D test pieces, with nobody watching.
rem   1. the six sentry bodies still waiting in the cast list (Ortega, Della, Tran)
rem   2. 30 props of the site            (TRELLIS.2)   out\trellis\silo_props_1\
rem   3. 5 buildings of the site         (Pixal3D)     out\trellis\silo_buildings_1\
rem   4. 18 people of the site, with skeletons and motions   out\cast\silo_people_1\
rem About four to five hours on this card. It approves nothing. Every step skips what is already made, so it is
rem safe to close this window and run it again: it carries on where it stopped.
rem Do not start another art or 3D run while it is going.
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
echo === 1 of 4: the sentries left in the cast list ===
python games\turing_accords\cast_overnight.py games\turing_accords\trellis\cast_test_1.json
echo.
echo === 2 of 4: the props of the site ===
python games\turing_accords\trellis_wait.py
python games\turing_accords\trellis_trial.py games\turing_accords\trellis\silo_props_1.json
echo.
echo === 3 of 4: the buildings of the site ===
python games\turing_accords\trellis_wait.py
python games\turing_accords\trellis_trial.py games\turing_accords\trellis\silo_buildings_1.json
echo.
echo === 4 of 4: the people of the site ===
python games\turing_accords\trellis_wait.py
python games\turing_accords\cast_overnight.py games\turing_accords\trellis\silo_people_1.json
echo.
echo Finished. Tell Claude "the launch-site run is finished".
echo Reports: out\cast\cast_test_1\REPORT.txt, out\trellis\silo_props_1\REPORT.txt,
echo          out\trellis\silo_buildings_1\REPORT.txt, out\cast\silo_people_1\REPORT.txt
pause
