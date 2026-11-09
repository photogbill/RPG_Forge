"""How long the queue will take (roadmap N7's ETA and N9e's bedtime line).

The estimate is the median duration of the last 20 finished jobs **of the same type** (falling back to the last 20 of
any type, then to a bake-off plan's `seconds_per_render`-based estimate, then to 30 s), summed over what is pending.
It is an estimate: a queue that mixes 2-second CPU jobs and 70-second 1080p paintings is only as good as its history.
"""
from __future__ import annotations
import json
import statistics
from datetime import datetime
from pathlib import Path

from . import config as cfgmod

FALLBACK_SEC = 30.0


def _dur(j: dict) -> float | None:
    s = (j.get("result") or {}).get("seconds") if isinstance(j.get("result"), dict) else None
    if isinstance(s, (int, float)) and s > 0:
        return float(s)
    try:
        a = datetime.fromisoformat(j["started_at"])
        b = datetime.fromisoformat(j["finished_at"])
        d = (b - a).total_seconds()
        return d if d > 0 else None
    except (KeyError, TypeError, ValueError):
        return None


def history(cfg: dict, limit: int = 400) -> list[dict]:
    """The most recently finished jobs (by file time), newest first: {type, batch, seconds}."""
    done = cfgmod.path_of(cfg, "jobs") / "done"
    files = sorted(done.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for p in files:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        d = _dur(j)
        if d is not None:
            out.append({"type": j.get("type"), "batch": j.get("batch"), "seconds": d})
    return out


def per_type(hist: list[dict], n: int = 20) -> tuple[dict[str, float], float | None]:
    by: dict[str, list[float]] = {}
    for h in hist:
        by.setdefault(h["type"], [])
        if len(by[h["type"]]) < n:
            by[h["type"]].append(h["seconds"])
    overall = [h["seconds"] for h in hist[:n]]
    return {t: statistics.median(v) for t, v in by.items() if v}, (statistics.median(overall) if overall else None)


def estimate(cfg: dict) -> dict:
    jobs = cfgmod.path_of(cfg, "jobs")
    pend = []
    for p in sorted((jobs / "pending").glob("*.json")):
        try:
            pend.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    med, overall = per_type(history(cfg))
    batches: dict[str, dict] = {}
    total = 0.0
    for j in pend:
        sec = med.get(j.get("type")) or overall or FALLBACK_SEC
        b = str(j.get("batch") or "(no batch)")
        e = batches.setdefault(b, {"jobs": 0, "seconds": 0.0})
        e["jobs"] += 1
        e["seconds"] += sec
        total += sec
    return {"pending": len(pend), "seconds": round(total), "per_type": {k: round(v, 1) for k, v in med.items()},
            "batches": batches, "based_on": "median of the last 20 finished jobs of each type" if med else f"no history — {FALLBACK_SEC:.0f} s a job"}


def human(seconds: float) -> str:
    m = int(round(seconds / 60.0))
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60:02d} min"


def lines(cfg: dict) -> list[str]:
    e = estimate(cfg)
    if not e["pending"]:
        return ["queue is empty"]
    out = [f"{e['pending']} job(s) queued — about {human(e['seconds'])} ({e['based_on']})"]
    for b, v in sorted(e["batches"].items(), key=lambda kv: -kv[1]["seconds"]):
        out.append(f"  {b:40s} {v['jobs']:5d} jobs  ~{human(v['seconds'])}")
    return out
