@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem ============================================================================
rem  sprite_intake.bat - a character sheet you drew → the game's sprite sheet.
rem    sprite_intake.bat "<sheet.png or a folder of sheets>" <character> [variant] [--tool "<name version>"]
rem  e.g.  sprite_intake.bat "D:\Sheets\hero_front.png" hero default
rem  First run: the forge guesses which figure is which facing and writes a mapping file + numbers.png.
rem  Fix any number in the mapping file and run the same line again. Nothing of yours is copied or changed.
rem ============================================================================
if "%~2"=="" (
  echo usage: sprite_intake.bat "^<sheet or folder^>" ^<character^> [variant] [--tool "^<name version^>"]
  pause & exit /b 2
)
call venv\Scripts\python.exe -m forge intake %*
pause
