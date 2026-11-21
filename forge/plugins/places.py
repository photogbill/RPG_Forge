"""The places job type (BUILD 34): compile_place — a place plan → the stage model (Blender on the processor, no graphics
card), the placed-things list and the place's entries on its game's world list. Starts no generation: what the place
needs goes on the world list and the world queue makes it. A plug-in, so a running worker takes it without a restart."""
from __future__ import annotations

DEPENDS = ("forge.threed.place",)

JOB_TYPES = {
    "compile_place": {
        "needs": "cpu",
        "doc": "A place plan (`place`: a path under the forge or the game, `<id>.place.json`) compiled into a walkable stage: "
               "<id>.stage.glb (the plan-built solids, modelled in Blender), <id>.things.json (what stands where, the grey "
               "boxes' sizes until each model is delivered) and, with `game`, games/<game>/wanted_3d/<id>.json (every "
               "generated thing in story order; a thing nobody has described is held, no look guessed; with `hold`, every new "
               "entry is held). Output folder: `out` (e.g. the game's assets/stages/<id>) or the job's own. prov.json, report.json.",
        "required": ["place"],
        "optional": {"game": None, "minutes": 15, "out": None, "hold": False},
    },
}


def compile_place(job, ctx, out):
    import json
    from pathlib import Path
    from forge.threed import place
    root = Path(ctx.root)
    src = Path(job["place"])
    if not src.is_absolute():
        for base in (root, root / "games" / str(job.get("game") or "")):
            if (base / src).exists():
                src = base / src
                break
    python = ((ctx.cfg or {}).get("threed") or {}).get("blender_python") or None
    dest = Path(job["out"]) if job.get("out") else Path(out)
    rep = place.compile_place(ctx.cfg, job.get("game") or "", src, dest,
                              games_root=(root / "games") if job.get("game") else None, python=python,
                              minutes=float(job.get("minutes") or 15), hold=bool(job.get("hold")))
    if not rep.get("ok"):
        raise RuntimeError(rep.get("error") or "the place was not compiled")
    (Path(out) / "prov.json").write_text(json.dumps({"job": Path(out).name, "kind": "compile_place", "place": str(src),
                                                     "tools": ["blender"], "generated": "nothing (plan-built solids only)"},
                                                    indent=1), encoding="utf-8")
    (Path(out) / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    return {k: v for k, v in rep.items() if k in ("model", "things", "wanted", "lines", "faces", "meshes")}


HANDLERS = {"compile_place": compile_place}
