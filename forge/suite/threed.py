"""The 3D area (BUILD 36): picture -> 3D body -> skeleton -> motions as a place the person works by hand.

Tabs (areas.py): Bodies · Skeleton & motions · Props & buildings · Trees · Viewer · Runs. Every button here becomes a
job in the forge's queue (render, model_3d, rig_body, fit_motions, grow_tree, line_3d — forge/threed/specs.py), so the
art worker does the work and the card lock keeps the two ComfyUIs apart. A **try** is one attempt at one character or
thing: the words it was made from, its four pictures, the one picked, the body, the skeleton and the motions — kept in
games/<id>/threed/tries/<who>/<try>.json, so "try again with changes" starts from a filled-in card and two tries can be
seen side by side. Nothing here names a game: the game picker decides whose characters and words fill it.

Approving is the person's. A model they keep goes to Art -> Review & approve (its own "3D models" section); approving
holds it after the licence check of every tool that touched it; Deliver copies the .glb, its motion sheet and its
provenance into the game and records it in the same delivered.json ledger as pictures. The rigging pack's test dances
never reach a game.
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod
from ..log import get
from ..threed import cardlock, glb, line, licences, motions, rules, trees
from ..threed.env import from_cfg, out_root

log = get("suite")
DEFAULTS = json.loads((Path(__file__).resolve().parents[1] / "threed" / "defaults.json").read_text(encoding="utf-8"))
JOB_TYPES_3D = ("model_3d", "rig_body", "fit_motions", "grow_tree", "line_3d")
PICTURE_UNET = "flux-2-klein-4b.safetensors"


class ThreeDRefused(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ where things are
def tdir(cfg: dict, gid: str) -> Path:
    return cfgmod.path_of(cfg, "games") / gid / "threed"


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")
    return s[:48] or "unnamed"


def _read(p: Path, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    tmp.replace(p)


def _need(who: str | None, what: str) -> None:
    if not who:
        raise ThreeDRefused(f"say who you are first (top right) — {what} is signed")


def _person(who: str | None, what: str) -> None:
    from . import settings
    _need(who, what)
    if settings.is_assistant(who):
        raise ThreeDRefused(f"{what} is the person's — an assistant can't do it")


def _sign(cfg: dict, gid: str, who: str | None, kind: str, obj: str, note: str = "", link: str | None = None) -> None:
    from . import games, journal
    if not who or not gid:
        return
    try:
        root = games.game_root(cfg, gid)
        if root and root.is_dir():
            journal.append(root, who, kind, obj, note=note, link=link)
    except Exception as e:  # noqa: BLE001 — an action is never undone because its journal line failed
        log.warning("3d: journal line not written (%s)", e)


def _queue(cfg: dict):
    from ..queue import Queue
    return Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))


def _submit(cfg: dict, job: dict) -> str:
    """Into the queue, ahead of bulk work: a person is waiting at the screen for these (forge.json threed.priority,
    default 5; a whole-list run threed.line_priority, default 2). The bulk queues run at 0."""
    from .. import schema
    schema._plugins()
    t = (cfg.get("threed") or {})
    job.setdefault("priority", int(t.get("line_priority", 2)) if job.get("type") == "line_3d" else int(t.get("priority", 5)))
    return _queue(cfg).submit(job)


def job_state(cfg: dict, jid: str | None) -> tuple[str, dict]:
    """('pending'|'running'|'done'|'failed'|'paused'|'missing', the job file)."""
    if not jid:
        return "missing", {}
    jobs = cfgmod.path_of(cfg, "jobs")
    for st in ("done", "running", "pending", "failed", "paused"):
        p = jobs / st / f"{jid}.json"
        if p.exists():
            return st, _read(p, {})
    return "missing", {}


def rel(cfg: dict, p: Path | str) -> str:
    try:
        return Path(p).resolve().relative_to(cfgmod.ROOT.resolve()).as_posix()
    except ValueError:
        return str(p)


def file_url(rel_path: str | None) -> str | None:
    return f"/suite/3dfile?p={rel_path}" if rel_path else None


# ------------------------------------------------------------------------------------------------ the standing words
def words(cfg: dict, gid: str) -> dict:
    """For each kind (body, prop, building): the 'always' and negative words in use — the game's block when it has one,
    else the forge's standing words — and which it is."""
    try:
        from .. import prompts
        lib = prompts.load(cfg, gid)["blocks"]
    except Exception:  # noqa: BLE001
        lib = {}
    out = {}
    for kind, k in DEFAULTS["kinds"].items():
        d = {"model": k["model"]}
        for which in ("always", "negative"):
            block = k[which]
            mine = lib.get(block)
            usable = mine is not None and "TODO" not in str(mine)
            d[which] = {"block": block, "text": mine if usable else DEFAULTS["blocks"][block],
                        "from": "game" if usable else "forge"}
        out[kind] = d
    return out


def save_block(cfg: dict, gid: str, block: str, text: str, who: str | None) -> dict:
    """The person's words for a standing block, into the game's prompt library (finishing.edit_block: history, journal)."""
    from . import finishing
    if block not in DEFAULTS["blocks"]:
        raise ThreeDRefused(f"{block} is not one of the 3D blocks")
    _person(who, "changing the standing words")
    r = finishing.edit_block(cfg, gid, block, text, who)
    return r


