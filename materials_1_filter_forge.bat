@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Materials, step 1 (BUILD 87): Filter Forge's own channels for the texture library.
rem   1. THE PROOF (a few minutes): three filters rendered small, to find which preset number is which channel
rem      (normal, height, roughness, occlusion). It reads the answer off the pictures; it does not guess.
rem   2. If the proof says yes: a true channel set for every library picture that Filter Forge made
rem      (games\<game>\ref\materials) - put beside the picture under new names; no file there is changed.
rem   3. Two more seeds of each ground the game lists, and the three mixed so a street never shows its tile.
rem   4. The wear decals (cracks, scorch, grime) and the sheets: one a town, and each place's ground with its
rem      wear on and off.
rem Filter Forge works on the processor: this may run beside the 3D queue (both go a little slower).
rem No graphics card, no ComfyUI. Close the window any time; run it again and it carries on.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
echo.
echo === 1 of 4: the proof ===
python -m forge.materials ff-proof
if errorlevel 2 (
  echo.
  echo The proof did not come out. Nothing else was started. Tell Claude what this window says.
  pause & exit /b 1
)
echo.
echo === 2 of 4: the library's channel sets ===
python -m forge.materials ff-library
echo.
echo === 3 of 4: three seeds and a mix for each ground ===
python -m forge.materials ff-seeds
echo.
echo === 4 of 4: decals and sheets ===
python -m forge.materials decals
python -m forge.materials sheets
echo.
echo Done. The reports and sheets are in out\materials\. Tell Claude "the channels are rendered".
pause
