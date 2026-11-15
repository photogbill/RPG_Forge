"""One lock on the graphics card, honoured by every 3D step, so two ComfyUIs never hold the card at once.

Before this (2026-11-12/13) each script waited until the *other* ComfyUI looked idle ("wait until the art ComfyUI's
queue has been empty for a minute"). That works for one script at a time and fails the day two are started together.
Now every step that puts work on the card through a ComfyUI takes this lock first and gives it back when it is done:

    with CardLock(cfg, "rig_body 2026...-a1b2") as lock:      # waits for the card, then holds it
        ... lock.beat() while it waits on ComfyUI ...

The lock is a small file (`out/3d/_card.lock`) holding who has it, since when, and a heartbeat. A holder that stops
beating for `stale_after` seconds (it crashed, or the computer slept and woke) is taken over, and the takeover is
logged. The per-game scripts of 2026-11-13 do not know this lock; `others_busy()` still looks at both ComfyUIs the way
they did, so the new steps never land on top of an old script that is running.
"""
from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

from . import comfyapi

STALE_AFTER = 15 * 60          # seconds without a heartbeat before a holder is taken to be gone
BEAT_EVERY = 30


class CardBusy(TimeoutError):
    """The card did not come free in time."""


def lock_path(cfg: dict | None = None, root: Path | None = None) -> Path:
    from .env import out_root
    return out_root(cfg, root) / "_card.lock"


def read(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool | None:
    """True/False when it can be told on this computer; None when it can't."""
    try:
        if os.name == "nt":
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            return code.value == 259                                             # STILL_ACTIVE
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:  # noqa: BLE001
        return None


def state(cfg: dict | None = None, path: Path | None = None, stale_after: float = STALE_AFTER) -> dict:
    """Who holds the card now, for the Runs tab: {held, holder, since, beat_age, stale}."""
    p = Path(path) if path else lock_path(cfg)
    d = read(p)
    if not d:
        return {"held": False}
    age = time.time() - float(d.get("beat", 0))
    stale = age > stale_after
    if not stale and d.get("host") == socket.gethostname() and d.get("pid"):
        alive = _pid_alive(int(d["pid"]))
        stale = alive is False
    return {"held": not stale, "holder": d.get("holder"), "since": d.get("since"), "beat_age": round(age), "stale": stale,
            "pid": d.get("pid")}


class CardLock:
    def __init__(self, cfg: dict | None, holder: str, path: Path | None = None, wait_minutes: float = 24 * 60,
                 poll: float = 5.0, stale_after: float = STALE_AFTER, log=None, check_others: bool = True,
                 art_url: str | None = None, rig_url: str | None = None, side: str = "art"):
        self.path = Path(path) if path else lock_path(cfg)
        self.holder = holder
        self.wait = wait_minutes * 60
        self.poll = poll
        self.stale_after = stale_after
        self.log = log
        self.check_others = check_others
        self.art_url = art_url or ((cfg or {}).get("comfy") or {}).get("url") or "http://127.0.0.1:8188"
        from .env import from_cfg
        self.rig_url = rig_url or from_cfg(cfg).url
        self.side = side                       # "art" (the art ComfyUI's card work) or "rig" (the rigging ComfyUI)
        self.held = False
        self._last = 0.0
        self.waited = 0.0

    def _say(self, msg: str) -> None:
        if self.log:
            self.log.info(msg)

    def _write(self, d: dict) -> None:
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, self.path)

    def _try(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        me = {"holder": self.holder, "pid": os.getpid(), "host": socket.gethostname(),
              "since": time.strftime("%Y-%m-%d %H:%M:%S"), "beat": time.time()}
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            st = state(path=self.path, stale_after=self.stale_after)
            if st.get("held"):
                return False
            old = read(self.path) or {}
            self._say(f"the card lock held by {old.get('holder', '?')} has had no heartbeat for {st.get('beat_age', '?')} s "
                      "(or its process is gone) - taking it over")
            self._write(me)
            time.sleep(0.2)
            got = read(self.path) or {}
            return got.get("pid") == me["pid"] and got.get("holder") == self.holder
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(me))
        return True

    def others_busy(self) -> str:
        """The old scripts don't take the lock: look at the ComfyUIs themselves, as they did. '' when the card looks free."""
        if not self.check_others:
            return ""
        if self.side == "rig":
            n = comfyapi.queue_count(self.art_url)
            if n:
                return f"the art ComfyUI has {n} request(s) on the card"
        else:
            if comfyapi.is_up(self.rig_url, timeout=2.0):
                return "the rigging ComfyUI is running (it holds the card)"
        return ""

    def acquire(self) -> "CardLock":
        t0 = time.time()
        told = 0.0
        while True:
            busy = ""
            if self._try():
                busy = self.others_busy()
                if not busy:
                    self.held = True
                    self._last = time.time()
                    self.waited = time.time() - t0
                    self._say(f"the graphics card is ours ({self.holder})" + (f" after waiting {self.waited / 60:.0f} min" if self.waited > 60 else ""))
                    return self
                self._release_file()
            else:
                st = state(path=self.path, stale_after=self.stale_after)
                busy = f"{st.get('holder', 'someone')} has it (since {st.get('since', '?')})"
            if time.time() - t0 > self.wait:
                raise CardBusy(f"the graphics card did not come free in {self.wait / 60:.0f} minutes: {busy}")
            if time.time() - told > 300:
                self._say(f"waiting for the graphics card - {busy}")
                told = time.time()
            time.sleep(self.poll)

    def beat(self) -> None:
        """Call while working (cheap: writes at most every BEAT_EVERY seconds)."""
        if self.held and time.time() - self._last >= BEAT_EVERY:
            d = read(self.path) or {}
            if d.get("pid") == os.getpid() and d.get("holder") == self.holder:
                d["beat"] = time.time()
                self._write(d)
            self._last = time.time()

    def _release_file(self) -> None:
        d = read(self.path) or {}
        if d.get("pid") == os.getpid() and d.get("holder") == self.holder:
            try:
                os.replace(self.path, self.path.with_suffix(".released"))      # a rename needs no delete permission
            except OSError:
                pass

    def release(self) -> None:
        if self.held:
            self._release_file()
            self.held = False
            self._say(f"the graphics card is free again ({self.holder})")

    def __enter__(self) -> "CardLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()
