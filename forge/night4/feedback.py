"""His verdicts come back (Night 4, F5): the game's F9 key writes playtest/art_feedback.json
{"map", "state", "files": [...], "note", "shot", "time", "tester"} (game plan 27 §2.1). feedback_in.bat reads it:

  * each entry's files → the delivered picture (delivered.json / approved.json) → its job and provenance
  * out/feedback/<date>.md: his screenshot beside the forge's picture, his words, the job's prompt and seed
  * a redo DRAFT in jobs/drafts/ — never queued: same type, family and control image, a new seed, his note attached
    as `comment`; for a scene also a scene_state inpaint draft with an EMPTY mask path (Fable draws the mask)
  * an entry that matches no delivery (a stand-in, a greybox) becomes a priority bump on that wanted item
    (games/<game>/priority_bumps.json — produce plan paints bumped items first)
Entries already read are remembered (out/feedback/seen.json), so running it twice files nothing twice.
The dashboard's "Called out" section lists the drafts: Approve draft (queue it) · Dismiss · He'll fix it himself
(hands the picture out to him with a handoff folder)."""
from __future__ import annotations
import hashlib
import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod

log = logging.getLogger("forge.feedback")
DROP = ("id", "result", "submitted_at", "started_at", "finished_at", "error", "traceback", "retries", "ran", "meta")


def drafts_dir(cfg: dict) -> Path:
    return cfgmod.path_of(cfg, "jobs") / "drafts"


def _wanted_of(path: str) -> str | None:
    p = str(path).replace("\\", "/")
    for pre in ("res://assets/", "project/assets/", "assets/"):
        if pre in p:
            p = p.split(pre, 1)[1]
            break
    return p.rsplit(".", 1)[0] if p else None


def _entries(data) -> list[dict]:
    if isinstance(data, dict):
        data = data.get("entries") or data.get("feedback") or []
    return [e for e in (data or []) if isinstance(e, dict)]


def _key(e: dict) -> str:
    return hashlib.sha1(json.dumps(e, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def _source_of(cfg: dict, game: str, wanted: str) -> dict | None:
    from .. import manifest
    from . import deliver as dl
    led = dl.live(cfg, game).get(wanted)
    if led:
        return {"job_id": led["job_id"], "file": led.get("file"), "via": "delivered.json"}
    a = manifest.load_approved(cfg, game).get(wanted)
    if a:
        return {"job_id": a["job_id"], "file": a.get("file"), "via": "approved.json"}
    return None


def _job(cfg: dict, jid: str) -> dict | None:
    p = cfgmod.path_of(cfg, "jobs") / "done" / f"{jid}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None


def _side_by_side(shot: Path | None, pic: Path | None, dest: Path) -> Path | None:
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in (shot, pic) if p is not None and p.exists()]
    if not ims:
        return None
    h = 540
    ims = [im.resize((max(1, int(im.width * h / im.height)), h)) for im in ims]
    out = Image.new("RGB", (sum(i.width for i in ims) + 10 * (len(ims) - 1), h), (24, 24, 28))
    x = 0
    for im in ims:
        out.paste(im, (x, 0)); x += im.width + 10
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, "JPEG", quality=85)
    return dest


