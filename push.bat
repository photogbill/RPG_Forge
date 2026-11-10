@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
rem ============================================================================
rem  push.bat - commit everything and push to GitHub, Bill-proof.
rem  Message: COMMIT_MESSAGE.txt if present (written by whoever changed the files),
rem  else the first argument, else you are asked for one line. The message is
rem  appended to CHANGELOG.md in the same commit; the inbox file is git-ignored
rem  and removed after a successful push.
rem ============================================================================
where git >nul 2>nul
if errorlevel 1 goto nogit
if not exist .git goto norepo

echo == RPG_Forge push ==
git status --short
echo.

set "MSGFILE=COMMIT_MESSAGE.txt"
set "USEFILE="
set "MSG=%~1"
if not "%MSG%"=="" goto commit
if not exist "%MSGFILE%" goto ask
for %%A in ("%MSGFILE%") do if %%~zA GTR 0 set "USEFILE=1"
if defined USEFILE goto fromfile
:ask
set /p "MSG=Commit message (Enter = 'update'): "
if "!MSG!"=="" set "MSG=update"
goto commit

:fromfile
echo -- committing with %MSGFILE%:
type "%MSGFILE%"
echo.
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"
if exist CHANGELOG.md goto append
echo # Changelog>CHANGELOG.md
echo.>>CHANGELOG.md
echo Each entry is the commit message push.bat was given. Newest at the bottom.>>CHANGELOG.md
echo.>>CHANGELOG.md
:append
echo ## !TODAY!>>CHANGELOG.md
echo.>>CHANGELOG.md
type "%MSGFILE%">>CHANGELOG.md
echo.>>CHANGELOG.md
echo.>>CHANGELOG.md

:commit
rem Never push what .gitignore excludes, even if git tracked it before (a game's own data, run state).
rem Nothing is deleted from this PC - git just stops carrying those files from this commit on.
git ls-files -ci --exclude-standard > "%TEMP%\rpgforge_untrack.txt"
for %%A in ("%TEMP%\rpgforge_untrack.txt") do if %%~zA GTR 0 (
  echo -- no longer pushing files that .gitignore excludes ^(they stay on this PC^)
  git rm -r -q --cached --pathspec-from-file="%TEMP%\rpgforge_untrack.txt"
  if errorlevel 1 (
    echo Could not stop tracking the excluded files ^(git older than 2.26?^) - NOTHING was committed or pushed.
    echo Update git ^(https://git-scm.com/download/win^) and run push.bat again.
    pause
    exit /b 1
  )
)
del "%TEMP%\rpgforge_untrack.txt" 2>nul
git add -A
if defined USEFILE git commit -F "%MSGFILE%"
if not defined USEFILE git commit -m "!MSG!"
if errorlevel 1 echo (nothing new to commit - pushing anything already committed)

git push
if not errorlevel 1 goto pushed
echo.
echo Push rejected - fetching the remote and retrying once with a rebase...
git pull --rebase
git push
if not errorlevel 1 goto pushed
echo.
echo Push still failing. Nothing is lost: your commit is local. Common causes:
echo   - not signed in: run  git push  once in a terminal to log in
echo   - a conflict: run  git status  and resolve the files it lists
pause
exit /b 1

:pushed
if not defined USEFILE goto done
copy /y "%MSGFILE%" COMMIT_MESSAGE.last.txt >nul
del "%MSGFILE%"
:done
echo.
echo Pushed. Latest commits:
git log --oneline -n 5
pause
exit /b

:nogit
echo git is required: https://git-scm.com/download/win
pause
exit /b 1
:norepo
echo This folder is not a git repository.
pause
exit /b 1
