"""Is the art worker running? — for the Home screen. Read-only, except `start()`, which opens the worker's own
window exactly as double-clicking run_worker.bat would.

The worker writes no heartbeat, so its state is put together from three things:
- **its process** — a `python -m forge worker` on this PC (PowerShell's process list on Windows, `ps` elsewhere);
- **jobs/running/** — a job file there means a picture is being made (or a worker stopped mid-job);
- **its log** — the newest `logs/forge_<date>.log`: when it last claimed, finished, or said "idle".

States: rendering · idle · stopped · stopped-mid-job (a job file is stuck in running/ — `python -m forge requeue`
puts it back) · unknown (the process list could not be read; the log line is shown instead). The process check is
the only platform-specific code in the suite, and it lives here.
"""
from __future__ import annotations
import base64, json, os, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod
from ..log import get

log = get("suite")
_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ \[(\w+)\] ([\w.]+): (.*)$")
_cache: dict = {"t": 0.0, "procs": None}
RECENT_LOG_SEC = 30 * 60          # a log line this recent means a worker may be alive even if the process list disagrees
_PS = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } | "
       "ForEach-Object { '' + $_.ProcessId + [char]9 + $_.CommandLine }")


def _is_worker(cmdline: str) -> bool:
    c = " ".join(cmdline.replace('"', " ").split()).lower()
    return bool(re.search(r"-m forge worker\b", c)) or bool(re.search(r"forge[\\/]__main__\.py worker\b", c))


def processes(timeout: float = 8.0) -> list[dict] | None:
    """Worker processes on this PC: [{pid, cmdline}], or None when the process list can't be read."""
    now = time.time()
    if now - _cache["t"] < 5.0:
        return _cache["procs"]
    procs: list[dict] | None
    try:
        if os.name == "nt":
            enc = base64.b64encode(_PS.encode("utf-16-le")).decode("ascii")
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
                               capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
            rows = [l.split("\t", 1) for l in r.stdout.splitlines() if "\t" in l]
            unreadable = sum(1 for x in rows if len(x) == 2 and not x[1].strip())   # Windows hides an elevated process's command line
        else:
            r = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True, text=True, timeout=timeout)
            rows = [l.strip().split(None, 1) for l in r.stdout.splitlines() if l.strip()]
            unreadable = 0
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[:200] or f"exit {r.returncode}")
        me = os.getpid()
        procs = [{"pid": int(p), "cmdline": c} for p, c in (x for x in rows if len(x) == 2)
                 if p.strip().isdigit() and int(p) != me and _is_worker(c)]
        if not procs and unreadable:
            log.info("suite: %d python process(es) with a hidden command line — can't rule out a worker", unreadable)
            procs = None
    except Exception as e:  # noqa: BLE001 — unknown, not an error
        log.warning("suite: could not read the process list (%s) — worker state from the log only", e)
        procs = None
    _cache.update(t=now, procs=procs)
    return procs


def last_log_lines(cfg: dict, n: int = 400) -> list[dict]:
    logs = cfgmod.path_of(cfg, "logs")
    files = sorted(logs.glob("forge_*.log"))
    out: list[dict] = []
    for p in reversed(files[-2:]):
        try:
            with open(p, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 256 * 1024))
                raw = f.read().decode("utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for l in reversed(raw):
            m = _LINE.match(l)
            if m and m.group(3) == "forge.queue":
                out.append({"time": m.group(1), "level": m.group(2), "msg": m.group(4)})
                if len(out) >= n:
                    return out
        if out:
            break
    return out                      # newest first


def state(cfg: dict, procs=...) -> dict:
    jobs = cfgmod.path_of(cfg, "jobs")
    running = []
    for p in sorted((jobs / "running").glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            j = {"id": p.stem}
        running.append({"id": j.get("id", p.stem), "name": j.get("name"), "type": j.get("type"), "batch": j.get("batch"),
                        "started": j.get("started_at")})
    if procs is ...:
        procs = processes()
    lines = last_log_lines(cfg, 50)
    last = lines[0] if lines else None
    idle_since = next((l["time"] for l in lines if l["msg"].startswith("idle")), None)
    claimed = next((l["time"] for l in lines if l["msg"].startswith("claimed")), None)
    if idle_since and claimed and claimed > idle_since:
        idle_since = None
    alive = None if procs is None else bool(procs)
    if alive is False and last:
        # No worker in the process list, but its log moved minutes ago: don't call it stopped (Start would requeue the
        # job it is making and launch a second worker). Say "can't tell" instead.
        try:
            age = (datetime.now() - datetime.fromisoformat(last["time"])).total_seconds()
        except ValueError:
            age = None
        if age is not None and age < RECENT_LOG_SEC:
            alive = None
    if running and alive is not False:
        st, since = "rendering", running[0].get("started") or claimed
        words = f"making {running[0].get('name') or running[0]['id']}"
    elif alive:
        st, since, words = "idle", idle_since, "running, with nothing to do — it takes the next job the moment one is queued"
    elif alive is False and running:
        st, since = "stopped-mid-job", last["time"] if last else None
        words = (f"not running, and {len(running)} job file(s) are still in jobs\\running — the worker stopped in the middle. "
                 "Start puts them back in the queue first, then starts the worker.")
    elif alive is False:
        st, since, words = "stopped", last["time"] if last else None, "not running — nothing is being made"
    else:
        st, since = "unknown", last["time"] if last else None
        words = "I can't read this PC's process list, so I can't tell whether the worker is running. Its log's last word: " + \
                (f"“{last['msg']}” at {last['time'][11:16]}" if last else "(no log yet)")
    return {"state": st, "since": since, "words": words, "running": running, "processes": procs,
            "last_log": last, "checked": datetime.now().isoformat(timespec="seconds")}


def start(cfg: dict) -> dict:
    """Open the GPU worker in its own window (run_worker.bat — it starts ComfyUI first if needed). Refuses when a
    worker is already running or the state can't be read (two workers on one GPU fight over it)."""
    st = state(cfg)
    if st["state"] in ("rendering", "idle"):
        return {"ok": False, "message": "the worker is already running — nothing to start"}
    if st["state"] == "unknown":
        return {"ok": False, "message": "I can't tell whether a worker is already running, so I won't start a second one. "
                                       "Look for a 'GPU worker' window on the taskbar; if there is none, double-click run_worker.bat."}
    requeued = 0
    if st["state"] == "stopped-mid-job":
        from ..queue import Queue
        requeued = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out")).requeue_running()
        log.info("suite: %d job(s) left in running/ by a stopped worker put back in the queue before starting", requeued)
    bat = cfgmod.ROOT / "run_worker.bat"
    if os.name == "nt":
        if not bat.exists():
            return {"ok": False, "message": "run_worker.bat is missing from the forge folder"}
        subprocess.Popen(f'start "RPG_Forge GPU worker" "{bat}"', shell=True, cwd=str(cfgmod.ROOT))
    else:
        subprocess.Popen([sys.executable, "-m", "forge", "worker", "--gpu"], cwd=str(cfgmod.ROOT),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    _cache["t"] = 0.0
    log.info("suite: worker started from Home")
    msg = "the worker is starting in its own window (ComfyUI first, about 15 seconds). Close that window to stop it."
    if requeued:
        msg += f" First I put back the {requeued} job(s) the last worker left half-done, so they are made again from the start."
    return {"ok": True, "message": msg}
