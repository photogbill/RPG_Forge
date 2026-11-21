@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The opera, filmed (BUILD 43). The cue sheets, beat maps and marks are the game's: <game folder>\film\opera\.
rem   opera_film.bat check                     every cue sheet checked; what is wrong goes in film\opera\film_check.txt
rem   opera_film.bat beats                     measure every song again (the beat maps and their pictures)
rem   opera_film.bat preview duel_a            a small silent preview of one part, with a click on every beat
rem   opera_film.bat preview duel_a song       the same with the song
rem   opera_film.bat final duel_a              one part at 4K with the song (slow: the graphics card renders it)
rem   opera_film.bat video heads               the parts joined into the heads film (tails for the other); add "final"
rem   opera_film.bat refit opera_conductor     fit a body with both motion libraries and the keyed moves (beside its own)
rem The parts: prologue, duel_a, waltz, duel_b, coin, cenere_heads, cenere_tails, stinger.
rem Nothing is written to C: - the renders go to out\film\turing_accords\opera\<part>\.
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -c "import librosa, soundfile" 2>nul || (echo Installing the film tools once: librosa and soundfile... & python -m pip install -r requirements-film.txt)
if "%~1"=="" goto :help
if /i "%~1"=="check" (python -m forge film check & goto :end)
if /i "%~1"=="beats" (python -m forge film beatmaps & goto :end)
if /i "%~1"=="preview" goto :preview
if /i "%~1"=="final" goto :final
if /i "%~1"=="video" goto :video
if /i "%~1"=="refit" goto :refit
:help
echo opera_film.bat check ^| beats ^| preview ^<part^> [song] ^| final ^<part^> ^| video heads^|tails [final] ^| refit ^<body id^> ...
goto :end
:preview
if "%~2"=="" (echo Which part? prologue, duel_a, waltz, duel_b, coin, cenere_heads, cenere_tails & goto :end)
python -m forge film check %2
if /i "%~3"=="song" (
  python -m forge film render %2 --song
  python -m forge film encode %2 --song
) else (
  python -m forge film clicks %2
  python -m forge film render %2
  python -m forge film encode %2
)
start "" "out\film\turing_accords\opera\%~2\preview"
goto :end
:final
if "%~2"=="" (echo Which part? & goto :end)
python -m forge film check %2
python -m forge film render %2 --final --song
python -m forge film encode %2 --final --song
start "" "out\film\turing_accords\opera\%~2\final"
goto :end
:video
if /i "%~3"=="final" (python -m forge film video %2 --final) else (python -m forge film video %2)
start "" "out\film\turing_accords\opera"
goto :end
:refit
shift
python -m forge film refit %1 %2 %3 %4 %5 %6 %7 %8 %9
goto :end
:end
pause
