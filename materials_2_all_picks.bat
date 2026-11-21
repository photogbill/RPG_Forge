@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Materials, step 2 (BUILD 87): a true channel set for EVERY kept Filter Forge pick (the game's cull file).
rem Run materials_1_filter_forge.bat first - this needs its proof.
rem It is long: every pick is rendered again once a channel (about seven renders a pick), on the processor.
rem Leave it running; close it any time; run it again and it carries on where it stopped (a pick that already
rem has its set is skipped). It may run beside the 3D queue.
rem   materials_2_all_picks.bat 40      only the next 40 picks this time
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if "%~1"=="" (
  python -m forge.materials ff-picks
) else (
  python -m forge.materials ff-picks --limit %1
)
python -m forge.materials sheets
echo.
echo Done for now. The report is out\materials\^<game^>\picks_channels.md; the town sheets are beside it.
pause
