"""Standing by itself for days (Night 4, F3): the disk guard and the 24-hour report, run by produce_watch.bat.

    check(cfg)   free space on the output drive under `disk_guard_gb` (forge.json, default 40) → every pending job is
                 parked in jobs/paused/ and the dashboard says why; back over the limit + 5 GB → exactly those jobs
                 come back. Nothing is deleted.
    watch(cfg)   check every 5 minutes; while anything is queued or running, write the morning report every 24 h
                 (out/reports/night_<date>.html) without being asked. State: out/reports/disk_guard.json.
"""
from __future__ import annotations
import json
import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from .. import config as cfgmod

log = logging.getLogger("forge.guard")
HYSTERESIS_GB = 5.0


def _state_path(cfg: dict) -> Path:
    return cfgmod.path_of(cfg, "out") / "reports" / "disk_guard.json"


def read(cfg: dict) -> dict:
    p = _state_path(cfg)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def _save(cfg: dict, st: dict) -> None:
    p = _state_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
    tmp.replace(p)


def free_gb(cfg: dict) -> float:
    """Free space on the drive that holds out/ (the nearest folder that exists, if out/ is not made yet)."""
    p = Path(cfgmod.path_of(cfg, "out"))
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free / 1e9


def check(cfg: dict, free: float | None = None) -> dict:
    limit = float(cfg.get("disk_guard_gb", 40))
    free = free_gb(cfg) if free is None else free
    st = read(cfg)
    jobs = cfgmod.path_of(cfg, "jobs")
    st.update({"checked": datetime.now().isoformat(timespec="seconds"), "free_gb": round(free, 1), "limit_gb": limit})
    if free < limit and not st.get("paused_ids"):
        ids = []
        for p in sorted((jobs / "pending").glob("*.json")):
            try:
                os.replace(p, jobs / "paused" / p.name)
                ids.append(p.stem)
            except OSError:
                continue
        st.update({"paused_ids": ids, "paused_since": st["checked"],
                   "message": f"DISK GUARD: {free:.0f} GB free on the output drive (limit {limit:.0f} GB) — "
                              f"{len(ids)} queued job(s) parked. Free some space; they come back by themselves at "
                              f"{limit + HYSTERESIS_GB:.0f} GB."})
        log.warning(st["message"])
    elif st.get("paused_ids") and free >= limit + HYSTERESIS_GB:
        back = 0
        for jid in st["paused_ids"]:
            src = jobs / "paused" / f"{jid}.json"
            if src.exists():
                os.replace(src, jobs / "pending" / src.name)
                back += 1
        log.info("disk guard: %.0f GB free — %d job(s) back in the queue", free, back)
        st.update({"paused_ids": [], "message": None, "resumed": st["checked"], "resumed_count": back})
    _save(cfg, st)
    return st


def busy(cfg: dict) -> bool:
    jobs = cfgmod.path_of(cfg, "jobs")
    return any(any((jobs / s).glob("*.json")) for s in ("pending", "running"))


def watch(cfg: dict, interval: float = 300.0, report_every_h: float = 24.0, rounds: int | None = None) -> None:
    from .. import night_report
    n = 0
    while rounds is None or n < rounds:
        st = check(cfg)
        last = st.get("last_report")
        due = not last or datetime.fromisoformat(last) < datetime.now() - timedelta(hours=report_every_h)
        if due and busy(cfg):
            try:
                path = night_report.build(cfg, hours=report_every_h)
                st = read(cfg); st["last_report"] = datetime.now().isoformat(timespec="seconds")
                st["last_report_file"] = str(path[0] if isinstance(path, tuple) else path)
                _save(cfg, st)
                log.info("watch: wrote the %d-hour report", report_every_h)
            except Exception as e:  # noqa: BLE001
                log.warning("watch: report failed: %s", e)
        n += 1
        if rounds is None or n < rounds:
            time.sleep(interval)
