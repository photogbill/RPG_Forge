"""3D -> Places (BUILD 34 part 9): a game's places as stages. Pick one: its plan, a picture of its stage as it stands, its
world-list entries with their states (made / held / waiting), Compile again, Open in the game here.

A place plan lives in the game's forge folder (`games/<game>/places/<id>.place.json`, metres, x east, y south); compiling
it writes the stage into the game's own asset folder (`<asset_root>/stages/<id>/`, place.stage_dir) and the things it
needs onto the world list (`games/<game>/wanted_3d/<id>.json`). Compiling from here holds every NEW world-list entry
(released in 3D -> World list when someone wants it made): compiling a place never starts generation by itself.

BUILD 63 (the look): a look picker — Open in the game here under any of the game's look profiles (the adapter's
`looks()`), not only day or night — and Take the pictures: the game's own still mode, one picture a look, at the film
tier, into the place's picture folder (`out/places/<game>/<place>/look_<id>.png`), one after another in the background
(the adapter's `still_command()`). They are the game's pictures of the stage: what it looks like, not greybox.

The picture is the plan seen from above — ground, plan-built solids, the placed things as boxes (grey until their model
is delivered), lamps and anchors — stamped "plan from above — not how the game looks". The game's own pictures of a stage
come from the game (its shots tool). Which game map shows a place, and how to start the game there, is the game's
adapter's (`stage_maps()`, `play_command()`); nothing here names a game.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import config as cfgmod
from ..log import get
from ..threed import place as placemod
from ..threed import world
from .threed import ThreeDRefused, _need, _person, _read, _sign, _submit, file_url, job_state, rel

log = get("suite")

STAMP = "plan from above — greybox, not how the game looks"


# ------------------------------------------------------------------------------------------------ where things are
def places_dir(cfg: dict, gid: str) -> Path:
    return cfgmod.path_of(cfg, "games") / gid / "places"


def pictures_dir(cfg: dict, gid: str) -> Path:
    return cfgmod.path_of(cfg, "out") / "places" / gid


def sources(cfg: dict, gid: str) -> list[Path]:
    d = places_dir(cfg, gid)
    return sorted(d.glob("*.place.json")) if d.is_dir() else []


def _adapter(cfg: dict, gid: str):
    try:
        from . import games
        return games.adapter(cfg, gid)
    except Exception as e:  # noqa: BLE001 — the tab still shows the plans without the game
        log.info("places: no adapter for %s (%s)", gid, e)
        return None


def _stage_maps(adp) -> dict:
    fn = getattr(adp, "stage_maps", None) if adp is not None else None
    if not callable(fn):
        return {}
    try:
        return dict(fn() or {})
    except Exception as e:  # noqa: BLE001
        log.warning("places: the adapter's stage_maps failed (%s)", e)
        return {}


def _mtime(p: Path | None) -> float:
    try:
        return p.stat().st_mtime if p is not None and p.exists() else 0.0
    except OSError:
        return 0.0


def _when(t: float) -> str | None:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else None


# ------------------------------------------------------------------------------------------------ the world list's states
def entry_state(item: dict) -> str:
    """made / held / waiting — the three words the Places tab uses for a world-list entry."""
    if item.get("model") or str(item.get("state") or "") in ("made", "delivered", "done", "approved"):
        return "made"
    if item.get("hold") or str(item.get("state") or "") == "held" or str(item.get("shown") or "").startswith("held"):
        return "held"
    return "waiting"


def entries_for(status: dict, place_id: str) -> list[dict]:
    out = []
    for i in status.get("items") or []:
        if Path(str(i.get("file") or "")).stem != place_id:
            continue
        out.append({"id": i["id"], "kind": i.get("kind"), "tier": i.get("tier"), "state": entry_state(i),
                    "shown": i.get("shown"), "why": (i.get("why") or [])[:2], "words": bool(str(i.get("words") or "").strip()),
                    "size": i.get("size"), "model": file_url(i.get("model")) if i.get("model") else None})
    return out


# ------------------------------------------------------------------------------------------------ the picture
def draw(place: dict, things: dict | None, delivered: set, dest: Path, px_per_m: float = 14.0) -> Path:
    """The plan from above as a PNG: ground by material, plan-built solids, placed things as boxes (grey until their
    model is delivered, green when it is), lamps, anchors — and the stamp that says what it is."""
    from PIL import Image, ImageDraw
    size = place.get("size") or [40, 30]
    W, H = max(64, int(float(size[0]) * px_per_m)), max(64, int(float(size[1]) * px_per_m))
    pad_top = 26
    im = Image.new("RGB", (W, H + pad_top), (36, 38, 44))
    dr = ImageDraw.Draw(im)

    def P(x, y):
        return (float(x) * px_per_m, float(y) * px_per_m + pad_top)

    def colour(word: str) -> tuple:
        w = str(word or "")
        table = {"grass": (78, 118, 64), "asphalt": (62, 64, 70), "dirt_road": (128, 104, 74), "dirt": (128, 104, 74),
                 "gravel": (118, 114, 106), "sidewalk": (150, 150, 146), "kerb": (170, 170, 166), "path": (150, 140, 120),
                 "water": (54, 92, 138), "concrete": (140, 140, 138)}
        for k, v in table.items():
            if k in w:
                return v
        return (96, 100, 96)
    dr.rectangle([0, pad_top, W, H + pad_top], fill=colour(place.get("background") or "grass"))
    for g in place.get("ground") or []:
        if not isinstance(g, dict):
            continue
        c = colour(g.get("mat"))
        if "rect" in g:
            x, y, w, h = g["rect"]
            dr.rectangle([P(x, y), P(x + w, y + h)], fill=c)
        elif "ellipse" in g:
            x, y, rx, ry = g["ellipse"]
            dr.ellipse([P(x - rx, y - ry), P(x + rx, y + ry)], fill=c)
        elif "poly" in g:
            dr.polygon([P(*q) for q in g["poly"]], fill=c)
    for s in place.get("solids") or []:
        if not isinstance(s, dict) or s.get("roof"):
            continue
        c = (214, 200, 170) if s.get("show") == "inside" or s.get("mat") == "cut" else (190, 178, 160)
        if "rect" in s:
            x, y, w, h = s["rect"]
            dr.rectangle([P(x, y), P(x + w, y + h)], fill=c, outline=(60, 54, 46))
        else:
            for k in ("cyl", "circle"):
                if k in s:
                    x, y, r = s[k][:3]
                    dr.ellipse([P(x - r, y - r), P(x + r, y + r)], fill=c, outline=(60, 54, 46))
    tl = (things or {}).get("things") or []
    for t in tl:
        if not isinstance(t, dict) or t.get("plan_built"):
            continue
        at = t.get("at") or [0, 0]
        box = t.get("box_m") or [1, 1, 1]
        made = str(t.get("model") or t.get("id")) in delivered
        if str(t.get("kind")) == "tree":
            r = max(1.2, float(box[0]) * 0.5)
            dr.ellipse([P(at[0] - r, at[1] - r), P(at[0] + r, at[1] + r)], outline=(120, 200, 120) if made else (170, 170, 170), width=2)
            continue
        import math
        a = math.radians(float(t.get("turn") or 0))
        w, d = float(box[0]) * 0.5, float(box[1]) * 0.5
        pts = []
        for cx, cy in ((-w, -d), (w, -d), (w, d), (-w, d)):
            pts.append(P(at[0] + cx * math.cos(a) - cy * math.sin(a), at[1] + cx * math.sin(a) + cy * math.cos(a)))
        dr.polygon(pts, fill=(96, 150, 96) if made else (128, 128, 132), outline=(230, 230, 230))
        dr.text((pts[0][0] + 3, pts[0][1] + 2), str(t.get("label") or t.get("id"))[:28], fill=(250, 250, 250))
    for li in ((place.get("lighting") or {}).get("lights") or []):
        if isinstance(li, dict) and not str(li.get("id", "")).startswith("moon_"):
            x, y = (li.get("at") or [0, 0])[:2]
            dr.ellipse([P(x - 0.35, y - 0.35), P(x + 0.35, y + 0.35)], fill=(255, 214, 120))
    for name, at in (place.get("anchors") or {}).items():
        if isinstance(at, list) and len(at) >= 2:
            x, y = P(at[0], at[1])
            dr.line([x - 4, y, x + 4, y], fill=(120, 220, 255))
            dr.line([x, y - 4, x, y + 4], fill=(120, 220, 255))
    dr.rectangle([0, 0, W, pad_top], fill=(20, 20, 24))
    dr.text((8, 7), f"{place.get('id', '')} · {size[0]} × {size[1]} m · {STAMP}", fill=(255, 200, 120))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp.png")
    im.save(tmp)
    tmp.replace(dest)
    return dest


# ------------------------------------------------------------------------------------------------ the tab
def _jobs_for(cfg: dict, gid: str, place_id: str, limit: int = 6) -> list[dict]:
    out = []
    jobs = cfgmod.path_of(cfg, "jobs")
    for st in ("running", "pending", "done", "failed"):
        for p in sorted((jobs / st).glob("*place_*.json"), reverse=True)[:40]:
            j = _read(p, {})
            if j.get("type") != "compile_place" or (j.get("game") and j.get("game") != gid):
                continue
            if Path(str(j.get("place") or "")).name != f"{place_id}.place.json":
                continue
            out.append({"id": j.get("id"), "state": st, "error": j.get("error"), "at": j.get("created") or j.get("submitted")})
    return out[:limit]


def _looks(adp) -> list:
    fn = getattr(adp, "looks", None) if adp is not None else None
    try:
        return list(fn() or []) if callable(fn) else []
    except Exception as e:  # noqa: BLE001
        log.info("places: the game's looks can't be listed (%s)", e)
        return []


def look_pictures(cfg: dict, gid: str, pid: str) -> list[dict]:
    """The game's own pictures of a place, one a look (Take the pictures), newest first."""
    d = pictures_dir(cfg, gid) / world.slug(pid)
    out = []
    for p in sorted(d.glob("look_*.png")) if d.is_dir() else []:
        out.append({"look": p.stem[5:], "picture": file_url(rel(cfg, p)), "at": _when(_mtime(p))})
    return out


