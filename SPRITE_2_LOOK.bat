@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
echo.
echo  SPRITE TEST - STEP 2: LOOK  (safe any time, even while it runs)
echo  Building the comparison pages ...
python -m forge bakeoff report sprite_samplers_v2
python -m forge bakeoff report sprite_samplers_klein_v2
python -m forge bakeoff report sprite_flux1_v2
python -m forge bakeoff report guardian_prerap_v1
python -m forge bakeoff report guardian_prerap_flux_v1
python -m forge bakeoff report guardian_prerap_klein_v1
python -m forge bakeoff report sprite_samplers_v1
python -m forge eta
if exist "out\bakeoff\sprite_samplers_v2\index.html" start "" "out\bakeoff\sprite_samplers_v2\index.html"
echo.
echo  Best sheets: out\bakeoff\sprite_samplers_v2\across_sarah_*.png  (rows = models, columns = samplers)
pause
