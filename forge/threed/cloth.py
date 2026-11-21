"""Capes, cloaks and long coats as their own piece (BUILD 73 part 6).

The picture gate cannot see arms against a cape, and the rigger cannot bend one — and a principal of the first game wears
one from now on. So a body entry may carry
    "worn_over": [{"id": "cape_raven_count", "kind": "cape", "words": "..."}]
— the body's picture is made without it (world.worn_words_out), the piece is its own world-list entry of kind `cloth`
(world.worn_pieces: a flat-hanging garment on a stand, checked like a prop), and when both are made the Blender step
(blender/cloth_pin.py) pins it to the shoulder and collar bones, into the body's .glb as a mesh of its own, with a `cloth`
block in the moves file for the game: the pinned band, a stiffness, a wind word. The game moves the free edge with a
simple spring (BUILD 68), not a cloth simulation.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .env import RigEnv, run_blender

log = logging.getLogger("forge.threed.cloth")


def block(piece: dict, report: dict) -> dict:
    """The `cloth` block written into the moves file's sheet for the game to read."""
    return {"mesh": report.get("mesh") or piece["id"], "kind": piece.get("cloth_kind") or "cape",
            "pin_bones": report.get("pin_bones") or piece.get("pin") or [], "pinned_share": float(piece.get("pin_share") or 0.14),
            "pinned_vertices": int(report.get("pinned") or 0), "free_vertices": int(report.get("free") or 0),
            "stiffness": float(piece.get("stiffness") or 0.6), "wind": str(piece.get("wind") or "a slow sway"),
            "colour_mark": piece.get("colour_mark"), "spring": {"model": "free edge on a spring", "not": "a cloth simulation"}}


def pin(env: RigEnv, body_glb: Path, cloth_glb: Path, out_glb: Path, piece: dict, minutes: float = 10,
        python: str | None = None) -> dict:
    """Run the Blender step; on success also write the sheet beside out_glb with its `cloth` block added. Returns
    {"ok", "report"|"error", "block"}."""
    body_glb, cloth_glb, out_glb = Path(body_glb), Path(cloth_glb), Path(out_glb)
    for p in (body_glb, cloth_glb):
        if not p.exists():
            return {"ok": False, "error": f"no file at {p}"}
    out_glb.parent.mkdir(parents=True, exist_ok=True)
    args = [str(body_glb), str(cloth_glb), str(out_glb), "--pin", ",".join(piece.get("pin") or ["shoulder.L", "shoulder.R", "neck"]),
            "--share", str(float(piece.get("pin_share") or 0.14)), "--stiffness", str(float(piece.get("stiffness") or 0.6)),
            "--wind", str(piece.get("wind") or "a slow sway"), "--name", piece["id"]]
    code, lines = run_blender(env, "cloth_pin.py", args, minutes, log=log, python=python)
    line = next((ln for ln in lines if ln.startswith("CLOTH ")), "")
    if not line or not out_glb.exists():
        tail = [ln for ln in lines if ln.strip()][-4:]
        return {"ok": False, "error": f"exit {code}: " + " / ".join(tail)[:600]}
    rep = json.loads(line[6:])
    if "error" in rep:
        return {"ok": False, "error": rep["error"]}
    blk = block(piece, rep)
    sheet_in = body_glb.with_suffix(".json")
    sheet = json.loads(sheet_in.read_text(encoding="utf-8")) if sheet_in.exists() else {}
    sheet.setdefault("cloth", [])
    sheet["cloth"] = [c for c in sheet["cloth"] if c.get("mesh") != blk["mesh"]] + [blk]
    out_glb.with_suffix(".json").write_text(json.dumps(sheet, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "report": rep, "block": blk}
