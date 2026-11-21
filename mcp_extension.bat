@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title RPG_Forge - the connector as an extension file for Claude
rem The other way to give Claude the forge's connector (BUILD 83): an extension file you install by hand.
rem Use it when mcp_setup.bat said "Done" and Claude still has no forge tools after a full quit and restart.
rem   1. Makes local\mcp\rpg-forge.mcpb (a small file that tells Claude how to start the connector in this folder).
rem   2. Opens the folder with the file selected, and says where the Install button is in Claude.
rem   3. If Claude's settings file still has the rpg-forge entry from mcp_setup.bat, it offers to take it out (a copy
rem      of the file kept first): the entry and the extension carry one name, and only one of them is needed.
rem Otherwise changes nothing outside this folder. Safe to run again: the file is made again.
if not exist venv_mcp\Scripts\python.exe (echo Run mcp_setup.bat first. & pause & exit /b 1)
venv_mcp\Scripts\python.exe -m forge.mcpserver.bundle
if errorlevel 1 (echo. & echo The extension file was not made - scroll up for the reason. & pause & exit /b 1)
explorer /select,"%~dp0local\mcp\rpg-forge.mcpb"
echo.
venv_mcp\Scripts\python.exe -m forge.mcpserver.claude_settings --after-extension
echo.
pause