_TAKING: dict = {}


def view(cfg: dict, gid: str) -> dict:
    adp = _adapter(cfg, gid)
    maps = _stage_maps(adp)
    looks = _looks(adp)
    try:
        status = world.status(cfg, gid)
    except Exception as e:  # noqa: BLE001
        status = {"items": [], "problems": [f"the world list can't be read ({e})"]}
    delivered = {i["id"] for i in status.get("items") or [] if entry_state(i) == "made"}
    out = []
    for src in sources(cfg, gid):
        try:
            p = placemod.load(src)
        except Exception as e:  # noqa: BLE001
            out.append({"id": src.name.replace(".place.json", ""), "file": rel(cfg, src), "error": str(e)})
            continue
        pid = str(p.get("id") or src.name.replace(".place.json", ""))
        sd = placemod.stage_dir(cfg, gid, pid)
        things_p = sd / f"{pid}.things.json" if sd else None
        model_p = sd / f"{pid}.stage.glb" if sd else None
        things = _read(things_p, {}) if things_p is not None and things_p.exists() else {}
        compiled_at = _mtime(things_p)
        pic = pictures_dir(cfg, gid) / f"{pid}.png"
        if _mtime(pic) < max(_mtime(src), compiled_at):
            try:
                draw(p, things, delivered, pic)
            except Exception as e:  # noqa: BLE001 — a plan that can't be drawn still shows
                log.warning("places: %s not drawn (%s)", pid, e)
        ents = entries_for(status, pid)
        counts = {"made": 0, "held": 0, "waiting": 0}
        for e in ents:
            counts[e["state"]] += 1
        out.append({
            "id": pid, "name": p.get("name") or pid, "file": rel(cfg, src), "size": p.get("size"),
            "solids": len(p.get("solids") or []), "things": len(p.get("things") or []), "anchors": sorted((p.get("anchors") or {}).keys()),
            "lights": len((p.get("lighting") or {}).get("lights") or []), "problems": placemod.check(p),
            "asked": p.get("asked") or [], "compiled": {"at": _when(compiled_at), "model": bool(model_p and model_p.exists()),
                                                       "things": len(things.get("things") or []), "folder": str(sd) if sd else None,
                                                       "stale": bool(compiled_at) and _mtime(src) > compiled_at},
            "picture": file_url(rel(cfg, pic)) if pic.exists() else None, "entries": ents, "counts": counts,
            "maps": maps.get(pid, []), "jobs": _jobs_for(cfg, gid, pid),
            "look_pictures": look_pictures(cfg, gid, pid), "taking": _TAKING.get((gid, pid))})
    return {"game": gid, "places": out, "folder": rel(cfg, places_dir(cfg, gid)), "stamp": STAMP,
            "can_play": adp is not None and callable(getattr(adp, "play_command", None)),
            "looks": looks, "can_take": adp is not None and callable(getattr(adp, "still_command", None)),
            "world_problems": (status.get("problems") or [])[:5]}


