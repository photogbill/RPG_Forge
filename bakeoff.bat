@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Queue the bake-off: every checkpoint x every compatible LoRA x the suite's test prompts.
rem Usage: bakeoff.bat                 -> lists the suites on this PC (games\<game>\bakeoff\*.json) and asks which
rem        bakeoff.bat --quick         -> a smoke run: 1 checkpoint, 2 LoRAs, 1 prompt per category
rem        bakeoff.bat path\to\suite.json [--quick]
rem Then start run_worker.bat (or leave it running) and let it work; bakeoff_report.bat builds the comparison.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "SUITE="
set "FLAGS="
:args
if "%~1"=="" goto run
if /i "%~1"=="--quick" (set "FLAGS=%FLAGS% --quick") else (set "SUITE=%~1")
shift
goto args
:run
if "%SUITE%"=="" goto pick
echo Scanning model folders (header-only, fast) ...
python -m forge models scan >nul
python -m forge bakeoff submit "%SUITE%" --rescan %FLAGS%
echo.
echo If run_worker.bat is not running, start it now. Progress: doctor.bat. Comparison: bakeoff_report.bat
pause
exit /b
:pick
echo Bake-off suites on this PC:
for /d %%G in (games\*) do if exist "%%G\bakeoff" for %%F in ("%%G\bakeoff\*.json") do echo   %%F
echo.
set /p "SUITE=Which one? Paste its path: "
if "%SUITE%"=="" (echo Nothing chosen. & pause & exit /b 1)
goto run
