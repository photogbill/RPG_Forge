"""Handlers of the 3D job types (specs.py). Each one: callable(job, ctx, out_dir) -> result dict; a failure raises with
the reason in words (the queue writes it into the failed job). Each writes run.log (everything it said), prov.json
(what made the output) and report.json in the job's own folder.

Loaded lazily by forge/plugins/threed.py (never at the worker's start), so a fix here reaches a running worker.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from . import bodies, glb, licences, motions, rig, tidy, trees
from .env import from_cfg

log = logging.getLogger("forge.threed.jobs")
DEFAULTS = json.loads((Path(__file__).with_name("defaults.json")).read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------ helpers
class _JobLog:
    """Everything the 3D code says during one job also goes to <out>/run.log."""

    def __init__(self, out: Path):
        self.h = logging.FileHandler(Path(out) / "run.log", encoding="utf-8")
        self.h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
        self.lg = logging.getLogger("forge.threed")

    def __enter__(self):
        Path(self.h.baseFilename).parent.mkdir(parents=True, exist_ok=True)
        self.lg.addHandler(self.h)
        if self.lg.level == logging.NOTSET or self.lg.level > logging.INFO:
            self.lg.setLevel(logging.INFO)
        return self

    def __exit__(self, *exc):
        self.lg.removeHandler(self.h)
        self.h.close()


def resolve(root: Path, p: str | None) -> Path | None:
    if not p:
        return None
    q = Path(str(p).replace("\\", "/"))
    return q if q.is_absolute() else Path(root) / q


def rel(root: Path, p: Path) -> str:
    try:
        return Path(p).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return str(p)


def words(cfg: dict, game: str | None, kind: str, which: str) -> str:
    """The standing 'always' or negative words for a kind: the game's block when it has one, else the forge's."""
    k = DEFAULTS["kinds"].get(kind) or DEFAULTS["kinds"]["body"]
    block = k[which]
    if game:
        try:
            from .. import prompts
            lib = prompts.load(cfg, game)
            if block in lib["blocks"] and "TODO" not in lib["blocks"][block]:
                return prompts.expand_text(lib["blocks"][block], lib["blocks"])
        except Exception as e:  # noqa: BLE001 — a library that doesn't load falls back to the forge's words, said in the log
            log.warning("the prompt library of %s did not load (%s) - using the forge's standing words", game, e)
    return DEFAULTS["blocks"][block]


def _url(ctx, cfg) -> str:
    c = getattr(ctx, "comfy", None)
    return getattr(c, "url", None) or ((cfg or {}).get("comfy") or {}).get("url") or "http://127.0.0.1:8188"


def _write(out: Path, name: str, data) -> Path:
    p = Path(out) / name
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


def _blender_python(cfg: dict | None):
    """Tests may name a stand-in for Blender's Python (forge.json threed.blender_python, a list or a path)."""
    return ((cfg or {}).get("threed") or {}).get("blender_python") or None


# ------------------------------------------------------------------------------------------------ model_3d
def model_3d(job: dict, ctx, out: Path) -> dict:
    cfg, root, out = ctx.cfg, Path(ctx.root), Path(out)
    with _JobLog(out):
        kind = str(job.get("kind") or "body")
        model = job.get("model") or DEFAULTS["kinds"].get(kind, DEFAULTS["kinds"]["body"])["model"]
        name = job.get("name") or "model"
        game = job.get("game")
        always = job["always"] if job.get("always") is not None else words(cfg, game, kind, "always")
        negative = job["negative"] if job.get("negative") is not None else words(cfg, game, kind, "negative")
        obj = {"id": name, "prompt": str(job.get("prompt") or ""), "always": always, "negative": negative,
               "seed": int(job.get("seed") if job.get("seed") is not None else 1001)}
        if job.get("image"):
            img = resolve(root, job["image"])
            if not img or not img.exists():
                raise FileNotFoundError(f"the picture {job['image']} is not there")
            obj["image"] = str(img)
        elif not obj["prompt"].strip():
            raise ValueError("a model_3d job needs a picture (`image`) or a description (`prompt`)")
        if job.get("seed3d") is not None:
            obj["seed3d"] = int(job["seed3d"])
        spec = {"batch": out.name, "models": [model], "resolutions": [int(r) for r in (job.get("resolutions") or [1024])],
                "faces": int(job.get("faces") or 60000), "texture": int(job.get("texture") or 2048),
                "minutes_per_model": int(job.get("minutes") or 60),
                "picture": {"unet": job.get("unet") or bodies.DEFAULT_UNET, "size": int(job.get("size") or 1024),
                            "seed": obj["seed"], "always": always, "negative": negative},
                "objects": [obj]}
        comfy_out = root / "out" / "_comfy"
        rows = bodies.run(cfg, spec, out, url=_url(ctx, cfg), local_out=comfy_out if comfy_out.is_dir() else None,
                          lock_holder=f"model_3d {out.name}")
        row = rows[0] if rows else {}
        if not row.get("ok"):
            raise RuntimeError(f"no 3D model was made: {row.get('error') or 'see run.log'}")
        final = out / f"{name}__{model}.glb"
        os.replace(out / "models" / f"{name}__{model}.glb", final)
        mprov = out / "models" / f"{name}__{model}.prov.json"
        prov = json.loads(mprov.read_text(encoding="utf-8")) if mprov.exists() else {}
        if mprov.exists():
            os.replace(mprov, out / f"{name}__{model}.model_prov.json")
        pic = out / "picture.png"
        if (out / "pictures" / f"{name}.png").exists():
            os.replace(out / "pictures" / f"{name}.png", pic)
        result = {"model": rel(root, final), "picture": rel(root, pic) if pic.exists() else None, "kind": kind, "engine": model,
                  "resolution": row.get("resolution"), "seconds_3d": row.get("seconds")}
        size = job.get("real_size_m") or None
        do_tidy = job.get("tidy")
        if do_tidy is None:
            do_tidy = kind in ("prop", "building") and bool(size)
        if do_tidy:
            raw = out / f"{name}__{model}_raw.glb"
            os.replace(final, raw)
            t = tidy.tidy(from_cfg(cfg), raw, final, scraps=float(job.get("scraps") or 0.02), size=size,
                          python=_blender_python(cfg))
            if t["ok"]:
                result["tidy"] = t["report"]
                prov.setdefault("licences", []).extend(licences.lines(["blender"]))
            else:
                os.replace(raw, final)                    # the untidied model is still worth having
                result["tidy_failed"] = t["error"]
                log.warning("the model was made but not tidied: %s", t["error"])
        result["info"] = glb.info(final)
        prov.update({"job": out.name, "kind": "model_3d", "name": name, "character": job.get("character"),
                     "try_id": job.get("try_id"), "game": game, "file": final.name, "tidy": result.get("tidy"),
                     "real_size_m": size})
        prov.setdefault("commercial_ok", licences.all_ok(["flux2_klein_4b" if not obj.get("image") else None, model, "comfy_template"]))
        _write(out, "prov.json", prov)
        _write(out, "report.json", {**result, "row": row})
        return result


