"""BUILD 60 — the ground outdoors: a place plan's `terrain` block → a height picture the game's terrain reads.

Game-neutral: nothing here names a game, a place or a story. numpy only (no Blender, no engine).

A place plan's `terrain` block (the plan's `ground` is already its list of flat ground items — roads, paths, lawns):

    "terrain": {
      "size_m": [w, d],              # how much land (defaults to the plan's size)
      "pixels": 257,                 # samples a side (Terrain3D likes 2^n + 1 or 2^n)
      "rules": [                     # what the land does, in order, added together (metres)
        {"kind": "roll", "height_m": 1.2, "across_m": 90, "seed": 3},           # gentle farmland swell (smooth noise)
        {"kind": "draw", "line": [[x, y], ...], "width_m": 30, "depth_m": 2.5}, # a shallow valley along a line
        {"kind": "rise", "line": [[x, y], ...], "width_m": 40, "height_m": 6},  # a ridge or a bank along a line
        {"kind": "slope", "from": [x, y], "to": [x, y], "drop_m": 3},           # the whole place tilts
        {"kind": "basin", "poly": [[x, y], ...], "depth_m": 1.5, "edge_m": 8}   # a pond or a low place
      ],
      "picture": "<a height picture>", "range_m": [lo, hi],  # OR heights from a picture (a DTED bake, a hand-painted
                                                             #   grey picture) instead of rules; rules then add to it
      "flat_under": ["solids", "gravel"],                     # where the land is levelled to the floor's height: under
      "flat_margin_m": 6,                                   #   every solid and these ground words, easing out over this
      "surfaces": [{"word": "grass"}, {"word": "dirt_road"}, ...]   # 1–8 words from the game's surfaces table
    }

Walls, doors and exits stay the plan's: the land gives the height under a foot, never the right of way. The plan's own
solids stand at the floor's height (0 m), so the land is levelled to 0 under them and under the roads.

Writes beside the stage: `<id>.terrain.r16` (16-bit little-endian, row by row from the north-west corner) and
`<id>.terrain.json` (`height`, `size_m`, `range_m`, `pixels`, `origin_m`) — what the game's `terrain` block reads.

`pack_for_terrain` — a terrain surface is two packed pictures: colour with height in alpha, normal with roughness in
alpha (the terrain add-on's own layout). From a library picture and its relief (`<name>_n.png`, BUILD 63's relief step).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

SURFACE_MAX = 8
KINDS = ("roll", "draw", "rise", "slope", "basin")


# ----------------------------------------------------------------------------------------------- the land's shapes
def dims(size_m, n: int) -> tuple[int, int]:
    """Samples across and down for `n` on the long side, the same spacing both ways (the terrain's cells are square)."""
    w, d = float(size_m[0]), float(size_m[1])
    if w >= d:
        return n, max(2, int(round((n - 1) * d / w)) + 1)
    return max(2, int(round((n - 1) * w / d)) + 1), n


def _grid(size_m, n):
    """n: samples on the long side (an int), or (across, down)."""
    nx, ny = (int(n[0]), int(n[1])) if isinstance(n, (tuple, list)) else dims(size_m, int(n))
    w = float(size_m[0])
    sx = w / (nx - 1)
    xs = np.arange(nx) * sx
    ys = np.arange(ny) * sx             # square cells: the same spacing down as across (d is met to within a cell)
    return np.meshgrid(xs, ys)          # X[y, x], Y[y, x] in metres


def _smooth_noise(n: int, size_m, across_m: float, seed: int) -> np.ndarray:
    """Value noise on a coarse lattice, cosine-interpolated: hills about `across_m` apart, -1..1, the same for a seed."""
    rng = np.random.default_rng(int(seed))
    w, d = float(size_m[0]), float(size_m[1])
    cells_x = max(2, int(math.ceil(w / max(across_m, 1.0))) + 2)
    cells_y = max(2, int(math.ceil(d / max(across_m, 1.0))) + 2)
    lattice = rng.uniform(-1.0, 1.0, (cells_y, cells_x))
    X, Y = _grid(size_m, n)
    gx = X / max(across_m, 1.0)
    gy = Y / max(across_m, 1.0)
    x0 = np.floor(gx).astype(int)
    y0 = np.floor(gy).astype(int)
    fx = (1 - np.cos((gx - x0) * math.pi)) * 0.5
    fy = (1 - np.cos((gy - y0) * math.pi)) * 0.5
    x1 = np.minimum(x0 + 1, cells_x - 1)
    y1 = np.minimum(y0 + 1, cells_y - 1)
    a = lattice[y0, x0] * (1 - fx) + lattice[y0, x1] * fx
    b = lattice[y1, x0] * (1 - fx) + lattice[y1, x1] * fx
    return a * (1 - fy) + b * fy


def _dist_to_line(X, Y, line) -> np.ndarray:
    pts = [np.array([float(p[0]), float(p[1])]) for p in line]
    best = np.full(X.shape, np.inf)
    for a, b in zip(pts, pts[1:]):
        ab = b - a
        L2 = float(ab @ ab) or 1e-9
        t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / L2, 0.0, 1.0)
        dx = X - (a[0] + t * ab[0])
        dy = Y - (a[1] + t * ab[1])
        best = np.minimum(best, np.sqrt(dx * dx + dy * dy))
    if len(pts) == 1:
        best = np.sqrt((X - pts[0][0]) ** 2 + (Y - pts[0][1]) ** 2)
    return best


