@echo off
chcp 65001 >nul
rem publish.bat is the old name - push.bat does the work now.
call "%~dp0push.bat" %*
