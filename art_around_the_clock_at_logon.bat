@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Has art_around_the_clock.bat start by itself each time you log on to Windows, one minute after log-on (BUILD 82).
rem It adds one Windows Task Scheduler entry, "RPG_Forge art around the clock", and changes nothing else.
rem To take it off again: art_around_the_clock_not_at_logon.bat
echo This adds one Windows Task Scheduler entry, so Art around the clock starts by itself when you log on.
echo It starts one minute after you log on, in its own window. You can close that window any time.
echo.
choice /c YN /m "Add it"
if errorlevel 2 (echo Nothing was changed. & pause & exit /b 0)
schtasks /Create /TN "RPG_Forge art around the clock" /TR "\"%~dp0art_around_the_clock.bat\"" /SC ONLOGON /DELAY 0001:00 /F
if errorlevel 1 goto failed
echo.
echo Done. From your next log-on, Art around the clock starts by itself.
pause
exit /b 0
:failed
echo.
echo Windows did not add it. That usually means it needs administrator rights:
echo right-click art_around_the_clock_at_logon.bat and choose "Run as administrator".
pause
exit /b 1