# ------------------------------------------------------------------------------------------------ who: the people and things
def people(cfg: dict, gid: str) -> list[dict]:
    """Everyone the workshop knows: the character registry, plus any free name a try was made for."""
    from . import cast
    seen: dict[str, dict] = {}
    try:
        for c in cast.listing(cfg, gid):
            seen[c["id"]] = {"id": c["id"], "name": c.get("name") or c["id"], "registry": True}
    except Exception as e:  # noqa: BLE001
        log.warning("3d: the registry didn't list (%s)", e)
    root = tdir(cfg, gid) / "tries"
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if d.is_dir() and d.name not in seen:
                first = next(iter(sorted(d.glob("*.json"))), None)
                t = _read(first, {}) if first else {}
                seen[d.name] = {"id": d.name, "name": t.get("who_name") or d.name, "registry": False, "kind": t.get("kind")}
    for p in seen.values():
        p.update(person_file(cfg, gid, p["id"]))
        p["stage"] = stage_of(cfg, gid, p["id"])
    return list(seen.values())


def person_file(cfg: dict, gid: str, sid: str) -> dict:
    d = _read(tdir(cfg, gid) / "people" / f"{slug(sid)}.json", {})
    return {"never": list(d.get("never") or []), "height_m": d.get("height_m"), "rig_kind": d.get("rig_kind") or "people"}


def set_never(cfg: dict, gid: str, sid: str, never: list[str], who: str | None, height_m=None, rig_kind: str | None = None) -> dict:
    """The motions this character never does (and their height / rig kind), kept with the character."""
    _need(who, "a character's motions")
    p = tdir(cfg, gid) / "people" / f"{slug(sid)}.json"
    d = _read(p, {})
    d["never"] = sorted({str(m) for m in never if str(m).strip()})
    if height_m is not None:
        d["height_m"] = float(height_m)
    if rig_kind:
        d["rig_kind"] = rig_kind
    d.setdefault("history", []).append({"by": who, "at": datetime.now().isoformat(timespec="seconds"), "never": d["never"]})
    d["history"] = d["history"][-20:]
    _write(p, d)
    _sign(cfg, gid, who, "setting", f"3d:{slug(sid)}", note="motions never done: " + (", ".join(d["never"]) or "none"))
    return {"ok": True, "message": "Kept: " + (", ".join(d["never"]) or "no motion is left out") + ".", "never": d["never"]}


# ------------------------------------------------------------------------------------------------ tries
def _try_path(cfg: dict, gid: str, tid: str) -> Path:
    if not re.match(r"^[A-Za-z0-9_\-]+$", tid or ""):
        raise ThreeDRefused("no such try")
    hits = list((tdir(cfg, gid) / "tries").glob(f"*/{tid}.json"))
    if not hits:
        raise ThreeDRefused(f"no try {tid}")
    return hits[0]


def load_try(cfg: dict, gid: str, tid: str) -> dict:
    return _read(_try_path(cfg, gid, tid), {})


def _save_try(cfg: dict, gid: str, t: dict) -> None:
    _write(tdir(cfg, gid) / "tries" / t["who"] / f"{t['id']}.json", t)


STEPS = ("pictures", "body", "skeleton", "motions")


def gate_pictures(cfg: dict, t: dict, files: list[str]) -> list[dict]:
    """BUILD 40: the picture gate over a body try's pictures. In the Bodies form it is a warning only: the person picks."""
    from ..threed import gate
    obj = {"prompt": t.get("look") or "", "always": t.get("always") or ""}
    for k in ("age", "seated", "carried_object", "expects"):
        if t.get(k) not in (None, "", {}):
            obj[k] = t[k]
    out = []
    for f in files:
        p = Path(f) if Path(f).is_absolute() else cfgmod.ROOT / f
        try:
            j = gate.judge(p, obj, cfg)
            out.append({"ok": j["ok"], "lines": [ln.replace("Picture gate — ", "").replace(" Made again.", "") for ln in j["lines"]]})
        except Exception as e:  # noqa: BLE001 — a picture the gate can't read is not a reason to stop the form
            out.append({"ok": True, "lines": [f"not measured ({type(e).__name__})"]})
    return out


def refresh(cfg: dict, gid: str, t: dict) -> dict:
    """Bring a try's steps up to date with the queue: state, files, errors."""
    changed = False
    for step in STEPS:
        s = t.get("steps", {}).get(step)
        if not s or not s.get("job"):
            continue
        st, job = job_state(cfg, s["job"])
        if st != s.get("state"):
            s["state"] = st
            changed = True
        if st == "failed":
            s["error"] = str(job.get("error") or "")[:2000]
        res = job.get("result") or {}
        out = cfgmod.path_of(cfg, "out") / s["job"]
        if st == "done":
            if step == "pictures":
                s["files"] = [rel(cfg, out / f) for f in (res.get("outputs") or []) if (out / f).exists()]
                if t.get("kind") == "body":
                    s["gate"] = gate_pictures(cfg, t, s["files"])
            elif step == "body":
                s.update({k: res.get(k) for k in ("model", "picture", "engine", "resolution", "info", "tidy")})
            elif step == "skeleton":
                s.update({k: res.get(k) for k in ("fbx", "preview", "rigger", "orientation")})
            elif step == "motions":
                s.update({k: res.get(k) for k in ("moves", "sheet", "motions", "speeds", "left_out", "height_m")})
    ps = t.get("steps", {}).get("pictures") or {}
    if t.get("kind") == "body" and ps.get("state") == "done" and ps.get("files") and "gate" not in ps:
        ps["gate"] = gate_pictures(cfg, t, ps["files"])
        changed = True
    if changed:
        _save_try(cfg, gid, t)
    t["stage"] = next((s for s in reversed(STEPS) if (t.get("steps", {}).get(s) or {}).get("state") == "done"), "words")
    t["urls"] = {}
    for step in STEPS:
        s = t.get("steps", {}).get(step) or {}
        for k in ("model", "picture", "fbx", "preview", "orientation", "moves", "sheet"):
            if s.get(k):
                t["urls"][f"{step}.{k}"] = file_url(s[k])
        if step == "pictures":
            t["urls"]["pictures"] = [file_url(f) for f in s.get("files") or []]
    return t