def _inside_poly(X, Y, poly) -> np.ndarray:
    """Even-odd rule, vectorised."""
    inside = np.zeros(X.shape, dtype=bool)
    pts = [(float(p[0]), float(p[1])) for p in poly]
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        cond = ((yi > Y) != (yj > Y)) & (X < (xj - xi) * (Y - yi) / ((yj - yi) or 1e-12) + xi)
        inside ^= cond
        j = i
    return inside


def _dist_to_poly(X, Y, poly) -> np.ndarray:
    """0 inside, the distance to the edge outside."""
    ring = list(poly) + [poly[0]]
    d = _dist_to_line(X, Y, ring)
    return np.where(_inside_poly(X, Y, poly), 0.0, d)


def _ease(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def heights_by_rule(size_m, n, rules: list, base: np.ndarray | None = None) -> np.ndarray:
    X, Y = _grid(size_m, n)
    n = X.shape[1] if not isinstance(n, (tuple, list)) else n
    h = np.zeros(X.shape) if base is None else base.astype(float).copy()
    for r in rules or []:
        k = r.get("kind")
        if k == "roll":
            h += float(r.get("height_m", 1.0)) * _smooth_noise(n, size_m, float(r.get("across_m", 80.0)), int(r.get("seed", 1)))
        elif k in ("draw", "rise"):
            d = _dist_to_line(X, Y, r.get("line") or [[0, 0]])
            half = max(float(r.get("width_m", 20.0)) * 0.5, 0.5)
            prof = np.cos(np.clip(d / half, 0.0, 1.0) * math.pi) * 0.5 + 0.5          # 1 on the line, 0 at the edge
            amt = -float(r.get("depth_m", 2.0)) if k == "draw" else float(r.get("height_m", 4.0))
            h += amt * prof
        elif k == "slope":
            a = np.array(r.get("from", [0, 0]), dtype=float)
            b = np.array(r.get("to", [size_m[0], 0]), dtype=float)
            ab = b - a
            L2 = float(ab @ ab) or 1e-9
            t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / L2, 0.0, 1.0)
            h -= float(r.get("drop_m", 2.0)) * t
        elif k == "basin":
            d = _dist_to_poly(X, Y, r.get("poly") or [[0, 0], [1, 0], [1, 1]])
            edge = max(float(r.get("edge_m", 6.0)), 0.5)
            h -= float(r.get("depth_m", 1.0)) * (1.0 - _ease(d / edge))
    return h


