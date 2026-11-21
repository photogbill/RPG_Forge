"""Icons and portraits from the models (BUILD 91): the pictures a game needs of its things and its people, taken from
the 3D models the world queue has already made — not painted separately, so a thing looks like itself everywhere.

    python -m forge.threed.modelpics icons | portraits | all | sheets  [--game <id>] [--only <id> …] [--again]

icon      (job type model_icon) a made thing on a clear background, 512, three-quarter view, one fixed key light — the
          same view rule and the same light for every thing (forge/threed/blender/picture_model.py says the rule).
portrait  (job type model_portrait) a made body's head and shoulders, at rest (its idle motion's first frame, the head
          set upright), smooth-shaded, lit by one warm key close to the face with a faint rim behind — and once more
          for every expression the body carries, if it carries any.

Both are rendered by Blender's Cycles on the PROCESSOR: no graphics card, no ComfyUI, nothing the queue is using. So
they may run while the world queue runs.

What a game says, in games/<id>/pictures/ (proposal files — nothing here approves anything or changes a game's data):
    items_to_models.json   {"items_file": "<the game's items>", "items": {"<item id>": {"world": "<world-list id>" | null,
                            "fit": "exact" | "near", "note": "…"}}, "also": ["<world id>", …]}
    portraits.json         {"portraits": {"<name>": {"world": "<body id>" | "model": "<a .glb>", "rim": [r, g, b]}}}
The commands picture what is made, list what is on the world list but not made yet, and list what has no model at all
(for whoever keeps the world list). Results: out/pictures/<game>/ — icons/, portraits/, the sheets, MISSING.md.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from pathlib import Path

from PIL import Image, ImageDraw

from .. import config as cfgmod

log = logging.getLogger("forge.modelpics")
SCRIPT = "picture_model.py"
PANEL = (38, 38, 44)


class PictureError(Exception):
    pass


# ------------------------------------------------------------------ one picture
def _python(cfg: dict | None):
    """A Python with Blender inside it to use instead of the forge's own Blender: forge.json threed.blender_python (tests),
    or the environment's FORGE_BLENDER_PYTHON (a computer whose Blender is a Python module)."""
    import os
    return ((cfg or {}).get("threed") or {}).get("blender_python") or os.environ.get("FORGE_BLENDER_PYTHON") or None


def shrink(src: Path, dst: Path, size: int) -> Image.Image:
    """The render (made at twice the size) down to `size`, with its see-through edge kept clean (no dark fringe)."""
    im = Image.open(src).convert("RGBA")
    if im.size != (size, size):
        im = im.convert("RGBa").resize((size, size), Image.LANCZOS).convert("RGBA")
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst)
    return im


def picture(cfg: dict | None, model: Path, out: Path, name: str, spec: dict, size: int, minutes: float = 15.0,
            python=None) -> tuple[Image.Image, dict]:
    """Run the Blender script for one picture and bring it to its size. Returns (the picture, what the script said)."""
    from .env import from_cfg, run_blender
    model = Path(model)
    if not model.is_file():
        raise FileNotFoundError(f"model not found: {model}")
    raw = out / f"_{name}_raw.png"
    full = {**spec, "model": str(model), "out": str(raw), "pixels": int(size) * 2}
    sp = out / f"_{name}_spec.json"
    sp.write_text(json.dumps(full, indent=1), encoding="utf-8")
    code, lines = run_blender(from_cfg(cfg), SCRIPT, [str(sp)], minutes=minutes, log=None, python=python or _python(cfg))
    said = next((ln for ln in reversed(lines) if ln.startswith("PICTURE ")), None)
    if code == -2:
        raise PictureError(lines[-1] if lines else "no Blender here")
    if code == -1:
        raise PictureError(f"Blender took longer than {minutes:g} minutes on {model.name} and was stopped")
    if said is None:
        raise PictureError(f"Blender ended (code {code}) without a picture of {model.name}: " + " | ".join(lines[-4:])[:600])
    info = json.loads(said[8:])
    if not info.get("ok") or not raw.is_file():
        raise PictureError(f"no picture of {model.name}: {info.get('error') or 'the file was not written'}")
    img = shrink(raw, out / f"{name}.png", int(size))
    try:
        raw.unlink()
    except OSError:
        pass
    return img, info