# ------------------------------------------------------------------------------------------------ rig_body
def rig_body(job: dict, ctx, out: Path) -> dict:
    cfg, root, out = ctx.cfg, Path(ctx.root), Path(out)
    with _JobLog(out):
        env = from_cfg(cfg)
        name = job.get("name") or "body"
        kind = str(job.get("kind") or "people")
        src = resolve(root, job["glb"])
        if not src or not src.exists():
            raise FileNotFoundError(f"the body {job['glb']} is not there")
        rigger, weld_first = ("unirig", True) if kind in ("animal", "thing") else ("mia", False)
        body_glb = src
        weld = None
        if weld_first:
            welded = out / f"{name}_welded.glb"
            weld = tidy.weld_for_animal(env, src, welded, python=_blender_python(cfg))
            if not weld["ok"]:
                raise RuntimeError("an animal's seams are welded before UniRig, and the weld failed: " + weld["error"])
            body_glb = welded
        b = {"id": name, "glb": str(body_glb), "kind": kind, "use_normal": bool(job.get("use_normal")),
             "no_fingers": bool(job.get("no_fingers")), "rigger": rigger}
        rows = rig.rig_bodies(cfg, [b], out, env=env, minutes_per_rig=int(job.get("minutes") or 30),
                              lock_holder=f"rig_body {out.name}", art_url=_url(ctx, cfg))
        row = rows[0] if rows else {}
        fbx = out / f"{name}__{rigger}.fbx"
        if not row.get("ok") or not fbx.exists():
            raise RuntimeError(f"no skeleton was made: {row.get('error') or 'see run.log'}")
        prev = out / f"{name}__{rigger}_preview.glb"
        result = {"fbx": rel(root, fbx), "preview": rel(root, prev) if prev.exists() else None, "rigger": rigger, "kind": kind,
                  "orientation": rel(root, out / f"{name}__orientation.png") if (out / f"{name}__orientation.png").exists() else None,
                  "seconds_rig": row.get("rig_seconds"), "welded": (weld or {}).get("report")}
        _write(out, "prov.json", {"job": out.name, "kind": "rig_body", "name": name, "from": job["glb"], "rigger": rigger,
                                  "fingers": not bool(job.get("no_fingers")), "character": job.get("character"),
                                  "try_id": job.get("try_id"), "game": job.get("game"),
                                  "licences": licences.lines([rigger, "comfyui_unirig"] + (["blender"] if weld_first else [])),
                                  "commercial_ok": licences.all_ok([rigger, "comfyui_unirig"])})
        _write(out, "report.json", {**result, "row": row})
        return result


