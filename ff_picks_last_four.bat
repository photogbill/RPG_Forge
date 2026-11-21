@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The last four Filter Forge picks (Fable, 2026-11-17, on William's word: "set the time out way longer than
rem needed so that it finishes"). 393 of the 397 picks are rendered. These four ran out of time:
rem   #10014-1 (once, at 15 minutes), #15751-1 Wood Chips, #16257-1 Plant Lab - Carpet Moss, #16549-1 Vents
rem   (the last three at 15 and again at 25 minutes).
rem Each now gets up to FOUR HOURS. CPU only, no ComfyUI, no graphics card. It may run beside the world queue.
rem Worst case this window is open for sixteen hours; it closes its work by itself. Run it again to carry on.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
echo Planning the picks (the four that ran out of time get four hours each) ...
python games\turing_accords\ff_picks.py plan
if errorlevel 1 (echo Could not plan the picks - tell Claude what the lines above say. & pause & exit /b 1)
echo.
echo Queueing - the 393 already rendered are skipped ...
python -m forge submit games\turing_accords\batches\ff_picks.json --skip-done
if errorlevel 1 (echo Could not queue the picks - tell Claude what the lines above say. & pause & exit /b 1)
echo.
echo Rendering in Filter Forge until the queue is empty. A render may sit for a long time with nothing printed.
python -m forge worker --once
echo.
echo Building the tiling sheets ...
python games\turing_accords\ff_picks.py sheets
if exist "games\turing_accords\ref\ff_palette\picks\index.html" start "" "games\turing_accords\ref\ff_palette\picks\index.html"
echo.
echo Done. Tell Claude "the last four are rendered" - or which ones still ran out of time.
pause
