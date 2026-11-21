@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Icons and portraits from the made 3D models (BUILD 91).
rem   icons      every game item that has a made model on the world list, as a 512 icon on a clear background:
rem              three-quarter view, one fixed key light, the same rule for every thing.
rem   portraits  head and shoulders of every principal whose body is made: at rest, one warm key, a faint rim.
rem It reads games\<game>\pictures\items_to_models.json and portraits.json (proposal tables) and writes
rem out\pictures\<game>\: icons\, portraits\, the sheets, and MISSING.md (what has no model yet, and why).
rem Blender renders these on the PROCESSOR: no graphics card, no ComfyUI. It may run beside the 3D queue.
rem Run it again any time: only things whose model is new or was made again are pictured again.
rem   icons_from_models.bat again      take every picture again
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if /i "%~1"=="again" (
  python -m forge.threed.modelpics all --again
) else (
  python -m forge.threed.modelpics all
)
echo.
echo Done. Open out\pictures\^<game^>\icons_sheet.png and portraits_sheet.png; MISSING.md is beside them.
pause
