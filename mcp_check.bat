@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The connector's self-test (BUILD 83): the MCP library, its tools, and the forge answering. Changes nothing.
if not exist venv_mcp\Scripts\python.exe (echo Run mcp_setup.bat first. & pause & exit /b 1)
venv_mcp\Scripts\python.exe -m forge.mcpserver --check
echo.
pause
