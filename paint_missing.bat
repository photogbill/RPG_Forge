@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Paint what the game is missing: one DRAFT job per painted map that has no approved art yet,
rem with the job type chosen for you (scene_kit / scene_big / scene_state, or "waiting for its base").
rem Maps that share a layout template are drafted as one family. Nothing is submitted.
rem   Draft:  games\turing_accords\batches\draft_missing.json     Table: out\reports\missing_<date>.md
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge brief missing %*
pause
