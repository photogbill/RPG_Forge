@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Whisper large-v3 for the voice bench's words check (BUILD 71): faster-whisper (MIT) in its own environment and the
rem large-v3 weights (MIT) inside engines\voice\whisper\ - about 3 GB. Its caches and temp files stay inside engines\voice\_home\.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge voice get whisper
pause