def covered(img: Image.Image) -> float:
    """How much of the frame the thing fills (0..1) — an icon that fills a twentieth of its square was framed badly."""
    a = img.getchannel("A")
    box = a.point(lambda v: 255 if v > 24 else 0).getbbox()
    if not box:
        return 0.0
    return round(max(box[2] - box[0], box[3] - box[1]) / float(max(img.size)), 3)


def on_panel(img: Image.Image, cell: int, bg=PANEL) -> Image.Image:
    out = Image.new("RGBA", (cell, cell), bg + (255,))
    out.alpha_composite(img.resize((cell, cell), Image.LANCZOS) if img.size != (cell, cell) else img)
    return out.convert("RGB")


def _licences(cfg, root: Path, job: dict) -> tuple[list[str], bool | None, dict]:
    """The licence lines of the model a picture was taken from, read from the world queue's own record of it."""
    game, wid = job.get("game"), job.get("world_id")
    if not (game and wid):
        return [], None, {}
    try:
        from . import licences, world
        st = world.read_state(cfg, str(game), str(wid))
        keys = world.licence_keys(st)
        return licences.lines(keys), licences.all_ok(keys), {"try": st.get("try"), "engine": st.get("engine"), "licence_keys": keys}
    except Exception as e:  # noqa: BLE001
        return [f"licences not read ({e})"], None, {}


def _resolve(root: Path, p) -> Path:
    q = Path(str(p))
    return q if q.is_absolute() else Path(root) / q


def icon_job(job: dict, ctx, out: Path, python=None) -> dict:
    """The model_icon job handler."""
    from ..jobs.common import save_png, write_prov
    out = Path(out)
    cfg = getattr(ctx, "cfg", None)
    root = Path(getattr(ctx, "root", None) or cfgmod.ROOT)
    size = int(job.get("size") or 512)
    slot = str(job.get("slot_name") or "icon")
    spec = {"kind": "icon", "samples": int(job.get("samples") or 40), "az": float(job.get("az", 35.0)), "el": float(job.get("el", 22.0)),
            "auto_view": bool(job.get("auto_view", True)), "margin": float(job.get("margin", 0.07)), "light": job.get("light") or {}}
    img, info = picture(cfg, _resolve(root, job["model"]), out, slot, spec, size, float(job.get("minutes") or 15), python)
    fill = covered(img)
    notes = []
    if fill < 0.35:
        notes.append(f"the thing fills only {fill:.0%} of its square: give this one its own `az` / `el`")
    small = img.resize((64, 64), Image.LANCZOS)
    sheet = Image.new("RGB", (512 * 2 + 96, 512), PANEL)
    sheet.paste(on_panel(img, 512), (0, 0))
    sheet.paste(on_panel(img, 512, (214, 210, 200)), (512, 0))
    sheet.paste(on_panel(small, 64), (1024 + 16, 16))
    sheet.paste(on_panel(small.resize((32, 32), Image.LANCZOS), 32), (1024 + 32, 112))
    save_png(sheet, out / "contact.png")
    lines, ok, rec = _licences(cfg, root, job)
    write_prov(out, job, op="model_icon", model=str(job["model"]), world_id=job.get("world_id"), view=info.get("view"),
               light=info.get("light"), size=size, blender=info.get("blender"), licences_lines=lines, commercial_ok=ok,
               fills=fill, notes=notes, **rec)
    return {"outputs": [f"{slot}.png", "contact.png"], "view": info.get("view"), "fills": fill, "size_m": info.get("size_m"),
            "seconds_blender": info.get("seconds"), "notes": notes, "commercial_ok": ok}


