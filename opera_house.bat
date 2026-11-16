@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Rebuild the opera house in Blender from whatever the world queue has made (BUILD 44: the full-scale house, a full
rem house of about 1,800 people, two lighting looks) and render its fourteen views in both looks plus the rise.
rem It reads the models and changes none of them. Result: out\3d\places\turing_accords\opera_house\
set "BLENDER=C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
if not exist "%BLENDER%" (echo Blender was not found at "%BLENDER%". Edit this file and set BLENDER to your blender.exe. & pause & exit /b 1)
echo Building the opera house at full scale. From nothing this takes 15 to 25 minutes (each body is posed six ways);
echo the graphics card is used for the pictures, a few seconds each. Safe to run beside the world queue.
"%BLENDER%" --background --factory-startup --python "games\turing_accords\scenes\opera_house_build.py" -- --all --render
echo.
echo Done. The report and the pictures are in out\3d\places\turing_accords\opera_house\
start "" "out\3d\places\turing_accords\opera_house\renders"
pause
