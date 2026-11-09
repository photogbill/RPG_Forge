"""Do not queue what is already done (roadmap N5).

A bake-off cell's identity is suite · category · prompt id · checkpoint · LoRA · seed · job type · the tool fields
(target, refine, face_fix, control, … — whatever the suite or category adds on top of a plain render). A plain batch
job's identity is batch · name · type. A job whose identity already has a **done, pending, running or paused** job is
skipped; a **failed** one is queued again. `--force` turns all this off.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

from . import config as cfgmod

# fields every bake-off render has (not "tool" fields) and the queue's own receipt fields — neither is identity
BASE_KEYS = {"type", "game", "name", "batch", "prompt", "negative", "checkpoint", "loras", "seed", "size", "steps", "cfg",
             "sampler", "scheduler", "style_prefix", "meta", "graph", "text_encoder", "vae", "clip_l", "t5", "guidance",
             "all_in_one", "distilled"}
RECEIPT_KEYS = {"id", "submitted_at", "started_at", "finished_at", "result", "error", "traceback", "retries", "worker",
                "claimed_at", "priority"}
LIVE = ("done", "pending", "running", "paused")


def _h(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:16]


def cell_key(job: dict) -> str | None:
    """Identity of a bake-off cell, or None if the job is not one (no meta.suite)."""
    m = job.get("meta") or {}
    if not m.get("suite"):
        return None
    tools = {k: v for k, v in job.items() if k not in BASE_KEYS and k not in RECEIPT_KEYS}
    return _h(["cell", m.get("suite"), m.get("category"), m.get("prompt_id"), m.get("checkpoint"), m.get("lora"),
               m.get("seed"), job.get("type"), tools])


def batch_key(job: dict) -> str | None:
    if not job.get("batch") or not job.get("name"):
        return None
    return _h(["job", job.get("batch"), job.get("name"), job.get("type")])


def key(job: dict) -> str | None:
    return cell_key(job) or batch_key(job)


def existing(cfg: dict, batch_prefix: str | None = None) -> dict[str, str]:
    """{identity: state} for every job in done/pending/running/paused (optionally only one batch prefix)."""
    jobs = cfgmod.path_of(cfg, "jobs")
    out: dict[str, str] = {}
    for state in LIVE:
        for p in (jobs / state).glob("*.json"):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if batch_prefix and not str(j.get("batch") or "").startswith(batch_prefix):
                continue
            k = key(j)
            if k and (k not in out or state != "done"):
                out[k] = state
    return out


def filter_new(cfg: dict, jobs: list[dict], batch_prefix: str | None = None) -> tuple[list[dict], dict[str, int]]:
    """(the jobs to queue, {"done": n, "pending": n, …} skipped by state). Jobs with no identity are always queued."""
    have = existing(cfg, batch_prefix)
    new, skipped = [], {}
    seen = set()
    for j in jobs:
        k = key(j)
        if k is None:
            new.append(j)
            continue
        if k in have:
            skipped[have[k]] = skipped.get(have[k], 0) + 1
            continue
        if k in seen:                      # the same cell twice in one plan
            skipped["duplicate"] = skipped.get("duplicate", 0) + 1
            continue
        seen.add(k)
        new.append(j)
    return new, skipped


def describe(skipped: dict[str, int]) -> str:
    if not skipped:
        return ""
    parts = [f"{n} {s}" for s, n in sorted(skipped.items())]
    return f"skipped {sum(skipped.values())} already queued or finished ({', '.join(parts)}) — --force queues them anyway"
