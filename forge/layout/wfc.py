"""Wave Function Collapse — for texture only (fences, rubble fields, crop rows, barricade lines).

It fills the free cells of a mask that the plan left empty. It never decides the plan: roads, buildings, doors and
the story element are placed before it runs, and anything it puts down that would cut a path is turned to walkable
rubble afterwards (town.py). A simple tiled model: each tile says which tiles may sit beside it in each direction.
"""
from __future__ import annotations
import random

from . import tiles as T

DIRS = ((1, 0, "E", "W"), (-1, 0, "W", "E"), (0, 1, "S", "N"), (0, -1, "N", "S"))

# tileset: name → (semantic tile, weight, {dir: allowed neighbours})
TILESETS: dict[str, dict] = {
    # crop rows: horizontal stripes of field, furrows between
    "crops": {
        "row": (T.FIELD, 3, {"E": {"row"}, "W": {"row"}, "N": {"furrow", "row"}, "S": {"furrow"}}),
        "furrow": (T.GROUND, 1, {"E": {"furrow"}, "W": {"furrow"}, "N": {"row"}, "S": {"row"}}),
    },
    # rubble fields: clumps of rubble on open ground
    "rubble": {
        "g": (T.GROUND, 5, {"E": {"g", "r"}, "W": {"g", "r"}, "N": {"g", "r"}, "S": {"g", "r"}}),
        "r": (T.RUBBLE, 3, {"E": {"g", "r"}, "W": {"g", "r"}, "N": {"g", "r"}, "S": {"g", "r"}}),
    },
    # fences: straight runs only — a fence piece continues or ends on open ground, never a blob
    "fence": {
        "g": (T.GROUND, 8, {"E": {"g", "v"}, "W": {"g", "v"}, "N": {"g", "h"}, "S": {"g", "h"}}),
        "h": (T.FENCE, 2, {"E": {"h", "g"}, "W": {"h", "g"}, "N": {"g"}, "S": {"g"}}),
        "v": (T.FENCE, 1, {"E": {"g"}, "W": {"g"}, "N": {"v", "g"}, "S": {"v", "g"}}),
    },
    # lawns: kept grass with the odd hedge run (the pretend town, the sanctuary's gardens)
    "field": {
        "g": (T.GROUND, 4, {"E": {"g", "f"}, "W": {"g", "f"}, "N": {"g", "f"}, "S": {"g", "f"}}),
        "f": (T.FIELD, 3, {"E": {"g", "f"}, "W": {"g", "f"}, "N": {"g", "f"}, "S": {"g", "f"}}),
    },
}


def collapse(cells: list[tuple[int, int]], tileset: str, rng: random.Random, tries: int = 6) -> dict:
    """Returns {(x, y): semantic tile} for every cell, or {} if every try contradicted (the caller leaves it empty)."""
    ts = TILESETS[tileset]
    names = sorted(ts)
    cellset = set(cells)
    order = sorted(cells, key=lambda c: (c[1], c[0]))
    for _ in range(tries):
        wave = {c: set(names) for c in order}
        ok = True
        # cells collapse in scanline order (every open cell here has the same entropy at the start, and
        # propagation narrows the rest) — linear time, so a whole town's filler stays fast
        for pick in order:
            if len(wave[pick]) <= 1:
                continue
            opts = sorted(wave[pick])
            weights = [ts[o][1] for o in opts]
            wave[pick] = {rng.choices(opts, weights)[0]}
            stack = [pick]
            while stack:
                cx, cy = stack.pop()
                for dx, dy, d, _back in DIRS:
                    n = (cx + dx, cy + dy)
                    if n not in cellset:
                        continue
                    allowed = set()
                    for t in wave[(cx, cy)]:
                        allowed |= ts[t][2][d]
                    new = wave[n] & allowed
                    if not new:
                        ok = False
                        break
                    if new != wave[n]:
                        wave[n] = new
                        stack.append(n)
                if not ok:
                    break
            if not ok:
                break
        if ok:
            return {c: ts[next(iter(wave[c]))][0] for c in order}
    return {}
