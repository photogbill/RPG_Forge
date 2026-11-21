@echo off
chcp 65001 >nul
setlocal
rem Takes off the Windows Task Scheduler entry art_around_the_clock_at_logon.bat added (BUILD 82). Changes nothing else.
schtasks /Delete /TN "RPG_Forge art around the clock" /F
if errorlevel 1 goto failed
echo.
echo Done. Art around the clock no longer starts by itself when you log on.
pause
exit /b 0
:failed
echo.
echo Windows did not take it off. Either it was never added, or it needs administrator rights:
echo right-click art_around_the_clock_not_at_logon.bat and choose "Run as administrator".
pause
exit /b 1
