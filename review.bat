@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Review sheets + a page to rate pictures.  review.bat <suite-or-batch> [--by model]
rem   e.g. review.bat style_v1        review.bat draft_maps --by model
rem   On the page: click 1-5 under each picture, then "Export ratings.json", then: rate.bat <same name>
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "T=%~1"
if "%T%"=="" set /p "T=Suite or batch name: "
python -m forge review %T% --open %2 %3 %4 %5
pause
