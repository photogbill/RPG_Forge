@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Measure every song and sound and write the gain that evens them out (files are never changed).
call venv\Scripts\python.exe -m forge.audio.loudness measure "D:\Turing Accords Game\project\assets\music" %*
call venv\Scripts\python.exe -m forge.audio.loudness measure "D:\Turing Accords Game\project\assets\sfx" --out "D:\Turing Accords Game\project\data\audio_loudness_sfx.json" %*
pause
