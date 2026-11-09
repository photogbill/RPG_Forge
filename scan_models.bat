@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Inspect every checkpoint and LoRA in the model folders (forge.json model_dirs): kind, base model, triggers.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge models scan
echo Written: models\INVENTORY.md and models\inventory.json
pause
