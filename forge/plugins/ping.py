"""`ping` - the smallest plug-in job type: the example to copy, and the check that a worker has plug-in support.

Submit {"type": "ping", "name": "hello", "priority": 10}. A worker started after 2026-11-09 21:00 runs it at once
and writes out/<id>/ping.txt; an older worker does not know the type and leaves the job in jobs/pending/.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path


def ping(job: dict, ctx, out_dir) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = f"pong {datetime.now().isoformat(timespec='seconds')} {job.get('say') or ''}".strip()
    (out / "ping.txt").write_text(text + "\n", encoding="utf-8")
    return {"outputs": ["ping.txt"], "said": text}


JOB_TYPES = {
    "ping": {
        "needs": "cpu",
        "doc": "Plug-in health check (forge/plugins/ping.py): writes ping.txt. If a worker runs it, that worker "
               "picks up new plug-in job types without a restart. Output: ping.txt.",
        "required": [],
        "optional": {"say": None},
    },
}
HANDLERS = {"ping": ping}
