@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem produce_watch.bat - leave this window open while a long queue runs: the disk guard (parks the queue under 40 GB free,
rem brings it back by itself) and the 24-hour report. Close the window to stop it; nothing is lost.
call venv\Scripts\python.exe -m forge produce watch %*
