"""Art production in the suite (BUILD 12 — spec §6 screens 3 and 4): the Wanted board, and Review & approve → Deliver.

    board(cfg, game)                       every wanted item with where it stands — missing · stand-in · drafted ·
                                           queued · rendered · approved · delivered — and its town, era, state, fate,
                                           look words, kind, size, and its place in the story order
    plan_selection(cfg, game, names)       the plan's jobs for a selection: GPU hours, disk against free space and the
                                           guard, and what refuses (placeholder blocks, named) — nothing queued
    queue_selection(cfg, game, names, who) produce.queue(names=…) — the same refusals; queues only on a clean plan
    review(cfg, game, state)               finished pictures waiting for a verdict (made for a wanted item, not yet
                                           approved), then the newest of the rest
    job_view(cfg, game, jid, state)        one picture: its files, prompt, seed, licence line, kit check, candidates
    approve(…), redo(…), send_out(…)       approve (held for delivery — the licence gate runs now; a kit as a set),
                                           a redo draft with a note (never queued), a hand-out folder for an outside tool
    deliver(cfg, game, dry, fit, who)      deliver.run — the dry-run list first, then the copy, the ledger, nothing deleted

Every one calls the forge's own functions (night4/produce, night4/deliver, manifest, kitcheck, feedback, handoff) —
the same ones the .bat files use — and every write is signed in the game's journal.
"""
from __future__ import annotations
import hashlib, json, os
from pathlib import Path

from .. import config as cfgmod
from ..log import get
from . import journal

log = get("suite")
STATES = ("missing", "stand-in", "drafted", "queued", "rendered", "approved", "delivered")
_done: dict[str, dict[str, tuple | None]] = {}


class ProductionRefused(ValueError):
    pass


def _game_root(cfg: dict, game: str) -> Path | None:
    from . import games
    try:
        r = games.game_root(cfg, game)
        return r if r and r.is_dir() else None
    except Exception:  # noqa: BLE001
        return None


