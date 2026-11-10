@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Record the licence of an outside tool once (name, version, commercial yes/no, any condition, where you checked).
rem   handoff_tool_add.bat              asks the questions one at a time
rem   handoff_tool_add.bat list         shows the tools on file
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if /i "%~1"=="list" (python -m forge handoff tool list) else (python -m forge handoff tool add %*)
pause
