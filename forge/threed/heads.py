"""Heads on shared bodies (BUILD 39, part 7): one uniform body per build, each person's own head joined at the collar.

The launch-site run's sixteen soldiers came out as nearly one body with different heads, at sixteen times the cost. If
joining holds up on the real card (the test after the run), crowds are made this way: the shared body once, a
head-and-shoulders picture and a small head model for each person, joined in Blender (blender/join_head.py), then
rigged and given motions like any body.

A world-list entry for one such person:

    {"id": "guard_08", "kind": "body", "tier": "crowd", "shared_body": "guard_body",
     "head_words": "a man in his forties, short grey hair, a moustache, weathered face"}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .env import RigEnv, run_blender

log = logging.getLogger("forge.threed.heads")

HEAD_ALWAYS = ("A head-and-shoulders reference picture for a 3D modeller: one person seen straight from the front at eye "
               "level, the head, the whole neck and the top of the shoulders inside the frame, looking straight ahead, "
               "relaxed, kind expression, mouth closed. Plain light grey background, nothing else in the picture, soft even "
               "studio light from the front. A clean 3D game character render, clear readable shapes, crisp detail.")
HEAD_NEGATIVE = ("text, letters, watermark, signature, logo, blurry, low quality, several people, cropped head, a room, a "
                 "landscape, dramatic lighting, side view, back view, three-quarter view, hands, hat brim covering the face, "
                 "smiling, open mouth, teeth")


def join(env: RigEnv, body: Path, head: Path, out: Path, collar: float | None = None, collar_m: float | None = None,
         overlap: float = 0.012, minutes: float = 15, python=None) -> dict:
    """Returns {ok, report | error}."""
    body, head, out = Path(body), Path(head), Path(out)
    for p, what in ((body, "the shared body"), (head, "the head")):
        if not p.exists():
            return {"ok": False, "error": f"{what} is not there: {p}"}
    out.parent.mkdir(parents=True, exist_ok=True)
    args = [str(body), str(head), str(out), "--overlap", str(float(overlap))]
    if collar_m:
        args += ["--collar-m", f"{float(collar_m):.4f}"]
    elif collar:
        args += ["--collar", f"{float(collar):.4f}"]
    code, lines = run_blender(env, "join_head.py", args, minutes, log=log, python=python)
    line = next((ln for ln in lines if ln.startswith("JOINED ")), "")
    if line:
        rep = json.loads(line[7:])
        if "error" not in rep and out.exists():
            return {"ok": True, "report": rep}
        if "error" in rep:
            return {"ok": False, "error": rep["error"]}
    tail = [ln for ln in lines if ln.strip()][-4:]
    return {"ok": False, "error": (f"exit {code}: " if code not in (-2,) else "") + " / ".join(tail)[:600]}
