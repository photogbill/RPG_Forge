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


# ------------------------------------------------------------------------------------------------ BUILD 74 part 6: a bearing
# Expressions live in the animation and the portrait; the small figure does not carry a face. What it carries is how it
# stands. A bearing is a few degrees of standing offset on spine, chest, neck, head and shoulders, laid over every idle —
# data, not new animation. (x = bend forward +, y = turn, z = lean to the side; degrees.) Hips and legs are never touched,
# so the feet stay where the motion puts them.
BEARINGS = {
    "easy":  {"spine": (1.0, 0, 0), "chest": (1.0, 0, 0), "neck": (2.0, 0, 0), "head": (-1.0, 0, 1.5),
              "shoulder.L": (0, 0, -2.0), "shoulder.R": (0, 0, 2.0)},
    "proud": {"spine": (-3.0, 0, 0), "chest": (-4.0, 0, 0), "neck": (-2.0, 0, 0), "head": (-3.0, 0, 0),
              "shoulder.L": (-3.0, 0, 1.0), "shoulder.R": (-3.0, 0, -1.0)},
    "tired": {"spine": (5.0, 0, 0), "chest": (6.0, 0, 0), "neck": (6.0, 0, 0), "head": (5.0, 0, 0),
              "shoulder.L": (4.0, 0, -4.0), "shoulder.R": (4.0, 0, 4.0)},
    "wary":  {"spine": (2.0, 0, 0), "chest": (2.0, 4.0, 0), "neck": (-1.0, -3.0, 0), "head": (-2.0, -6.0, 0),
              "shoulder.L": (2.0, 0, 3.0), "shoulder.R": (2.0, 0, -3.0)},
    "warm":  {"spine": (1.5, 0, 0), "chest": (0.5, 0, 0), "neck": (2.0, 0, 0), "head": (2.5, 0, 3.0),
              "shoulder.L": (0, 0, -1.5), "shoulder.R": (0, 0, 1.5)},
}
JOINT_LIMIT_DEG = {"spine": 8.0, "chest": 8.0, "neck": 10.0, "head": 12.0, "shoulder.L": 8.0, "shoulder.R": 8.0}
NEVER = ("hips", "pelvis", "root", "thigh", "leg", "knee", "calf", "foot", "toe", "ankle")
BEARING_WORDS = [  # the first that matches a body's words wins; else none (the motion as fitted)
    ("tired", ("exhausted", "weary", "tired", "worn out", "refugee", "stooped", "bent with age", "elderly", "ninety")),
    ("proud", ("proud", "imperious", "commanding", "regal", "haughty", "colonel", "general", "aristocrat", "count")),
    ("wary", ("wary", "watchful", "nervous", "guarded", "suspicious", "on edge", "skittish", "hunted")),
    ("warm", ("warm", "kind", "gentle", "friendly", "motherly", "sentry", "smiling eyes", "open face")),
    ("easy", ("relaxed", "easygoing", "laid-back", "casual", "at ease")),
]


def bearing_from_words(words: str, given: str | None = None) -> str | None:
    """A body's bearing: the entry's own `bearing` when it has one, else read from its words, else none."""
    if given:
        if given not in BEARINGS:
            raise ValueError(f"a bearing is one of {', '.join(BEARINGS)} (not {given!r})")
        return given
    low = (words or "").lower()
    for name, cues in BEARING_WORDS:
        if any(c in low for c in cues):
            return name
    return None


def bearing_offsets(name: str, limits: dict | None = None) -> dict:
    """The offsets a bearing lays over the idles, each axis clamped to the joint's limit; nothing below the waist."""
    lim = {**JOINT_LIMIT_DEG, **(limits or {})}
    out = {}
    for joint, (x, y, z) in BEARINGS[name].items():
        if any(n in joint.lower() for n in NEVER):
            continue
        m = float(lim.get(joint, 6.0))
        out[joint] = [max(-m, min(m, float(v))) for v in (x, y, z)]
    return out


def add_bearing(sheet_path: Path, name: str | None, limits: dict | None = None) -> dict | None:
    """Write the bearing into a fitted body's motion sheet (`bearing: {name, offsets, over}`) for the game to lay over
    every idle. Returns what was written, or None when there is no bearing."""
    if not name:
        return None
    p = Path(sheet_path)
    sheet = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    idles = [m for m in (sheet.get("motions") or {}) if "idle" in m.lower()] or [STAND]
    sheet["bearing"] = {"name": name, "offsets_deg": bearing_offsets(name, limits), "over": idles,
                        "axes": "x bend forward +, y turn, z lean to the side", "note": "standing offsets, data — not animation"}
    p.write_text(json.dumps(sheet, indent=1, ensure_ascii=False), encoding="utf-8")
    return sheet["bearing"]