def tries(cfg: dict, gid: str, sid: str | None = None, limit: int = 60) -> list[dict]:
    base = tdir(cfg, gid) / "tries"
    got = [(p, _read(p, {})) for p in base.glob(f"{slug(sid)}/*.json" if sid else "*/*.json")]
    got.sort(key=lambda x: (x[1].get("t_ns") or 0, x[0].name), reverse=True)
    out = []
    for p, t in got[:limit]:
        t = refresh(cfg, gid, t)
        out.append({k: t.get(k) for k in ("id", "who", "who_name", "kind", "look", "seed", "created", "by", "parent", "stage",
                                          "review", "urls", "height_m", "real_size_m", "model")} |
                   {"states": {s: (t.get("steps", {}).get(s) or {}).get("state") for s in STEPS}})
    return out


def try_view(cfg: dict, gid: str, tid: str) -> dict:
    t = refresh(cfg, gid, load_try(cfg, gid, tid))
    t["chips"] = rules.look_chips(t.get("look", ""))
    t["pose"] = rules.apose_check(f"{t.get('look', '')} {t.get('always', '')}") if t.get("kind") == "body" else []
    t["standing"] = rules.standing_check(t.get("look", "")) if t.get("kind") == "body" else []
    t["person"] = person_file(cfg, gid, t["who"])
    return t


def new_try(cfg: dict, gid: str, form: dict, who: str | None) -> dict:
    """'Make 4 pictures': a new try and one picture job of four (FLUX.2 klein, the words exactly as shown)."""
    _need(who, "making pictures")
    kind = str(form.get("kind") or "body")
    if kind not in DEFAULTS["kinds"]:
        raise ThreeDRefused(f"kind must be one of {', '.join(DEFAULTS['kinds'])}")
    name = str(form.get("who") or form.get("name") or "").strip()
    if not name:
        raise ThreeDRefused("say who (or what) this is")
    look = str(form.get("look") or "").strip()
    if not look:
        raise ThreeDRefused("describe the look in words — that is what the picture is painted from")
    w = words(cfg, gid)[kind]
    always = str(form["always"]) if form.get("always") is not None else w["always"]["text"]
    negative = str(form["negative"]) if form.get("negative") is not None else w["negative"]["text"]
    seed = int(form.get("seed") or 1001)
    count = max(1, min(8, int(form.get("count") or 4)))
    sid = slug(form.get("who_id") or name)
    t = {"id": f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}", "who": sid, "who_name": name, "kind": kind,
         "look": look, "always": always, "negative": negative, "seed": seed, "count": count,
         "model": form.get("model") or w["model"], "parent": form.get("parent") or None, "by": who,
         "created": datetime.now().isoformat(timespec="seconds"), "t_ns": time.time_ns(), "steps": {}}
    if kind == "body":
        h = form.get("height_m") or person_file(cfg, gid, sid).get("height_m") or 1.72
        t["height_m"] = float(h)
        t["rig_kind"] = str(form.get("rig_kind") or person_file(cfg, gid, sid).get("rig_kind") or "people")
        t["height_warning"] = rules.height_check(h, t["rig_kind"])
    else:
        size = form.get("real_size_m") or {}
        t["real_size_m"] = {k: float(v) for k, v in size.items() if k in ("height", "width", "depth") and v not in (None, "")}
    prompt = (look + " " + always).strip()
    jid = _submit(cfg, {"type": "render", "name": f"3d_{sid}"[:48], "graph": "flux2_klein", "checkpoint": form.get("unet") or PICTURE_UNET,
                        "prompt": prompt, "negative": negative, "style_prefix": "", "seed": seed, "size": [1024, 1024],
                        "count": count, "game": gid, "batch": f"3d_{sid}"[:48],
                        "meta": {"threed_try": t["id"], "threed_kind": kind}})
    t["steps"]["pictures"] = {"job": jid, "state": "pending", "prompt": prompt}
    _save_try(cfg, gid, t)
    _sign(cfg, gid, who, "queue", f"3d:{sid}", note=f"asked for {count} pictures of {name} ({kind})" +
          (f", changed from try {t['parent']}" if t["parent"] else ""), link=f"jobs/pending/{jid}.json")
    return {"ok": True, "message": f"{count} pictures are queued — they appear here when the art worker has painted them.",
            "try": t["id"], "job": jid}


