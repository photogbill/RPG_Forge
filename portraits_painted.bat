@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Portraits painted over the bodies (BUILD 93).
rem A portrait taken from a made body is true to the body and too crude for a dialogue box. This paints each one
rem again from what the forge already has: the body portrait, and the picture that body was made from, through
rem FLUX.2 [klein] 4B (Apache-2.0; nothing to download). Three ways, two seeds each, so they can be compared:
rem   over     the body portrait alone: the same pose, framing, clothes and light; real skin and eyes
rem   picture  the body's own picture alone: its true face; the framing asked for in words
rem   both     the face from the body's picture, the pose and the light from the body portrait
rem It first takes any body portrait that is missing (Blender, on the PROCESSOR), then paints on the GRAPHICS CARD.
rem It waits its turn for the card - between two of the world queue's models - and holds it for the few minutes the
rem whole batch takes. The queue waits and carries on by itself. ComfyUI must be answering (the launcher keeps it up).
rem Results: out\pictures\<game>\portraits_painted\  -  <name>.png (768), 384\<name>.png (the dialogue box's size),
rem candidates\, and portraits_painted_sheet.png: the body portrait beside every candidate, the proposed one in amber.
rem Run it again any time: only names whose body portrait is new are painted.
rem   portraits_painted.bat again                    paint every portrait again
rem   portraits_painted.bat pick <name> <way> <seed> make another candidate the proposed one (no card)
rem   portraits_painted.bat sheet                    the sheet again (no card)
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
if /i "%~1"=="pick" (
  python -m forge.threed.portraitpaint pick %2 %3 %4
  goto done
)
if /i "%~1"=="sheet" (
  python -m forge.threed.portraitpaint sheet
  goto done
)
echo Taking any body portrait that is missing (on the processor) ...
python -m forge.threed.modelpics portraits
echo.
echo Painting (on the graphics card, when it is free) ...
if /i "%~1"=="again" (
  python -m forge.threed.portraitpaint paint --again
) else (
  python -m forge.threed.portraitpaint paint
)
:done
echo.
echo Done. Open out\pictures\^<game^>\portraits_painted\portraits_painted_sheet.png
pause
