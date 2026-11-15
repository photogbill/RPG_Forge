"""Trees grown by rule, not guessed from a picture (✦ "trees by rule", 2026-11-12): a species sheet (numbers) and a seed.
One seed is one tree; the next seed is its sibling, never its copy. Bare (winter, or dead) or in leaf.

Species sheets: the forge ships one broadleaf sheet (species/broadleaf.json — the defaults the grower was proven with);
a game keeps its own in games/<id>/threed/species/<name>.json, and the Trees tab's sliders write them. A sheet is
{"name", "about", "numbers": {height, trunk_radius, ...}}; `SLIDERS` says what each number means and its range.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .env import RigEnv, run_blender

log = logging.getLogger("forge.threed.trees")
SHIPPED = Path(__file__).with_name("species")

# number -> (plain words, smallest, largest, step)
SLIDERS: dict[str, tuple[str, float, float, float]] = {
    "height": ("height, roots to the top of the crown (m)", 2, 40, 0.5),
    "trunk_radius": ("trunk radius at chest height (m)", 0.05, 2.0, 0.05),
    "fork_height": ("where the heavy limbs leave the trunk (m)", 0.5, 12, 0.25),
    "limbs": ("heavy low limbs", 1, 12, 1),
    "crown_centre_z": ("height of the crown's middle (m)", 1, 30, 0.25),
    "crown_radius": ("crown width, to the side (m)", 0.5, 20, 0.25),
    "crown_half_height": ("crown half-height (m)", 0.5, 20, 0.25),
    "crown_floor": ("no leaves below (m)", 0, 20, 0.25),
    "masses": ("separate masses of leaf in the crown", 1, 60, 1),
    "attractors": ("how finely the crown is filled", 500, 15000, 100),
    "step": ("length of one piece of twig (m)", 0.1, 1.0, 0.05),
    "reach": ("how far a twig sees free room (m)", 1, 10, 0.25),
    "close": ("room counts as taken within (m)", 0.1, 2, 0.02),
    "twig_radius": ("twig radius (m)", 0.005, 0.08, 0.001),
    "pipe": ("pipe-rule exponent (how fast limbs thin)", 1.5, 3.5, 0.05),
    "cards_per_twig": ("leaf cards per twig", 1, 10, 1),
}


def sheets(game_dir: Path | None = None) -> list[dict]:
    """Every species sheet: the forge's own, then the game's (a game's sheet of the same name wins)."""
    found: dict[str, dict] = {}
    for folder, where in ((SHIPPED, "forge"), ((Path(game_dir) / "threed" / "species") if game_dir else None, "game")):
        if folder is None or not folder.is_dir():
            continue
        for p in sorted(folder.glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            d.setdefault("name", p.stem)
            d["file"], d["where"] = str(p), where
            found[p.stem] = d
    return list(found.values())


def grow(env: RigEnv, out_dir: Path, sheet: dict | None, seed: int, bare: bool = False, name: str | None = None,
         views: int = 1, size: int = 360, samples: int = 16, minutes: float = 20, python: str | None = None) -> dict:
    """Grow one tree. Returns {ok, glb, views, stats | error}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = name or (sheet or {}).get("name") or "tree"
    args = [str(out_dir), "--seed", str(int(seed)), "--name", name, "--views", str(int(views)), "--size", str(int(size)),
            "--samples", str(int(samples))]
    if bare:
        args.append("--bare")
    if sheet:
        sp = out_dir / f"{name}.sheet.json"
        sp.write_text(json.dumps({"name": name, "numbers": sheet.get("numbers") or {}}, indent=1), encoding="utf-8")
        args += ["--sheet", str(sp)]
    t0 = time.time()
    code, lines = run_blender(env, "grow_tree.py", args, minutes, log=log, python=python)
    tag = f"{name}_seed{int(seed)}" + ("_bare" if bare else "")
    g = out_dir / f"{tag}.glb"
    if g.exists() and g.stat().st_mtime >= t0 - 2:
        stats = next((ln[len("TREE "):] for ln in lines if ln.startswith("TREE ")), "")
        return {"ok": True, "glb": str(g), "views": sorted(str(p) for p in out_dir.glob(f"{tag}_*.png")), "stats": stats,
                "seconds": round(time.time() - t0)}
    tail = [ln for ln in lines if ln.strip()][-4:]
    return {"ok": False, "error": f"exit {code}: " + " / ".join(tail)[:600]}