def draft_redo(cfg: dict, src_job: dict, note: str, wanted: str, entry: dict) -> list[Path]:
    """The full redo (new seed) and, for a scene, a scene_state inpaint with an empty mask for Fable."""
    d = drafts_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = {k: v for k, v in src_job.items() if k not in DROP}
    old_seed = src_job.get("seed") if isinstance(src_job.get("seed"), int) else (src_job.get("result") or {}).get("seed")
    new_seed = random.randint(1, 2**31 - 2)
    common = {"_draft": True, "redo_of": src_job["id"], "comment": note, "_wanted": wanted, "_called_out": entry,
              "meta": {**(src_job.get("meta") or {}), "wanted": wanted, "redo_of": src_job["id"]}}
    redo = {**base, **common, "seed": new_seed, "_why": f"redo with a new seed (was {old_seed})"}
    paths = []
    p = d / f"{stamp}-redo-{Path(wanted).name}.json"
    p.write_text(json.dumps(redo, indent=1, ensure_ascii=False), encoding="utf-8")
    paths.append(p)
    if src_job.get("type") in ("scene_kit", "scene_paint", "repaint", "scene_big", "scene_state", "handoff_kit", "photo_plate"):
        fix = {"type": "scene_state", "name": f"{src_job.get('name') or Path(wanted).name}_fix", "base": f"out/{src_job['id']}",
               "mask": "", "prompt": "", "seed": old_seed if isinstance(old_seed, int) else new_seed, **common,
               "_why": "a small fix: Fable draws the mask over what he called out and writes the prompt for that part only"}
        q = d / f"{stamp}-fix-{Path(wanted).name}.json"
        q.write_text(json.dumps(fix, indent=1, ensure_ascii=False), encoding="utf-8")
        paths.append(q)
    return paths


def bump(cfg: dict, game: str, wanted: str, entry: dict) -> None:
    p = cfgmod.path_of(cfg, "games") / game / "priority_bumps.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    e = d.setdefault(wanted, {"bump": 0, "notes": []})
    e["bump"] += 1
    e["notes"].append({"note": entry.get("note"), "time": entry.get("time"), "tester": entry.get("tester")})
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")


def take_in(cfg: dict, path: str | None = None, game: str = "turing_accords") -> dict:
    gcfg = cfgmod.game_config(cfg, game)
    root = Path(gcfg.get("game_root") or "")
    src = Path(path) if path else root / "playtest" / "art_feedback.json"
    if not src.exists():
        raise FileNotFoundError(f"no feedback file at {src} (the game's F9 key writes playtest/art_feedback.json)")
    entries = _entries(json.loads(src.read_text(encoding="utf-8")))
    fb = cfgmod.path_of(cfg, "out") / "feedback"
    fb.mkdir(parents=True, exist_ok=True)
    seen_p = fb / "seen.json"
    seen = json.loads(seen_p.read_text(encoding="utf-8")) if seen_p.exists() else {}
    day = datetime.now().strftime("%Y-%m-%d")
    md = fb / f"{day}.md"
    L = [] if md.exists() else [f"# Called out — {day}", ""]
    rep = {"filed": [], "bumped": [], "skipped": 0, "md": str(md)}
    for e in entries:
        k = _key(e)
        if k in seen:
            rep["skipped"] += 1
            continue
        files = [f for f in (e.get("files") or []) if f]
        if not files and e.get("map"):
            files = [f"project/assets/scenes/{e['map']}" + (f"_{e['state']}" if e.get("state") else "") + ".png"]
        shot = None
        if e.get("shot"):
            sp = Path(str(e["shot"]).replace("user://", ""))
            shot = sp if sp.is_absolute() else root / "playtest" / sp
        for f in files:
            wanted = _wanted_of(f)
            s = _source_of(cfg, game, wanted) if wanted else None
            j = _job(cfg, s["job_id"]) if s else None
            n = len(rep["filed"]) + len(rep["bumped"]) + 1
            if not j:
                bump(cfg, game, wanted or f, e)
                rep["bumped"].append({"wanted": wanted or f, "note": e.get("note")})
                L += [f"## {wanted or f} — no forge picture behind it (a stand-in): priority bumped", "",
                      f"> {e.get('note') or ''}  — {e.get('tester') or 'tester'}, {e.get('time') or ''}", ""]
                continue
            pic = cfgmod.path_of(cfg, "out") / j["id"] / (s.get("file") or "")
            sbs = _side_by_side(shot, pic if pic.is_file() else None, fb / day / f"{n:02d}_{Path(wanted).name}.jpg")
            prov = {}
            pp = cfgmod.path_of(cfg, "out") / j["id"] / "prov.json"
            if pp.exists():
                prov = json.loads(pp.read_text(encoding="utf-8"))
            drafts = draft_redo(cfg, j, e.get("note") or "", wanted, e)
            rep["filed"].append({"wanted": wanted, "job": j["id"], "drafts": [str(d) for d in drafts], "note": e.get("note")})
            L += [f"## {wanted} — {e.get('note') or '(no words)'}", "",
                  f"- tester: {e.get('tester') or '-'} · {e.get('time') or ''} · map {e.get('map') or '-'} state {e.get('state') or '-'}",
                  f"- picture: job `{j['id']}` ({j.get('type')}) via {s['via']} · seed {prov.get('seed') or (j.get('result') or {}).get('seed')}",
                  f"- prompt: {prov.get('prompt') or j.get('prompt') or ''}",
                  f"- side by side (his screenshot · the forge's picture): {sbs.name if sbs else 'no pictures readable'}",
                  f"- drafts (not queued): {', '.join(Path(d).name for d in drafts)}", ""]
        seen[k] = {"time": datetime.now().isoformat(timespec="seconds"), "note": e.get("note")}
    if L:
        with open(md, "a", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
    seen_p.write_text(json.dumps(seen, indent=1, ensure_ascii=False), encoding="utf-8")
    log.info("feedback: filed %d, bumped %d, skipped %d already seen", len(rep["filed"]), len(rep["bumped"]), rep["skipped"])
    return rep


# ------------------------------------------------------------------ the dashboard's "Called out"
def list_drafts(cfg: dict) -> list[dict]:
    out = []
    for p in sorted(drafts_dir(cfg).glob("*.json"), reverse=True):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"draft": p.name, "type": j.get("type"), "wanted": j.get("_wanted"), "note": j.get("comment"),
                    "why": j.get("_why"), "redo_of": j.get("redo_of"), "ready": bool(j.get("prompt")) and j.get("mask") != ""})
    return out