def _place_file(cfg: dict, gid: str, pid: str) -> Path:
    pid = world.slug(pid)
    p = places_dir(cfg, gid) / f"{pid}.place.json"
    if not p.exists():
        raise ThreeDRefused(f"there is no place plan '{pid}' in {rel(cfg, places_dir(cfg, gid))}")
    return p


def compile_again(cfg: dict, gid: str, pid: str, who: str | None) -> dict:
    """Queue compile_place for one place, into the game's own stage folder; every new world-list entry is held."""
    _need(who, "compiling a place")
    src = _place_file(cfg, gid, pid)
    probs = placemod.check(placemod.load(src))
    if probs:
        raise ThreeDRefused("the plan has problems: " + "; ".join(probs[:3]))
    sd = placemod.stage_dir(cfg, gid, world.slug(pid))
    if sd is None:
        raise ThreeDRefused("the game names no asset folder (forge.game.json asset_root) — there is nowhere to compile it into")
    for j in _jobs_for(cfg, gid, world.slug(pid)):
        if j["state"] in ("pending", "running"):
            return {"ok": False, "message": f"{pid} is already being compiled ({j['state']})."}
    jid = _submit(cfg, {"type": "compile_place", "name": f"place_{world.slug(pid)}"[:48], "place": rel(cfg, src), "game": gid,
                        "out": str(sd), "hold": True})
    _sign(cfg, gid, who, "queue", f"3d:place:{pid}", note="compile again (new world-list things held)", link=f"jobs/pending/{jid}.json")
    return {"ok": True, "job": jid, "message": f"{pid} is queued to compile (Blender on the processor, a minute or two). "
                                               "Anything new it needs goes on the world list held — release it in World list when you want it made."}


