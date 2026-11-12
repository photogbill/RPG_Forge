@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The materials bake-off (BUILD 30): SDXL ArtUniverse vs FLUX.2 Klein 4B vs Filter Forge, one flat top-down tile per
rem material per source. Resumable: run it again and it skips what is already queued or done.
rem   bakeoff_materials.bat           plan it and queue it (then run_worker.bat; ~2 hours for 23 materials)
rem   bakeoff_materials.bat report    contact sheets + scores -> out\bakeoff\materials\MATERIALS_VERDICT.md
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if /i "%~1"=="report" (
  python -m forge tiles report
  start "" "out\bakeoff\materials"
  pause
  exit /b 0
)
echo Scanning model folders (header-only, fast) ...
python -m forge models scan >nul
python -m forge tiles plan
if errorlevel 3 (
  echo.
  echo  Filter Forge would be left out of this bake-off ^(see the line above^).
  choice /M "Queue SDXL and Klein anyway"
  if errorlevel 2 (echo Nothing queued. & pause & exit /b 1)
)
echo.
python -m forge bakeoff submit games\turing_accords\bakeoff\materials_sdxl_v1.json --rescan
python -m forge bakeoff submit games\turing_accords\bakeoff\materials_klein_v1.json
python -m forge tiles submit
echo.
echo Queued. If run_worker.bat is not running, start it now.
echo Filter Forge's renders run first (a few minutes): if any fail, they show in jobs\failed - tell Claude.
echo When it is all done: bakeoff_materials.bat report
pause