def make_body(cfg: dict, gid: str, tid: str, pick, who: str | None) -> dict:
    """'Make the body' from the picture picked (an index into the try's pictures, or a picture path)."""
    _need(who, "making a body")
    t = refresh(cfg, gid, load_try(cfg, gid, tid))
    pics = (t["steps"].get("pictures") or {}).get("files") or []
    if isinstance(pick, int) or (isinstance(pick, str) and pick.isdigit()):
        i = int(pick)
        if not (0 <= i < len(pics)):
            raise ThreeDRefused("pick one of the pictures first")
        image = pics[i]
    else:
        image = str(pick or "")
        if image not in pics:
            raise ThreeDRefused("pick one of this try's pictures")
    job = {"type": "model_3d", "name": t["who"], "image": image, "kind": t["kind"], "model": t.get("model"),
           "prompt": t["look"], "game": gid, "character": t["who"], "try_id": t["id"], "resolutions": [1024]}
    if t["kind"] != "body" and t.get("real_size_m"):
        job["real_size_m"] = t["real_size_m"]
    jid = _submit(cfg, job)
    t["steps"]["picked"] = {"picture": image, "index": pics.index(image)}
    t["steps"]["body"] = {"job": jid, "state": "pending"}
    for later in ("skeleton", "motions"):
        t["steps"].pop(later, None)
    _save_try(cfg, gid, t)
    _sign(cfg, gid, who, "queue", f"3d:{t['who']}", note=f"asked for the 3D {'body' if t['kind'] == 'body' else 'model'} "
          f"from picture {pics.index(image) + 1} of try {tid}", link=f"jobs/pending/{jid}.json")
    return {"ok": True, "message": "The 3D " + ("body" if t["kind"] == "body" else "model") + " is queued (about four minutes on "
            "the card once it starts).", "job": jid}


def add_skeleton(cfg: dict, gid: str, tid: str, kind: str | None, who: str | None) -> dict:
    _need(who, "adding a skeleton")
    t = refresh(cfg, gid, load_try(cfg, gid, tid))
    b = t["steps"].get("body") or {}
    if b.get("state") != "done" or not b.get("model"):
        raise ThreeDRefused("make the body first")
    kind = kind or t.get("rig_kind") or "people"
    jid = _submit(cfg, {"type": "rig_body", "name": t["who"], "glb": b["model"], "kind": kind, "game": gid,
                        "character": t["who"], "try_id": t["id"]})
    t["rig_kind"] = kind
    t["steps"]["skeleton"] = {"job": jid, "state": "pending", "kind": kind}
    t["steps"].pop("motions", None)
    _save_try(cfg, gid, t)
    _sign(cfg, gid, who, "queue", f"3d:{t['who']}", note=f"asked for a skeleton ({kind}) for try {tid}", link=f"jobs/pending/{jid}.json")
    return {"ok": True, "message": "The skeleton is queued (the rigging ComfyUI takes two minutes to start, then seconds a body).",
            "job": jid}


def fit(cfg: dict, gid: str, tid: str, who: str | None) -> dict:
    _need(who, "fitting motions")
    t = refresh(cfg, gid, load_try(cfg, gid, tid))
    s = t["steps"].get("skeleton") or {}
    if s.get("state") != "done" or not s.get("fbx"):
        raise ThreeDRefused("add the skeleton first")
    never = person_file(cfg, gid, t["who"])["never"]
    jid = _submit(cfg, {"type": "fit_motions", "name": t["who"], "fbx": s["fbx"], "height": float(t.get("height_m") or 1.72),
                        "skip": never, "game": gid, "character": t["who"], "try_id": t["id"]})
    t["steps"]["motions"] = {"job": jid, "state": "pending", "skip": never}
    _save_try(cfg, gid, t)
    _sign(cfg, gid, who, "queue", f"3d:{t['who']}", note=f"asked for the motions for try {tid}" + (f" (never: {', '.join(never)})" if never else ""),
          link=f"jobs/pending/{jid}.json")
    return {"ok": True, "message": "The motions are queued (under a minute, on the processor).", "job": jid}


# ------------------------------------------------------------------------------------------------ review, approve, deliver
def send_review(cfg: dict, gid: str, tid: str, who: str | None, note: str = "") -> dict:
    _need(who, "sending to review")
    t = refresh(cfg, gid, load_try(cfg, gid, tid))
    if t["kind"] == "body" and (t["steps"].get("motions") or {}).get("state") != "done":
        raise ThreeDRefused("a body goes to review with its motions — fit them first")
    if t["kind"] != "body" and (t["steps"].get("body") or {}).get("state") != "done":
        raise ThreeDRefused("make the model first")
    t["review"] = {"state": "waiting", "by": who, "at": datetime.now().isoformat(timespec="seconds"), "note": note}
    _save_try(cfg, gid, t)
    _sign(cfg, gid, who, "review", f"3d:{t['who']}", note=f"sent try {tid} to Review & approve" + (f": {note}" if note else ""))
    return {"ok": True, "message": "It's in Art → Review & approve, under 3D models."}


def _deliver_files(t: dict) -> list[str]:
    st = t.get("steps", {})
    if t.get("kind") == "body":
        m = st.get("motions") or {}
        return [x for x in (m.get("moves"), m.get("sheet")) if x]
    b = st.get("body") or {}
    return [x for x in (b.get("model"),) if x]


def _licence_check(cfg: dict, t: dict) -> tuple[bool, list[str]]:
    if t.get("licence_keys") is not None:                 # BUILD 39: a thing from the world list says what made it
        keys = [k for k in t["licence_keys"] if k]
        return licences.all_ok(keys) if keys else False, licences.lines(keys)
    keys = []
    st = t.get("steps", {})
    if (st.get("body") or {}).get("job"):
        keys += ["flux2_klein_4b", (st["body"].get("engine") or t.get("model") or "trellis2"), "comfy_template"]
    if (st.get("skeleton") or {}).get("job"):
        keys += [st["skeleton"].get("rigger") or "mia", "comfyui_unirig"]
    if (st.get("motions") or {}).get("job"):
        keys += ["quaternius_ual", "blender"]
    return licences.all_ok(keys), licences.lines(keys)


