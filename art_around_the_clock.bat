@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Art around the clock - RPG_Forge
rem The never-stop launcher (BUILD 82, 2026-11-19). Requirement #1: the graphics card never sits idle while there is art to make.
rem It keeps ComfyUI and the world queue running, day and night:
rem   - ComfyUI is started in its own minimised window whenever it stops answering (never while another step has the card).
rem   - The world queue runs WITHOUT stopping when the list is empty: it waits for the list to grow. It still steps aside
rem     for anything else that needs the graphics card. If it stops by itself, it is started again.
rem   - Once a day (05:00, and at start if the last was over 20 hours ago), the daily redo: what did not pass goes back in line.
rem   - Every hour it says how many hours of work are left on the list.
rem   - It keeps the computer from going to sleep while it runs (the screen may still turn off).
rem To stop it: close this window, or choose Stop in 3D - Runs. ComfyUI keeps running in its own window.
rem To have it start by itself when you log on: run art_around_the_clock_at_logon.bat once.
rem To see what it sees without starting anything: art_around_the_clock.bat --look
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge.around_the_clock %*
echo.
echo Art around the clock has stopped. Run art_around_the_clock.bat to start it again.
pause
