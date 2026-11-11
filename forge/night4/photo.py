"""photo_plate (Night 4, F6): one of William's photographs → a painted plate that lights like any painted scene.

The photograph is referenced by PATH — never copied into the repo (games/<game>/REFERENCES.md). The people guard: a
frame goes through only if the git-ignored games/<game>/refs.local.json lists it with `people: none` or
`people: william` (his cameo ruling, 2026-11-09); anything else refuses and says to pick another frame or mask the
person first. Choosing the frames is Fable's and William's.

    refs.local.json  {"frames": {"D:\\\\Iraq\\\\IMG_0412.jpg": {"people": "none", "note": "smoke front over the tents"}}}

Then: cover-fit to `target` (a working copy in the job's own out folder — git-ignored, never pushed), img2img on the
scene checkpoint with ControlNet canny or depth from the photo, and — `companions: true` — the kit's depth, normals,
glow and layers (a scene_kit with the photo as its init)."""
from __future__ import annotations
import json
import logging
from pathlib import Path

from PIL import Image, ImageOps

from .. import config as cfgmod
from ..jobs.common import Context, save_png, write_prov

log = logging.getLogger("forge.photo")
ALLOWED = ("none", "william")


class PeopleGuard(PermissionError):
    pass


def refs_path(cfg: dict, game: str) -> Path:
    return cfgmod.path_of(cfg, "games") / game / "refs.local.json"


def guard(cfg: dict, game: str, photo: Path) -> dict:
    p = refs_path(cfg, game)
    if not p.exists():
        raise PeopleGuard(f"no {p.name} — list the frame there first with people: none or people: william "
                          "(the forge never uses a photograph of anyone else)")
    frames = json.loads(p.read_text(encoding="utf-8")).get("frames") or {}
    key = {str(Path(k)).lower(): v for k, v in frames.items()}
    rec = key.get(str(photo).lower()) or key.get(str(Path(photo).resolve()).lower())
    if rec is None:
        raise PeopleGuard(f"{photo} is not listed in {p.name} — add it with people: none (or william) after checking it")
    who = str(rec.get("people", "")).strip().lower()
    if who not in ALLOWED:
        raise PeopleGuard(f"{Path(photo).name}: people = '{rec.get('people')}' — only frames with no one in them, or "
                          "only William (his cameo), may be used. Pick another frame or mask the person out first.")
    return rec


def run(job: dict, ctx: Context, out: Path) -> dict:
    from ..jobs import get_handlers
    out = Path(out)
    game = job.get("game") or cfgmod.default_game(ctx.cfg)          # W9: the engine names no game
    photo = Path(str(job["photo"]))
    if not photo.is_absolute():
        photo = ctx.resolve(photo)
    if not photo.exists():
        raise FileNotFoundError(f"photograph not found: {photo}")
    rec = guard(ctx.cfg, game, photo)
    tw, th = [int(v) for v in (job.get("target") or [1920, 1080])]
    with Image.open(photo) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        fitted = ImageOps.fit(im, (tw, th), Image.LANCZOS)
    work = out / "_photo_fitted.png"                     # working copy in this job's (git-ignored) out folder
    save_png(fitted, work)
    ctrl = {"type": str(job.get("control") or "canny"), "strength": float(job.get("control_strength") or 0.5)}
    keys = ("prompt", "negative", "checkpoint", "loras", "seed", "steps", "cfg", "sampler", "scheduler", "graph", "game")
    base = {k: job[k] for k in keys if job.get(k) is not None}
    handlers = get_handlers()
    if job.get("companions", True):
        sub = {**base, "type": "scene_kit", "id": f"{job.get('id')}_kit", "name": job.get("name") or "plate",
               "init": str(work), "denoise": float(job.get("denoise") or 0.55), "control": ctrl, "target": [tw, th]}
        res = handlers["scene_kit"](sub, ctx, out)
    else:
        sub = {**base, "type": "repaint", "id": f"{job.get('id')}_paint", "init": str(work),
               "denoise": float(job.get("denoise") or 0.55), "control": ctrl, "target": [tw, th]}
        res = handlers["repaint"](sub, ctx, out)
    prov = json.loads((out / "prov.json").read_text(encoding="utf-8")) if (out / "prov.json").exists() else {}
    write_prov(out, job, **{k: v for k, v in prov.items() if k not in ("job_id", "type", "name", "batch", "created", "prompt", "negative", "op")},
               kit_op=prov.get("op"),
               op="photo_plate", source_photo={"what": "William's own photograph", "path": str(photo),
                                               "people": rec.get("people"), "note": rec.get("note"),
                                               "copied_into_repo": False},
               photo_fitted_to=[tw, th], control=ctrl)
    log.info("photo_plate %s from %s (people: %s)", job.get("id"), photo.name, rec.get("people"))
    return {**res, "photo": str(photo), "people": rec.get("people")}
