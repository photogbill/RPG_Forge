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
        for sub in ("pending", "running", "done", "failed", "paused"):
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
        """Move the acceptable pending job with the highest `priority` (default 0), oldest first among equals,
        to running/. Returns (id, job) or None."""
        cands = []
        for p in self.pending():
            try:
                job = self._read(p)
            except Exception as e:  # a half-written or broken file: leave it, say so once
                log.warning("cannot read %s: %s", p.name, e)
                continue
            if accept is not None and not accept(job):
                continue
            try:
                pr = float(job.get("priority", 0) or 0)
            except (TypeError, ValueError):
                pr = 0.0
            cands.append((-pr, p.name, p, job))
        for _, _, p, job in sorted(cands, key=lambda c: (c[0], c[1])):
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

    def pause(self, prefix: str | None = None) -> int:
        """Move pending jobs (optionally only a batch prefix) to jobs/paused/ — nothing runs them until resume."""
        return self._move("pending", "paused", prefix)

    def resume(self, prefix: str | None = None) -> int:
        return self._move("paused", "pending", prefix)

    def _move(self, src: str, dst: str, prefix: str | None) -> int:
        n = 0
        for p in sorted((self.jobs / src).glob("*.json")):
            try:
                job = self._read(p)
            except Exception:
                continue
            if prefix and not str(job.get("batch", "")).startswith(prefix) and not p.stem.startswith(prefix):
                continue
            os.replace(p, self.jobs / dst / p.name)
            n += 1
        return n

    def status(self) -> dict:
        out = {}
        for sub in ("pending", "running", "done", "failed", "paused"):
            n = 0
            for p in (self.jobs / sub).glob("*.json"):
                try:
                    if self._read(p).get("tombstone"):
                        continue
                except Exception:
                    pass
                n += 1
            if sub != "paused" or n:
                out[sub] = n          # "paused" only shows up when something is parked
        return out

    def retry_failed(self, prefix: str | None = None) -> int:
        """Move failed jobs back to pending (optionally only those whose `batch` starts with prefix),
        dropping the old error so they run again with the current code. Returns how many."""
        n = 0
        for p in sorted((self.jobs / "failed").glob("*.json")):
            job = self._read(p)
            if job.get("tombstone"):
                continue
            if prefix and not str(job.get("batch", "")).startswith(prefix):
                continue
            for k in ("error", "traceback", "started_at", "finished_at", "result"):
                job.pop(k, None)
            job["retries"] = int(job.get("retries", 0)) + 1
            self._write_atomic(p, job)
            os.replace(p, self.jobs / "pending" / p.name)
            n += 1
        return n

    def release(self, job_id: str, note: str = "", count: bool = True) -> bool:
        """Put ONE claimed job back in pending/ untouched by failure (ComfyUI went away mid-run — not the job's fault).
        Counts it in `comfy_waits` so a job that keeps taking ComfyUI down is failed after COMFY_RELEASES tries."""
        p = self.jobs / "running" / f"{job_id}.json"
        if not p.exists():
            return False
        job = self._read(p)
        job.pop("started_at", None)
        if count:
            job["comfy_waits"] = int(job.get("comfy_waits", 0)) + 1
        if note:
            job["last_wait"] = note
        self._write_atomic(p, job)
        os.replace(p, self.jobs / "pending" / p.name)
        log.warning("released %s back to pending (%s)", job_id, note or "engine away")
        return True

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


GUARD_EVERY_SEC = 300.0
COMFY_RELEASES = 2           # a job that loses ComfyUI this many times is failed for real (it may be what crashes it)
COMFY_WAIT_LOG_SEC = 60.0


def _engine_away(e: Exception) -> bool:
    """ComfyUI stopped answering (crashed, closed, still starting) — the job itself is not at fault."""
    msg = f"{type(e).__name__}: {e}"
    return ("ComfyUI is not reachable" in msg or isinstance(e, (ConnectionResetError, ConnectionRefusedError, ConnectionAbortedError))
            or "WinError 10054" in msg or "WinError 10061" in msg or "Connection refused" in msg)


