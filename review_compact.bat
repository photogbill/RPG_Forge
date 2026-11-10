@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Small labelled review sheets (12 cells at most, under 1.5 MB) + review_index.json - built for Claude to read.
rem   review_compact.bat finish_v1
rem   review_compact.bat finish_v1 --pairs t0_upscale_only,t1_refine_030     (side by side + 1:1 detail crop)
rem   review_compact.bat sdxl_v1 --prompt icon_coffee_cup                    (one prompt only)
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "T=%~1"
if "%T%"=="" set /p "T=Suite or batch name: "
python -m forge review %T% --compact --open %2 %3 %4 %5 %6
pause
