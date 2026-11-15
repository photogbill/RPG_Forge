"""A motion library fitted to a rigged body: one .glb with every motion by name, and a sheet of each motion's length,
whether it loops, and how fast the ground passes under it (so a game moves a body at the speed its feet move).

The fitting is Blender's work (blender/fit_motions.py, proven 2026-11-13 on 92 bodies); this runs it and reads what it
wrote. The library's speeds are measured, not guessed: its walk is a stroll (about 1 m/s) and its run nearly a sprint.

Motions a character never does (a tick-list kept on the character — one never dances, say) are left out with --skip.
The rigging pack ships Mixamo test dances for testing the pack; `TEST_DANCES` names them, and `refuse_test_dances()`
keeps any file carrying one of them out of a game (Deliver calls it).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from . import glb
from .env import RigEnv, run_blender

log = logging.getLogger("forge.threed.motions")
# the ComfyUI-UniRig pack's own animation templates (input/animation_templates/mixamo): test motions, never shipped
TEST_DANCES = ("breakdance", "capoeira", "dying", "hip_hop_dancing", "mma_kick")
DEFAULT_LIBRARY = "local/libraries/quaternius_ual/Universal Animation Library[Standard]/Unreal-Godot/UAL1_Standard.glb"
DEFAULT_TRAVEL = "local/libraries/quaternius_ual/Universal Animation Library[Standard]/Unreal-Godot/UAL1_Standard_RM.glb"
WALK, RUN, STAND = "Walk_Loop", "Jog_Fwd_Loop", "Idle_Loop"     # what the viewer plays first


def library_paths(cfg: dict | None, root: Path) -> tuple[Path, Path | None]:
    t = (cfg or {}).get("threed") or {}
    lib = Path(t.get("motion_library") or DEFAULT_LIBRARY)
    trav = Path(t.get("motion_travel") or DEFAULT_TRAVEL)
    lib = lib if lib.is_absolute() else root / lib
    trav = trav if trav.is_absolute() else root / trav
    return lib, (trav if trav.exists() else None)


def library_motions(library: Path) -> list[str]:
    """The motions a library offers (read from the file; the tick-list of motions a character never does uses it)."""
    try:
        names = glb.info(library)["motions"]
    except Exception:  # noqa: BLE001
        return []
    return [n[:-len("_Armature")] if n.endswith("_Armature") else n for n in names]


def fit(env: RigEnv, library: Path, rigged_fbx: Path, out_glb: Path, height: float = 1.72, travel: Path | None = None,
        skip: list[str] | None = None, clips: list[str] | None = None, minutes: float = 20, python: str | None = None) -> dict:
    """Fit the library to one body. Returns {ok, sheet, seconds, note | error}; never raises for a failed fit."""
    out_glb = Path(out_glb)
    out_glb.parent.mkdir(parents=True, exist_ok=True)
    if not Path(library).exists():
        return {"ok": False, "error": f"the motion library is not at {library}"}
    if not Path(rigged_fbx).exists():
        return {"ok": False, "error": f"the rigged body is not at {rigged_fbx}"}
    args = [str(library), str(rigged_fbx), str(out_glb), "--height", f"{float(height):.3f}"]
    if travel is not None and Path(travel).exists():
        args += ["--travel", str(travel)]
    if skip:
        args += ["--skip", ",".join(skip)]
    if clips:
        args += ["--clips", ",".join(clips)]
    t0 = time.time()
    code, lines = run_blender(env, "fit_motions.py", args, minutes, log=log, python=python)
    sheet_path = out_glb.with_suffix(".json")
    if out_glb.exists() and sheet_path.exists() and out_glb.stat().st_mtime >= t0 - 2:
        sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
        return {"ok": True, "sheet": sheet, "seconds": round(time.time() - t0),
                "note": next((ln for ln in lines if ln.startswith("FITTED")), ""),
                "stands": next((ln for ln in lines if ln.startswith("STANDS")), "")}
    tail = [ln for ln in lines if ln.strip()][-4:]
    why = {-1: f"stopped after {minutes:.0f} minutes", -2: " ".join(lines)[:400]}.get(code, f"exit {code}")
    return {"ok": False, "error": f"{why}: " + " / ".join(tail)[:600], "seconds": round(time.time() - t0)}


def speeds(sheet: dict) -> dict:
    """{motion: metres a second} for the motions that travel, from a fitted body's sheet."""
    return {k: v["speed"] for k, v in (sheet.get("motions") or {}).items() if isinstance(v, dict) and "speed" in v}


def test_dances_in(path: Path) -> list[str]:
    """The pack's test dances found in a file's name or its motions (empty = clean)."""
    p = Path(path)
    hits = [d for d in TEST_DANCES if d in p.name.lower()]
    if p.suffix.lower() == ".glb" and p.exists():
        try:
            hits += [m for m in glb.info(p)["motions"] if any(d in m.lower().replace(" ", "_") for d in TEST_DANCES)]
        except Exception:  # noqa: BLE001
            pass
    return sorted(set(hits))


def refuse_test_dances(paths) -> None:
    """Raise when any file carries one of the rigging pack's test dances (they must never reach a game)."""
    bad = {str(p): test_dances_in(Path(p)) for p in paths}
    bad = {k: v for k, v in bad.items() if v}
    if bad:
        raise ValueError("these carry the rigging pack's Mixamo test dances, which never go into a game: "
                         + "; ".join(f"{Path(k).name} ({', '.join(v)})" for k, v in bad.items()))
