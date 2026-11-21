"""The forge's operations for Claude (BUILD 83 Part A, 2026-11-19) — run in the forge's own environment, one call a process.

    <the forge's venv python> -m forge.mcpserver.ops     one request (JSON) on stdin -> one answer (JSON) on stdout

The MCP server (forge/mcpserver/server.py, in its own small environment) starts this for every call, so each call runs
the forge's newest code with the forge's own packages, and nothing the server holds can go stale.

Request: {"op": "jobs.submit", "input": {...}, "dry_run": false, "key": "", "who": "Claude Fable", "game": ""}
Answer, always one of:
  {"status": "done",           "result": {...}, "next": "..."}
  {"status": "running",        "jobs": [...], "next": "forge_wait"}               (work queued; it goes on after the call)
  {"status": "needs_approval", "waits_on": "...", "where": "...", "message": "..."}
  {"status": "dry_run",        "would": "...", "files_written": 0, ...}
  {"status": "error",          "code": "...", "message": "...", "next": "..."}

**The one rule: no new rules here.** Reads come from the files the forge already keeps. Every change goes through a function
the Workbench already uses (world3d.act, places3d.act, approve_all, mail.send, provide.add, Queue.submit), so signing,
licence checks, look blocks and refusals stay the forge's own. If the Workbench would refuse it, this refuses it.
Not offered at all: deleting anything, starting or stopping the world queue or the launcher, the order of need, settings,
any shell command. This connector is for Claude: a change is signed with `who`, which must start with "Claude".
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod
from ..log import get

log = get("mcp")

KEY_IN_PROGRESS_FOR = 900          # a call with this key started this many seconds ago and has not finished: still working
KEY_KEEP_DAYS = 30
RESULT_LIMIT = 60                  # list lengths, unless asked


# ------------------------------------------------------------------------------------------------ answers
def done(result, nxt: str = "") -> dict:
    a = {"status": "done", "result": result}
    if nxt:
        a["next"] = nxt
    return a


def error(code: str, message: str, nxt: str) -> dict:
    return {"status": "error", "code": code, "message": str(message)[:1500], "next": nxt}


def needs_approval(message: str, where: str) -> dict:
    return {"status": "needs_approval", "waits_on": "William — or Claude Fable, while William's \"Claude Fable may "
            "approve for me\" is on (Settings -> Approvals) — or Claude Opus, while a concurrence William opened with concur.bat "
            "is live (30 minutes)", "where": where, "message": str(message)[:800]}


def refused(message: str, where: str = "") -> dict:
    """The forge said no: its own words, sorted into the person's (needs_approval) and the rest (refused)."""
    m = str(message)
    if "person's" in m or "may approve for me" in m:
        return needs_approval(m, where or "the Workbench")
    return error("refused", m, "read the message: it is the forge's own reason; change the input or ask William")


def _act_answer(r: dict, where: str) -> dict:
    """A Workbench action's {"ok", "message", ...} as one answer."""
    if r.get("ok") is False and not any(r.get(k) for k in ("again", "released", "placed", "done")):
        return refused(r.get("message") or "the forge refused", where)
    return done({k: v for k, v in r.items() if k != "ok"})


# ------------------------------------------------------------------------------------------------ the call
class Ctx:
    def __init__(self, cfg: dict, gid: str, who: str):
        self.cfg, self.gid, self.who = cfg, gid, who
        self.root = Path(cfg.get("_root") or cfgmod.ROOT)

    def rel(self, p) -> str:
        p = Path(p)
        try:
            return p.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return str(p)

    def queue(self):
        from ..queue import Queue
        return Queue(cfgmod.path_of(self.cfg, "jobs"), cfgmod.path_of(self.cfg, "out"))


class Op:
    def __init__(self, name: str, kind: str, doc: str, fn, inputs: dict | None = None, dry=None, needs_who: bool = False):
        self.name, self.kind, self.doc, self.fn, self.dry = name, kind, doc, fn, dry
        self.inputs = inputs or {}                 # field -> "required: …" or "optional: …"
        self.needs_who = needs_who or kind == "change"

    @property
    def required(self) -> list[str]:
        return [k for k, v in self.inputs.items() if str(v).startswith("required")]

    def describe(self) -> dict:
        return {"op": self.name, "kind": self.kind, "what": self.doc, "input": self.inputs,
                "signed": self.needs_who, "dry_run": self.kind == "change"}


OPS: dict[str, Op] = {}


def op(name, kind, doc, inputs=None, dry=None, needs_who=False):
    def deco(fn):
        OPS[name] = Op(name, kind, doc, fn, inputs, dry, needs_who)
        return fn
    return deco


# ------------------------------------------------------------------------------------------------ status
def _safe(fn, default=None):
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001 — a status shows what it can
        return {"unavailable": f"{type(ex).__name__}: {ex}"[:300]} if default is None else default


TOMBSTONE_MAX_BYTES = 1024         # a moved job leaves {"id", "moved_to", "tombstone"} behind: never bigger than this


def count_jobs(jobs_dir: Path) -> dict:
    """BUILD 84 part 4 — the art queue's counts without opening every job file. `Queue.status()` reads each file to leave
    out the tombstones a move leaves behind; with 16,700 finished jobs that was the first half of a status that took a
    minute. A tombstone is three short fields, so only files that small are opened; a real job (its type, its words, its
    times, its result) is always bigger and is counted from the folder's own listing. The answer is the same."""
    out = {}
    for sub in ("pending", "running", "done", "failed", "paused"):
        n = 0
        try:
            with os.scandir(Path(jobs_dir) / sub) as it:
                for f in it:
                    if not f.name.endswith(".json"):
                        continue
                    try:
                        if f.stat().st_size <= TOMBSTONE_MAX_BYTES:
                            with open(f.path, encoding="utf-8") as fh:
                                if json.load(fh).get("tombstone"):
                                    continue
                    except (OSError, ValueError, AttributeError):
                        pass                              # unreadable or half-written: counted, as Queue.status() does
                    n += 1
        except OSError:
            pass
        if sub != "paused" or n:
            out[sub] = n                                  # "paused" only shows up when something is parked
    return out