def play(cfg: dict, gid: str, pid: str, time_of_day: str, who: str | None) -> dict:
    """Start the game at the place's stage map (the adapter says which map and how)."""
    adp = _adapter(cfg, gid)
    maps = _stage_maps(adp).get(world.slug(pid), [])
    if not maps:
        raise ThreeDRefused(f"no map in the game shows {pid} yet — the game needs a stage map whose place is {pid}")
    fn = getattr(adp, "play_command", None)
    if not callable(fn):
        raise ThreeDRefused("this game's adapter can't start the game at a place (no play_command)")
    tod = time_of_day if (time_of_day in ("day", "night") or time_of_day in _looks(adp)) else ""   # BUILD 63: or a look
    try:
        try:
            cmd = fn(maps[0], "peace", tod) if tod else fn(maps[0], "peace")
        except TypeError:
            cmd = fn(maps[0], "peace")
    except ValueError as e:
        raise ThreeDRefused(str(e))
    if not cmd:
        raise ThreeDRefused(f"the game can't start at {maps[0]}")
    import subprocess
    log.info("places: open in the game: %s", cmd)
    subprocess.Popen(cmd, cwd=str(getattr(adp, "root", cfgmod.ROOT)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _sign(cfg, gid, who, "play", f"3d:place:{pid}", note=f"opened {maps[0]} in the game{' by ' + tod if tod else ''}")
    return {"ok": True, "message": f"Starting the game at {maps[0]}{' by ' + tod if tod else ''} — it opens in its own window."}


def take_pictures(cfg: dict, gid: str, pid: str, who: str | None, looks: list | None = None, wait: bool = False,
                  run=None) -> dict:
    """BUILD 63: one picture of the place's stage a look, by the game's still mode, into the place's picture folder —
    one after another in the background (the card is used for a minute a picture; nothing is generated). `run` is
    subprocess.run's stand-in for the tests; `wait` runs them before returning."""
    _need(who, "taking the pictures of a place")
    adp = _adapter(cfg, gid)
    maps = _stage_maps(adp).get(world.slug(pid), [])
    if not maps:
        raise ThreeDRefused(f"no map in the game shows {pid} yet — the game needs a stage map whose place is {pid}")
    fn = getattr(adp, "still_command", None)
    if not callable(fn):
        raise ThreeDRefused("this game's adapter can't take a still (no still_command)")
    have = _looks(adp)
    want = [lk for lk in (looks or have) if lk in have]
    if not want:
        raise ThreeDRefused("the game has no look profiles to take a picture under")
    if _TAKING.get((gid, world.slug(pid)), {}).get("left"):
        return {"ok": False, "message": f"{pid}: the pictures are already being taken ({_TAKING[(gid, world.slug(pid))]['left']} left)."}
    dest = pictures_dir(cfg, gid) / world.slug(pid)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        cmds = [(lk, fn(maps[0], "peace", lk, str(dest / f"look_{lk}.png"))) for lk in want]
    except ValueError as e:
        raise ThreeDRefused(str(e))
    import subprocess
    import threading
    state = {"left": len(cmds), "done": [], "failed": [], "started": time.strftime("%H:%M")}
    _TAKING[(gid, world.slug(pid))] = state
    runner = run or subprocess.run

    def go():
        for lk, cmd in cmds:
            try:
                r = runner(cmd, cwd=str(getattr(adp, "root", cfgmod.ROOT)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=600)
                ok = getattr(r, "returncode", 0) == 0 and (dest / f"look_{lk}.png").exists()
            except Exception as e:  # noqa: BLE001 — one look failing doesn't stop the rest
                log.warning("places: still %s %s failed (%s)", pid, lk, e)
                ok = False
            (state["done"] if ok else state["failed"]).append(lk)
            state["left"] -= 1
        log.info("places: pictures of %s: %d taken, %d failed", pid, len(state["done"]), len(state["failed"]))

    _sign(cfg, gid, who, "pictures", f"3d:place:{pid}", note=f"took the game's pictures of {maps[0]} under {', '.join(want)}")
    if wait:
        go()
    else:
        threading.Thread(target=go, daemon=True).start()
    return {"ok": True, "message": f"Taking {len(cmds)} pictures of {maps[0]} (one a look, at the film tier) — the game opens and "
                                   "closes by itself for each; they appear here as they are done. Keep the graphics card free."}


def approve_as_stage(cfg: dict, gid: str, folder: Path, who: str | None) -> dict:
    """Floor plans → Approve "as a stage": the town's approved layout written out as a place plan (place.from_town),
    a stage map for it in the game (the adapter's stage_install, a draft), and a compile queued (new things held).
    A person's call, like any Approve. A plan already in places/ is never written over."""
    _person(who, "approving a floor plan as a stage")
    from ..layout import store
    top, pset = store.load_set(Path(folder))
    if pset.get("problems"):
        raise ThreeDRefused("it still has problems: " + "; ".join(pset["problems"][:3]))
    pl = placemod.from_town(top.layout_record(), top.grid.c, dict(pset.get("sheet") or {}), 1.0, top.entities)
    pid = world.slug(str(pl.get("id") or pset.get("place") or "place"))
    dest = places_dir(cfg, gid) / f"{pid}.place.json"
    if dest.exists():
        raise ThreeDRefused(f"{rel(cfg, dest)} already exists — a place plan is never written over; compile it from 3D → Places")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(pl, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [f"Wrote {rel(cfg, dest)}: {len(pl.get('things') or [])} buildings, {len(pl.get('ground') or [])} ground pieces."]
    adp = _adapter(cfg, gid)
    inst = getattr(adp, "stage_install", None) if adp is not None else None
    if callable(inst):
        try:
            lines.extend(inst(pid, pl, who) or [])
        except Exception as e:  # noqa: BLE001 — the plan is written; say what didn't follow
            lines.append(f"the game's stage map wasn't written ({type(e).__name__}: {e})")
    else:
        lines.append("this game's adapter can't write a stage map yet (no stage_install) — the plan is ready to compile")
    try:
        r = compile_again(cfg, gid, pid, who)
        lines.append(r["message"])
    except ThreeDRefused as e:
        lines.append(f"not compiled: {e}")
    for u in pl.get("unknowns") or []:
        lines.append("ask: " + u)
    _sign(cfg, gid, who, "approve", f"3d:place:{pid}", note=f"approved {Path(folder).name} as a stage")
    return {"ok": True, "place": pid, "lines": lines, "message": " ".join(lines[:3])}


def act(cfg: dict, gid: str, action: str, body: dict, who: str | None) -> dict:
    pid = str(body.get("place") or "")
    try:
        if action == "threed_places_compile":
            return compile_again(cfg, gid, pid, who)
        if action == "threed_places_play":
            return play(cfg, gid, pid, str(body.get("time") or ""), who)
        if action == "threed_places_pictures":                       # BUILD 63
            looks = body.get("looks")
            return take_pictures(cfg, gid, pid, who, looks if isinstance(looks, list) else None)
        if action == "threed_places_draw":
            _place_file(cfg, gid, pid)
            pic = pictures_dir(cfg, gid) / f"{world.slug(pid)}.png"
            if pic.exists():
                pic.unlink()
            view(cfg, gid)
            return {"ok": True, "message": f"{pid}: drawn again from its plan."}
    except ThreeDRefused as e:
        return {"ok": False, "message": str(e)}
    except world.WorldError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": False, "message": f"unknown action {action}"}
