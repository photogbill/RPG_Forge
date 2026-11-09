"""The disk job queue — the protocol everything else rests on (docs/PROTOCOL.md).

    jobs/pending/<id>.json   written by whoever wants work done (a person, a script, Claude)
    jobs/running/<id>.json   claimed by a worker (atomic rename)
    jobs/done/<id>.json      finished; the job file gains a "result" summary
    jobs/failed/<id>.json    failed; the job file gains "error" + "traceback"
    out/<id>/                everything the job produced: images, report.json, prov.json, job.log

Ids are `YYYYMMDD-HHMMSS-<name>-<4 hex>` so a folder listing is already a timeline. Moves between
folders are `os.replace` (atomic on one filesystem), so two workers never run the same job.
"""
from __future__ import annotations
import json, os, secrets, time, traceback
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import schema
from .log import get

log = get("queue")


class Queue:
    def __init__(self, jobs_dir: Path, out_dir: Path):
        self.jobs = Path(jobs_dir)
        self.out = Path(out_dir)
        for sub in ("pending", "running", "done", "failed"):
            (self.jobs / sub).mkdir(parents=True, exist_ok=True)
        self.out.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ submitting
    @staticmethod
    def make_id(name: str) -> str:
        safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in (name or "job"))[:48]
        return f"{datetime.now():%Y%m%d-%H%M%S}-{safe}-{secrets.token_hex(2)}"

    def submit(self, job: dict) -> str:
        problems = schema.validate(job)
        if problems:
            raise ValueError("; ".join(problems))
        job = dict(job)
        job_id = job.get("id") or self.make_id(job.get("name") or job["type"])
        job["id"] = job_id
        job["submitted_at"] = datetime.now().isoformat(timespec="seconds")
        self._write_atomic(self.jobs / "pending" / f"{job_id}.json", job)
        log.info("submitted %s (%s)", job_id, job["type"])
        return job_id

    def submit_batch(self, batch: dict) -> list[str]:
        """{"batch": "name", "defaults": {...}, "jobs": [ {...}, ... ]} → ids. Defaults fill each job."""
        defaults = batch.get("defaults", {})
        ids = []
        for j in batch.get("jobs", []):
            job = dict(defaults)
            job.update(j)
            if batch.get("batch"):
                job.setdefault("batch", batch["batch"])
            ids.append(self.submit(job))
        return ids

    # ------------------------------------------------------------------ working
    def pending(self) -> list[Path]:
        return sorted(p for p in (self.jobs / "pending").glob("*.json"))

    def claim(self, accept: Callable[[dict], bool] | None = None) -> tuple[str, dict] | None:
        """Move the oldest acceptable pending job to running/. Returns (id, job) or None."""
        for p in self.pending():
            try:
                job = self._read(p)
            except Exception as e:  # a half-written or broken file: leave it, say so once
                log.warning("cannot read %s: %s", p.name, e)
                continue
            if accept is not None and not accept(job):
                continue
            target = self.jobs / "running" / p.name
            try:
                os.replace(p, target)
            except FileNotFoundError:
                continue  # another worker got it first
            job["started_at"] = datetime.now().isoformat(timespec="seconds")
            self._write_atomic(target, job)
            log.info("claimed %s", job["id"])
            return job["id"], job
        return None

    def out_dir(self, job_id: str) -> Path:
        d = self.out / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def finish(self, job_id: str, result: dict | None = None, error: str | None = None, tb: str | None = None) -> None:
        src = self.jobs / "running" / f"{job_id}.json"
        job = self._read(src) if src.exists() else {"id": job_id}
        job["finished_at"] = datetime.now().isoformat(timespec="seconds")
        if error is None:
            job["result"] = result or {}
            dest = self.jobs / "done" / f"{job_id}.json"
            log.info("done %s", job_id)
        else:
            job["error"] = error
            if tb:
                job["traceback"] = tb
            dest = self.jobs / "failed" / f"{job_id}.json"
            log.error("FAILED %s: %s", job_id, error)
        if src.exists():
            # rewrite in place, then rename: a rename needs no delete permission on locked-down folders
            self._write_atomic(src, job)
            try:
                os.replace(src, dest)
            except OSError:
                self._write_atomic(dest, job)
                self._write_atomic(src, {"id": job_id, "moved_to": str(dest), "tombstone": True})
        else:
            self._write_atomic(dest, job)
        # the job file is the receipt; a copy lives with the outputs
        self._write_atomic(self.out_dir(job_id) / "job.json", job)

    def status(self) -> dict:
        out = {}
        for sub in ("pending", "running", "done", "failed"):
            n = 0
            for p in (self.jobs / sub).glob("*.json"):
                try:
                    if self._read(p).get("tombstone"):
                        continue
                except Exception:
                    pass
                n += 1
            out[sub] = n
        return out

    def requeue_running(self) -> int:
        """After a crash: move running/ jobs back to pending/. Returns how many."""
        n = 0
        for p in (self.jobs / "running").glob("*.json"):
            job = self._read(p)
            if job.get("tombstone"):
                continue
            job.pop("started_at", None)
            self._write_atomic(p, job)
            os.replace(p, self.jobs / "pending" / p.name)
            n += 1
        return n

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _read(p: Path) -> dict:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_atomic(p: Path, data: dict) -> None:
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, p)


def run_worker(queue: Queue, handlers: dict[str, Callable], ctx, gpu: bool, once: bool = False,
               poll_sec: float = 2.0) -> int:
    """Claim and run jobs until the queue is empty (`once`) or forever. Returns jobs run.

    `handlers` maps job type → callable(job, ctx, out_dir) -> result dict. A handler's exception
    becomes a failed job with the traceback saved, and the worker keeps going.
    """
    def accept(job: dict) -> bool:
        t = job.get("type")
        if t not in handlers:
            return False
        if schema.needs_gpu(job) and not gpu:
            return False
        if job.get("tombstone"):
            return False
        return True

    ran = 0
    idle_logged = False
    while True:
        claimed = queue.claim(accept)
        if claimed is None:
            if once:
                return ran
            if not idle_logged:
                log.info("idle — waiting for jobs in %s", queue.jobs / "pending")
                idle_logged = True
            time.sleep(poll_sec)
            continue
        idle_logged = False
        job_id, job = claimed
        job = schema.with_defaults(job)
        out_dir = queue.out_dir(job_id)
        t0 = time.time()
        try:
            result = handlers[job["type"]](job, ctx, out_dir) or {}
            result["seconds"] = round(time.time() - t0, 1)
            queue.finish(job_id, result=result)
        except Exception as e:  # noqa: BLE001 — every failure is recorded, never swallowed
            queue.finish(job_id, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc())
        ran += 1
