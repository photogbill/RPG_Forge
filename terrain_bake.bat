@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Real ground from DTED Level 0 (BUILD 77). Bakes every window the game asks for (games\<game>\terrain\world.json) -
rem a 16-bit height picture, a shaded relief, a picture of how each height was made (measured, invented, edited), water when
rem the Natural Earth files are in local\natural_earth\ - into out\terrain\<game>\, with a contact sheet. The processor only;
rem the graphics card is never used. The DTED stays where it is (forge.json dted_dir, default local\dted, a folder or its zip).
rem   terrain_bake.bat                 every window
rem   terrain_bake.bat kerguelen       one window
rem   terrain_bake.bat proof           the reader against known ground first
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if /i "%~1"=="proof" (
  python -m forge terrain proof
) else if "%~1"=="" (
  python -m forge terrain proof
  python -m forge terrain bake
) else (
  python -m forge terrain bake --only %1
)
pause
