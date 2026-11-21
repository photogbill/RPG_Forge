@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Materials, step 3 (BUILD 87): Material Maker makes what no Filter Forge filter covers.
rem The forge's six graphs (canvas, fused glass, whitewash over brick, a chalked wall, ash crust, caliche),
rem each in the two states the game names (broken / mended), at 2048, with every channel.
rem Material Maker draws on the graphics card. This takes the forge's card lock for each material, so it
rem waits its turn: the 3D queue keeps the card while it makes a model and lends it between two.
rem A small Material Maker window opens for each material and closes by itself. Do not close it by hand.
rem Its settings stay in local\material_maker_data (nothing goes to the Windows user folder).
rem   materials_3_material_maker.bat 1024      a quicker first look at 1024
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
if not exist "engines\material_maker\material_maker.exe" (echo Material Maker is not in engines\material_maker. Nothing was started. & pause & exit /b 1)
call venv\Scripts\activate.bat
echo === the graphs against the installed node library ===
python -m forge.materials mm-lint
if errorlevel 1 (echo A graph does not fit this Material Maker. Nothing was exported. Tell Claude what this says. & pause & exit /b 1)
echo.
echo === exporting ===
if "%~1"=="" (
  python -m forge.materials mm-first
) else (
  python -m forge.materials mm-first --size %1
)
python -m forge.materials sheets
echo.
echo Done. Look at out\materials\^<game^>\material_maker_first.md and the town sheets. Tell Claude "the graphs are exported".
pause
