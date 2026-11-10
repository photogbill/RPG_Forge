@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
rem ======================================================================
rem  Night 3 GPU tests - big scenes (G3), room states and inpaint (G4).
rem  8 small jobs, about 15-25 minutes on the 3080 Ti. Test pictures only.
rem
rem  What it does:
rem    1. puts the half-finished bake-off job back in the queue
rem    2. parks the rest of the bake-off (jobs\paused\) so only these tests run
rem    3. queues the 8 test jobs from this folder
rem    4. starts ComfyUI if it is not running, runs the tests, then stops
rem    5. brings the bake-off back into the queue
rem  Afterwards: run_worker.bat (or bakeoff_tonight.bat) carries on the bake-off.
rem  If you stop this window early, run resume.bat to un-park the bake-off.
rem ======================================================================
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
echo [1/5] Putting the stopped job back in the queue ...
python -m forge requeue
echo [2/5] Parking the bake-off while the tests run ...
python -m forge pause
echo [3/5] Queueing the Night 3 tests ...
for %%F in (night3_tests\g*.json) do python -m forge submit "%%F"
echo [4/5] Running the tests ...
python -m forge comfy-paths >nul
python -m forge comfy-up >nul
if not errorlevel 1 goto run
echo Starting ComfyUI in its own minimised window ...
start "ComfyUI" /min "%CD%\start_comfy.bat"
echo Waiting 20 s for ComfyUI to come up ...
timeout /t 20 >nul
:run
python -m forge worker --gpu --once
echo [5/5] Bringing the bake-off back into the queue ...
python -m forge resume
python -m forge status
echo.
echo Done. Results are in out\ (folders named ...g3_... and ...g4_...).
echo Tell Claude the tests have run. To continue the bake-off: run_worker.bat
pause
