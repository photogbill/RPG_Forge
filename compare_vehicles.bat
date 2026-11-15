@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem TRELLIS.2 against Pixal3D on the two trucks and the missile (Fable, 2026-11-14).
rem Both sets are already made (silo_props_1 and silo_compare_models_1): this only draws them side by side
rem from the same angles and opens the picture. No graphics card, no ComfyUI, about a minute. Makes nothing new.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python games\turing_accords\compare_models.py
if errorlevel 1 (echo It stopped - tell Claude what the lines above say. & pause & exit /b 1)
if exist "out\trellis\silo_compare_models_1\_review\compare_vehicles.jpg" start "" "out\trellis\silo_compare_models_1\_review\compare_vehicles.jpg"
echo.
echo Done. The picture: out\trellis\silo_compare_models_1\_review\compare_vehicles.jpg
pause
