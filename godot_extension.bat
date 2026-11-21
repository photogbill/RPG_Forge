@echo off
cd /d "%~dp0"
rem Shows the Godot connector extension file in Explorer, selected, ready to install in Claude (BUILD 98 Part 13).
if not exist "local\mcp\godot-turing-accords.mcpb" (echo The file is missing: local\mcp\godot-turing-accords.mcpb & pause & exit /b 1)
explorer /select,"%~dp0local\mcp\godot-turing-accords.mcpb"
echo In Claude: Settings - Desktop app - Manage (beside Extensions) - Advanced settings - Extension Developer - Install Extension... and pick the selected file.
echo Or: double-click the selected file, or drag it onto that Extensions page.
pause
