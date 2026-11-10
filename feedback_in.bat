@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem feedback_in.bat [art_feedback.json] - the notes you made in the game with F9 come back as redo drafts (nothing is queued)
call venv\Scripts\python.exe -m forge feedback-in %*
pause