def portrait_job(job: dict, ctx, out: Path, python=None) -> dict:
    """The model_portrait job handler."""
    from ..jobs.common import save_png, write_prov
    out = Path(out)
    cfg = getattr(ctx, "cfg", None)
    root = Path(getattr(ctx, "root", None) or cfgmod.ROOT)
    size = int(job.get("size") or 768)
    slot = str(job.get("slot_name") or "portrait")
    light = {"preset": "candle", **(job.get("light") or {})}
    if job.get("rim"):
        light["rim"] = list(job["rim"])
    spec = {"kind": "portrait", "samples": int(job.get("samples") or 48), "az": float(job.get("az", 14.0)), "el": float(job.get("el", 2.0)),
            "margin": float(job.get("margin", 0.06)), "light": light, "clip": job.get("clip") or "Idle_Loop", "frame": int(job.get("frame") or 0),
            "level_head": bool(job.get("level_head", True)), "smooth": bool(job.get("smooth", True))}
    model = _resolve(root, job["model"])
    img, info = picture(cfg, model, out, slot, spec, size, float(job.get("minutes") or 15), python)
    outputs, tiles, labels = [f"{slot}.png"], [on_panel(img, 384, (14, 14, 18))], ["at rest"]
    notes = []
    if not info.get("armature"):
        notes.append("this body has no skeleton: it is pictured as it was built")
    elif not info.get("motion_used"):
        notes.append("this body has no idle motion: it is pictured as it was built (arms as modelled)")
    want = job.get("expressions")
    exprs = [e for e in (info.get("expressions") or []) if want in (None, True) or (isinstance(want, list) and e in want)][:12] if want is not False else []
    for e in exprs:
        safe = "".join(ch if ch.isalnum() else "_" for ch in e).strip("_").lower() or "expression"
        im2, _ = picture(cfg, model, out, f"{slot}_{safe}", {**spec, "shape_key": e}, size, float(job.get("minutes") or 15), python)
        outputs.append(f"{slot}_{safe}.png")
        tiles.append(on_panel(im2, 384, (14, 14, 18)))
        labels.append(e)
    if not info.get("expressions"):
        notes.append("the body carries no expressions (none were modelled on it): at rest only")
    from ..ops import sheet as sh
    save_png(sh.contact_sheet(tiles, labels, cols=min(4, len(tiles)), cell=(384, 384), title=str(job.get("name") or slot)), out / "contact.png")
    lines, ok, rec = _licences(cfg, root, job)
    write_prov(out, job, op="model_portrait", model=str(job["model"]), world_id=job.get("world_id"), view=info.get("view"),
               light=light, motion=info.get("motion_used"), framed_by=info.get("framed_by"), expressions=info.get("expressions"),
               size=size, blender=info.get("blender"), licences_lines=lines, commercial_ok=ok, notes=notes, **rec)
    return {"outputs": outputs + ["contact.png"], "motion": info.get("motion_used"), "framed_by": info.get("framed_by"),
            "expressions": info.get("expressions") or [], "seconds_blender": info.get("seconds"), "notes": notes, "commercial_ok": ok}


# ------------------------------------------------------------------ sheets
def _font(n: int):
    from ..ops.sheet import _font as f
    return f(n)


def _ascii(t: str) -> str:
    from ..ops.sheet import _ascii as f
    return f(t)


