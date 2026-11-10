@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The morning report: what the queue did overnight, what failed and why, how long each model took.
rem   night_report.bat              the last 12 hours
rem   night_report.bat --hours 24   or   night_report.bat --since 2026-11-09T21:00
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge report night --open %*
pause
