@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Material Maker (free, MIT licence): the material and shader tool, started so that what it saves stays on D:.
rem By itself it would keep its settings and library in the Windows user folder; this window points them at
rem local\material_maker_data instead. Safe to close and run again.
rem It uses the graphics card for its previews: do not start it while an art or 3D run is going.
if not exist "engines\material_maker\material_maker.exe" (echo Material Maker is not in engines\material_maker. Nothing was started. & pause & exit /b 1)
set "MMDATA=%~dp0local\material_maker_data"
if not exist "%MMDATA%\cache" mkdir "%MMDATA%\cache"
set "APPDATA=%MMDATA%"
set "LOCALAPPDATA=%MMDATA%\cache"
set "XDG_DATA_HOME=%MMDATA%"
set "XDG_CONFIG_HOME=%MMDATA%"
set "XDG_CACHE_HOME=%MMDATA%\cache"
echo %date% %time% started Material Maker, data in %MMDATA%>>"%MMDATA%\launcher.log"
start "" "engines\material_maker\material_maker.exe"
echo Material Maker is starting in its own window. Its settings and library are kept in local\material_maker_data.
timeout /t 4 >nul
