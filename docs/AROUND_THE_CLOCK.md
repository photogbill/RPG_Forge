# Art around the clock — the never-stop launcher (BUILD 82, 2026-11-19)

✦ William, 2026-11-19 03:42: "a non-stop 24/7 art generation effort until we have all or most of the art needed for the
game." 13:56: "ok, lets build the never stop launcher".

**Double-click `art_around_the_clock.bat`.** It runs in its own window, day and night, and keeps the graphics card working
whenever there is something on the world list. To stop it, close the window or choose Stop in 3D → Runs.

## What it does

| Every… | It… |
|---|---|
| 30 s | checks that ComfyUI answers. When it hasn't for 90 s, it starts it the way `make_enemies_and_redo.bat` does: its own minimised window (taskbar: ComfyUI). It never does this while another step holds the graphics card or the rigging ComfyUI is running. It tries at most once in 10 minutes, and once in 30 after three starts that didn't come up. |
| 30 s | checks that the world queue is running. It runs `3d world run` **without** `--until-empty`, so an empty list means "wait for the list to grow", not "stop". The queue already steps aside for anything else on the card. If it stops by itself, it is started again after 30 s, then 1, 2, 4 … minutes, at most 15. If a world queue was already started from 3D → Runs or a .bat, the launcher watches that one instead of starting a second. |
| day, at 05:00 (and at start, if the last was over 20 h ago) | runs **the daily redo** (`forge/threed/redo.py`) — see below. |
| hour | says how much is on the list, in hours. **Under a day:** it says so first (writing the next list comes first). **Empty:** it says the card is idle. |
| moment it runs | keeps Windows from going to sleep. The screen may still turn off; when the window closes, sleep is allowed again. |

## The daily redo

What did not pass goes back in line once a day, using the forge's own buttons:

| What it finds | What it does | Whose |
|---|---|---|
| failed while being made | **Try again** (keeps what it had) | anyone's |
| held by the picture gate, or for loose pieces | **Make again** (a fresh picture; the old folder is kept, renamed) | anyone's |
| held for its colours, or for a lean | **Approve everything here** (BUILD 78), signed "Claude Fable, for William" | only while Settings → Approvals → "Claude Fable may approve for me" is on (Fable's standing rule in the art-around-the-clock note); with it off, the redo leaves them and says so |
| held on purpose, waiting for words, up unclear, any other fault | left alone, named in the report | — |
| put back 3 times and still not past | not put back again; listed in `NEEDS_BETTER_WORDS.md` for the next Claude (the count starts over by itself when its words change) | — |

Its report: `out/3d/world/<game>/REDO_<date>.txt`. Every release has an Undo in 3D → World list → What was approved here.

## Files

- `art_around_the_clock.bat` — start it. `art_around_the_clock.bat --look` shows what it sees and changes nothing. `--redo-now` runs the redo once and exits. `--no-redo` and `--no-releases` switch those parts off for that run.
- `art_around_the_clock_at_logon.bat` — once: Windows starts it by itself a minute after you log on (a Task Scheduler entry, "RPG_Forge art around the clock"; may need "Run as administrator"). `art_around_the_clock_not_at_logon.bat` takes that off again.
- `out/3d/world/<game>/_around_the_clock.json` — its heartbeat: what it's doing, how often it restarted things, the last redo, the backlog.
- Everything it does also goes into `logs/forge_<date>.log`.
- Settings (optional) in `forge.json` → `"around_the_clock": {"redo_hour": 5, "releases": true, "approver": "Claude Fable"}`.

The world queue and ComfyUI run on the Windows PC only, so there is no Mac version.