def sheet(rows: list[dict], title: str, cell: int = 192, cols: int = 8, bg=PANEL, foot: list[str] | None = None) -> Image.Image:
    """A labelled grid: each row {"image": Image | None, "label": str, "sub": str, "flag": "near" | "missing" | ""}."""
    pad, lab = 8, 34
    n = max(1, len(rows))
    cols = min(cols, n)
    lines = (n + cols - 1) // cols
    W = pad + cols * (cell + pad)
    foot = foot or []
    H = 34 + lines * (cell + lab + pad) + pad + 18 * len(foot)
    im = Image.new("RGB", (W, H), (22, 22, 26))
    dr = ImageDraw.Draw(im)
    dr.text((pad, 8), _ascii(title), font=_font(16), fill=(235, 230, 215))
    for i, r in enumerate(rows):
        x = pad + (i % cols) * (cell + pad)
        y = 34 + (i // cols) * (cell + lab + pad)
        if r.get("image") is not None:
            im.paste(on_panel(r["image"], cell, bg), (x, y))
        else:
            dr.rectangle([x, y, x + cell - 1, y + cell - 1], outline=(90, 70, 60))
            dr.text((x + 10, y + cell // 2 - 8), _ascii(r.get("why", "not made yet"))[: cell // 7], font=_font(12), fill=(170, 130, 110))
        colour = {"near": (240, 190, 90), "missing": (200, 140, 120)}.get(r.get("flag") or "", (215, 215, 220))
        dr.text((x + 2, y + cell + 2), _ascii(r.get("label", ""))[: cell // 7 + 2], font=_font(12), fill=colour)
        dr.text((x + 2, y + cell + 17), _ascii(r.get("sub", ""))[: cell // 6 + 2], font=_font(11), fill=(150, 150, 160))
    for k, ln in enumerate(foot):
        dr.text((pad, H - 18 * (len(foot) - k) - 2), _ascii(ln)[: W // 6], font=_font(12), fill=(170, 180, 170))
    return im


# ------------------------------------------------------------------ the commands
def _setup_log(cfg: dict) -> Path:
    p = cfgmod.path_of(cfg, "logs") / "pictures.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(p, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger("forge").addHandler(h)
    logging.getLogger("forge").setLevel(logging.INFO)
    return p


def run_batch(cfg: dict, jobs: list[dict], batch: str, python=None) -> list[dict]:
    """Queue `jobs` under `batch` and run that batch here, in this window: the art worker is not started, stopped or
    fed, and other people's waiting jobs stay where they are."""
    from .. import schema
    from ..jobs.common import Context
    from ..queue import Queue
    handlers = {"model_icon": icon_job, "model_portrait": portrait_job}
    schema.validate({"type": "model_icon", "model": "x.glb"})            # the schema learns the plug-in's types
    q = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))
    for j in jobs:
        q.submit({**j, "batch": batch})
    ctx = Context(cfg=cfg, palettes_dir=cfgmod.path_of(cfg, "palettes"), root=cfgmod.ROOT)
    rows = []
    while True:
        got = q.claim(lambda job: job.get("batch") == batch and job.get("type") in handlers and not job.get("tombstone"))
        if got is None:
            return rows
        jid, job = got
        job = schema.with_defaults(job)
        t0 = time.time()
        print(f"  {time.strftime('%H:%M:%S')}  {job.get('name')} ...", end=" ", flush=True)
        try:
            res = handlers[job["type"]](job, ctx, q.out_dir(jid), python) or {}
            res["seconds"] = round(time.time() - t0, 1)
            q.finish(jid, result=res)
            rows.append({"id": jid, "name": job.get("name"), "ok": True, "result": res, "job": job})
            print(f"done in {res['seconds']:.0f} s", flush=True)
        except Exception as e:  # noqa: BLE001
            q.finish(jid, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc())
            rows.append({"id": jid, "name": job.get("name"), "ok": False, "error": f"{type(e).__name__}: {e}", "job": job})
            print("FAILED\n      " + str(e)[:800], flush=True)
            log.error("FAILED %s: %s", job.get("name"), e)


def made_model(cfg: dict, game: str, wid: str) -> tuple[Path | None, str]:
    """(the made model of a world-list id, or None; its state in plain words)."""
    from . import world
    st = world.read_state(cfg, game, wid)
    state = st.get("state")
    if state == "made" and st.get("model") and (cfgmod.ROOT / st["model"]).is_file():
        return cfgmod.ROOT / st["model"], "made"
    if not st:
        on_list = any(e.get("id") == wid for e in world.load(cfg, game)[0])
        return None, "on the world list, not made yet" if on_list else "not on the world list"
    return None, {"held": "made, but held by a check", "failed": "tried and failed", "making": "being made now"}.get(state or "", "on the world list, not made yet")


def _stale(dest: Path, model: Path) -> bool:
    side = dest.with_suffix(".json")
    try:
        return json.loads(side.read_text(encoding="utf-8")).get("model_mtime") != int(model.stat().st_mtime) or not dest.is_file()
    except (OSError, ValueError):
        return True


def _keep(cfg: dict, row: dict, dest: Path, model: Path, extra: dict) -> None:
    """Copy a finished picture into the game's stable folder under out/pictures, with a note of what it was taken from."""
    src = cfgmod.path_of(cfg, "out") / row["id"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for f in row["result"]["outputs"]:
        if f == "contact.png":
            continue
        tail = f[len(row["job"]["slot_name"]):]
        Image.open(src / f).save(dest.with_name(dest.stem + tail))
        files.append(dest.stem + tail)
    dest.with_suffix(".json").write_text(json.dumps({"model": str(model), "model_mtime": int(model.stat().st_mtime), "job": row["id"], "files": files,
                                                     **extra, **{k: row["result"].get(k) for k in ("view", "fills", "motion", "expressions", "notes")}},
                                                    indent=1), encoding="utf-8")


def cmd_icons(cfg: dict, game: str, args) -> dict:
    gdir = cfgmod.path_of(cfg, "games") / game / "pictures"
    table = json.loads((gdir / "items_to_models.json").read_text(encoding="utf-8"))
    items_file = Path(table.get("items_file") or "")
    items = json.loads(items_file.read_text(encoding="utf-8")) if items_file.is_file() else {}
    dest = cfgmod.path_of(cfg, "out") / "pictures" / game
    jobs, plan = [], {}
    wanted = dict(table.get("items") or {})
    for wid in table.get("also") or []:
        wanted[f"+{wid}"] = {"world": wid, "fit": "also"}
    for iid, m in wanted.items():
        if args.only and iid.lstrip("+") not in args.only:
            continue
        wid = m.get("world")
        name = (items.get(iid) or {}).get("name") or iid.lstrip("+")
        if not wid:
            plan[iid] = {"name": name, "state": "no model", "note": m.get("note"), "group": m.get("group")}
            continue
        model, state = made_model(cfg, game, wid)
        target = dest / ("also" if iid.startswith("+") else "icons") / f"{iid.lstrip('+')}.png"
        plan[iid] = {"name": name, "world": wid, "fit": m.get("fit"), "state": state, "note": m.get("note"), "file": str(target) if model else None}
        if model is not None and (args.again or _stale(target, model)):
            jobs.append({"type": "model_icon", "name": f"icon_{iid.lstrip('+')}"[:48], "model": str(model), "world_id": wid, "game": game,
                         "slot_name": iid.lstrip("+"), "size": int(table.get("size") or 512), **{k: m[k] for k in ("az", "el", "auto_view", "margin") if k in m},
                         "_dest": str(target), "_item": iid})
    print(f"{len(jobs)} icon(s) to take ({sum(1 for p in plan.values() if p.get('file')) - len(jobs)} already taken from the model as it is now)", flush=True)
    for r in run_batch(cfg, jobs, "pictures/icons", _python(cfg)):
        if r["ok"]:
            _keep(cfg, r, Path(r["job"]["_dest"]), Path(r["job"]["model"]), {"item": r["job"]["_item"], "world": r["job"].get("world_id")})
        else:
            plan[r["job"]["_item"]]["error"] = r["error"][:300]
    return plan


def cmd_portraits(cfg: dict, game: str, args) -> dict:
    gdir = cfgmod.path_of(cfg, "games") / game / "pictures"
    table = json.loads((gdir / "portraits.json").read_text(encoding="utf-8"))
    dest = cfgmod.path_of(cfg, "out") / "pictures" / game / "portraits"
    jobs, plan = [], {}
    for name, m in (table.get("portraits") or {}).items():
        if args.only and name not in args.only:
            continue
        if m.get("model"):
            model = Path(m["model"]) if Path(m["model"]).is_absolute() else cfgmod.ROOT / m["model"]
            model, state = (model, "made") if model.is_file() else (None, "its file is not there")
        elif m.get("world"):
            model, state = made_model(cfg, game, m["world"])
        else:
            model, state = None, "no body named"
        target = dest / f"{name}.png"
        plan[name] = {"world": m.get("world"), "state": state, "note": m.get("note"), "fit": m.get("fit"), "file": str(target) if model else None}
        if model is not None and (args.again or _stale(target, model)):
            jobs.append({"type": "model_portrait", "name": f"portrait_{name}"[:48], "model": str(model), "world_id": m.get("world"), "game": game,
                         "slot_name": name, "size": int(table.get("size") or 768),
                         **{k: m[k] for k in ("rim", "light", "clip", "frame", "az", "el", "level_head", "below_chin") if k in m},
                         "_dest": str(target), "_item": name})
    print(f"{len(jobs)} portrait(s) to take", flush=True)
    for r in run_batch(cfg, jobs, "pictures/portraits", _python(cfg)):
        if r["ok"]:
            _keep(cfg, r, Path(r["job"]["_dest"]), Path(r["job"]["model"]), {"portrait": r["job"]["_item"], "world": r["job"].get("world_id")})
        else:
            plan[r["job"]["_item"]]["error"] = r["error"][:300]
    return plan


def portrait_rows(portraits: dict) -> list[dict]:
    """The portraits sheet's rows: each name once, then the expressions ITS OWN note names (never a guess from
    the file names: `hero_boy` is another portrait, not an expression of `hero`), and an empty place for a name
    with no made body."""
    rows = []
    for name, p in portraits.items():
        f = Path(p["file"]) if p.get("file") else None
        if f is None or not f.is_file():
            rows.append({"image": None, "label": name, "sub": str(p.get("world") or ""), "flag": "missing", "why": p.get("state") or "not made yet"})
            continue
        rows.append({"image": Image.open(f), "label": name, "sub": str(p.get("world") or "its own file") + (" - near" if p.get("fit") == "near" else ""),
                     "flag": "near" if p.get("fit") == "near" else ""})
        try:
            extras = [x for x in json.loads(f.with_suffix(".json").read_text(encoding="utf-8")).get("files", []) if x != f.name]
        except (OSError, ValueError):
            extras = []
        for extra in extras:
            if (f.parent / extra).is_file():
                rows.append({"image": Image.open(f.parent / extra), "label": Path(extra).stem, "sub": "an expression the body carries", "of": name})
    return rows


def write_sheets(cfg: dict, game: str, icons: dict | None, portraits: dict | None) -> list[Path]:
    """The sheets and MISSING.md from what the commands found. Returns the files written."""
    dest = cfgmod.path_of(cfg, "out") / "pictures" / game
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    when = time.strftime("%Y-%m-%d %H:%M")
    if icons is not None:
        made = [(i, p) for i, p in icons.items() if p.get("file") and Path(p["file"]).is_file() and not i.startswith("+")]
        also = [(i, p) for i, p in icons.items() if p.get("file") and Path(p["file"]).is_file() and i.startswith("+")]
        waiting = [(i, p) for i, p in icons.items() if p.get("world") and not (p.get("file") and Path(p["file"]).is_file())]
        none = [(i, p) for i, p in icons.items() if not p.get("world")]
        total = len([i for i in icons if not i.startswith("+")])
        if made:
            rows = [{"image": Image.open(p["file"]), "label": p["name"], "sub": f"{p['world']}" + (" - near" if p.get("fit") == "near" else ""),
                     "flag": "near" if p.get("fit") == "near" else ""} for i, p in made]
            s = sheet(rows, f"Icons taken from the made models: {len(made)} of {total} items ({when})", cols=6,
                      foot=["amber = near: the made thing stands in for the item until its own is on the world list",
                            f"{len(waiting)} more have a thing on the world list that is not made yet; {len(none)} have no model at all (MISSING.md)"])
            s.save(dest / "icons_sheet.png")
            written.append(dest / "icons_sheet.png")
        if also:
            rows = [{"image": Image.open(p["file"]), "label": i.lstrip("+"), "sub": "made; no item of its own"} for i, p in also]
            s = sheet(rows, f"Made things a hand could hold, as icons: {len(also)} (no item in the game's data names them)", cols=6)
            s.save(dest / "icons_also_sheet.png")
            written.append(dest / "icons_also_sheet.png")
        lines = [f"# Icons: what cannot be taken yet - {when}", "",
                 f"{total} items. **{len(made)}** have an icon from a made model. **{len([w for w in waiting if not w[0].startswith('+')])}** name a thing on the world list that is "
                 f"not made yet. **{len(none)}** have no model at all.", "", "## On the world list, not made yet (the icon comes by itself once it is made: run the command again)", ""]
        lines += [f"- `{i}` ({p['name']}) -> `{p['world']}`: {p['state']}" + (f" [{p['fit']}]" if p.get("fit") else "") + (f" - {p['note']}" if p.get("note") else "")
                  for i, p in waiting if not i.startswith("+")] or ["- none"]
        lines += ["", "## No model at all (for whoever keeps the world list)", ""]
        groups: dict[str, list] = {}
        for i, p in none:
            groups.setdefault(p.get("group") or "one of its own", []).append((i, p))
        for g in sorted(groups, key=lambda k: (k == "one of its own", k)):
            lines.append(f"**{g}**" + (f" - {len(groups[g])} items" if g != "one of its own" else ""))
            lines += [f"- `{i}` ({p['name']})" + (f" - {p['note']}" if p.get("note") else "") for i, p in groups[g]]
            lines.append("")
        failed = [(i, p) for i, p in icons.items() if p.get("error")]
        if failed:
            lines += ["## Tried and failed", ""] + [f"- `{i}`: {p['error']}" for i, p in failed]
        (dest / "MISSING.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (dest / "icons.json").write_text(json.dumps(icons, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        written += [dest / "MISSING.md", dest / "icons.json"]
    if portraits is not None:
        rows = portrait_rows(portraits)
        have = sum(1 for r in rows if r["image"] is not None and not r.get("of"))
        s = sheet(rows, f"Portraits from the made bodies: {have} taken, {sum(1 for r in rows if r['image'] is None)} waiting for a body ({when})", cell=256, cols=6, bg=(14, 14, 18),
                  foot=["head and shoulders, at rest, one warm key and a faint rim (red: no body is made for that name yet)"])
        s.save(dest / "portraits_sheet.png")
        (dest / "portraits.json").write_text(json.dumps(portraits, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        written += [dest / "portraits_sheet.png", dest / "portraits.json"]
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m forge.threed.modelpics", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["icons", "portraits", "all"])
    ap.add_argument("--game", default=None)
    ap.add_argument("--only", action="append", help="an item id (icons) or a portrait name")
    ap.add_argument("--again", action="store_true", help="take every picture again, even one taken from the model as it is now")
    args = ap.parse_args(argv)
    cfg = cfgmod.load()
    cfgmod.ensure_dirs(cfg)
    logfile = _setup_log(cfg)
    game = args.game or cfgmod.default_game(cfg)
    try:
        icons = cmd_icons(cfg, game, args) if args.command in ("icons", "all") else None
        ports = cmd_portraits(cfg, game, args) if args.command in ("portraits", "all") else None
        for f in write_sheets(cfg, game, icons, ports):
            print(f"  {f}")
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("pictures failed: %s\n%s", e, traceback.format_exc())
        print(f"\nIt stopped: {e}\nThe whole story is in {logfile}. Tell Claude what this says.")
        return 3


if __name__ == "__main__":
    sys.exit(main())
