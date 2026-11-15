"""Tidy a model (Blender, blender/tidy_model.py): weld its seams, take off loose scraps, set its real size in metres,
stand it on the floor. Props and buildings get this after image-to-3D (owed since 2026-11-12); animals get a larger weld
before UniRig, which trips over a .glb's split seams.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .env import RigEnv, run_blender

log = logging.getLogger("forge.threed.tidy")
ANIMAL_WELD = 0.0005          # metres: closes the seams of a generated body without melting its fingers together


def tidy(env: RigEnv, src: Path, dst: Path, scraps: float = 0.02, weld: float = 0.00001, size: dict | None = None,
         floor: bool = True, minutes: float = 15, python: str | None = None) -> dict:
    """Returns {ok, report | error}. `size` is {"height": m} or {"width": m} or {"depth": m} (one of them)."""
    src, dst = Path(src), Path(dst)
    if not src.exists():
        return {"ok": False, "error": f"no model at {src}"}
    dst.parent.mkdir(parents=True, exist_ok=True)
    args = [str(src), str(dst), "--scraps", str(float(scraps)), "--weld", str(float(weld))]
    for k in ("height", "width", "depth"):
        if size and size.get(k):
            args += [f"--{k}", f"{float(size[k]):.4f}"]
            break
    if not floor:
        args.append("--no-floor")
    code, lines = run_blender(env, "tidy_model.py", args, minutes, log=log, python=python)
    line = next((ln for ln in lines if ln.startswith("TIDY ")), "")
    if line and dst.exists():
        rep = json.loads(line[5:])
        if "error" not in rep:
            return {"ok": True, "report": rep}
        return {"ok": False, "error": rep["error"]}
    tail = [ln for ln in lines if ln.strip()][-4:]
    return {"ok": False, "error": (f"exit {code}: " if code not in (-2,) else "") + " / ".join(tail)[:600]}


def weld_for_animal(env: RigEnv, src: Path, dst: Path, python: str | None = None) -> dict:
    """An animal's body before UniRig: seams closed, crumbs off, nothing rescaled or moved."""
    return tidy(env, src, dst, scraps=0.01, weld=ANIMAL_WELD, size=None, floor=False, python=python)