def flatten(h: np.ndarray, size_m, footprints: list, margin_m: float, level: float = 0.0) -> np.ndarray:
    """Level the land to `level` inside every footprint (polygons, metres), easing back over `margin_m`."""
    if not footprints:
        return h
    X, Y = _grid(size_m, (h.shape[1], h.shape[0]))
    d = np.full(h.shape, np.inf)
    for poly in footprints:
        d = np.minimum(d, _dist_to_poly(X, Y, poly))
    w = 1.0 - _ease(d / max(margin_m, 0.01))          # 1 under the footprint, 0 beyond the margin
    return h * (1.0 - w) + level * w


def _rect_poly(r):
    x, y, w, d = (float(v) for v in r[:4])
    return [[x, y], [x + w, y], [x + w, y + d], [x, y + d]]


def footprints(place: dict, words: list) -> list:
    """The plan's solids and the ground items whose word is in `words`, as polygons (metres)."""
    out = []
    if "solids" in words:
        for s in place.get("solids") or []:
            if s.get("roof") and (s["roof"] or {}).get("rect"):          # a building's whole footprint, not just its walls
                out.append(_rect_poly(s["roof"]["rect"]))
            elif s.get("rect"):
                out.append(_rect_poly(s["rect"]))
            elif s.get("cyl"):
                cx, cy, r = (float(v) for v in s["cyl"][:3])
                out.append([[cx + r * math.cos(a), cy + r * math.sin(a)] for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)])
            elif s.get("poly"):
                out.append(s["poly"])
    for g in place.get("ground") or []:
        if g.get("mat") in words:
            if g.get("rect"):
                out.append(_rect_poly(g["rect"]))
            elif g.get("poly"):
                out.append(g["poly"])
    return out


# ----------------------------------------------------------------------------------------------- pictures
def write_r16(h: np.ndarray, path: Path, lo: float, hi: float) -> None:
    """Row by row from the north-west corner, little-endian 16-bit."""
    span = max(hi - lo, 1e-6)
    v = np.clip(np.round((h - lo) / span * 65535.0), 0, 65535).astype("<u2")
    Path(path).write_bytes(v.tobytes())


def read_r16(path: Path, n=None, lo: float = 0.0, hi: float = 1.0) -> np.ndarray:
    """n: a side (square), or (across, down)."""
    raw = np.frombuffer(Path(path).read_bytes(), dtype="<u2")
    if n is None:
        n = int(round(math.sqrt(raw.size)))
    nx, ny = (n, n) if not isinstance(n, (tuple, list)) else n
    return lo + (hi - lo) * raw[: nx * ny].reshape(ny, nx).astype(float) / 65535.0


def read_height_picture(path: Path, n, lo: float, hi: float) -> np.ndarray:
    """A grey height picture (any size; 8 or 16 bit; .r16 too) resampled to n = (across, down), metres between lo and hi."""
    nx, ny = (n, n) if not isinstance(n, (tuple, list)) else n
    p = Path(path)
    if p.suffix.lower() == ".r16":
        g = read_r16(p, None, 0.0, 1.0)
    else:
        from PIL import Image
        im = Image.open(p)
        g = np.asarray(im.convert("I;16") if im.mode not in ("I;16", "I") else im, dtype=float)
        g = g / (65535.0 if g.max() > 255 else 255.0)
    if g.shape != (ny, nx):
        from PIL import Image
        g = np.asarray(Image.fromarray((g * 65535).astype(np.uint16)).resize((nx, ny), Image.BICUBIC), dtype=float) / 65535.0
    return lo + (hi - lo) * g


def check(place: dict) -> list[str]:
    t = place.get("terrain")
    if t is None:
        return []
    pid = place.get("id", "?")
    out = []
    if not isinstance(t, dict):
        return [f"place {pid}: terrain is not a table"]
    for r in t.get("rules") or []:
        if r.get("kind") not in KINDS:
            out.append(f"place {pid}: terrain rule '{r.get('kind')}' is not one of {', '.join(KINDS)}")
        if r.get("kind") in ("draw", "rise") and len(r.get("line") or []) < 2:
            out.append(f"place {pid}: terrain {r.get('kind')} needs a line of two or more points")
    surf = t.get("surfaces") or [{"word": "grass"}]
    if not 1 <= len(surf) <= SURFACE_MAX:
        out.append(f"place {pid}: terrain needs 1–{SURFACE_MAX} surfaces (it has {len(surf)})")
    n = int(t.get("pixels", 257))
    if not 33 <= n <= 4097:
        out.append(f"place {pid}: terrain pixels {n} out of range (33–4097)")
    if not t.get("rules") and not t.get("picture"):
        out.append(f"place {pid}: terrain has neither rules nor a picture")
    return out


