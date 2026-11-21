"""3D -> Terrain (BUILD 77 part 5): the DTED folder and whether it was found (cells counted, levels found, what was
skipped); a window picked on a small world picture; the dials as sliders with the shaded picture redrawn as they move;
"check a point"; Bake. Heights are coloured by how they were produced, as ATK colours its results: measured (the data),
invented (the added detail), edited (a crater, a pad). Nothing here uses the graphics card or starts a job; Bake runs the
same code as terrain_bake.bat, on the processor, in this process.
"""
from __future__ import annotations

import base64
import io
import json
import threading
import time
from pathlib import Path

from .. import cli_terrain
from .. import config as cfgmod
from ..log import get

log = get("suite")
_lib = {"at": 0.0, "lib": None, "dir": None}
_bake = {"running": False, "last": None, "lines": []}


def library(cfg: dict):
    d = cli_terrain.dted_dir(cfg)
    if _lib["lib"] is None or _lib["dir"] != str(d) or time.time() - _lib["at"] > 600:
        _lib.update(lib=cli_terrain.library(cfg), dir=str(d), at=time.time())
    return _lib["lib"]


def _png_b64(arr) -> str:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode("ascii")


def view(cfg: dict, gid: str) -> dict:
    lib = library(cfg)
    s = lib.summary()
    w = cli_terrain.world_file(cfg, gid)
    out = Path(w["out"])
    baked = sorted(p.name for p in out.glob("*.png")) if out.exists() else []
    return {"dted_dir": str(cli_terrain.dted_dir(cfg)), "found": lib.found, "cells": s["cells"], "zips": s["zips"],
            "skipped": [{"name": n, "why": y} for n, y in lib.skipped[:20]], "skipped_count": len(lib.skipped),
            "bad": [{"name": n, "why": y} for n, y in lib.bad[:20]],
            "windows": [{k: v for k, v in win.items() if k != "edits"} | {"edits": len(win.get("edits") or [])}
                        for win in w.get("windows") or []],
            "profiles": [{"id": p["id"], "title": p.get("title")} for p in w.get("profiles") or []],
            "story_file": w.get("story_file"), "out": str(out), "baked": baked, "bake": dict(_bake, lines=_bake["lines"][-12:]),
            "colours": {"measured": "#5aa0ff", "invented": "#ffc85a", "edited": "#ff505a"},
            "say": ("" if lib.found else f"No DTED cells found in {cli_terrain.dted_dir(cfg)}. Put the Level 0 folder, or its zip, "
                    "there — or point forge.json → \"dted_dir\" at where you keep it. Nothing of it is ever committed.")}


def preview(cfg: dict, south: float, west: float, north: float, east: float, dials: dict) -> dict:
    """The shaded picture (and how each height was produced) for a window at a small size, redrawn as the dials move."""
    import numpy as np
    from ..terrain import bake
    lib = library(cfg)
    if not lib.found:
        return {"ok": False, "message": "no DTED cells found"}
    win = {"south": south, "west": west, "north": north, "east": east, "edits": dials.pop("edits", None) or []}
    d = {"posts": int(dials.get("posts") or 320), "exaggerate": float(dials.get("exaggerate") or 1.0),
         "relief_x": float(dials.get("relief_x") or 6.0), "sun_az": float(dials.get("sun_az") or 315),
         "sun_el": float(dials.get("sun_el") or 35), "sea_level": float(dials.get("sea_level") or 0),
         "smooth": int(dials.get("smooth") or 0), "detail_m": float(dials.get("detail_m") or 0), "seed": int(dials.get("seed") or 77),
         "tint": bool(dials.get("tint", True))}
    w, h, layers = bake.heights(lib, win, d)
    s = bake.hillshade(h * d["relief_x"], w["m_per_post"], d["sun_az"], d["sun_el"])
    hs = [t[0] for t in bake.TINT]
    col = np.stack([np.interp(h, hs, [t[1][c] for t in bake.TINT]) for c in range(3)], -1) if d["tint"] else np.full(h.shape + (3,), 200.0)
    img = col * (0.35 + 0.65 * s[..., None])
    img[layers["sea"]] = (52, 86, 128)
    img = np.clip(img, 0, 255).astype(np.uint8)
    L = np.full(h.shape + (3,), (90, 160, 255), np.float64)
    L[layers["invented"]] = (255, 200, 90)
    L[layers["edited"]] = (255, 80, 90)
    L[layers["sea"]] = (30, 40, 60)
    how = np.clip(L * (0.4 + 0.6 * s[..., None]), 0, 255).astype(np.uint8)
    return {"ok": True, "shade": _png_b64(img), "how": _png_b64(how), "size_m": w["size_m"], "m_per_post": round(w["m_per_post"]),
            "min_m": round(float(np.nanmin(h))), "max_m": round(float(np.nanmax(h))), "cells": len(w["cells"]),
            "missing": len(w["missing"])}


def act(cfg: dict, gid: str, action: str, body: dict, who: str | None) -> dict:
    if action == "threed_terrain_check":
        lat, lon = float(body.get("lat")), float(body.get("lon"))
        h, cell = library(cfg).height_at(lat, lon)
        return {"ok": h is not None, "lat": lat, "lon": lon, "m": None if h is None else round(h, 1), "cell": cell,
                "message": (f"{h:.0f} m — measured (cell {str(cell).split('/', 1)[-1]})" if h is not None
                            else "no data here — DTED has no sea")}
    if action == "threed_terrain_preview":
        b = dict(body.get("dials") or {})
        return preview(cfg, float(body["south"]), float(body["west"]), float(body["north"]), float(body["east"]), b)
    if action == "threed_terrain_proof":
        from ..terrain import proof
        t = proof.table(library(cfg))
        return {"ok": not t["stop"], "table": t, "markdown": proof.markdown(t)}
    if action == "threed_terrain_bake":
        if not who:
            return {"ok": False, "message": "say who you are first"}
        if _bake["running"]:
            return {"ok": False, "message": "a bake is running already"}
        only = body.get("only") or None

        def run():
            _bake.update(running=True, lines=[], started=time.strftime("%H:%M"))
            try:
                r = cli_terrain.bake_all(cfg, gid, only, log=lambda s: _bake["lines"].append(s))
                _bake["last"] = {k: v for k, v in r.items() if k != "windows"} | {"windows": [w["id"] for w in r.get("windows") or []]}
                log.info("terrain: %s baked by %s — %s", gid, who, _bake["last"].get("out") or r.get("message"))
            except Exception as e:  # noqa: BLE001
                _bake["last"] = {"ok": False, "message": f"{type(e).__name__}: {e}"}
            finally:
                _bake["running"] = False
        threading.Thread(target=run, daemon=True).start()
        return {"ok": True, "message": "Baking on the processor — the page shows each window as it is done."}
    return {"ok": False, "message": f"unknown action {action}"}
