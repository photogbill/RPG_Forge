"""Run one job now, in this process, through the same handler the worker uses — for CPU jobs a person is waiting
on (sprite intake), so they do not queue behind a night of GPU renders. The job goes straight to jobs/running/
(never pending, so a running worker cannot claim it too) and is finished like any other: jobs/done or jobs/failed,
out/<id>/job.json."""
from __future__ import annotations
import logging
import traceback
from datetime import datetime

from .. import config as cfgmod
from .. import schema

log = logging.getLogger("forge.inline")


def run_now(cfg: dict, job: dict) -> tuple[str, dict | None, str | None]:
    from ..queue import Queue
    from ..jobs import get_handlers
    from ..jobs.common import Context
    problems = schema.validate(job)
    if problems:
        raise ValueError("; ".join(problems))
    if schema.needs_gpu(job):
        raise ValueError(f"{job['type']} needs the GPU worker — queue it instead")
    q = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))
    job = dict(job)
    jid = job.get("id") or q.make_id(job.get("name") or job["type"])
    job["id"] = jid
    now = datetime.now().isoformat(timespec="seconds")
    job["submitted_at"] = now
    job["started_at"] = now
    job["ran"] = "inline"
    q._write_atomic(q.jobs / "running" / f"{jid}.json", job)
    log.info("inline %s (%s)", jid, job["type"])
    ctx = Context(cfg=cfg, palettes_dir=cfgmod.path_of(cfg, "palettes"), root=cfgmod.ROOT)
    handlers = get_handlers()
    try:
        res = handlers[job["type"]](schema.with_defaults(job), ctx, q.out_dir(jid)) or {}
    except Exception as e:  # noqa: BLE001 — recorded like a worker failure
        q.finish(jid, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc())
        log.exception("inline %s failed", jid)
        return jid, None, f"{type(e).__name__}: {e}"
    q.finish(jid, result=res)
    return jid, res, None
