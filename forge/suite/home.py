"""Home / Tonight — the first Art screen (suite spec §6 screen 1): is the worker running, what is it making, how much
is left and how long, is there room on the disk, and the three safe buttons. Every number here comes from the same
functions the .bat files and the dashboard use (queue folders, eta.py, night4/guard.py, night_report) — nothing is
computed a second way.
"""
from __future__ import annotations
import time
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod
from ..log import get
from . import worker

log = get("suite")


def _newest_png(d: Path) -> str | None:
    try:
        pngs = [p for p in d.rglob("*.png") if p.is_file() and "_ui_thumbs" not in p.parts]
    except OSError:
        return None
    if not pngs:
        return None
    return max(pngs, key=lambda p: p.stat().st_mtime).as_posix()


def _since_words(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        t = datetime.fromisoformat(str(iso).replace(",", ".").replace(" ", "T")[:19])
    except ValueError:
        return ""
    s = max(0, int((datetime.now() - t).total_seconds()))
    if s < 90:
        return f"{s} s"
    if s < 5400:
        return f"{s // 60} min"
    h, m = divmod(s // 60, 60)
    return f"{h} h {m:02d} min" if h < 48 else f"{h // 24} days"


def _pc() -> str:
    from . import runwords
    return runwords.worker_pc()


def data(cfg: dict, ui_state) -> dict:
    """Everything Home shows. `ui_state` is the dashboard's State (it caches the done folder)."""
    t0 = time.time()
    snap = ui_state.snapshot()
    w = worker.state(cfg)
    out_root = cfgmod.path_of(cfg, "out")
    preview, preview_note = None, ""
    if w["running"]:
        p = _newest_png(out_root / w["running"][0]["id"])
        if p:
            preview, preview_note = Path(p).relative_to(out_root).as_posix(), "this job so far"
    if not preview and snap.get("recent"):
        r = next((j for j in snap["recent"] if j.get("image")), None)
        if r:
            preview, preview_note = r["image"], f"the newest finished picture — {r.get('name') or r['id']}"
    from ..night4 import guard
    limit = float(cfg.get("disk_guard_gb", 40))
    try:
        free = round(guard.free_gb(cfg), 1)
    except OSError:
        free = None
    gst = guard.read(cfg) or {}
    reports = sorted((out_root / "reports").glob("night_*.html")) if (out_root / "reports").is_dir() else []
    c = snap["counts"]
    st = w["state"]
    actions = {
        "start": {"enabled": st in ("stopped", "stopped-mid-job") and worker.here(),
                  "why_not": {"rendering": "it is already running", "idle": "it is already running (idle)",
                              "unknown": "I can't tell whether one is running"}.get(st, "") if worker.here() else
                             f"the art worker runs on {_pc()}, not on this computer",
                  "does": "Opens the GPU worker in its own window, exactly as run_worker.bat does (ComfyUI starts first). "
                          "Close that window to stop it." + (" The job left half-done is put back in the queue first." if st == "stopped-mid-job" else "")},
        "pause": {"enabled": c.get("pending", 0) > 0, "why_not": "nothing is waiting",
                  "does": f"Moves the {c.get('pending', 0):,} waiting job(s) into jobs\\paused. The picture being made now finishes; "
                          "nothing is cancelled or deleted. The same as pause.bat."},
        "resume": {"enabled": c.get("paused", 0) > 0, "why_not": "nothing is paused",
                   "does": f"Puts the {c.get('paused', 0):,} paused job(s) back in the queue, in their old order. The same as resume.bat."},
    }
    today = datetime.now().strftime("%Y-%m-%d")
    logf = cfgmod.path_of(cfg, "logs") / f"forge_{today}.log"
    return {
        "worker": {**w, "since_words": _since_words(w.get("since")), "here": worker.here(), "pc": _pc(),
                   **({} if worker.here() else {"words": f"the art worker runs on {_pc()} — this computer reviews what's in the folders"})},
        "counts": c, "eta": snap.get("eta"), "now_batch": snap.get("now_batch"), "upcoming": snap.get("upcoming", []),
        "preview": preview, "preview_note": preview_note,
        "disk": {"free_gb": free, "limit_gb": limit, "message": gst.get("message"), "low": free is not None and free < limit},
        "report": reports[-1].name if reports else None,
        "failed_recent": snap.get("failed", [])[:3],
        "actions": actions,
        "paths": {"log": str(logf if logf.exists() else cfgmod.path_of(cfg, "logs")), "jobs": str(cfgmod.path_of(cfg, "jobs")),
                  "out": str(out_root)},
        "took_ms": int((time.time() - t0) * 1000),
        "time": datetime.now().strftime("%H:%M:%S"),
    }
