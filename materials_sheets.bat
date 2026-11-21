@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The material sheets again (BUILD 87): one sheet a town (every channel, a piece under the lamp, a ball)
rem and each place's ground with its wear on and off. Seconds; no graphics card. Results: out\materials\
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge.materials sheets
pause
