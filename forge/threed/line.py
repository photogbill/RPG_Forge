"""The whole line for a list, unattended: picture -> 3D body -> skeleton -> motions, with one report.

What the first game's cast_overnight.py did on 2026-11-13 (92 of 92 bodies in one night), now in the forge:

    python -m forge 3d line <list.json> [--only <id>] [--skip-pictures] [--skip-rig] [--skip-fit] [--estimate]

The list is the same file (objects with id / prompt / always / seed / image / real_size_m {height}, plus "rig" and
"motions" blocks). A body that fails at one step is left out of the next and the run goes on. Every step skips what is
already made, so starting it again carries on where it stopped. It approves nothing: what it makes is for a person to
judge. Everything lands in out/3d/<batch>/ — pictures/, models/, rig/, moves/, run.log, report.json, REPORT.txt.

Per body, `skip_motions` (or the character's "never does" list) leaves motions out; `kind: animal` welds the body and
rigs it with UniRig; people get Make-It-Animatable with their finger bones.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from . import bodies, motions, rig
from .env import RigEnv, from_cfg, out_root

log = logging.getLogger("forge.threed.line")
MODEL = "trellis2"
# seconds, from the 2026-11-13 runs on the 16 GB card (estimates only: shown before a run, never relied on)
TIMES = {"picture": 35, "trellis2": 240, "pixal3d": 300, "rig_start": 120, "rig": 25, "fit": 25, "tree": 15}


def estimate(spec: dict, done: dict | None = None) -> dict:
    """How long a list should take, step by step, counting only what isn't made yet (`done` from status())."""
    objs = spec.get("objects", [])
    done = done or {}
    models = spec.get("models", [MODEL])
    need_pic = [o for o in objs if not o.get("image") and not done.get(o["id"], {}).get("picture")]
    need_body = [o for o in objs if not done.get(o["id"], {}).get("body")]
    need_rig = [o for o in objs if not done.get(o["id"], {}).get("skeleton")]
    need_fit = [o for o in objs if not done.get(o["id"], {}).get("motions")]
    secs = {
        "pictures": len(need_pic) * TIMES["picture"],
        "bodies": sum(len(need_body) * TIMES.get(m, 270) for m in models),
        "skeletons": (TIMES["rig_start"] if need_rig else 0) + len(need_rig) * TIMES["rig"],
        "motions": len(need_fit) * TIMES["fit"],
    }
    total = sum(secs.values())
    return {"bodies": len(objs), "to_make": {"pictures": len(need_pic), "bodies": len(need_body), "skeletons": len(need_rig),
                                             "motions": len(need_fit)},
            "seconds": secs, "total_seconds": total, "words": _words(total)}


def _words(s: float) -> str:
    if s < 90:
        return f"about {max(1, round(s / 60))} minute"
    if s < 3600:
        return f"about {round(s / 60)} minutes"
    return f"about {s / 3600:.1f} hours"


def folder(cfg: dict | None, batch: str) -> Path:
    return out_root(cfg) / batch


def status(cfg: dict | None, spec: dict, out: Path | None = None) -> dict:
    """{id: {picture, body, skeleton, motions}} for what is already on the disk."""
    out = Path(out) if out else folder(cfg, spec.get("batch", "list"))
    res = {}
    for o in spec.get("objects", []):
        i = o["id"]
        rg = o.get("rigger") or rig.rigger_for(o)
        res[i] = {"picture": (out / "pictures" / f"{i}.png").exists(),
                  "body": (out / "models" / f"{i}__{MODEL}.glb").exists(),
                  "skeleton": (out / "rig" / f"{i}__{rg}.fbx").exists(),
                  "motions": (out / "moves" / f"{i}_moves.glb").exists()}
    return res