def _sign(cfg: dict, game: str, who: str | None, kind: str, obj: str, **kw) -> None:
    root = _game_root(cfg, game)
    if not who or root is None:
        return
    try:
        journal.append(root, who, kind, obj, **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("production: journal line not written (%s)", e)


def _need(who: str | None, what: str) -> None:
    if not who:
        raise ProductionRefused(f"set who you are first (top right) — {what} is signed")


# ------------------------------------------------------------------ what exists for each wanted item
def _wanted_of(j: dict) -> list[str]:
    w = j.get("_wanted") or (j.get("meta") or {}).get("wanted")
    if isinstance(w, str):
        return [w]
    if isinstance(w, list):
        return [x for x in w if isinstance(x, str)]
    if j.get("batch") and j.get("name"):
        return [f"@{j['batch']}/{j['name']}"]
    return []


def done_by_wanted(cfg: dict) -> dict[str, list[str]]:
    """{wanted name: [finished job ids, oldest first]} — the rule produce.done_index uses, each done file read once."""
    d = cfgmod.path_of(cfg, "jobs") / "done"
    seen = _done.setdefault(str(d), {})
    try:
        entries = sorted((e.name, e.stat().st_mtime) for e in os.scandir(d) if e.name.endswith(".json"))
    except OSError:
        return {}
    for name, _mt in entries:
        if name in seen:
            continue
        try:
            j = json.loads((d / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        seen[name] = None if j.get("tombstone") else (j["id"], tuple(_wanted_of(j)))
    out: dict[str, list[str]] = {}
    for name, _mt in sorted(entries, key=lambda e: e[1]):
        v = seen.get(name)
        if v:
            for w in v[1]:
                out.setdefault(w, []).append(v[0])
    return out


_queued: dict[str, tuple[float, list]] = {}


def in_queue(cfg: dict) -> dict[str, dict]:
    """{wanted name: {"id", "state"}} for jobs waiting, running or paused (a folder is read again only when it changed —
    a night's bake-off can leave thousands of files waiting)."""
    out = {}
    jobs = cfgmod.path_of(cfg, "jobs")
    for st in ("running", "pending", "paused"):
        d = jobs / st
        try:
            mt = d.stat().st_mtime_ns
        except OSError:
            continue
        hit = _queued.get(str(d))
        if not hit or hit[0] != mt:
            found = []
            for p in d.glob("*.json"):
                try:
                    j = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                for w in _wanted_of(j):
                    found.append((w, j.get("id")))
            hit = (mt, found)
            _queued[str(d)] = hit
        for w, jid in hit[1]:
            out.setdefault(w, {"id": jid, "state": st})
    return out


def _plan_file(cfg: dict, game: str) -> Path:
    return cfgmod.path_of(cfg, "games") / game / "batches" / "produce_plan.json"


def load_plan(cfg: dict, game: str) -> dict | None:
    p = _plan_file(cfg, game)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def board(cfg: dict, game: str) -> dict:
    from .. import manifest
    from ..night4 import deliver as dl, produce
    try:
        wanted = manifest.load_wanted(cfg, game)
    except Exception as e:  # noqa: BLE001
        return {"items": [], "error": f"no wanted list for this game yet ({e}) — Plan reads it from the game", "counts": {}}
    items = wanted.get("items") or {}
    base = produce.item_states(cfg, game, wanted)
    held = dl.held(cfg, game)
    approved = manifest.load_approved(cfg, game)
    made = done_by_wanted(cfg)
    queued = in_queue(cfg)
    plan = load_plan(cfg, game) or {}
    planned: dict[str, dict] = {}
    for j in plan.get("jobs") or []:
        for w in produce.wanted_of(j):
            planned.setdefault(w, {"type": j.get("type"), "lane": str(j.get("batch", "")).split("/")[-1],
                                   "why": j.get("_why"), "job": j.get("name")})
    waiting = {w["name"]: w for w in plan.get("_waiting") or []}
    by_hand = {b["name"]: b for b in plan.get("_by_hand") or []}
    first, story = produce._order(cfg, game)
    rank = {m: i for i, m in enumerate(first)}
    rank.update({m: 100 + i for i, m in enumerate(story) if m not in rank})
    rows, counts = [], {}
    root = _game_root(cfg, game)
    for name, w in sorted(items.items()):
        if w.get("set_of"):
            continue                                          # a kit's slot travels with its painting
        st = base.get(name, {}).get("state") or "missing"
        led = (base.get(name) or {}).get("delivery")
        if st == "stale" and led and root is not None and w.get("path"):
            # wanted.json still holds the stand-in's hash until the next export; the game's file itself says
            f = Path(root) / w["path"]
            try:
                if f.is_file() and hashlib.sha1(f.read_bytes()).hexdigest()[:16] == led.get("sha1"):
                    st = "delivered"
            except OSError:
                pass
        if st == "delivered":
            state = "delivered"
        elif name in held or name in approved:
            state = "approved"
        elif name in queued:
            state = "queued"
        elif made.get(name):
            state = "rendered"
        elif name in planned:
            state = "drafted"
        else:
            state = "stand-in" if st in ("stand-in", "stale") else "missing"
        mid = name.split("/", 1)[1] if "/" in name else name
        r = rank.get(mid)
        rows.append({"name": name, "kind": w.get("kind") or "other", "state": state, "town": w.get("town"),
                     "era": w.get("era"), "map_state": w.get("map_state"), "fate": w.get("fate"), "look": w.get("look"),
                     "target_size": w.get("target_size"), "path": w.get("path"), "label": w.get("name_in_game") or w.get("title"),
                     "notes": w.get("notes") or w.get("description"), "rank": r,
                     "first_hour": mid in first, "planned": planned.get(name), "waiting": waiting.get(name),
                     "by_hand": bool(by_hand.get(name)), "jobs": (made.get(name) or [])[-3:], "queued": queued.get(name),
                     "held": bool(held.get(name))})
        counts[state] = counts.get(state, 0) + 1
    est = plan.get("_estimate") or {}
    return {"items": rows, "counts": counts, "states": list(STATES),
            "plan": {"made": plan.get("_made"), "jobs": len(plan.get("jobs") or []), "estimate": est,
                     "waiting": len(plan.get("_waiting") or []), "by_hand": len(plan.get("_by_hand") or [])} if plan else None,
            "exported": wanted.get("exported"), "game_root_reachable": _game_root(cfg, game) is not None,
            "guard_gb": float(cfg.get("disk_guard_gb", 40))}


# ------------------------------------------------------------------ plan and queue a selection
def make_plan(cfg: dict, game: str, who: str | None) -> dict:
    """produce.plan — reads the game again (wanted.json refreshed when the game folder is reachable), drafts one job
    per missing item, writes batches/produce_plan.json. Nothing is queued."""
    from ..night4 import produce
    p = produce.plan(cfg, game)
    est = p["_estimate"]
    _sign(cfg, game, who, "queue", "produce plan", link=f"games/{game}/batches/produce_plan.md",
          note=f"planned {est['jobs']} job(s): about {est['gpu_hours']} GPU hours, {est['disk_gb']} GB")
    return {"ok": True, "message": f"Planned {est['jobs']} job(s) — about {est['gpu_hours']} GPU hours and {est['disk_gb']} GB. "
                                   "Nothing is queued.", "estimate": est, "new_blocks": p.get("_new_blocks") or []}


def plan_selection(cfg: dict, game: str, names: list[str]) -> dict:
    from ..night4 import produce
    names = [str(n) for n in names or []]
    if not names:
        raise ProductionRefused("select something on the board first")
    plan = load_plan(cfg, game)
    if plan is None:
        return {"ok": False, "no_plan": True, "message": "There is no plan yet — Plan reads the game and drafts the jobs first."}
    jobs = produce.select(plan.get("jobs") or [], names=names)
    covered = {w for j in jobs for w in produce.wanted_of(j)}
    waiting = {w["name"]: w for w in plan.get("_waiting") or []}
    by_hand = {b["name"]: b for b in plan.get("_by_hand") or []}
    rendered = {r["name"]: r for r in plan.get("_rendered") or []}
    left = []
    for n in names:
        if n in covered:
            continue
        if n in by_hand:
            left.append({"name": n, "why": "yours to draw — Sprite intake takes it in"})
        elif n in waiting:
            left.append({"name": n, "why": f"{waiting[n]['why']}; waits on {waiting[n]['waits_on']}"})
        elif n in rendered:
            left.append({"name": n, "why": "rendered already — approve one in Review & approve"})
        else:
            left.append({"name": n, "why": "not in the plan (delivered, or no draft for its kind) — Plan again if the game changed"})
    est = produce.estimate(cfg, jobs) if jobs else {"jobs": 0, "gpu_hours": 0.0, "disk_gb": 0.0, "free_gb": None, "basis": {}}
    bad = produce.blockers(cfg, game, jobs) if jobs else {}
    guard = float(cfg.get("disk_guard_gb", 40))
    disk_ok = est.get("free_gb") is None or (est["free_gb"] - est["disk_gb"] >= guard)
    return {"ok": True, "jobs": [{"name": j.get("name"), "type": j.get("type"), "lane": str(j.get("batch", "")).split("/")[-1],
                                  "town": (j.get("meta") or {}).get("town"), "why": j.get("_why"),
                                  "makes": produce.wanted_of(j)} for j in jobs],
            "estimate": est, "guard_gb": guard, "disk_ok": disk_ok, "left_out": left,
            "blockers": [{"problem": k, "jobs": v} for k, v in sorted(bad.items())],
            "can_queue": bool(jobs) and not bad and disk_ok, "plan_made": plan.get("_made")}


def queue_selection(cfg: dict, game: str, names: list[str], who: str | None) -> dict:
    from ..night4 import produce
    _need(who, "a queued selection")
    r = produce.queue(cfg, game, names=[str(n) for n in names or []])
    if r.get("refused"):
        return {"ok": False, "message": "Not queued — " + "; ".join(r["refused"]), "refused": r["refused"]}
    if not r.get("queued"):
        return {"ok": False, "message": r.get("note") or f"Nothing was queued (submit returned {r.get('rc')}).", "result": r}
    est = r.get("estimate") or {}
    _sign(cfg, game, who, "queue", "produce queue", link=r.get("file"),
          note=f"queued {r['queued']} job(s) for {len(names)} wanted item(s) — about {est.get('gpu_hours')} GPU hours")
    return {"ok": True, "message": f"Queued {r['queued']} job(s) behind what's already waiting — about "
                                   f"{est.get('gpu_hours')} GPU hours. The worker takes them in its own time.", "result": r}


def town_sheet(cfg: dict, game: str, town: str | None, who: str | None) -> dict:
    """reviews.town_sheet (every painting of one town — does it hold together?) or, with no town, reviews.atlas_sheet
    (one painting per town side by side — do they differ?). The same sheets as review --town / --atlas."""
    from ..night4 import reviews
    try:
        paths, n = reviews.town_sheet(cfg, town) if town else reviews.atlas_sheet(cfg)
    except ValueError as e:
        return {"ok": False, "message": f"Nothing to put on it yet: {e}."}
    out = cfgmod.path_of(cfg, "out")
    urls = ["/out/" + str(p.resolve().relative_to(out.resolve())).replace("\\", "/") for p in paths]
    _sign(cfg, game, who, "art", f"review · {'town ' + town if town else 'atlas'}", link=urls[0][1:] if urls else None,
          note=f"made the {'town' if town else 'atlas'} sheet — {n} painting(s)")
    return {"ok": True, "message": f"{n} painting(s) on {len(paths)} page(s).", "sheets": urls}


# ------------------------------------------------------------------ review
def _picture_files(out: Path) -> list[str]:
    if not out.is_dir():
        return []
    skip = ("raw", "control", "mask", "check", "numbers")
    return sorted(p.name for p in out.glob("*.png") if not p.name.startswith(skip))


def review(cfg: dict, game: str, state, limit: int = 40) -> dict:
    """Pictures waiting for a verdict (made for one of this game's wanted items, not approved or delivered yet), newest
    first; then the newest finished pictures that name no wanted item."""
    from .. import manifest
    from ..night4 import deliver as dl
    try:
        items = manifest.load_wanted(cfg, game).get("items") or {}
    except Exception:  # noqa: BLE001
        items = {}
    approved = manifest.load_approved(cfg, game)
    held = dl.held(cfg, game)
    live = dl.live(cfg, game)
    done = sorted(state.folder("done"), key=lambda j: j["_mtime"], reverse=True)
    waiting, other, decided = [], [], []
    for j in done:
        if j.get("game") and j.get("game") != game:
            continue
        ws = [w for w in _wanted_of(j) if w in items]
        rec = {"id": j["id"], "type": j.get("type"), "name": j.get("name"), "batch": j.get("batch"),
               "image": state.image_for(j), "licence": state.licence_of(j), "check": state.check_of(j),
               "finished": j.get("finished_at"), "wanted": ws[0] if ws else None,
               "set": bool((j.get("result") or {}).get("slots"))}
        if ws:
            w = ws[0]
            verdict = ("delivered" if (live.get(w) or {}).get("job_id") == j["id"] else
                       "approved" if (approved.get(w) or {}).get("job_id") == j["id"] or (held.get(w) or {}).get("job_id") == j["id"]
                       else None)
            rec["verdict"] = verdict
            if not verdict and len(waiting) < limit:
                waiting.append(rec)
            elif verdict and len(decided) < 24:
                decided.append(rec)                   # approved or in the game — still open to a mark-up
        elif len(other) < 24:
            other.append(rec)
    return {"waiting": waiting, "decided": decided, "recent": other, "deliver": deliver_list(cfg, game)}


def job_view(cfg: dict, game: str, jid: str, state) -> dict:
    from .. import manifest
    j = state.job(jid)
    if j is None:
        raise ProductionRefused(f"no job {jid}")
    out = cfgmod.path_of(cfg, "out") / jid
    prov = {}
    try:
        prov = json.loads((out / "prov.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    chain, ok, read = [], None, []
    try:
        from ..jobs.common import Context, licence_chain
        parts, read = manifest.collect_models(cfg, out)
        if parts:
            chain, ok = licence_chain(Context(cfg=cfg, root=cfgmod.ROOT), parts)
    except Exception as e:  # noqa: BLE001
        chain = [{"file": "?", "license": f"could not read the licence chain: {e}", "commercial_ok": None}]
    seen, uniq = set(), []
    for c in chain:
        if c.get("file") not in seen:
            seen.add(c.get("file"))
            uniq.append({k: c.get(k) for k in ("role", "file", "license", "commercial_ok")})
    check = None
    try:
        check = json.loads((out / "check.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    ws = _wanted_of(j)
    wanted = None
    try:
        items = manifest.load_wanted(cfg, game).get("items") or {}
        wanted = next((w for w in ws if w in items), None)
        target = (items.get(wanted) or {}).get("target_size") if wanted else None
    except Exception:  # noqa: BLE001
        items, target = {}, None
    others = [x for x in done_by_wanted(cfg).get(wanted, []) if x != jid][-6:] if wanted else []
    from PIL import Image
    files = []
    for f in _picture_files(out):
        try:
            with Image.open(out / f) as im:
                size = list(im.size)
        except OSError:
            size = None
        files.append({"file": f, "url": f"/out/{jid}/{f}", "size": size})
    return {"id": jid, "type": j.get("type"), "name": j.get("name"), "batch": j.get("batch"), "finished": j.get("finished_at"),
            "prompt": j.get("prompt") or prov.get("prompt"), "negative": j.get("negative") or prov.get("negative"),
            "seed": j.get("seed") if j.get("seed") not in (None, -1) else prov.get("seed"),
            "checkpoint": prov.get("checkpoint") or j.get("checkpoint"), "files": files, "licences": uniq,
            "commercial_ok": ok, "kit_check": check, "set": bool((j.get("result") or {}).get("slots") or prov.get("set")),
            "wanted": wanted, "target_size": target, "candidates": others, "comment": j.get("comment"),
            "meta": j.get("meta") or {}, "read_prov": [str(p) for p in read][:6]}


def approve(cfg: dict, game: str, jid: str, wanted: str, who: str | None, as_set: bool = False, pick: int | None = None,
            dry: bool = True) -> dict:
    """A single picture is *held*: deliver.hold runs approve's licence gate and size check now and records the
    approval; Deliver copies it into the game. A kit is approved as a set (manifest.approve_set: the kit check first,
    all six files or none) — its dry run shows the table, the confirmed run copies."""
    from .. import manifest
    from ..night4 import deliver as dl
    if not wanted:
        raise ProductionRefused("choose which wanted item this picture is for")
    if not dry:
        _need(who, "an approval")
    from . import settings
    if who and settings.is_assistant(who) and not dry:
        raise ProductionRefused("an assistant can't approve a picture — approved means the person's")
    try:
        if as_set:
            from .. import kitcheck
            kd = cfgmod.path_of(cfg, "out") / jid
            chk = kitcheck.check(cfg, kd, wanted.split("/")[-1])
            fails = [l for l in chk["lines"] if l["status"] == "fail"]
            if fails:
                return {"ok": False, "message": "The kit check failed: " + "; ".join(f"{l['check']} — {l['message']}" for l in fails),
                        "check": chk}
            plan = manifest.approve_set(cfg, jid, wanted, game, dry_run=dry)
            rows = [{"what": r["slot"], "file": Path(r["file"]).name, "dest": r["dest"], "size": r["size"],
                     "target": r.get("target_size")} for r in plan["rows"]]
            if dry:
                return {"ok": True, "dry": True, "rows": rows, "licences": plan.get("licences"),
                        "message": "The set is ready to copy into the game — check the table, then confirm."}
            _sign(cfg, game, who, "approve", wanted, link=f"out/{jid}", note=f"approved the kit {jid} as a set — copied into the game")
            return {"ok": True, "rows": rows, "message": f"Approved — the set is in the game as {wanted}."}
        if dry:
            plan = manifest.approve(cfg, jid, wanted, game, pick=pick, dry_run=True)
            return {"ok": True, "dry": True, "licences": plan.get("licences"), "size": plan.get("size"),
                    "target": plan.get("target_size"), "note": plan.get("size_note"), "dest": plan.get("dest"),
                    "file": Path(plan["file"]).name,
                    "message": "Approve holds it for delivery: the licence check passes now; Deliver copies it into the game."}
        h = dl.hold(cfg, jid, wanted, game, pick=pick)
    except manifest.ApproveError as e:
        return {"ok": False, "message": str(e)}
    _sign(cfg, game, who, "approve", wanted, link=f"out/{jid}", note=f"approved {jid} ({Path(h['file']).name}) — held for delivery")
    return {"ok": True, "message": f"Approved — {wanted} is held for delivery. Deliver copies it into the game.", "held": h}


def redo(cfg: dict, game: str, jid: str, note: str, who: str | None, state) -> dict:
    """feedback.draft_redo — a redo draft in jobs/drafts/ with a new seed and the note attached (never queued; the
    dashboard's Called out lists it with Approve draft / Dismiss)."""
    from ..night4 import feedback
    _need(who, "a redo note")
    note = str(note or "").strip()
    if not note:
        raise ProductionRefused("say what to change — the note goes with the redo")
    j = state.job(jid)
    if j is None:
        raise ProductionRefused(f"no job {jid}")
    wanted = (_wanted_of(j) or [j.get("name") or jid])[0]
    paths = feedback.draft_redo(cfg, j, note, wanted, {"note": note, "tester": who, "from": "suite review"})
    _sign(cfg, game, who, "draft", wanted, link=f"jobs/drafts/{paths[0].name}", note=f"redo of {jid}: {note}")
    return {"ok": True, "message": f"A redo draft with your note is in jobs/drafts ({len(paths)} file(s)) — it's under "
                                   "Called out in Queue & pictures; nothing is queued until someone approves the draft.",
            "drafts": [p.name for p in paths]}


def send_out(cfg: dict, game: str, jid: str, who: str | None, tool: str | None = None) -> dict:
    from .. import handoff as ho
    _need(who, "a hand-out")
    import re
    from datetime import datetime
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{jid.split('-', 2)[-1][:40]}_{datetime.now():%m%d_%H%M%S}").strip("_")
    try:
        man = ho.hand_out(cfg, [jid], to=tool or None, name=None if tool else name)
    except ho.HandoffError as e:
        return {"ok": False, "message": str(e)}
    _sign(cfg, game, who, "queue", f"hand-out {man['name']}", link=man["in"],
          note=f"handed {jid} out to an outside tool — edit in {man['in']}, save into {man['done']}")
    return {"ok": True, "message": f"Handed out. Open {man['in']}, edit, save into {man['done']}, then handoff_in.bat {man['name']}.",
            "handout": man}


def deliver_list(cfg: dict, game: str) -> dict:
    from ..night4 import deliver as dl
    try:
        r = dl.run(cfg, game, dry=True)
    except Exception as e:  # noqa: BLE001
        return {"ready": [], "refused": [], "error": str(e)}
    keep = ("wanted", "job_id", "why", "dest_rel", "target_size", "fitted")
    return {"ready": [{k: it.get(k) for k in keep} for it in r["moved"]],
            "refused": [{**{k: it.get(k) for k in keep}, "reason": it.get("reason")} for it in r["refused"]],
            "game_reachable": _game_root(cfg, game) is not None}


def deliver(cfg: dict, game: str, who: str | None, dry: bool = True, fit: bool = False) -> dict:
    from ..night4 import deliver as dl
    if dry:
        return {"ok": True, "dry": True, **deliver_list(cfg, game)}
    _need(who, "a delivery")
    r = dl.run(cfg, game, dry=False, fit=fit)
    moved = r.get("moved") or []
    if r.get("listed"):
        _sign(cfg, game, who, "deliver", "deliver", link=r["listed"],
              note=f"the game folder wasn't reachable — wrote the copy list for {len(moved)} picture(s) as a .bat")
        return {"ok": True, "message": f"The game's asset folder isn't reachable from here, so the copy list is a .bat: "
                                       f"{r['listed']} — double-click it to copy and record the deliveries.", "listed": r["listed"]}
    for it in moved:
        _sign(cfg, game, who, "deliver", it["wanted"], link=f"out/{it['job_id']}",
              note=f"delivered into the game at {it.get('dest_rel')}" + (" (the old file is in out/_replaced/)" if it.get("replaced") else ""))
    msg = f"Delivered {len(moved)} picture(s) into the game." if moved else "Nothing to deliver."
    if r.get("refused"):
        msg += f" {len(r['refused'])} refused — see why below."
    return {"ok": True, "message": msg, "moved": [{"wanted": m["wanted"], "dest": m.get("dest_rel"), "replaced": m.get("replaced")}
                                                  for m in moved],
            "refused": [{"wanted": x.get("wanted"), "reason": x.get("reason")} for x in r.get("refused") or []]}