def review_list(cfg: dict, gid: str) -> dict:
    base = tdir(cfg, gid) / "tries"
    waiting, decided = [], []
    for p in sorted(base.glob("*/*.json"), key=lambda p: p.name, reverse=True):
        t = _read(p, {})
        r = t.get("review")
        if not r:
            continue
        t = refresh(cfg, gid, t)
        ok, lines = _licence_check(cfg, t)
        item = {"id": t["id"], "who": t["who"], "who_name": t.get("who_name"), "kind": t["kind"], "look": t.get("look"),
                "review": r, "urls": t["urls"], "licences": lines, "commercial_ok": ok, "files": _deliver_files(t),
                "dest": dest_rel(cfg, gid, t), "from": t.get("from"), "checks": t.get("checks") or [],
                "check_picture": file_url(t.get("check_picture")), "world_kind": t.get("world_kind")}
        (waiting if r.get("state") == "waiting" else decided).append(item)
    return {"waiting": waiting, "decided": decided[:30], "approved": _read(tdir(cfg, gid) / "approved.json", {})}


def dest_rel(cfg: dict, gid: str, t: dict) -> str:
    """Where a model goes in the game: the adapter's threed_dest(kind, name) when it has one, else
    project/assets/models/<characters|props|buildings>/<name>.glb."""
    from . import games
    try:
        if games.has_adapter(cfg, gid):
            a = games.adapter(cfg, gid)
            fn = getattr(a, "threed_dest", None)
            if callable(fn):
                return str(fn(t["kind"], t["who"]))
    except Exception as e:  # noqa: BLE001
        log.warning("3d: the adapter's threed_dest failed (%s) — using the forge's default", e)
    folder = {"body": "characters", "prop": "props", "building": "buildings"}.get(t["kind"], "models")
    return f"project/assets/models/{folder}/{t['who']}.glb"


def decide(cfg: dict, gid: str, tid: str, verdict: str, who: str | None, note: str = "") -> dict:
    """Approve (held for Deliver, after the licence check) or turn down a 3D model. The person's alone."""
    if verdict not in ("approve", "reject"):
        raise ThreeDRefused("approve or reject")
    _person(who, "approving a model" if verdict == "approve" else "turning a model down")
    t = refresh(cfg, gid, load_try(cfg, gid, tid))
    files = _deliver_files(t)
    if verdict == "approve":
        ok, lines = _licence_check(cfg, t)
        if not ok:
            raise ThreeDRefused("refused — not every tool behind this model is known commercial-OK: " + "; ".join(lines))
        try:
            motions.refuse_test_dances([cfgmod.ROOT / f for f in files])
        except ValueError as e:
            raise ThreeDRefused(str(e))
        if not files or not all((cfgmod.ROOT / f).exists() for f in files):
            raise ThreeDRefused("its files are not all there any more: " + ", ".join(files))
        appr = _read(tdir(cfg, gid) / "approved.json", {})
        key = f"{t['kind']}/{t['who']}"
        appr[key] = {"try": t["id"], "files": files, "dest": dest_rel(cfg, gid, t), "licences": lines, "by": who,
                     "at": datetime.now().isoformat(timespec="seconds"), "delivered": None}
        _write(tdir(cfg, gid) / "approved.json", appr)
    t["review"] = {**(t.get("review") or {}), "state": "approved" if verdict == "approve" else "rejected", "decided_by": who,
                   "decided_at": datetime.now().isoformat(timespec="seconds"), "verdict_note": note}
    _save_try(cfg, gid, t)
    _sign(cfg, gid, who, "approve" if verdict == "approve" else "review", f"3d:{t['who']}",
          note=f"{'approved' if verdict == 'approve' else 'turned down'} try {tid}" + (f": {note}" if note else ""))
    return {"ok": True, "message": ("Approved — held for Deliver." if verdict == "approve" else "Turned down — it stays in its try.")}