def make(place: dict, out_dir, place_dir=None) -> dict:
    """The place's land → `<id>.terrain.r16` + `<id>.terrain.json` in out_dir. Returns the game's `terrain` block."""
    t = place.get("terrain") or {}
    pid = place["id"]
    size = t.get("size_m") or place.get("size") or [64, 64]
    n = int(t.get("pixels", 257))
    base = None
    if t.get("picture"):
        pic = Path(t["picture"])
        if not pic.is_absolute() and place_dir is not None:
            pic = Path(place_dir) / pic
        lo, hi = (t.get("range_m") or [0.0, 10.0])[:2]
        base = read_height_picture(pic, dims(size, n), float(lo), float(hi))
    h = heights_by_rule(size, dims(size, n), t.get("rules") or [], base)
    fl = footprints(place, t.get("flat_under", ["solids", "road", "path", "asphalt", "dirt_road", "gravel", "sidewalk"]))
    h = flatten(h, size, fl, float(t.get("flat_margin_m", 6.0)), float(t.get("flat_level_m", 0.0)))
    lo, hi = float(h.min()), float(h.max())
    if hi - lo < 0.01:
        hi = lo + 0.01
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    r16 = out / f"{pid}.terrain.r16"
    write_r16(h, r16, lo, hi)
    nx, ny = h.shape[1], h.shape[0]
    spacing = float(size[0]) / (nx - 1)
    block = {"height": r16.name, "size_m": [round(spacing * (nx - 1), 4), round(spacing * (ny - 1), 4)],
             "range_m": [round(lo, 4), round(hi, 4)],
             "pixels": [nx, ny], "origin_m": [0.0, 0.0], "surfaces": t.get("surfaces") or [{"word": "grass"}],
             "flat": len(fl)}
    (out / f"{pid}.terrain.json").write_text(json.dumps(block, indent=1) + "\n", encoding="utf-8")
    return block


# ----------------------------------------------------------------------------------------------- surfaces
def pack_for_terrain(picture: Path, out_dir=None, roughness: float = 0.85, size: int = 1024) -> dict:
    """Colour with height in alpha (`<name>_t3d_albedo.png`) and normal with roughness in alpha (`<name>_t3d_normal.png`).
    Height comes from the picture's own tone, high-passed (BUILD 63's relief idea); the normal from `<name>_n.png` when
    it is there, else from that height."""
    from PIL import Image
    from . import relief
    pic = Path(picture)
    out = Path(out_dir) if out_dir else pic.parent
    out.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(Image.open(pic).convert("RGB").resize((size, size), Image.LANCZOS), dtype=float) / 255.0
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    hp = lum - relief.blur_wrap(lum, size / 32.0)
    height = np.clip(0.5 + hp * 2.2, 0.0, 1.0)
    alb = np.dstack([rgb, height])
    a_path = out / f"{pic.stem}_t3d_albedo.png"
    Image.fromarray((alb * 255).round().astype(np.uint8), "RGBA").save(a_path)
    npath = pic.with_name(f"{pic.stem}_n.png")
    if npath.exists():
        nrm = np.asarray(Image.open(npath).convert("RGB").resize((size, size), Image.LANCZOS), dtype=float) / 255.0
    else:
        nrm = relief.normal_from_height(height, 6.0)
        if nrm.max() > 1.5:
            nrm = nrm / 255.0
    nor = np.dstack([nrm, np.full(height.shape, float(roughness))])
    n_path = out / f"{pic.stem}_t3d_normal.png"
    Image.fromarray((np.clip(nor, 0, 1) * 255).round().astype(np.uint8), "RGBA").save(n_path)
    return {"picture": str(pic), "albedo": str(a_path), "normal": str(n_path), "normal_from": npath.name if npath.exists() else "height"}