def eta_fast(cfg: dict, pending: int | None = None) -> dict:
    """How long the art queue will take. Nothing pending: nothing to work out, and no file is read. Otherwise the forge's
    own estimate, with the newest finished jobs found from the folder's listing (one pass, no file opened to sort them)."""
    from .. import eta
    if pending == 0:
        return {"pending": 0, "hours": 0.0}
    jobs = cfgmod.path_of(cfg, "jobs")
    pend = []
    for q in sorted((jobs / "pending").glob("*.json")):
        try:
            j = json.loads(q.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not j.get("tombstone"):
            pend.append(j)
    newest = []
    try:
        with os.scandir(jobs / "done") as it:
            newest = sorted(((f.stat().st_mtime, f.path) for f in it if f.name.endswith(".json")), reverse=True)[:400]
    except OSError:
        pass
    hist = []
    for _, path in newest:
        try:
            j = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        d = eta._dur(j)
        if d is not None:
            hist.append({"type": j.get("type"), "batch": j.get("batch"), "seconds": d})
    med, overall = eta.per_type(hist)
    total = sum((med.get(j.get("type")) or overall or eta.FALLBACK_SEC) for j in pend)
    return {"pending": len(pend), "hours": round(total / 3600, 1)}


STATUS_SLOW_SECONDS = 5.0          # BUILD 84 part 4: a status slower than this says so in the log, with its slowest part


@op("status", "read", "Everything at a glance: the art queue, the world queue and its backlog in hours, the never-stop "
    "launcher, ComfyUI, the disk, and what waits for approval. Says how long each part of it took.")
def _status(c: Ctx, inp: dict) -> dict:
    import shutil
    from ..threed import world
    t_all = time.time()
    took: dict = {}

    def part(name, fn):
        t = time.time()
        out[name] = _safe(fn)
        took[name] = round(time.time() - t, 2)

    out: dict = {"game": c.gid, "at": datetime.now().isoformat(timespec="seconds")}
    part("art_queue", lambda: count_jobs(cfgmod.path_of(c.cfg, "jobs")))
    part("art_queue_time", lambda: eta_fast(c.cfg, (out.get("art_queue") or {}).get("pending")))
    read: dict = {}                                      # the list, read once and handed on (it was read three times)

    def _world():
        items, _ = world.merged(c.cfg, c.gid)
        read["items"] = items
        est = world.estimate(c.cfg, c.gid, items)
        ls = world.launcher_state(c.cfg, c.gid)
        counts: dict = {}
        for e in items:
            counts[e["shown"]] = counts.get(e["shown"], 0) + 1
        return {"running": ls.get("running"), "step": ls.get("step"), "item": ls.get("item"), "counts": counts,
                "to_make": est["to_make"], "hours_left": round(est["seconds"] / 3600, 1), "time_left": est["words"],
                "under_a_day": est["seconds"] < 24 * 3600}
    part("world_queue", _world)

    def _clock():
        p = world.world_dir(c.cfg, c.gid) / "_around_the_clock.json"
        if not p.exists():
            return {"running": False, "note": "never started (art_around_the_clock.bat)"}
        d = json.loads(p.read_text(encoding="utf-8"))
        alive = d.get("step") != "stopped" and time.time() - float(d.get("beat") or 0) < 120
        return {"running": alive, "step": d.get("step"), "last_redo": d.get("redo", {}).get("summary"),
                "queue_restarts": (d.get("queue") or {}).get("stopped_by_itself"),
                "comfy_starts": (d.get("comfy") or {}).get("starts")}
    part("around_the_clock", _clock)

    def _comfy():
        from ..threed import comfyapi
        url = ((c.cfg or {}).get("comfy") or {}).get("url") or "http://127.0.0.1:8188"
        # on this computer it answers in a few thousandths of a second or not at all: one second is long enough to know
        return {"url": url, "answering": bool(comfyapi.is_up(url, timeout=1.0))}
    part("comfyui", _comfy)

    def _disk():
        u = shutil.disk_usage(c.root)
        return {"free_gb": round(u.free / 1e9, 1), "total_gb": round(u.total / 1e9, 1)}
    part("disk", _disk)

    def _approvals():
        from ..suite import approve_all
        w = approve_all.world_plan(c.cfg, c.gid, read.get("items"))
        r = approve_all.review_plan(c.cfg, c.gid)
        s = approve_all.setting(c.cfg, c.gid)
        return {"world_list_waiting": w["count"], "review_waiting": r.get("count"),
                "fable_may_approve": bool(s.get("on")) and "Claude Fable" in (s.get("assistants") or []),
                "left_for_a_look": w.get("left")}
    part("approvals", _approvals)
    total = round(time.time() - t_all, 2)
    out["took_seconds"] = {"all": total, **took}
    slowest = max(took, key=took.get) if took else "-"
    (log.warning if total > STATUS_SLOW_SECONDS else log.info)(
        "mcp: status took %.2f s (%s)%s", total, ", ".join(f"{k} {v:.2f}" for k, v in took.items()),
        f" — slower than {STATUS_SLOW_SECONDS:.0f} s; the slowest part is {slowest}" if total > STATUS_SLOW_SECONDS else "")
    return done(out)


# ------------------------------------------------------------------------------------------------ the art queue
@op("jobs.types", "read", "Every job type the art queue knows: what it makes, GPU or CPU, its required and optional fields.",
    {"type": "optional: one type's name"})
def _job_types(c: Ctx, inp: dict) -> dict:
    from .. import schema
    schema._plugins()
    want = inp.get("type")
    rows = [{"type": t, "needs": s["needs"], "what": s["doc"], "required": s["required"], "optional": s["optional"]}
            for t, s in sorted(schema.JOB_TYPES.items()) if not want or t == want]
    if want and not rows:
        return error("not_found", f"no job type {want!r}", "jobs.types with no input lists them all")
    return done(rows)


def _job_dirs(c: Ctx) -> dict:
    jobs = cfgmod.path_of(c.cfg, "jobs")
    return {s: jobs / s for s in ("pending", "running", "done", "failed", "paused")}


def _find_job(c: Ctx, jid: str):
    for state, d in _job_dirs(c).items():
        p = d / f"{jid}.json"
        if p.exists():
            return state, json.loads(p.read_text(encoding="utf-8"))
    return None, None


def _short_job(j: dict, state: str) -> dict:
    keep = ("id", "type", "name", "batch", "game", "submitted_at", "started_at", "finished_at")
    d = {k: j.get(k) for k in keep if j.get(k) is not None}
    d["state"] = state
    if j.get("prompt"):
        d["prompt"] = str(j["prompt"])[:200]
    if state == "failed":
        d["error"] = str(j.get("error") or "")[:400]
    if state == "done" and isinstance(j.get("result"), dict):
        d["result"] = {k: v for k, v in j["result"].items() if not isinstance(v, (list, dict)) or len(str(v)) < 400}
    return d


@op("jobs.list", "read", "The art queue's jobs, newest first.",
    {"state": "optional: pending | running | done | failed | paused (default: all)", "batch": "optional: only this batch",
     "limit": f"optional: how many (default {RESULT_LIMIT // 3})"})
def _jobs_list(c: Ctx, inp: dict) -> dict:
    states = [inp["state"]] if inp.get("state") else ["running", "pending", "failed", "done", "paused"]
    limit = int(inp.get("limit") or RESULT_LIMIT // 3)
    rows = []
    dirs = _job_dirs(c)
    for s in states:
        if s not in dirs:
            return error("invalid_input", f"state is one of {', '.join(dirs)}", "jobs.list with a valid state")
        for p in sorted(dirs[s].glob("*.json"), reverse=True):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if j.get("tombstone") or (inp.get("batch") and j.get("batch") != inp["batch"]):
                continue
            rows.append(_short_job(j, s))
    rows.sort(key=lambda r: r.get("id") or "", reverse=True)
    return done({"jobs": rows[:limit], "shown": min(limit, len(rows)), "of": len(rows)})


@op("jobs.get", "read", "One job: its state, its result and the files it made (forge_job also shows its contact sheet).",
    {"id": "required: the job id"})
def _jobs_get(c: Ctx, inp: dict) -> dict:
    state, j = _find_job(c, str(inp["id"]))
    if not j:
        return error("not_found", f"no job {inp['id']!r} in the queue", "jobs.list shows the ids")
    out_dir = cfgmod.path_of(c.cfg, "out") / str(inp["id"])
    files = sorted(p.name for p in out_dir.iterdir()) if out_dir.is_dir() else []
    contact = out_dir / "contact.png"
    pics = [c.rel(out_dir / f) for f in files if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    return done({"job": _short_job(j, state), "files": files[:80], "folder": c.rel(out_dir),
                 "contact": c.rel(contact) if contact.exists() else (pics[0] if pics else None), "pictures": pics[:20]})


def _prepare(c: Ctx, data: dict) -> list[dict]:
    """The same road `python -m forge submit` takes: characters resolved from the registry, the prompt library's
    {{blocks}} expanded and its never-list checked, then the schema. Raises ValueError with the forge's own words."""
    from .. import prompts as pl
    from .. import schema
    from ..night4 import characters as ch, charset as cs

    def with_character(job, game):
        if job.get("type") == "character_set":
            return cs.expand_set(c.cfg, job, game)
        if job.get("character"):
            return ch.resolve(c.cfg, job, game)
        return job

    try:
        if "jobs" in data:
            d = data.get("defaults") or {}
            g = data.get("game") or d.get("game") or c.gid
            jobs = pl.prepare(c.cfg, [with_character({**d, **j}, g) for j in data["jobs"]], g)
            if data.get("batch"):
                for j in jobs:
                    j.setdefault("batch", data["batch"])
        else:
            jobs = pl.prepare(c.cfg, [with_character(dict(data), data.get("game") or c.gid)])
    except (pl.PromptError, ch.CharacterError, cs.CharsetError) as ex:
        raise ValueError(str(ex)) from ex
    problems = [f"{j.get('name') or j.get('type')}: {p}" for j in jobs for p in schema.validate(j)]
    if problems:
        raise ValueError("; ".join(problems))
    return jobs


def _submit_dry(c: Ctx, inp: dict) -> dict:
    from .. import eta, schema
    data = inp.get("batch") or inp.get("job")
    try:
        jobs = _prepare(c, data)
    except ValueError as ex:
        return refused(ex)
    med, overall = eta.per_type(eta.history(c.cfg))
    secs = sum(med.get(j["type"]) or overall or eta.FALLBACK_SEC for j in jobs)
    return {"status": "dry_run", "would": f"queue {len(jobs)} job(s) on the art queue", "files_written": 0,
            "gpu_hours": round(secs / 3600, 2), "jobs": [{"type": j["type"], "name": j.get("name"), "gpu": schema.needs_gpu(j),
                                                         "prompt": str(j.get("prompt") or "")[:300]} for j in jobs[:20]]}


def _submit(c: Ctx, inp: dict) -> dict:
    data = inp.get("batch") or inp.get("job")
    try:
        jobs = _prepare(c, data)
    except ValueError as ex:
        return refused(ex)
    q = c.queue()
    ids = [q.submit({**j, "submitted_by": c.who}) for j in jobs]
    return {"status": "running", "jobs": ids, "message": f"queued {len(ids)} job(s); GPU jobs run while the art worker runs "
            "(run_worker.bat) and the card is free", "next": "forge_wait(job_id) or forge_job(job_id)"}


@op("jobs.submit", "change", "Queue one art job (see jobs.types). Characters and {{prompt blocks}} resolve as `submit` does.",
    {"job": "required: one job, e.g. {\"type\": \"concept\", \"name\": \"inn_dusk\", \"prompt\": \"…\"}"}, dry=_submit_dry)
def _jobs_submit(c: Ctx, inp: dict) -> dict:
    return _submit(c, inp)


@op("jobs.submit_batch", "change", "Queue a batch: {\"batch\": name, \"defaults\": {...}, \"jobs\": [...]}.",
    {"batch": "required: the batch object"}, dry=_submit_dry)
def _jobs_submit_batch(c: Ctx, inp: dict) -> dict:
    if not isinstance(inp.get("batch"), dict) or "jobs" not in inp["batch"]:
        return error("invalid_input", "batch must be {\"batch\": name, \"defaults\": {...}, \"jobs\": [...]}", "fix the batch")
    return _submit(c, inp)


def _retry_dry(c: Ctx, inp: dict) -> dict:
    n = sum(1 for p in _job_dirs(c)["failed"].glob("*.json") if not inp.get("prefix") or p.name.startswith(inp["prefix"]))
    return {"status": "dry_run", "would": f"put {n} failed job(s) back in pending", "files_written": 0}


@op("jobs.retry_failed", "change", "Put failed art jobs back in line (all, or those whose id starts with a prefix).",
    {"prefix": "optional: only ids that start with this"}, dry=_retry_dry)
def _jobs_retry(c: Ctx, inp: dict) -> dict:
    n = c.queue().retry_failed(inp.get("prefix") or None)
    return done({"back_in_line": n})


# ------------------------------------------------------------------------------------------------ the world list
def _world_items(c: Ctx):
    from ..threed import world
    return {e["id"]: e for e in world.merged(c.cfg, c.gid)[0]}


@op("world.list", "read", "The world list (the 3D things the world queue makes): what is made, held, failed and next, "
    "with the hours left.", {"state": "optional: wanted | making | made | held | failed | superseded",
                             "kind": "optional: body | prop | building | panel | tree | cloth",
                             "find": "optional: words to look for in the id or words", "limit": f"optional (default {RESULT_LIMIT})"})
def _world_list(c: Ctx, inp: dict) -> dict:
    from ..threed import world
    s = world.status(c.cfg, c.gid)
    limit = int(inp.get("limit") or RESULT_LIMIT)
    rows = []
    for it in s["items"]:
        if inp.get("state") and it["state"] != inp["state"]:
            continue
        if inp.get("kind") and it["kind"] != inp["kind"]:
            continue
        if inp.get("find") and str(inp["find"]).lower() not in (it["id"] + " " + str(it.get("words") or "")).lower():
            continue
        rows.append({"id": it["id"], "kind": it["kind"], "tier": it["tier"], "state": it["state"], "shown": it["shown"],
                     "hold": it["hold"], "why": (it.get("why") or [None])[0], "error": (it.get("error") or "")[:200] or None,
                     "next": it["next"], "words": str(it.get("words") or "")[:140]})
    return done({"counts": s["counts"], "estimate": {k: s["estimate"][k] for k in ("to_make", "words")},
                 "launcher": s["launcher"], "items": rows[:limit], "shown": min(limit, len(rows)), "of": len(rows),
                 "problems": s["problems"][:10]})


def _world_act(action: str, body_of, where: str = "3D -> World list"):
    def fn(c: Ctx, inp: dict) -> dict:
        from ..suite import world3d
        return _act_answer(world3d.act(c.cfg, c.gid, action, body_of(inp), c.who), where)
    return fn


def _world_dry(what: str, ids_of, states: tuple | None = None):
    def fn(c: Ctx, inp: dict) -> dict:
        items = _world_items(c)
        ids = ids_of(inp)
        missing = [i for i in ids if i not in items]
        if missing:
            return error("not_found", f"not on the world list: {', '.join(missing)}", "world.list shows the ids")
        rows = [{"id": i, "state": items[i]["state"], "hold": items[i]["hold"]} for i in ids]
        wrong = [r for r in rows if states and r["state"] not in states]
        return {"status": "dry_run", "would": f"{what}: {', '.join(ids)}", "files_written": 0, "things": rows,
                **({"note": "not in a state this applies to (the forge will say so): " + ", ".join(r["id"] for r in wrong)}
                   if wrong else {})}
    return fn


def _one(inp):
    return [str(inp.get("id") or "")]


def _many(inp):
    v = inp.get("ids") or ([inp["id"]] if inp.get("id") else [])
    return [str(i) for i in (v if isinstance(v, list) else [v])]


def _add_dry(c: Ctx, inp: dict) -> dict:
    from ..threed import world
    try:
        e = world.normalise(dict(inp.get("entry") or {}))
    except world.WorldError as ex:
        return error("invalid_input", str(ex), "fix the entry (world.list shows how others are written)")
    if e["id"] in _world_items(c):
        return error("conflict", f"{e['id']} is already on the world list", "choose another id, or world.make_again")
    return {"status": "dry_run", "would": f"add {e['id']} ({e['kind']}, {e['tier']}) to the world list", "files_written": 0,
            "entry": {k: e[k] for k in ("id", "kind", "tier", "words", "real_size_m", "hold")}}


OPS_WORLD = [
    ("world.add", "Add one thing to the world list; the world queue makes it in its turn.",
     {"entry": "required: {\"id\", \"kind\", \"tier\", \"words\", \"real_size_m\", …} — as the lists in wanted_3d/ are written"},
     "threed_world_add", lambda i: {"entry": i.get("entry")}, _add_dry),
    ("world.hold", "Hold a thing (the queue skips it) or take it off hold.",
     {"id": "required", "hold": "optional: true (default) or false"},
     "threed_world_hold", lambda i: {"id": i["id"], "hold": i.get("hold", True)}, _world_dry("hold / unhold", _one)),
    ("world.make_again", "Make a thing again from a fresh picture (the old folder is kept, renamed).", {"id": "required"},
     "threed_world_again", lambda i: {"id": i["id"]}, _world_dry("make again", _one)),
    ("world.try_again", "Failed things back in line, keeping what they had.", {"ids": "required: a list of ids"},
     "threed_world_try_again", lambda i: {"ids": _many(i)}, _world_dry("try again", _many, ("failed",))),
    ("world.straighten", "Turn a leaning model level.", {"id": "required"},
     "threed_world_straighten", lambda i: {"id": i["id"]}, _world_dry("straighten", _one, ("held", "made"))),
    ("world.place_again", "Place things again from the forge (tidied); nothing is remade.", {"ids": "required: a list"},
     "threed_world_place_again", lambda i: {"ids": _many(i)}, _world_dry("place again", _many)),
    ("world.match_and_release", "Release things held only for their colours, matched to the picture (an approval: Claude "
     "Fable only, while William's setting allows).", {"ids": "required: a list"},
     "threed_world_match_release", lambda i: {"ids": _many(i)}, _world_dry("match and release", _many, ("held",))),
    ("world.release_as_made", "Release things with their colours as made (an approval: Claude Fable only, while allowed).",
     {"ids": "required: a list"},
     "threed_world_as_made", lambda i: {"ids": _many(i)}, _world_dry("release as made", _many, ("held",))),
]
for _name, _doc, _inputs, _action, _body, _dry in OPS_WORLD:
    OPS[_name] = Op(_name, "change", _doc, _world_act(_action, _body), _inputs, _dry)


@op("world.redo_plan", "read", "What the daily redo would do now (Try again, Make again, releases, left alone, needs better "
    "words), changing nothing.")
def _redo_plan(c: Ctx, inp: dict) -> dict:
    from ..threed import redo
    p = redo.plan(c.cfg, c.gid)
    p.pop("hashes", None)
    p["release"] = {k: p["release"].get(k) for k in ("count", "lines", "left_lines")}
    return done(p)


# ------------------------------------------------------------------------------------------------ approvals (BUILD 78)
@op("approvals.plan", "read", "What 'Approve everything here' would do on a page, with the setting and the recent approvals.",
    {"page": "required: world | review"})
def _approvals_plan(c: Ctx, inp: dict) -> dict:
    from ..suite import approve_all
    if inp["page"] not in ("world", "review"):
        return error("invalid_input", "page is world or review", "approvals.plan with page world or review")
    p = approve_all.plan(c.cfg, c.gid, inp["page"])
    p["recent"] = (p.get("recent") or [])[:10]
    return done(p)


def _approvals_dry(c: Ctx, inp: dict) -> dict:
    from ..suite import approve_all
    if inp["page"] not in ("world", "review"):
        return error("invalid_input", "page is world or review", "approvals.all with page world or review")
    if not approve_all.may_approve(c.cfg, c.gid, c.who):
        return needs_approval(f"{c.who} may not approve here", "3D -> World list / Art -> Review & approve")
    p = approve_all.plan(c.cfg, c.gid, inp["page"])
    n = p["count"]
    if inp.get("ids"):   # Fable 2026-11-20: the dry run used to ignore `ids` and report the whole page
        want = set(str(i) for i in inp["ids"])
        if inp["page"] == "review":
            n = sum(1 for m in p.get("models") or [] if m in want)
        else:
            n = sum(1 for g in (p.get("groups") or {}).values() for i in g if i in want)
    return {"status": "dry_run", "would": f"approve {n} thing(s) on the {inp['page']} page", "files_written": 0,
            "lines": p.get("lines"), "left": p.get("left")}


@op("approvals.all", "change", "Approve everything here (BUILD 78) on a page, signed '<you>, for William'. Only Claude "
    "Fable, and only while William's setting allows it.", {"page": "required: world | review",
                                                            "ids": "optional: only these"}, dry=_approvals_dry)
def _approvals_all(c: Ctx, inp: dict) -> dict:
    from ..suite import approve_all
    try:
        if inp["page"] == "world":
            r = approve_all.world_approve_all(c.cfg, c.gid, c.who, inp.get("ids"))
        elif inp["page"] == "review":
            r = approve_all.review_approve_all(c.cfg, c.gid, c.who, ids=inp.get("ids"))
        else:
            return error("invalid_input", "page is world or review", "approvals.all with page world or review")
    except approve_all.ApproveRefused as ex:
        return refused(ex, "Settings -> Approvals")
    return done(r, "approvals.log shows them, each with its uid for approvals.undo")


@op("approvals.undo", "change", "Undo one thing an approval touched (by its uid from approvals.log).", {"uid": "required"})
def _approvals_undo(c: Ctx, inp: dict) -> dict:
    from ..suite import approve_all
    try:
        return done(approve_all.undo(c.cfg, c.gid, str(inp["uid"]), c.who))
    except approve_all.ApproveRefused as ex:
        return refused(ex, "Settings -> Approvals")


@op("approvals.log", "read", "The newest approvals first, each with whether it was undone.", {"limit": "optional (default 30)"})
def _approvals_log(c: Ctx, inp: dict) -> dict:
    from ..suite import approve_all
    return done(approve_all.history(c.cfg, c.gid, int(inp.get("limit") or 30)))


# ------------------------------------------------------------------------------------------------ deliver (Fable 2026-11-20)
DELIVER_BATCH = 40     # about half a gigabyte of models: a batch finishes well inside one call


def _deliver_input(inp: dict) -> tuple[list | None, int]:
    ids = inp.get("ids")
    if isinstance(ids, str):
        ids = [ids]
    lim = inp.get("limit")
    return (list(ids) if ids else None), (max(1, min(200, int(lim))) if lim else DELIVER_BATCH)


def _deliver_dry(c: Ctx, inp: dict) -> dict:
    from ..suite import threed, approve_all
    if not approve_all.may_approve(c.cfg, c.gid, c.who):
        return needs_approval(f"{c.who} may not deliver here", "Art -> Review & approve -> 3D models -> Deliver")
    ids, lim = _deliver_input(inp)
    p = threed.deliver(c.cfg, c.gid, c.who, dry=True, only=ids, limit=lim)
    return {"status": "dry_run", "would": f"deliver {len(p['plan'])} approved model(s) into the game"
            + (f" ({p['left_after']} more after this batch)" if p.get("left_after") else ""), "files_written": 0,
            "plan": [f"{x['what']} -> {x['dest']}" for x in p["plan"][:RESULT_LIMIT]], "game_reachable": p["game_reachable"]}


@op("models.deliver", "change", "Deliver approved 3D models into the game (Art -> Review & approve -> 3D models -> Deliver): "
    "each .glb, its motion sheet and its provenance copied in, what it replaces kept in out/_replaced/, each recorded in "
    "delivered.json. In batches (default 40 a call); call again until left_after is 0. Signed '<you>, for William' — Claude "
    "Fable only, while William's setting allows it.",
    {"ids": "optional: only these (\"prop/x\", a bare id, or a try id)", "limit": "optional: how many this call (default 40)"},
    dry=_deliver_dry)
def _models_deliver(c: Ctx, inp: dict) -> dict:
    from ..suite import threed
    ids, lim = _deliver_input(inp)
    try:
        r = threed.deliver(c.cfg, c.gid, c.who, dry=False, only=ids, limit=lim)
    except threed.ThreeDRefused as ex:
        return refused(ex, "Art -> Review & approve -> 3D models -> Deliver")
    nxt = "models.deliver again for the next batch" if r.get("left_after") else "the game loads them on its next start"
    return done({k: v for k, v in r.items() if k != "ok"}, nxt)


# ------------------------------------------------------------------------------------------------ places (BUILD 34)
def _place_files(c: Ctx) -> dict:
    from ..suite import places3d
    d = places3d.places_dir(c.cfg, c.gid)
    return {p.name[: -len(".place.json")]: p for p in sorted(d.glob("*.place.json"))} if d.is_dir() else {}


def _pictures_of_place(c: Ctx, pid: str) -> dict:
    from ..suite import places3d
    from ..threed import world
    d = places3d.pictures_dir(c.cfg, c.gid)
    looks = sorted((d / world.slug(pid)).glob("look_*.png")) if (d / world.slug(pid)).is_dir() else []
    plan = d / f"{world.slug(pid)}.png"
    return {"look_pictures": [c.rel(p) for p in looks], "plan_picture": c.rel(plan) if plan.exists() else None}


@op("places.list", "read", "The game's places (town plans that become 3D stages), with their pictures.")
def _places_list(c: Ctx, inp: dict) -> dict:
    rows = []
    for pid, p in _place_files(c).items():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        pics = _pictures_of_place(c, pid)
        rows.append({"id": pid, "name": d.get("name") or d.get("title"), "file": c.rel(p),
                     "look_pictures": len(pics["look_pictures"]), "plan_picture": pics["plan_picture"]})
    return done({"places": rows, "count": len(rows)})


@op("places.show", "read", "One place: its plan file, its things on the world list and their states, its pictures.",
    {"place": "required: the place id"})
def _places_show(c: Ctx, inp: dict) -> dict:
    from ..suite import places3d
    from ..threed import world
    files = _place_files(c)
    pid = str(inp["place"])
    if pid not in files:
        return error("not_found", f"no place {pid!r}", "places.list shows the ids")
    d = json.loads(files[pid].read_text(encoding="utf-8"))
    things = places3d.entries_for(world.status(c.cfg, c.gid), pid)
    return done({"id": pid, "name": d.get("name") or d.get("title"), "file": c.rel(files[pid]),
                 "plan_keys": sorted(d)[:40], "things": things[:RESULT_LIMIT], "thing_count": len(things),
                 **_pictures_of_place(c, pid),
                 "area_check": "areas.check runs the checks built so far (delivered, people)"})


def _place_dry(what):
    def fn(c: Ctx, inp: dict) -> dict:
        if str(inp["place"]) not in _place_files(c):
            return error("not_found", f"no place {inp['place']!r}", "places.list shows the ids")
        return {"status": "dry_run", "would": f"{what} {inp['place']}", "files_written": 0}
    return fn


@op("places.compile", "change", "Compile a place's plan into its stage and put its things on the world list, held (it starts "
    "no generation).", {"place": "required"}, dry=_place_dry("compile"))
def _places_compile(c: Ctx, inp: dict) -> dict:
    from ..suite import places3d
    return _act_answer(places3d.act(c.cfg, c.gid, "threed_places_compile", {"place": inp["place"]}, c.who), "3D -> Places")


@op("places.take_pictures", "change", "Take the game's own pictures of a place, one a look (runs the game's still mode in the "
    "background; it uses the graphics card briefly).", {"place": "required", "looks": "optional: a list of look ids"},
    dry=_place_dry("take the look pictures of"))
def _places_pictures(c: Ctx, inp: dict) -> dict:
    from ..suite import places3d
    return _act_answer(places3d.act(c.cfg, c.gid, "threed_places_pictures", {"place": inp["place"], "looks": inp.get("looks")},
                                    c.who), "3D -> Places")


@op("areas.check", "read", "Check an area (BUILD 83 Part B): delivered (no stand-ins left) and its people described so far; "
    "the other checks say 'not built yet'. Writes only its report (out/areas/<game>/<place>/report.md).",
    {"place": "required"})
def _areas_check(c: Ctx, inp: dict) -> dict:
    from ..threed import areacheck
    if str(inp["place"]) not in _place_files(c):
        return error("not_found", f"no place {inp['place']!r}", "places.list shows the ids")
    rep = areacheck.check(c.cfg, c.gid, str(inp["place"]))
    rep["report"] = c.rel(rep["report"]) if rep.get("report") else None
    return done(rep, "Part C (Fable's review and approval) is not built yet")


# ------------------------------------------------------------------------------------------------ requests and the Mail
@op("provide.list", "read", "'User Needs To Provide Image': what the forge can't make and has asked William for.")
def _provide_list(c: Ctx, inp: dict) -> dict:
    from ..suite import provide
    return done(provide.load(c.cfg, c.gid))


@op("provide.add", "change", "Ask William for a picture the forge can't make (it shows in 'User Needs To Provide Image').",
    {"title": "required", "why": "required: why the forge can't make it", "helps": "required: what would help",
     "kind": "optional: image (default) …", "count": "optional", "priority": "optional: soon (default) …"})
def _provide_add(c: Ctx, inp: dict) -> dict:
    from ..suite import provide
    try:
        r = provide.add(c.cfg, c.gid, c.who, inp["title"], inp["why"], inp["helps"], kind=inp.get("kind") or "image",
                        count=int(inp.get("count") or 1), priority=inp.get("priority") or "soon")
    except provide.ProvideRefused as ex:
        return refused(ex, "Art -> User Needs To Provide Image")
    return done(r)


def _game_root(c: Ctx):
    from ..suite import games
    root = games.game_root(c.cfg, c.gid)
    if not root or not Path(root).is_dir():
        raise FileNotFoundError(f"the game folder for {c.gid} is not set on this computer (Settings -> This computer)")
    return Path(root)


@op("mail.inbox", "read", "Your letters (the Workbench's Mail) — what William and the other Claudes wrote to you.",
    {"box": "optional: inbox (default) | sent | archive", "find": "optional: words"}, needs_who=True)
def _mail_inbox(c: Ctx, inp: dict) -> dict:
    from ..suite import mail
    try:
        return done(mail.box(_game_root(c), c.who, inp.get("box") or "inbox", inp.get("find"))[:RESULT_LIMIT])
    except FileNotFoundError as ex:
        return error("not_found", str(ex), "tell William")


@op("mail.to_bill", "change", "Write a letter to William through the Mail (it shows in Story -> Mail).",
    {"subject": "required", "body": "required: markdown", "questions": "optional: a list of questions he answers in the Mail"})
def _mail_to_bill(c: Ctx, inp: dict) -> dict:
    from ..suite import mail
    try:
        l = mail.send(_game_root(c), c.who, "Bill", inp["subject"], inp["body"], questions=inp.get("questions"))
    except FileNotFoundError as ex:
        return error("not_found", str(ex), "tell William")
    except Exception as ex:  # noqa: BLE001 — the rulings book refuses a question already ruled; its words go back
        if type(ex).__name__ == "AlreadyRuled":
            return refused(f"a question is already ruled on: {ex}", "Story -> Mail")
        raise
    return done({"letter": getattr(l, "id", None) or str(l)[:80], "to": "Bill"})


# ------------------------------------------------------------------------------------------------ song review
@op("music.review", "read", "Review Suno sheets against William's rules and standard: the style box and the lyrics box (an "
    "instrumental's tags), voice locks against the singers' profiles, not generic, complex enough. With style/lyrics in the "
    "input it reviews that one draft — do it before a draft goes into a sheet or to Suno; 'ready' is the only verdict that "
    "may go. With no draft it reviews every sheet the game lists and writes the report. It never changes a word.",
    {"style": "optional: a draft's style box", "lyrics": "optional: its lyrics box (an instrumental's tags)",
     "title": "optional: its title (checked against every title on file)", "singers": "optional: a list of who sings",
     "instrumental": "optional: true / false (else guessed from the lyrics box)",
     "file": "optional: one sheet file or folder under the game folder, instead of all of them"})
def _music_review(c: Ctx, inp: dict) -> dict:
    from .. import song_review as sr
    from ..suite import games
    st = sr.game_settings(c.cfg, c.gid)
    rules = {**sr.RULES, **(st.get("rules") or {})}
    try:
        root = games.game_root(c.cfg, c.gid)
    except Exception:  # noqa: BLE001 — a game with no settings file: a draft is still reviewed, without profiles
        root = None
    if inp.get("style") or inp.get("lyrics"):
        prof = sr.load_profiles(Path(root) / (st.get("styles_dir") or "music/styles")) if root else {}
        s = sr.song(inp.get("title") or "", inp.get("style") or "", inp.get("lyrics") or "",
                    instrumental=inp.get("instrumental"), singers=inp.get("singers") or [], source="draft")
        r = sr.review(s, prof, rules)
        if root and s["title"]:
            existing, _ = sr.collect([Path(root) / x for x in st.get("sources") or []], all_status=True, rules=rules)
            same = [e["source"] for e in existing if e["title"].strip().lower() == s["title"].strip().lower()]
            if same:
                r["findings"].append({"level": "fail", "check": "title reused", "message": f"'{s['title']}' is already {same[0]}",
                                      "fix": "a new sheet gets a new title"})
                r["verdict"] = "fails"
        return done(r, "fix what it names and review again; only 'ready' goes to Suno")
    files = None
    if inp.get("file"):
        if not root:
            return error("not_found", "the game folder is not set on this computer", "tell William")
        files = [str(Path(root) / str(inp["file"]))]
    r = sr.run(c.cfg, c.gid, files)
    if not r["sources"]:
        return error("not_found", f"no sheets listed for {c.gid} (games/{c.gid}/song_review.json)", "give input.file")
    probs = [{"title": x["title"], "verdict": x["verdict"], "score": x["score"], "source": x["source"],
              "top": [f["check"] + ": " + f["message"] for f in x["findings"] if f["level"] != "info"][:3]}
             for x in sorted(r["results"], key=lambda x: x["score"]) if x["verdict"] != "ready"]
    return done({"report": c.rel(r["report"]), "counts": r["counts"], "problems": probs[:40], "problems_total": len(probs),
                 "not_reviewed": len(r["skipped"])}, "forge_pictures can't show a report; read it with the path, or ask William")


# ------------------------------------------------------------------------------------------------ the never-stop launcher
@op("clock.status", "read", "The never-stop launcher (art_around_the_clock.bat): running?, its last daily redo, restarts.")
def _clock_status(c: Ctx, inp: dict) -> dict:
    from ..threed import world
    p = world.world_dir(c.cfg, c.gid) / "_around_the_clock.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    if d:
        d["alive"] = d.get("step") != "stopped" and time.time() - float(d.get("beat") or 0) < 120
    return done({"heartbeat": d or None, "world_queue": world.launcher_state(c.cfg, c.gid),
                 "note": None if d else "never started: William double-clicks art_around_the_clock.bat"})


# ------------------------------------------------------------------------------------------------ safe retries
def _keys_path(c: Ctx) -> Path:
    return c.root / "local" / "mcp" / "keys.json"


def _read_keys(c: Ctx) -> dict:
    p = _keys_path(c)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def _write_keys(c: Ctx, d: dict) -> None:
    cut = time.time() - KEY_KEEP_DAYS * 86400
    d = {k: v for k, v in d.items() if float(v.get("at") or 0) >= cut}
    p = _keys_path(c)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, p)


def _with_key(c: Ctx, key: str, name: str, inp: dict, run) -> dict:
    h = hashlib.sha1(json.dumps({"op": name, "input": inp, "game": c.gid}, sort_keys=True, default=str).encode()).hexdigest()[:16]
    keys = _read_keys(c)
    rec = keys.get(key)
    if rec:
        if rec.get("hash") != h:
            return error("conflict", f"idempotency_key {key!r} was used for a different call ({rec.get('op')})",
                         "use a new key for a new call")
        if rec.get("state") == "done":
            return {**rec["answer"], "repeat": True, "note": "already done with this key — nothing was done again"}
        if time.time() - float(rec.get("at") or 0) < KEY_IN_PROGRESS_FOR:
            return error("in_progress", f"a call with key {key!r} is still working", "forge_status in a minute, then try again")
        return error("outcome_unknown", f"a call with key {key!r} started at {datetime.fromtimestamp(rec['at']):%H:%M} "
                     "and never finished", "look (jobs.list / world.list / approvals.log) before trying again with a new key")
    keys[key] = {"op": name, "hash": h, "at": time.time(), "state": "in progress", "who": c.who}
    _write_keys(c, keys)
    ans = run()
    keys = _read_keys(c)
    keys[key] = {"op": name, "hash": h, "at": time.time(), "state": "done", "who": c.who, "answer": ans}
    _write_keys(c, keys)
    return ans


# ------------------------------------------------------------------------------------------------ more operations
def _load_more_ops() -> None:
    """Operations kept in their own files beside this one (forge/mcpserver/ops_*.py; BUILD 98 Part 12). Each has
    install(ns) and registers through this module's own @op, so it works whether this runs as a module or as __main__.
    A file that fails to load is logged and skipped: the other operations still answer."""
    import importlib
    here = Path(__file__).resolve().parent
    me = sys.modules[__name__]
    for f in sorted(here.glob("ops_*.py")):
        try:
            mod = importlib.import_module(f"forge.mcpserver.{f.stem}")
            mod.install(me)
        except Exception:  # noqa: BLE001
            log.exception("mcp: could not load the operations in %s", f.name)


_load_more_ops()


# ------------------------------------------------------------------------------------------------ one request
def handle(req: dict, cfg: dict | None = None) -> dict:
    name = str(req.get("op") or "")
    o = OPS.get(name)
    if not o:
        return error("invalid_input", f"no operation {name!r}", "forge_search lists them, with their exact input")
    inp = req.get("input") or {}
    if not isinstance(inp, dict):
        return error("invalid_input", "input must be an object", "pass input as {\"field\": value}")
    cfg = cfg or cfgmod.load()
    gid = str(inp.get("game") or req.get("game") or cfgmod.default_game(cfg))
    who = str(req.get("who") or "").strip()
    if o.needs_who and not who.lower().startswith("claude"):
        return error("invalid_input", "say who you are: who = your own name as you sign it, e.g. \"Claude Fable\" or "
                     "\"Claude Opus\" (this connector is for Claude; William uses the Workbench)", "call again with who")
    missing = [f for f in o.required if inp.get(f) in (None, "", [])]
    if missing:
        return error("invalid_input", f"{name} needs {', '.join(missing)}", f"forge_search \"{name}\" shows its input")
    c = Ctx(cfg, gid, who)
    t0 = time.time()
    try:
        if req.get("dry_run") and o.kind == "change":
            ans = o.dry(c, inp) if o.dry else {"status": "dry_run", "would": f"{name} with {json.dumps(inp)[:300]}",
                                                "files_written": 0}
        elif o.kind == "change" and req.get("key"):
            ans = _with_key(c, str(req["key"]), name, inp, lambda: o.fn(c, inp))
        else:
            ans = o.fn(c, inp)
    except Exception as ex:  # noqa: BLE001 — every failure is an answer, never a broken pipe
        log.exception("mcp: %s failed", name)
        from ..threed import world
        if isinstance(ex, world.WorldError):
            ans = refused(ex)
        else:
            ans = error("internal", f"{type(ex).__name__}: {ex}", "logs/forge_<date>.log has the whole of it; tell William "
                        "if it repeats")
    log.info("mcp: %s %s by %s (%s, %.1f s)%s", name, "dry run" if req.get("dry_run") else "", who or "-", ans.get("status"),
             time.time() - t0, f" key {req.get('key')}" if req.get("key") else "")
    return ans


def main() -> int:
    real_out = sys.stdout
    sys.stdout = sys.stderr                  # every print in the forge's own functions goes to stderr, never into the answer
    try:
        from .. import log as logmod
        cfg = cfgmod.load()
        cfgmod.ensure_dirs(cfg)
        logmod.setup(cfgmod.path_of(cfg, "logs"))
        req = json.loads(sys.stdin.read() or "{}")
        ans = handle(req, cfg)
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        ans = error("internal", f"{type(ex).__name__}: {ex}", "logs/forge_<date>.log; tell William if it repeats")
    real_out.write(json.dumps(ans, default=str, ensure_ascii=False) + "\n")
    real_out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
