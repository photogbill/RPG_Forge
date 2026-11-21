@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Song review (2026-11-19): every Suno sheet the game lists (games\<game>\song_review.json) checked against William's
rem Suno rules, the singers' voice locks, "not generic" and "complex enough" (held against his own finished lyrics).
rem It changes no sheet: it writes a report (out\song_review\<game>\<date>\REPORT.md) and opens it.
rem One file or folder instead:  review_songs.bat "D:\Turing Accords Game\Calliope_Songs"
rem Only what needs work:        review_songs.bat --problems
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge.song_review %* --open
echo.
pause
