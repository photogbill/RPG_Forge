@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title RPG_Forge - the connector for Claude
rem Makes RPG_Forge a connector (an MCP server) that Claude Fable and Claude Opus can use from a chat (BUILD 83).
rem   1. A small Python environment of its own, venv_mcp, so the art worker's environment is never touched.
rem   2. The MCP library and Pillow into it (requirements-mcp.txt).
rem   3. The self-test.
rem   4. Claude's settings: it can add the forge for you (keeping a copy of the file first), or put the lines on the
rem      clipboard for you to paste. Then quit Claude fully and open it again.
rem   5. If Claude still shows no forge tools after a full quit and restart (the Microsoft Store install of Claude did
rem      exactly that on 2026-11-19): mcp_extension.bat is the other way in, and it worked at once.
rem Safe to run again: what is already there is kept.
if not exist venv\Scripts\python.exe (echo Run install.bat first. & pause & exit /b 1)
if exist venv_mcp\Scripts\python.exe goto have_env
echo Making venv_mcp ...
venv\Scripts\python.exe -m venv venv_mcp
if errorlevel 1 (echo Could not make venv_mcp - scroll up for the reason. & pause & exit /b 1)
:have_env
echo Installing the MCP library into venv_mcp ...
venv_mcp\Scripts\python.exe -m pip install --upgrade pip >nul
venv_mcp\Scripts\python.exe -m pip install -r requirements-mcp.txt
if errorlevel 1 (echo The install did not finish - scroll up for the reason. & pause & exit /b 1)
echo.
venv_mcp\Scripts\python.exe -m forge.mcpserver --check
if errorlevel 1 (echo. & echo The self-test did not pass - scroll up. & pause & exit /b 1)
echo.
venv_mcp\Scripts\python.exe -m forge.mcpserver.claude_settings
echo.
pause