def draft_action(cfg: dict, action: str, name: str) -> dict:
    d = drafts_dir(cfg)
    p = d / Path(name).name
    if not p.exists():
        return {"ok": False, "message": f"no draft {name}"}
    j = json.loads(p.read_text(encoding="utf-8"))
    if action == "draft_dismiss":
        (d / "_dismissed").mkdir(exist_ok=True)
        os.replace(p, d / "_dismissed" / p.name)
        return {"ok": True, "message": f"dismissed {p.name} (kept in jobs/drafts/_dismissed)"}
    if action == "draft_himself":
        from .. import handoff as ho
        man = ho.hand_out(cfg, [j["redo_of"]], name=f"fix_{Path(j.get('_wanted') or 'picture').name}")
        (d / "_himself").mkdir(exist_ok=True)
        os.replace(p, d / "_himself" / p.name)
        return {"ok": True, "message": f"handed out to you: {man['in']} — edit it, save into {man['done']}, then handoff_in.bat {man['name']}"}
    if action == "draft_submit":
        from .. import prompts as pl, schema
        from ..queue import Queue
        if j.get("type") == "scene_state" and not j.get("mask"):
            return {"ok": False, "message": "this fix draft has no mask yet — Fable draws it (path in \"mask\") and writes the prompt"}
        job = {k: v for k, v in j.items() if not k.startswith("_") or k == "_wanted"}
        try:
            job = pl.prepare(cfg, [job])[0]
        except pl.PromptError as e:
            return {"ok": False, "message": str(e)}
        probs = schema.validate(job)
        if probs:
            return {"ok": False, "message": "; ".join(probs)}
        jid = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out")).submit({**job, "batch": "produce/redo", "priority": 55})
        (d / "_queued").mkdir(exist_ok=True)
        os.replace(p, d / "_queued" / p.name)
        return {"ok": True, "message": f"queued {jid}"}
    return {"ok": False, "message": f"unknown {action}"}
