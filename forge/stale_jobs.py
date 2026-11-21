"""Jobs left behind in jobs/running by a worker that stopped (BUILD 73 part 9).

A job file in jobs/running older than a day, while no worker is running, is moved to jobs/failed with the reason "left
behind by a worker that stopped". Never deleted (the device shell cannot, and should not). Nothing is moved while a worker
is running, or while it can't be told whether one is — two workers on one card fight, and a long job is not a stale one.
The two Filter Forge jobs of 2026-11-12 were the first case.

    python -m forge housekeeping --stale-jobs [--older-h 24] [--dry-run]
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

from .log import get

log = get("queue")
REASON = "left behind by a worker that stopped"


def _started(p: Path, job: dict) -> float:
    for k in ("started_at", "claimed_at", "submitted_at"):
        v = job.get(k)
        if v:
            try:
                return datetime.fromisoformat(str(v)).timestamp()
            except ValueError:
                pass
    return p.stat().st_mtime


def stale(jobs_dir: Path, older_h: float = 24.0, now: float | None = None) -> list[dict]:
    """The job files in running/ older than `older_h` hours (by when they started, else the file's own time)."""
    now = time.time() if now is None else now
    out = []
    for p in sorted((Path(jobs_dir) / "running").glob("*.json")):
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            job = {"id": p.stem}
        if job.get("tombstone"):
            continue
        age_h = (now - _started(p, job)) / 3600.0
        if age_h > older_h:
            out.append({"path": p, "id": job.get("id", p.stem), "name": job.get("name"), "age_h": round(age_h, 1), "job": job})
    return out


def move_stale(jobs_dir: Path, worker_alive, older_h: float = 24.0, dry_run: bool = False, now: float | None = None) -> dict:
    """Move what `stale` finds to failed/, if `worker_alive` is False (None — can't tell — and True move nothing)."""
    found = stale(jobs_dir, older_h, now)
    if worker_alive is not False:
        why = "a worker is running" if worker_alive else "it can't be told whether a worker is running"
        return {"moved": [], "found": [f["id"] for f in found], "left": True,
                "message": f"{len(found)} old job file(s) in running/, none moved: {why}."}
    moved = []
    for f in found:
        job = dict(f["job"])
        job.update(error=REASON, finished_at=datetime.now().isoformat(timespec="seconds"), left_behind={"age_h": f["age_h"]})
        dest = Path(jobs_dir) / "failed" / f["path"].name
        if dry_run:
            moved.append(f["id"])
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = f["path"].with_suffix(".json.tmp")
        tmp.write_text(json.dumps(job, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, f["path"])            # rewritten in place, then renamed: a rename needs no delete permission
        os.replace(f["path"], dest)
        log.warning("job %s moved from running to failed: %s (%.1f h old)", f["id"], REASON, f["age_h"])
        moved.append(f["id"])
    return {"moved": moved, "found": [f["id"] for f in found], "left": False,
            "message": (f"{len(moved)} job file(s) {'would be ' if dry_run else ''}moved from running to failed — {REASON}."
                        if moved else "No job file in running/ is old enough to be stale.")}