def run(cfg: dict | None, spec: dict, out: Path | None = None, only: str | None = None, skip: tuple = (),
        art_url: str | None = None, env: RigEnv | None = None, blender_python: str | None = None,
        use_lock: bool = True, local_out: Path | None = None) -> list[dict]:
    batch = spec.get("batch") or "list"
    out = Path(out) if out else folder(cfg, batch)
    (out / "moves").mkdir(parents=True, exist_ok=True)
    env = env or from_cfg(cfg)
    objects = [o for o in spec["objects"] if not only or o["id"] == only]
    t_start = time.time()
    log.info("==== the 3D line '%s': %d bodies, started %s ====", batch, len(objects), time.strftime("%Y-%m-%d %H:%M"))
    root = Path((cfg or {}).get("_root") or env.root)
    lib, trav = motions.library_paths(cfg, root)
    mspec = spec.get("motions") or {}
    if mspec.get("library"):
        lib = Path(mspec["library"]) if Path(mspec["library"]).is_absolute() else root / mspec["library"]
    if mspec.get("travel"):
        t = Path(mspec["travel"]) if Path(mspec["travel"]).is_absolute() else root / mspec["travel"]
        trav = t if t.exists() else None
    # said at the start, not three hours in: can the last step run at all?
    if "fit" not in skip:
        if blender_python is None and env.blender_command(Path("x.py"), []) is None:
            log.warning("heads-up: there is no Blender here (the rigging environment's Python or forge.json threed.blender_exe) "
                        "- the motions step will not run")
        if not lib.exists():
            log.warning("heads-up: the motion library is not at %s - the motions step will not run", lib)

    # ---- 1. pictures and 3D bodies
    if "pictures" not in skip:
        sub = dict(spec, objects=objects, models=[MODEL])
        bodies.run(cfg, sub, out, url=art_url, local_out=local_out, lock_holder=f"3D line {batch}: bodies", use_lock=use_lock)
    made = [o for o in objects if (out / "models" / f"{o['id']}__{MODEL}.glb").exists()]
    log.info("3D bodies made: %d of %d", len(made), len(objects))

    # ---- 2. skeletons, for the bodies that exist
    rspec = spec.get("rig") or {}
    if "rig" not in skip and made:
        bl = [{"id": o["id"], "glb": str(out / "models" / f"{o['id']}__{MODEL}.glb"), "kind": o.get("kind", "people"),
               "use_normal": bool(o.get("use_normal", rspec.get("use_normal", False))),
               "no_fingers": bool(o.get("no_fingers", rspec.get("no_fingers", False)))} for o in made]
        for b, o in zip(bl, made):
            if b["kind"] in ("animal", "thing"):
                from . import tidy
                w = out / "models" / f"{o['id']}__{MODEL}_welded.glb"
                if not w.exists():
                    r = tidy.weld_for_animal(env, Path(b["glb"]), w, python=blender_python)
                    if not r["ok"]:
                        log.error("%s: could not weld the body before rigging - %s", o["id"], r["error"])
                if w.exists():
                    b["glb"] = str(w)
        rig.rig_bodies(cfg, bl, out / "rig", env=env, minutes_per_rig=int(rspec.get("minutes_per_rig", 30)),
                       lock_holder=f"3D line {batch}: skeletons", use_lock=use_lock, art_url=art_url)
    rigged = [o for o in made if (out / "rig" / f"{o['id']}__{o.get('rigger') or rig.rigger_for(o)}.fbx").exists()]
    log.info("skeletons made: %d of %d", len(rigged), len(made))

    # ---- 3. the motion library, for the skeletons that exist
    fit_rows: dict[str, dict] = {}
    if "fit" not in skip and rigged:
        for o in rigged:
            target = out / "moves" / f"{o['id']}_moves.glb"
            if target.exists() and target.with_suffix(".json").exists():
                fit_rows[o["id"]] = {"ok": True, "note": "already there"}
                log.info("motions %s: already there", o["id"])
                continue
            fbx = out / "rig" / f"{o['id']}__{o.get('rigger') or rig.rigger_for(o)}.fbx"
            r = motions.fit(env, lib, fbx, target, height=float((o.get("real_size_m") or {}).get("height", 1.72)), travel=trav,
                            skip=list(o.get("skip_motions") or []), python=blender_python)
            fit_rows[o["id"]] = r
            if not r["ok"]:
                log.error("motions %s: FAILED - %s", o["id"], r["error"])
            else:
                log.info("motions %s: %s", o["id"], r.get("note"))

    # ---- the report
    t_rows = {r["id"]: r for r in _read(out / "report.json", []) if isinstance(r, dict) and "id" in r}
    r_rows = {r["body"]: r for r in _read(out / "rig" / "report.json", []) if isinstance(r, dict) and "body" in r}
    st = status(cfg, dict(spec, objects=objects), out)
    rows = []
    for o in objects:
        i, s = o["id"], st[o["id"]]
        why = ""
        if not s["picture"]:
            why = "no picture was made"
        elif not s["body"]:
            why = "3D body: " + str(t_rows.get(i, {}).get("error", "not made"))[:160]
        elif not s["skeleton"]:
            why = "skeleton: " + " ".join(str(r_rows.get(i, {}).get("error", "not made")).splitlines()[:2])[:160]
        elif not s["motions"]:
            why = "motions: " + str(fit_rows.get(i, {}).get("error", "not fitted"))[:160]
        rows.append({"id": i, **s, "why": why, "body_seconds": t_rows.get(i, {}).get("seconds"),
                     "rig_seconds": r_rows.get(i, {}).get("rig_seconds"), "fit": fit_rows.get(i, {}).get("note", "")})
    done = sum(r["motions"] for r in rows)
    mark = lambda ok: "yes" if ok else " - "                                    # noqa: E731
    lines = [f"The 3D line '{batch}': {done} of {len(rows)} bodies came through all four steps "
             f"({(time.time() - t_start) / 60:.0f} minutes this time)", "",
             f"  {'body':<22} picture  3D body  skeleton  motions"]
    for r in rows:
        lines.append(f"  {r['id']:<22} {mark(r['picture']):^7}  {mark(r['body']):^7}  {mark(r['skeleton']):^8}  {mark(r['motions']):^7}"
                     + (f"   {r['why']}" if r["why"] else ""))
    lines += ["", f"Everything: {out}", "Nothing here is approved: these are bodies to judge (3D -> Runs, then Art -> Review & approve)."]
    (out / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "line.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    for ln in lines:
        log.info(ln)
    return rows


def _read(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def log_to(out: Path) -> logging.Handler:
    """Everything the line says also goes to <out>/run.log (and the console)."""
    out.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(out / "run.log", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    lg = logging.getLogger("forge.threed")
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    if not any(isinstance(x, logging.StreamHandler) and getattr(x, "stream", None) is sys.stdout for x in lg.handlers):
        s = logging.StreamHandler(sys.stdout)
        s.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        lg.addHandler(s)
    return h
