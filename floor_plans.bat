@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The floor-plan generator (BUILD 29). With nothing after it: every town the game can lay out, the archetype
rem suggested for each and why. With a town and an era: four candidate plans, each a map + greybox + paint guide,
rem in out\layout\<game>\<town>\<era>\<archetype>\seed_<n>\  - nothing is written into the game until you approve one.
rem   floor_plans.bat linden_mills war
rem   floor_plans.bat linden_mills after purity_town
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if "%~1"=="" (
  python -m forge layout sheets
) else if "%~3"=="" (
  python -m forge layout generate %1 --era %2
) else (
  python -m forge layout generate %1 --era %2 --archetype %3
)
pause