def _wait_for_engine(ctx, poll: float = 15.0) -> None:
    """Block until ComfyUI answers again, logging once a minute (2026-11-11: a ComfyUI crash at 19:17 made the worker
    fail ~240 queued jobs in seconds, each with 'not reachable'; now the queue waits instead of burning)."""
    comfy = getattr(ctx, "comfy", None)
    if comfy is None:
        return
    t0 = last = time.time()
    log.warning("ComfyUI is not answering at %s — the queue waits for it (restart it with start_comfy.bat)", getattr(comfy, "url", "?"))
    while True:
        try:
            if comfy.is_up():
                log.info("ComfyUI is back after %.0f s — carrying on", time.time() - t0)
                return
        except Exception:  # noqa: BLE001
            pass
        if time.time() - last >= COMFY_WAIT_LOG_SEC:
            log.warning("still waiting for ComfyUI (%.0f min)", (time.time() - t0) / 60)
            last = time.time()
        time.sleep(poll)


def _guard(cfg) -> None:
    """Wiring day W8: the disk guard, inside the worker (so it works without produce_watch.bat). It only moves pending
    files to paused (and back); the job being rendered finishes. A guard error is logged and never stops the worker."""
    try:
        from .night4 import guard
        guard.check(cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("disk guard check failed (the worker carries on): %s", e)


PRUNE_EVERY_SEC = 600.0


def _prune(cfg) -> None:
    """2026-11-11: ComfyUI's own copy of each picture (out/_comfy) is never read again — delete those older than 20 min."""
    try:
        from .night4 import housekeeping
        n, b = housekeeping.prune_comfy(cfg, 20.0)
        if n:
            log.info("deleted %d of ComfyUI's duplicate picture(s) in out/_comfy (%.2f GB)", n, b / 1e9)
    except Exception as e:  # noqa: BLE001
        log.warning("pruning out/_comfy failed (the worker carries on): %s", e)


def run_worker(queue: Queue, handlers, ctx, gpu: bool, once: bool = False, poll_sec: float = 2.0, cfg=None) -> int:
    """Claim and run jobs until the queue is empty (`once`) or forever. Returns jobs run.

    `handlers` maps job type → callable(job, ctx, out_dir) -> result dict, or is a callable returning
    that map (called before every job, so handler code can be reloaded while the worker runs).
    `cfg` (W8): when given, the disk guard runs every GUARD_EVERY_SEC — before the first claim, then between jobs.
    A handler's exception becomes a failed job with the traceback saved, and the worker keeps going.
    """
    def current() -> dict:
        return handlers() if callable(handlers) else handlers

    # Load the handler map ONCE per claim cycle. accept() runs for every pending file, and current() reloads the
    # handler modules — with thousands of jobs queued that was thousands of reloads between renders (~16 s idle per
    # job in the 2026-11-10 sprite run). Code fixes are still picked up: the map is refreshed before every claim.
    hmap: dict = {}

    def accept(job: dict) -> bool:
        t = job.get("type")
        if t not in hmap:
            return False
        if schema.needs_gpu(job) and not gpu:
            return False
        if job.get("tombstone"):
            return False
        return True

    ran = 0
    idle_logged = False
    last_guard = 0.0
    last_prune = time.time()
    while True:
        if cfg is not None and time.time() - last_guard >= GUARD_EVERY_SEC:
            _guard(cfg)
            last_guard = time.time()
        if cfg is not None and gpu and time.time() - last_prune >= PRUNE_EVERY_SEC:
            _prune(cfg)
            last_prune = time.time()
        hmap = current()
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
            result = hmap[job["type"]](job, ctx, out_dir) or {}
            result["seconds"] = round(time.time() - t0, 1)
            queue.finish(job_id, result=result)
        except Exception as e:  # noqa: BLE001 — every failure is recorded, never swallowed
            # down before the job started (never its fault) → always back to pending; lost mid-render → at most COMFY_RELEASES times
            before = "ComfyUI is not reachable" in str(e)
            if gpu and _engine_away(e) and (before or int(job.get("comfy_waits", 0) or 0) < COMFY_RELEASES):
                queue.release(job_id, f"{type(e).__name__}: {e}"[:300], count=not before)
                _wait_for_engine(ctx)
                continue
            queue.finish(job_id, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc())
        ran += 1
