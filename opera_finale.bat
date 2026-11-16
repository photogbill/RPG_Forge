@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Rebuild the opera finale (the forest, the ridge, the beacon, the moon, the comet roses) and render its ten shots (quick; finale_overnight.bat does this and everything before it).
rem Reads the models and the photographs; changes none of them. Result: out\3d\places\turing_accords\opera_finale\
set "BLENDER=C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
if not exist "%BLENDER%" (echo Blender was not found at "%BLENDER%". Edit this file and set BLENDER to your blender.exe. & pause & exit /b 1)
echo Building the opera finale. A few minutes; the graphics card is used for the pictures.
"%BLENDER%" --background --factory-startup --python "games\turing_accords\scenes\opera_finale_build.py" -- --all --render
echo.
echo Done. The report and the pictures are in out\3d\places\turing_accords\opera_finale\
start "" "out\3d\places\turing_accords\opera_finale\renders"
pause
