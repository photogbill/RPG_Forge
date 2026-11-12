@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Writes every Filter Forge filter the forge can see (name, file, kind, presets) to out\filter_forge_list.txt,
rem so Claude can match the materials bake-off to real filters by name. Read-only: nothing in Filter Forge is touched.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if not exist out mkdir out
python -m forge filter-forge list --all > out\filter_forge_list.txt 2>&1
python -c "import sys; n=sum(1 for l in open(r'out\filter_forge_list.txt',encoding='utf-8',errors='replace') if '.ffxml' in l); print(n, 'filters written to out\\filter_forge_list.txt - tell Claude it is there.')"
pause