def deliver(cfg: dict, gid: str, who: str | None, dry: bool = True) -> dict:
    """Copy every approved model (and its motion sheet and provenance) into the game; keep what it replaces in
    out/_replaced/; record each in delivered.json (the same ledger as pictures) and the journal."""
    from . import games
    from ..night4 import deliver as dl
    appr = _read(tdir(cfg, gid) / "approved.json", {})
    root = games.game_root(cfg, gid)
    todo = [(k, a) for k, a in appr.items() if not a.get("delivered")]
    plan = [{"what": k, "files": a["files"], "dest": a["dest"]} for k, a in todo]
    if dry:
        return {"ok": True, "dry": True, "plan": plan, "game_reachable": bool(root and root.is_dir())}
    _person(who, "a delivery")
    if not root or not root.is_dir():
        raise ThreeDRefused("the game's folder isn't reachable from this computer")
    moved = []
    for k, a in todo:
        dest = root / a["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        glb_src = next((cfgmod.ROOT / f for f in a["files"] if f.endswith(".glb")), None)
        if glb_src is None or not glb_src.exists():
            continue
        motions.refuse_test_dances([glb_src])
        replaced = None
        if dest.exists():
            bdir = cfgmod.path_of(cfg, "out") / "_replaced" / k.replace("/", "__")
            bdir.mkdir(parents=True, exist_ok=True)
            replaced = bdir / f"{datetime.now():%Y%m%d-%H%M%S}_{dest.name}"
            shutil.copyfile(dest, replaced)
        shutil.copyfile(glb_src, dest)
        for f in a["files"]:
            if f.endswith(".json"):
                shutil.copyfile(cfgmod.ROOT / f, dest.with_suffix(".json"))
        prov_dir = root / "project" / "assets" / "_provenance"
        prov_dir.mkdir(parents=True, exist_ok=True)
        t = _read(next(iter((tdir(cfg, gid) / "tries").glob(f"*/{a['try']}.json")), Path("-")), {})
        (prov_dir / (a["dest"].replace("project/assets/", "").replace("/", "__").rsplit(".", 1)[0] + ".json")).write_text(
            json.dumps({"asset": a["dest"], "approved": a["at"], "approved_by": a["by"], "try": a["try"], "files": a["files"],
                        "licences": a["licences"], "commercial_ok": True, "look": t.get("look"),
                        "made_by": "RPG_Forge 3D workshop (AI-generated with the tools listed; see licences)"},
                       indent=1, ensure_ascii=False), encoding="utf-8")
        import hashlib
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        dl.ledger_add(cfg, gid, {"action": "delivered", "wanted": "models/" + k, "job_id": a["try"], "file": glb_src.name,
                                 "sha256": digest, "dest_rel": a["dest"], "licences": a["licences"],
                                 "replaced": str(replaced) if replaced else None, "kind": "3d"})
        a["delivered"] = datetime.now().isoformat(timespec="seconds")
        moved.append({"what": k, "dest": a["dest"], "replaced": bool(replaced)})
        _sign(cfg, gid, who, "deliver", "models/" + k, note=f"delivered into the game at {a['dest']}", link=a["files"][0])
    _write(tdir(cfg, gid) / "approved.json", appr)
    return {"ok": True, "message": f"Delivered {len(moved)} model(s) into the game." if moved else "Nothing to deliver.", "moved": moved}


def stage_of(cfg: dict, gid: str, sid: str) -> str:
    """Where a character's body stands: no picture · picture · body · skeleton · motions · approved (Characters page)."""
    appr = _read(tdir(cfg, gid) / "approved.json", {})
    if f"body/{slug(sid)}" in appr:
        return "approved"
    best = "no picture"
    order = ["no picture", "picture", "body", "skeleton", "motions"]
    for p in (tdir(cfg, gid) / "tries" / slug(sid)).glob("*.json"):
        t = _read(p, {})
        for step, name in (("motions", "motions"), ("skeleton", "skeleton"), ("body", "body"), ("pictures", "picture")):
            s = (t.get("steps") or {}).get(step) or {}
            if s.get("job") and job_state(cfg, s["job"])[0] == "done":
                if order.index(name) > order.index(best):
                    best = name
                break
    return best


# ------------------------------------------------------------------------------------------------ trees
def grow(cfg: dict, gid: str, form: dict, who: str | None) -> dict:
    _need(who, "growing trees")
    sheet = form.get("sheet") or {}
    name = slug(sheet.get("name") or form.get("species") or "tree")
    numbers = {k: v for k, v in (sheet.get("numbers") or {}).items()}
    if not numbers:
        base = next((s for s in trees.sheets(cfgmod.path_of(cfg, "games") / gid) if s["name"] == (form.get("species") or "broadleaf")), None)
        if base is None:
            raise ThreeDRefused("choose a species sheet")
        numbers = base["numbers"]
    count = max(1, min(8, int(form.get("count") or 4)))
    jid = _submit(cfg, {"type": "grow_tree", "name": f"tree_{name}"[:48], "species": {"name": name, "numbers": numbers},
                        "seed": int(form.get("seed") or 11), "count": count, "bare": bool(form.get("bare")), "game": gid})
    _sign(cfg, gid, who, "queue", f"3d:tree:{name}", note=f"asked for {count} trees ({name}, seed {form.get('seed') or 11})",
          link=f"jobs/pending/{jid}.json")
    return {"ok": True, "message": f"{count} trees are queued (seconds each, on the processor).", "job": jid}


def save_species(cfg: dict, gid: str, sheet: dict, who: str | None) -> dict:
    _need(who, "a species sheet")
    name = slug(sheet.get("name") or "")
    if not name or name in ("broadleaf", "young_broadleaf") and sheet.get("where") == "forge":
        raise ThreeDRefused("give the sheet a name of its own (the forge's sheets aren't written over)")
    p = tdir(cfg, gid) / "species" / f"{name}.json"
    _write(p, {"name": name, "about": str(sheet.get("about") or ""), "numbers": sheet.get("numbers") or {},
               "by": who, "at": datetime.now().isoformat(timespec="seconds")})
    _sign(cfg, gid, who, "setting", f"3d:species:{name}", note="saved a tree species sheet")
    return {"ok": True, "message": f"Saved as {name}.", "file": rel(cfg, p)}


def tree_jobs(cfg: dict, gid: str, limit: int = 12) -> list[dict]:
    out = []
    jobs = cfgmod.path_of(cfg, "jobs")
    for st in ("running", "pending", "done", "failed"):
        for p in sorted((jobs / st).glob("*tree_*.json"), reverse=True)[:limit]:
            j = _read(p, {})
            if j.get("type") != "grow_tree" or (j.get("game") and j.get("game") != gid):
                continue
            res = j.get("result") or {}
            out.append({"id": j["id"], "state": st, "species": (j.get("species") or {}).get("name") if isinstance(j.get("species"), dict) else j.get("species"),
                        "seed": j.get("seed"), "count": j.get("count"), "bare": j.get("bare"), "error": j.get("error"),
                        "trees": [{"seed": t["seed"], "glb": file_url(t["glb"]), "view": file_url(t["views"][0]) if t.get("views") else None}
                                  for t in res.get("trees") or []]})
    return sorted(out, key=lambda x: x["id"], reverse=True)[:limit]


# ------------------------------------------------------------------------------------------------ runs and lists
def runs(cfg: dict, gid: str) -> dict:
    """What is running, what waits for the card, the last lines of each log, each report; the lists and their estimate."""
    jobs = cfgmod.path_of(cfg, "jobs")
    outd = cfgmod.path_of(cfg, "out")
    active = []
    for st in ("running", "pending", "paused"):
        for p in sorted((jobs / st).glob("*.json")):
            j = _read(p, {})
            if j.get("type") in JOB_TYPES_3D or (j.get("type") == "render" and (j.get("meta") or {}).get("threed_try")):
                tail = ""
                lp = outd / j["id"] / "run.log"
                if lp.exists():
                    tail = "\n".join(lp.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
                active.append({"id": j["id"], "state": st, "type": j["type"], "name": j.get("name"), "since": j.get("started_at") or j.get("submitted_at"),
                               "log": tail})
    recent = []
    for p in sorted((jobs / "done").glob("*.json"), key=lambda p: p.name, reverse=True)[:400]:
        j = _read(p, {})
        if j.get("type") in JOB_TYPES_3D:
            recent.append({"id": j["id"], "state": "done", "type": j["type"], "name": j.get("name"), "finished": j.get("finished_at")})
        if len(recent) >= 15:
            break
    failed = []
    for p in sorted((jobs / "failed").glob("*.json"), key=lambda p: p.name, reverse=True)[:200]:
        j = _read(p, {})
        if j.get("type") in JOB_TYPES_3D:
            failed.append({"id": j["id"], "type": j["type"], "name": j.get("name"), "error": str(j.get("error") or "")[:600]})
        if len(failed) >= 8:
            break
    batches = []
    od = out_root(cfg)
    if od.is_dir():
        for d in sorted((x for x in od.iterdir() if x.is_dir() and not x.name.startswith("_")), key=lambda x: x.stat().st_mtime, reverse=True)[:12]:
            rep = d / "REPORT.txt"
            logp = d / "run.log"
            batches.append({"batch": d.name, "report": rep.read_text(encoding="utf-8", errors="replace") if rep.exists() else "",
                            "log": "\n".join(logp.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]) if logp.exists() else "",
                            "when": datetime.fromtimestamp(d.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
    # the 2026-11-13 per-game runs are read too (never written)
    old = []
    for sub in ("cast", "trellis"):
        base = outd / sub
        if base.is_dir():
            for d in sorted((x for x in base.iterdir() if x.is_dir()), key=lambda x: x.stat().st_mtime, reverse=True)[:6]:
                rep = d / "REPORT.txt"
                if rep.exists():
                    old.append({"batch": f"{sub}/{d.name}", "report": rep.read_text(encoding="utf-8", errors="replace")[:4000],
                                "when": datetime.fromtimestamp(rep.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
    try:
        from . import world3d
        wq = world3d.summary(cfg, gid)
    except Exception as e:  # noqa: BLE001 — a broken list never hides the rest of Runs
        wq = {"error": str(e)}
    return {"card": cardlock.state(cfg), "active": active, "recent": recent, "failed": failed, "batches": batches, "earlier": old,
            "lists": lists(cfg, gid), "install_log": _install_tail(cfg), "world": wq}


def lists(cfg: dict, gid: str) -> list[dict]:
    """The game's lists (games/<id>/threed/lists/*.json), each with what is made already and an estimate for the rest."""
    out = []
    for p in sorted((tdir(cfg, gid) / "lists").glob("*.json")):
        spec = _read(p, None)
        if not isinstance(spec, dict) or not spec.get("objects"):
            continue
        spec.setdefault("batch", p.stem)
        st = line.status(cfg, spec)
        out.append({"file": rel(cfg, p), "batch": spec["batch"], "bodies": len(spec["objects"]),
                    "estimate": line.estimate(spec, st), "done": sum(1 for v in st.values() if v["motions"])})
    return out


def run_list(cfg: dict, gid: str, file: str, who: str | None) -> dict:
    """'Run a whole list overnight': one line_3d job (the estimate is shown before this is asked)."""
    _person(who, "starting an overnight run")
    p = cfgmod.ROOT / file
    if not p.exists() or tdir(cfg, gid).resolve() not in p.resolve().parents:
        raise ThreeDRefused("choose one of this game's lists")
    spec = _read(p, {})
    jid = _submit(cfg, {"type": "line_3d", "name": f"line_{slug(spec.get('batch') or p.stem)}"[:48], "list": rel(cfg, p), "game": gid})
    _sign(cfg, gid, who, "queue", f"3d:list:{p.stem}", note=f"started the whole 3D line for {p.name} ({len(spec.get('objects') or [])} bodies)",
          link=f"jobs/pending/{jid}.json")
    return {"ok": True, "message": "Queued. The art worker runs it when it gets to it; Runs shows it as it goes.", "job": jid}


def models(cfg: dict, gid: str, limit: int = 80) -> list[dict]:
    """Every model the forge has made (for the Viewer): the 3D jobs' outputs and the line folders' models and moves."""
    out = []
    jobs = cfgmod.path_of(cfg, "jobs")
    for p in sorted((jobs / "done").glob("*.json"), key=lambda p: p.name, reverse=True)[:600]:
        j = _read(p, {})
        if j.get("type") not in JOB_TYPES_3D or (j.get("game") and j.get("game") != gid):
            continue
        res = j.get("result") or {}
        for k in ("model", "preview", "moves"):
            if res.get(k):
                out.append({"name": j.get("name"), "kind": j["type"], "file": res[k], "url": file_url(res[k]), "when": j.get("finished_at"),
                            "sheet": file_url(res.get("sheet")) if k == "moves" else None})
        for t in res.get("trees") or []:
            out.append({"name": f"{j.get('name')} seed {t['seed']}", "kind": "tree", "file": t["glb"], "url": file_url(t["glb"]),
                        "when": j.get("finished_at")})
        if len(out) >= limit:
            break
    # BUILD 39: what the world queue made (newest first), at its real size
    sdir = cfgmod.path_of(cfg, "games") / gid / "wanted_3d" / "_state"
    if sdir.is_dir():
        for p in sorted(sdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:60]:
            st = _read(p, {})
            if st.get("model") and st.get("state") in ("made", "held"):
                out.append({"name": f"world: {p.stem}", "kind": "world", "file": st["model"], "url": file_url(st["model"]),
                            "sheet": file_url(st.get("sheet")) if st.get("sheet") else None, "when": st.get("finished")})
    od = out_root(cfg)
    if od.is_dir():
        for d in sorted((x for x in od.iterdir() if x.is_dir() and not x.name.startswith("_") and x.name != "world"),
                        key=lambda x: x.stat().st_mtime, reverse=True)[:6]:
            for f in sorted(list((d / "moves").glob("*.glb")) + list((d / "models").glob("*.glb")))[:40]:
                r = rel(cfg, f)
                sheet = f.with_suffix(".json")
                out.append({"name": f"{d.name}: {f.stem}", "kind": "line", "file": r, "url": file_url(r),
                            "sheet": file_url(rel(cfg, sheet)) if sheet.exists() else None,
                            "when": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%dT%H:%M")})
    return out[:limit * 2]


# ------------------------------------------------------------------------------------------------ install and check
_check_cache: dict = {}


def check(cfg: dict, fresh: bool = False) -> dict:
    from ..threed import install
    if fresh or not _check_cache or time.time() - _check_cache.get("at", 0) > 120:
        try:
            _check_cache.update(install.check(cfg), at=time.time())
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "items": [{"what": "the check itself", "ok": False, "detail": str(e), "fix": ""}]}
    return {k: v for k, v in _check_cache.items() if k != "at"}


def _install_log(cfg: dict) -> Path:
    return out_root(cfg) / "_install" / "install.log"


def _install_tail(cfg: dict, n: int = 30) -> str:
    p = _install_log(cfg)
    try:
        return "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


_install_proc: dict = {}


def install_start(cfg: dict, who: str | None, dry: bool = False) -> dict:
    """Settings -> 3D tools -> Install: runs `python -m forge 3d install` beside the suite (it can take an hour).
    Safe to start again: finished steps are skipped. The page shows its log."""
    _person(who, "installing the 3D tools")
    p = _install_proc.get("p")
    if p is not None and p.poll() is None:
        return {"ok": False, "message": "The install is already running — its log is below."}
    if from_cfg(cfg).is_up():
        return {"ok": False, "message": "Something is answering on the rigging ComfyUI's port — close it first."}
    log_path = _install_log(cfg)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "forge", "3d", "install"] + (["--dry-run"] if dry else [])
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    with open(log_path.with_name("install_console.log"), "a", encoding="utf-8") as f:
        _install_proc["p"] = subprocess.Popen(cmd, cwd=str(cfgmod.ROOT), stdout=f, stderr=subprocess.STDOUT, creationflags=flags)
    log.info("3d: install started by %s (%s)", who, " ".join(cmd))
    return {"ok": True, "message": "The install has started. It can take an hour the first time; finished steps are skipped "
                                   "next time. Its log follows below."}


# ------------------------------------------------------------------------------------------------ the page's one call
def view(cfg: dict, gid: str) -> dict:
    lib, trav = motions.library_paths(cfg, cfgmod.ROOT)
    from . import worker
    wstate = "unknown"
    try:
        wstate = worker.state(cfg)["state"]
    except Exception:  # noqa: BLE001
        pass
    return {
        "game": gid, "people": people(cfg, gid), "tries": tries(cfg, gid, limit=40), "words": words(cfg, gid),
        "rules": {"apose": rules.APOSE_RULE, "example": rules.APOSE_EXAMPLE, "faults": rules.KNOWN_FAULTS},
        "species": trees.sheets(cfgmod.path_of(cfg, "games") / gid), "sliders": trees.SLIDERS,
        "library": {"file": rel(cfg, lib), "there": lib.exists(), "motions": motions.library_motions(lib) if lib.exists() else [],
                    "speeds": bool(trav)},
        "card": cardlock.state(cfg), "worker": wstate, "check": check(cfg),
        "kinds": list(DEFAULTS["kinds"]),
    }


def chips(text: str, kind: str = "body") -> dict:
    """The live warnings for the words being typed."""
    return {"chips": rules.look_chips(text), "pose": rules.apose_check(text) if kind == "body" else [],
            "standing": rules.standing_check(text) if kind == "body" else []}


def safe_file(cfg: dict, p: str) -> Path:
    """A file the 3D pages may show: under out/, the forge's own species, or a game's threed folder."""
    q = (cfgmod.ROOT / str(p).replace("\\", "/")).resolve()
    allowed = [cfgmod.path_of(cfg, "out").resolve(), cfgmod.path_of(cfg, "games").resolve()]
    if not any(a == q or a in q.parents for a in allowed) or not q.is_file():
        raise FileNotFoundError(p)
    if q.suffix.lower() not in (".glb", ".gltf", ".png", ".jpg", ".jpeg", ".json", ".txt", ".log"):
        raise FileNotFoundError(p)
    games = cfgmod.path_of(cfg, "games").resolve()
    if games in q.parents and "threed" not in q.relative_to(games).parts:
        raise FileNotFoundError(p)                  # of a game's forge folder, only its 3D part
    return q
