@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The opera finale, overnight. One question at the start, then it runs on its own until it is done (a few hours, at
rem most until morning): the lace gown from the world queue, depth and trees for the finale's photographs, the finale
rem rebuilt and rendered at 1080p and 4K, the opera house rebuilt, a contact sheet and a report. It keeps the computer
rem awake while it runs. Safe to run again: every step skips what is already made.
rem Result and report: out\3d\places\turing_accords\opera_finale\  (overnight_REPORT.txt, share\overnight\)
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge comfy-paths >nul
python -m forge comfy-up >nul
if not errorlevel 1 goto run
echo Starting ComfyUI in its own minimised window ...
start "ComfyUI" /min "%~dp0start_comfy.bat"
echo Waiting for ComfyUI to come up (up to five minutes) ...
for /l %%i in (1,1,30) do (
  timeout /t 10 >nul
  python -m forge comfy-up >nul && goto run
)
echo ComfyUI did not come up in five minutes. Open its window (taskbar: ComfyUI) and read the last lines. Nothing was made.
pause & exit /b 1
:run
python "games\turing_accords\scenes\finale_overnight.py"
echo.
echo Finished. The report: out\3d\places\turing_accords\opera_finale\overnight_REPORT.txt
echo Tell Claude it is done.
pause
