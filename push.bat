@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
rem ============================================================================
rem  push.bat - commit everything and push to GitHub, Bill-proof.
rem
rem  The commit message comes from COMMIT_MESSAGE.txt when that file exists:
rem  whoever changes files (Claude, a script, you) writes what changed into it,
rem  then you double-click this. The message is appended to CHANGELOG.md in the
rem  same commit, so the repo's history reads; the inbox file itself is ignored
rem  by git and removed after a successful push.
rem  No COMMIT_MESSAGE.txt?  You are asked for a one-line message instead.
rem  Usage: push.bat            (reads COMMIT_MESSAGE.txt or asks)
rem         push.bat "message"  (uses the message given, ignores the file)
rem ============================================================================
where git >nul 2>nul || (echo git is required: https://git-scm.com/download/win & pause & exit /b 1)
if not exist .git (echo This folder is not a git repository. & pause & exit /b 1)

echo == RPG_Forge push ==
git status --short
echo.

set "MSGFILE=COMMIT_MESSAGE.txt"
set "USEFILE="
set "MSG="
if not "%~1"=="" (
  set "MSG=%~1"
) else if exist "%MSGFILE%" (
  for %%A in ("%MSGFILE%") do if %%~zA GTR 0 set "USEFILE=1"
)
if not defined USEFILE if not defined MSG (
  set /p "MSG=Commit message (Enter = 'update'): "
  if "!MSG!"=="" set "MSG=update"
)

if defined USEFILE (
  echo -- committing with %MSGFILE%:
  type "%MSGFILE%"
  echo.
  rem record it in CHANGELOG.md as part of the same commit
  for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"
  if not exist CHANGELOG.md (
    echo # Changelog>CHANGELOG.md
    echo.>>CHANGELOG.md
    echo Each entry is the commit message push.bat was given. Newest at the bottom.>>CHANGELOG.md
    echo.>>CHANGELOG.md
  )
  echo ## !TODAY!>>CHANGELOG.md
  echo.>>CHANGELOG.md
  type "%MSGFILE%">>CHANGELOG.md
  echo.>>CHANGELOG.md
  echo.>>CHANGELOG.md
)

git add -A
if defined USEFILE (
  git commit -F "%MSGFILE%"
) else (
  git commit -m "!MSG!"
)
if errorlevel 1 echo (nothing new to commit - pushing anything already committed)

git push
if errorlevel 1 (
  echo.
  echo Push rejected - fetching the remote and retrying once with a rebase...
  git pull --rebase && git push
  if errorlevel 1 (
    echo.
    echo Push still failing. Nothing is lost: your commit is local. Common causes:
    echo   - not signed in: run  git push  once in a terminal to log in
    echo   - a conflict: run  git status  and resolve the files it lists
    pause & exit /b 1
  )
)

if defined USEFILE (
  copy /y "%MSGFILE%" COMMIT_MESSAGE.last.txt >nul
  del "%MSGFILE%"
)

echo.
echo Pushed. Latest commits:
git log --oneline -n 5
pause
