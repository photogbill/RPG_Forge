@echo off
rem BUILD 98 Part 3: your R5 photos onto the Libraries shelf.
rem Put each subject in D:\RPG_Forge\scans\incoming\<date>_<subject>\ (raw CR3, or TIFFs exported from the Studio), then run this.
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (echo The forge's Python is missing: run install.bat first. & pause & exit /b 1)
venv\Scripts\python.exe -m forge.scans intake
echo.
echo Done. What each folder became is above; the textures are on the Libraries shelf (library\scan\).
pause
