@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Puts in the forge changes a Claude session prepared while the world queue was running (BUILD 78). They wait in
rem _xfer\waiting\. If the queue is running it asks you first, and stops it only when you type S - after the thing in hand,
rem so nothing is lost - then starts it again. A file someone changed since the session read it is never overwritten: the
rem whole set waits and this window says which file. What every file was is kept; if a test fails, all of it goes back.
rem You never edit this file.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge.sync_when_idle %*
echo.
pause
