"""Art around the clock — the never-stop launcher (BUILD 82, 2026-11-19).

✦ William, 2026-11-19 03:42: "a non-stop 24/7 art generation effort until we have all or most of the art needed for the
game. Since it will take the longest of anything, it behooves us to get it kicked out without exception."
✦ 13:56: "ok, lets build the never stop launcher"

    art_around_the_clock.bat                       (Windows) this, in its own window; close the window to stop it
    python -m forge.around_the_clock [--game <id>] [--look] [--redo-now] [--no-redo] [--no-releases]

Every 30 seconds, until its window is closed, Ctrl+C, or someone chooses Stop in 3D -> Runs (or `3d world stop`):

1. **ComfyUI stays up.** When the art ComfyUI (forge.json -> comfy.url, 8188) has not answered for 90 s, it is started
   the way make_enemies_and_redo.bat starts it: its own minimised window, start_comfy.bat. Never while another step
   holds the graphics card (out/3d/_card.lock) or the rigging ComfyUI is running. At most once in 10 minutes; once in
   30 after three starts that did not come up. At the launcher's start a ComfyUI that is down is started at once.
2. **The world queue stays running.** `3d world run` without --until-empty: when the list is empty it waits for the list
   to grow instead of stopping, and it already steps aside for anything else on the card (world.machine_busy). If it
   stops by itself (a crash), it is started again after 30 s, then 1, 2, 4 … minutes, at most 15, while it keeps
   stopping. If someone chose Stop, the launcher stops too and says so. If a world queue is already running (3D -> Runs,
   a .bat), the launcher watches it instead of starting a second.
3. **Once a day, the daily redo** (forge/threed/redo.py): at `redo_hour` (05:00), and at the launcher's start when the
   last redo was more than 20 hours ago.
4. **Every hour, the backlog in hours** (the note's rule 6). Under a day of work it says so first; an empty list, it
   says the card is idle.
5. **Windows: the computer is kept from going to sleep while it runs** (the screen may still turn off).

One launcher per game: a second one says so and stops. Its heartbeat is out/3d/world/<game>/_around_the_clock.json;
everything it does goes into the forge's daily log (logs/forge_<date>.log). It writes nothing outside the forge.
Settings, all optional, in forge.json -> "around_the_clock": {"redo_hour": 5, "releases": true, "approver": "Claude Fable"}.
Nothing here names a game.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from .log import get

log = get("clock")
WIN = sys.platform == "win32"

TICK = 30                    # seconds between looks
COMFY_GRACE = 90             # ComfyUI silent this long before the launcher starts it (not at the launcher's own start)
COMFY_COME_UP = 300          # a ComfyUI it started has this long to answer
COMFY_RETRY = 600            # at most one start in this many seconds …
COMFY_RETRY_SLOW = 1800      # … or in this many, after COMFY_SLOW_AFTER starts that did not come up
COMFY_SLOW_AFTER = 3
BACKOFF_FIRST = 30           # the world queue stopped by itself: start it again after 30 s, then 1, 2, 4 … minutes
BACKOFF_MAX = 900
CRASH_WINDOW = 3600
CRASH_ALARM = 5              # this many stops within CRASH_WINDOW: said loudly
REDO_AFTER = 20 * 3600       # at start, a redo when the last was longer ago than this
REDO_MIN_GAP = 6 * 3600      # the scheduled redo is skipped when one ran this recently
BACKLOG_EVERY = 3600
HEART_STALE = 120


def words_for(seconds: float) -> str:
    s = int(round(seconds))
    if s < 90:
        return f"{s} s"
    if s < 5400:
        return f"{round(s / 60)} min"
    return f"{s / 3600:.1f} h"


# ------------------------------------------------------------------------------------------------ the machine
class Machine:
    """Everything the launcher touches, in one place (tests swap it for a stand-in)."""

    def __init__(self, cfg: dict, gid: str):
        from .threed import world
        self.cfg, self.gid, self.world = cfg, gid, world
        self.root = Path(world.root_of(cfg))
        self.wd = world.world_dir(cfg, gid)
        self.url = ((cfg or {}).get("comfy") or {}).get("url") or "http://127.0.0.1:8188"

    # ComfyUI and the card
    def comfy_up(self) -> bool:
        from .threed import comfyapi
        return bool(comfyapi.is_up(self.url, timeout=4.0))

    def rig_up(self) -> bool:
        try:
            from .threed import comfyapi
            from .threed.env import from_cfg
            return bool(comfyapi.is_up(from_cfg(self.cfg).url, timeout=2.0))
        except Exception:  # noqa: BLE001 — no rigging ComfyUI installed is not a reason to stop
            return False

    def card_holder(self) -> str:
        try:
            from .threed import cardlock
            st = cardlock.state(self.cfg)
            return str(st.get("holder") or "someone") if st.get("held") else ""
        except Exception:  # noqa: BLE001
            return ""

    def start_comfy(self) -> str:
        """'' when started; else why not, in words."""
        bat = self.root / "start_comfy.bat"
        if not WIN:
            return "this computer is not the Windows PC — start ComfyUI yourself"
        if not bat.exists():
            return f"{bat.name} is missing — run install_comfy.bat"
        subprocess.Popen(f'cmd /c start "ComfyUI" /min "{bat}"', cwd=str(self.root))
        return ""

    # the world queue
    def queue_state(self) -> dict:
        return self.world.launcher_state(self.cfg, self.gid)

    def start_queue(self):
        return subprocess.Popen([sys.executable, "-m", "forge", "3d", "world", "run", "--game", self.gid], cwd=str(self.root))

    def stop_marks(self) -> float:
        """The newest Stop anyone asked for (STOP waiting, or STOP.done kept by the queue that obeyed it); 0 if none."""
        t = 0.0
        for n in ("STOP", "STOP.done"):
            try:
                t = max(t, (self.wd / n).stat().st_mtime)
            except OSError:
                pass
        return t

    def put_in_marks(self) -> tuple[float, bool]:
        """BUILD 84: (when changes were last put in, whether that is still going on). put_in_waiting_changes.bat writes
        PUT_IN before it asks the queue to stop and renames it PUT_IN.done when it has finished: its Stop is a pause."""
        for n, going in (("PUT_IN", True), ("PUT_IN.done", False)):
            try:
                return (self.wd / n).stat().st_mtime, going
            except OSError:
                pass
        return 0.0, False

    def clear_old_stop(self) -> None:
        self.world._clear_stop(self.cfg, self.gid)     # a Stop from before the launcher started is not meant for it

    def estimate(self) -> dict:
        return self.world.estimate(self.cfg, self.gid)

    # the daily redo
    def redo(self, releases: bool, approver: str) -> dict:
        from .threed import redo
        return redo.do(self.cfg, self.gid, releases=releases, approver=approver)

    def redo_plan(self) -> dict:
        from .threed import redo
        return redo.plan(self.cfg, self.gid)

    # the launcher's own things
    def heart_path(self) -> Path:
        return self.wd / "_around_the_clock.json"

    def pid_alive(self, pid: int):
        from .threed.cardlock import _pid_alive
        return _pid_alive(pid)

    def keep_awake(self, on: bool) -> None:
        if not WIN:
            return
        try:
            import ctypes
            ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
        except Exception as ex:  # noqa: BLE001
            log.warning("clock: could not ask Windows to stay awake (%s)", ex)


# ------------------------------------------------------------------------------------------------ the launcher
class Clock:
    def __init__(self, machine, gid: str, redo: bool = True, releases: bool = True, approver: str = "Claude Fable",
                 redo_hour: int = 5, now=time.time, sleep=time.sleep, out=None):
        self.m, self.gid = machine, gid
        self.redo_on, self.releases, self.approver, self.redo_hour = redo, releases, approver, int(redo_hour)
        self.now, self.sleep = now, sleep
        self.out = out or (lambda s: print(s, flush=True))
        self.pid, self.host = os.getpid(), socket.gethostname()
        self.started = 0.0
        self.step = "starting"
        # ComfyUI
        self.comfy_checked = False
        self.comfy_down_since = None
        self.comfy_last_start = 0.0
        self.comfy_waiting_since = None
        self.comfy_failed = 0
        self.comfy_starts = 0
        # the world queue
        self.proc = None
        self.queue_started_at = 0.0
        self.queue_starts = 0
        self.queue_exits = 0
        self.crashes: list[float] = []
        self.next_start = 0.0
        self.watching = False
        self.watch_since = 0.0
        # the redo and the backlog
        self.last_redo = None
        self.redo_summary = ""
        self.last_backlog = 0.0
        self.backlog: dict = {}
        self._said: dict[str, str] = {}

    # -------------------------------------------------------------------------------------------- saying things
    def say(self, msg: str) -> None:
        self.out(f"{datetime.fromtimestamp(self.now()):%H:%M:%S}  {msg}")
        log.info("clock [%s]: %s", self.gid, msg)

    def once(self, topic: str, msg: str) -> None:
        """Say it unless the same thing was the last said on this topic (no line every 30 s)."""
        if self._said.get(topic) != msg:
            self._said[topic] = msg
            self.say(msg)

    # -------------------------------------------------------------------------------------------- the heartbeat
    def _read_heart(self) -> dict:
        try:
            return json.loads(self.m.heart_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def heartbeat(self, step: str | None = None) -> None:
        if step:
            self.step = step
        d = {"pid": self.pid, "host": self.host, "game": self.gid, "started": self.started, "beat": self.now(),
             "step": self.step,
             "queue": {"starts": self.queue_starts, "stopped_by_itself": self.queue_exits,
                       "running_here": self.proc is not None, "watching_one_started_elsewhere": self.watching},
             "comfy": {"starts": self.comfy_starts, "last_start": self.comfy_last_start or None,
                       "starts_that_did_not_come_up": self.comfy_failed},
             "redo": {"last": self.last_redo, "summary": self.redo_summary, "on": self.redo_on, "releases": self.releases,
                      "approver": self.approver, "hour": self.redo_hour},
             "backlog": self.backlog}
        p = self.m.heart_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".part")
            tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
            os.replace(tmp, p)
        except OSError as ex:
            log.warning("clock: heartbeat not written (%s)", ex)

    def other_launcher(self, d: dict) -> bool:
        if not d or d.get("step") == "stopped" or d.get("pid") == self.pid:
            return False
        if self.now() - float(d.get("beat") or 0) > HEART_STALE:
            return False
        if d.get("host") == self.host and d.get("pid"):
            return self.m.pid_alive(int(d["pid"])) is not False
        return True

    # -------------------------------------------------------------------------------------------- the loop
    def run(self, max_ticks: int | None = None) -> str:
        before = self._read_heart()
        if self.other_launcher(before):
            self.say(f"Art around the clock is already running for {self.gid} (pid {before.get('pid')}, since "
                     f"{datetime.fromtimestamp(float(before.get('started') or 0)):%Y-%m-%d %H:%M}). Nothing was started.")
            return "already running"
        self.started = self.now()
        self.last_redo = (before.get("redo") or {}).get("last")
        self.m.clear_old_stop()
        self.m.keep_awake(True)
        self.say(f"Art around the clock: started for {self.gid}. It keeps ComfyUI and the world queue running, day and "
                 f"night. Close this window to stop it, or choose Stop in 3D -> Runs.")
        ticks = 0
        try:
            while True:
                r = self.tick()
                if r:
                    return r
                ticks += 1
                if max_ticks and ticks >= max_ticks:
                    return "ticks"
                self.sleep(TICK)
        except KeyboardInterrupt:
            self.say("Stopped with Ctrl+C. The world queue in this window stops too; ComfyUI keeps running in its own.")
            return "ctrl+c"
        finally:
            self.m.keep_awake(False)
            self.heartbeat("stopped")

    def tick(self) -> str | None:
        now = self.now()
        self._comfy(now)
        r = self._queue(now)
        if r:
            return r
        self._redo(now)
        self._backlog(now)
        self.heartbeat()
        return None

    # -------------------------------------------------------------------------------------------- 1. ComfyUI
    def _comfy(self, now: float) -> None:
        first = not self.comfy_checked
        self.comfy_checked = True
        if self.m.comfy_up():
            if self.comfy_down_since is not None and not first:
                self.say("ComfyUI is answering.")
            self.comfy_down_since = None
            if self.comfy_waiting_since is not None:
                self.comfy_failed = 0
                self.comfy_waiting_since = None
            self._said.pop("comfy", None)
            return
        if self.comfy_down_since is None:
            self.comfy_down_since = now
        if self.comfy_waiting_since is not None:
            if now - self.comfy_waiting_since < COMFY_COME_UP:
                return
            self.comfy_failed += 1
            self.comfy_waiting_since = None
            self.say(f"ComfyUI did not answer within {words_for(COMFY_COME_UP)} of being started — its window (taskbar: "
                     f"ComfyUI) says why. It will be tried again.")
        if not first and now - self.comfy_down_since < COMFY_GRACE:
            return
        retry = COMFY_RETRY_SLOW if self.comfy_failed >= COMFY_SLOW_AFTER else COMFY_RETRY
        if self.comfy_last_start and now - self.comfy_last_start < retry:
            return
        holder = self.m.card_holder()
        if holder:
            self.once("comfy", f"ComfyUI is not answering, but {holder} has the graphics card — waiting for it.")
            return
        if self.m.rig_up():
            self.once("comfy", "ComfyUI is not answering; the rigging ComfyUI is running (it holds the card) — waiting.")
            return
        why = self.m.start_comfy()
        self.comfy_last_start = now
        if why:
            self.once("comfy", f"ComfyUI is not answering, and it was not started: {why}.")
            return
        self.comfy_starts += 1
        self.comfy_waiting_since = now
        self._said.pop("comfy", None)
        self.say("Starting ComfyUI in its own minimised window (taskbar: ComfyUI) …")

    # -------------------------------------------------------------------------------------------- 2. the world queue
    def _stop_asked(self, since: float) -> bool:
        stop = self.m.stop_marks()
        if stop <= since - 1:
            return False
        # BUILD 84: a Stop asked by put_in_waiting_changes.bat (it writes PUT_IN first) is a pause, not a stop — the
        # launcher waits while the changes go in and then takes the queue up again (it used to stop itself here)
        put, _going = getattr(self.m, "put_in_marks", lambda: (0.0, False))()
        return not (put and put - 2 <= stop <= put + 120)          # the put-in writes PUT_IN, then STOP, at once

    def _put_in_going(self) -> bool:
        return bool(getattr(self.m, "put_in_marks", lambda: (0.0, False))()[1])

    def _queue(self, now: float) -> str | None:
        if self.proc is not None:
            rc = self.proc.poll()
            if rc is None:
                self.step = "the world queue is running"
                return None
            self.proc = None
            if self.m.stop_marks() > self.queue_started_at - 1 and not self._stop_asked(self.queue_started_at):
                # BUILD 84: stopped for a put-in (put_in_waiting_changes.bat) — not a crash, not a Stop: wait, then go on
                self.step = "waiting while changes are put in (put_in_waiting_changes.bat)"
                self.next_start = 0.0
                self.say("The world queue was paused to put changes in; the launcher waits and carries on afterwards.")
                return None
            if self._stop_asked(self.queue_started_at):
                self.say("The world queue stopped because someone chose Stop (3D -> Runs, or 3d world stop). The launcher "
                         "stops too — run art_around_the_clock.bat to start it again.")
                return "stop asked"
            self.queue_exits += 1
            self.crashes = [t for t in self.crashes if now - t < CRASH_WINDOW] + [now]
            delay = min(BACKOFF_MAX, BACKOFF_FIRST * 2 ** (len(self.crashes) - 1))
            self.next_start = now + delay
            self.say(f"The world queue stopped by itself (exit code {rc}). Starting it again in {words_for(delay)}. "
                     f"Why: out/3d/world/{self.gid}/world.log")
            if len(self.crashes) >= CRASH_ALARM:
                self.say(f"It has stopped {len(self.crashes)} times in the last hour — something is wrong. Read world.log; "
                         f"the launcher keeps trying every {words_for(BACKOFF_MAX)}.")
            return None
        qs = self.m.queue_state() or {}
        if not qs.get("running") and self._put_in_going():
            self.step = "waiting while changes are put in (put_in_waiting_changes.bat)"
            return None
        if qs.get("running"):
            if not self.watching:
                self.watching, self.watch_since = True, now
                self.say("A world queue is already running (started from 3D -> Runs or a .bat) — watching it instead of "
                         "starting a second.")
            self.step = "watching a world queue started elsewhere"
            return None
        if self.watching:
            self.watching = False
            if self._stop_asked(self.watch_since):
                self.say("The world queue stopped because someone chose Stop. The launcher stops too — run "
                         "art_around_the_clock.bat to start it again.")
                return "stop asked"
            self.say("The world queue that was started elsewhere has stopped; starting one here.")
            self.next_start = 0.0
        if self._stop_asked(self.started + 1):
            self.say("Someone chose Stop for the world queue while it was not running. The launcher stops — run "
                     "art_around_the_clock.bat to start it again.")
            return "stop asked"
        if now < self.next_start:
            self.step = "waiting to start the world queue again"
            return None
        self.proc = self.m.start_queue()
        self.queue_started_at = now
        self.queue_starts += 1
        self.step = "the world queue is running"
        self.say("The world queue is running in this window (without --until-empty: when the list is empty it waits for "
                 "it to grow).")
        return None

    # -------------------------------------------------------------------------------------------- 3. the daily redo
    def redo_due(self, now: float) -> bool:
        if not self.redo_on:
            return False
        last = self.last_redo
        if last is None or now - float(last) >= REDO_AFTER:
            return True
        today = datetime.fromtimestamp(now).replace(hour=self.redo_hour, minute=0, second=0, microsecond=0).timestamp()
        return now >= today and float(last) < today and now - float(last) >= REDO_MIN_GAP

    def _redo(self, now: float) -> None:
        if not self.redo_due(now):
            return
        self.heartbeat("the daily redo")
        self.say("The daily redo: what did not pass goes back in line …")
        try:
            r = self.m.redo(self.releases, self.approver)
        except Exception as ex:  # noqa: BLE001 — tomorrow's redo tries again; the queue is not stopped for it
            self.last_redo = now
            self.redo_summary = f"did not finish: {type(ex).__name__}: {ex}"[:300]
            self.say(f"The daily redo did not finish ({type(ex).__name__}: {ex}). It runs again tomorrow; nothing else "
                     f"stops for it.")
            log.exception("clock: the daily redo")
            return
        self.last_redo = now
        parts = [f"{len(r.get('again') or [])} tried again", f"{len(r.get('fresh') or [])} made again",
                 f"{len(r.get('released') or [])} released" + (f" (signed {self.approver}, for the person)" if r.get("released") else "")]
        if r.get("release_skipped"):
            parts.append(r["release_skipped"])
        if r.get("tired"):
            parts.append(f"{len(r['tired'])} need better words (NEEDS_BETTER_WORDS.md)")
        if r.get("errors"):
            parts.append(f"{len(r['errors'])} errors")
        self.redo_summary = "; ".join(parts)
        self.say(f"The daily redo: {self.redo_summary}. Report: {r.get('report')}")

    # -------------------------------------------------------------------------------------------- 4. the backlog
    def _backlog(self, now: float) -> None:
        if self.last_backlog and now - self.last_backlog < BACKLOG_EVERY:
            return
        self.last_backlog = now
        try:
            est = self.m.estimate() or {}
        except Exception as ex:  # noqa: BLE001
            self.say(f"The list could not be counted ({type(ex).__name__}: {ex}).")
            return
        n, secs = int(est.get("to_make") or 0), float(est.get("seconds") or 0)
        hours = secs / 3600
        self.backlog = {"to_make": n, "hours": round(hours, 1), "at": now, "under_a_day": hours < 24}
        if n == 0:
            self.say("On the list: nothing to make — the graphics card is idle. Requirement #1: writing the next list comes "
                     "first (tell Claude \"the list ran dry\").")
        elif hours < 24:
            self.say(f"On the list: {n} things, {est.get('words') or words_for(secs)} of work — UNDER A DAY. "
                     f"Requirement #1: writing the next list comes first.")
        else:
            self.say(f"On the list: {n} things, {est.get('words') or words_for(secs)} of work.")


# ------------------------------------------------------------------------------------------------ the command
def _opt(args: list[str], flag: str, default=None):
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            return args[i + 1]
    return default


def look(m: Machine, clock: Clock) -> None:
    """--look: what the launcher sees right now, changing nothing."""
    p = print
    heart = clock._read_heart()
    p(f"Art around the clock — {m.gid}")
    if clock.other_launcher(heart):
        p(f"  The launcher: RUNNING (pid {heart.get('pid')}), {heart.get('step')}")
    else:
        p("  The launcher: not running")
    if (heart.get("redo") or {}).get("last"):
        p(f"  Last daily redo: {datetime.fromtimestamp(float(heart['redo']['last'])):%Y-%m-%d %H:%M} — "
          f"{heart['redo'].get('summary')}")
    p(f"  ComfyUI ({m.url}): {'answering' if m.comfy_up() else 'NOT answering'}")
    p(f"  The rigging ComfyUI: {'running' if m.rig_up() else 'not running'}")
    holder = m.card_holder()
    p(f"  The graphics card: {('held by ' + holder) if holder else 'free'}")
    qs = m.queue_state() or {}
    p(f"  The world queue: {'running — ' + str(qs.get('step')) if qs.get('running') else 'not running'}"
      + (f" ({qs.get('item')})" if qs.get("item") else ""))
    try:
        est = m.estimate()
        p(f"  On the list: {est.get('to_make')} things, {est.get('words')}")
    except Exception as ex:  # noqa: BLE001
        p(f"  On the list: could not be counted ({ex})")
    try:
        r = m.redo_plan()
        p(f"  The redo would: try again {len(r['again'])}, make again {len(r['fresh'])}, release {r['release']['count']} "
          f"(if \"{clock.approver} may approve for me\" is on), leave {len(r['left'])}, list {len(r['tired'])} for better words")
    except Exception as ex:  # noqa: BLE001
        p(f"  The redo: could not plan ({ex})")
    p(f"  Settings: redo at {clock.redo_hour:02d}:00, releases {'on' if clock.releases else 'off'}, approver {clock.approver}")
    p("Nothing was changed.")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    from . import config as cfgmod
    from . import log as logmod
    cfg = cfgmod.load()
    cfgmod.ensure_dirs(cfg)
    logmod.setup(cfgmod.path_of(cfg, "logs"))
    gid = _opt(argv, "--game") or cfgmod.default_game(cfg)
    if not gid:
        print("No game chosen: pass --game <id>.")
        return 2
    st = cfg.get("around_the_clock") or {}
    m = Machine(cfg, gid)
    clock = Clock(m, gid, redo="--no-redo" not in argv, releases=bool(st.get("releases", True)) and "--no-releases" not in argv,
                  approver=str(st.get("approver") or "Claude Fable"), redo_hour=int(st.get("redo_hour", 5)))
    if "--look" in argv:
        look(m, clock)
        return 0
    if "--redo-now" in argv:
        r = m.redo(clock.releases, clock.approver)
        print("\n".join(r.get("lines") or []))
        return 0
    r = clock.run()
    return 0 if r in ("stop asked", "ctrl+c") else 1


if __name__ == "__main__":
    sys.exit(main())