# ------------------------------------------------------------------------------------------------ fit_motions
def fit_motions(job: dict, ctx, out: Path) -> dict:
    cfg, root, out = ctx.cfg, Path(ctx.root), Path(out)
    with _JobLog(out):
        env = from_cfg(cfg)
        name = job.get("name") or "body"
        fbx = resolve(root, job["fbx"])
        lib, trav = motions.library_paths(cfg, root)
        if job.get("library"):
            lib = resolve(root, job["library"])
        if job.get("travel"):
            trav = resolve(root, job["travel"])
        target = out / f"{name}_moves.glb"
        r = motions.fit(env, lib, fbx, target, height=float(job.get("height") or 1.72), travel=trav,
                        skip=list(job.get("skip") or []), clips=list(job.get("clips") or []),
                        minutes=float(job.get("minutes") or 20), python=_blender_python(cfg))
        if not r["ok"]:
            raise RuntimeError(f"the motions were not fitted: {r['error']}")
        sheet = r["sheet"]
        result = {"moves": rel(root, target), "sheet": rel(root, target.with_suffix(".json")), "height_m": sheet.get("height_m"),
                  "motions": sorted((sheet.get("motions") or {}).keys()), "speeds": motions.speeds(sheet),
                  "left_out": sheet.get("left_out", []), "note": r.get("note"), "stands": r.get("stands")}
        _write(out, "prov.json", {"job": out.name, "kind": "fit_motions", "name": name, "from": job["fbx"],
                                  "library": rel(root, lib) if lib else None, "left_out": sheet.get("left_out", []),
                                  "character": job.get("character"), "try_id": job.get("try_id"), "game": job.get("game"),
                                  "licences": licences.lines(["quaternius_ual", "blender"]),
                                  "commercial_ok": licences.all_ok(["quaternius_ual", "blender"])})
        _write(out, "report.json", result)
        return result


# ------------------------------------------------------------------------------------------------ grow_tree
def grow_tree(job: dict, ctx, out: Path) -> dict:
    cfg, root, out = ctx.cfg, Path(ctx.root), Path(out)
    with _JobLog(out):
        env = from_cfg(cfg)
        sp = job.get("species") or "broadleaf"
        if isinstance(sp, str):
            gdir = (root / "games" / job["game"]) if job.get("game") else None
            sheet = next((s for s in trees.sheets(gdir) if s["name"] == sp or Path(s["file"]).stem == sp), None)
            if sheet is None:
                raise ValueError(f"there is no species sheet called {sp!r}")
        else:
            sheet = dict(sp)
        made, failed = [], []
        for k in range(max(1, int(job.get("count") or 1))):
            seed = int(job.get("seed") or 11) + k
            r = trees.grow(env, out, sheet, seed, bare=bool(job.get("bare")), name=sheet.get("name"), views=int(job.get("views") or 1),
                           size=int(job.get("size") or 360), samples=int(job.get("samples") or 16),
                           minutes=float(job.get("minutes") or 20), python=_blender_python(cfg))
            (made if r["ok"] else failed).append({"seed": seed, **r})
        if not made:
            raise RuntimeError("no tree was grown: " + "; ".join(f["error"] for f in failed)[:1500])
        result = {"trees": [{"seed": m["seed"], "glb": rel(root, Path(m["glb"])), "views": [rel(root, Path(v)) for v in m["views"]]}
                            for m in made], "failed": failed, "species": sheet.get("name")}
        _write(out, "prov.json", {"job": out.name, "kind": "grow_tree", "species": sheet, "bare": bool(job.get("bare")),
                                  "licences": licences.lines(["forge_tree", "blender"]), "commercial_ok": True})
        _write(out, "report.json", result)
        return result


# ------------------------------------------------------------------------------------------------ line_3d
def line_3d(job: dict, ctx, out: Path) -> dict:
    from . import line
    cfg, root, out = ctx.cfg, Path(ctx.root), Path(out)
    with _JobLog(out):
        lp = resolve(root, job["list"])
        if not lp or not lp.exists():
            raise FileNotFoundError(f"the list {job['list']} is not there")
        spec = json.loads(lp.read_text(encoding="utf-8"))
        spec.setdefault("batch", lp.stem)
        folder = line.folder(cfg, spec["batch"])
        h = line.log_to(folder)
        try:
            comfy_out = root / "out" / "_comfy"
            rows = line.run(cfg, spec, folder, only=job.get("only"), skip=tuple(job.get("skip") or ()), art_url=_url(ctx, cfg),
                            blender_python=_blender_python(cfg), local_out=comfy_out if comfy_out.is_dir() else None)
        finally:
            logging.getLogger("forge.threed").removeHandler(h)
            h.close()
        done = sum(1 for r in rows if r["motions"])
        result = {"folder": rel(root, folder), "report": rel(root, folder / "REPORT.txt"), "bodies": len(rows), "through": done,
                  "failed": [{"id": r["id"], "why": r["why"]} for r in rows if r["why"]]}
        _write(out, "result.json", result)
        _write(out, "prov.json", {"job": out.name, "kind": "line_3d", "list": job["list"], "folder": result["folder"],
                                  "licences": licences.lines(["flux2_klein_4b", "trellis2", "comfy_template", "mia", "comfyui_unirig",
                                                              "quaternius_ual", "blender"])})
        return result


HANDLERS = {"model_3d": model_3d, "rig_body": rig_body, "fit_motions": fit_motions, "grow_tree": grow_tree, "line_3d": line_3d}
