"""The autotile builder: from base materials and an edge-mask style, every tile a terrain needs.

Transitions are painted by a mask, never generated, so every material in a game joins the same way
(forge/ops/tiles.py's rule). What it builds:

  blob47     the 47-tile blob set of material A on material B (Godot "Match Corners and Sides"), plus B's fill tile
  set16      the 16-tile corner set (Godot "Match Corners") for simple edges
  walls      a strip of three faces — top, front, cap — cut from one crop of the wall material so the faces line up
  variants   4–8 versions of a tile that differ inside and keep their borders, so neighbours still join
  decals     cracks, stains, scorch marks and debris as separate RGBA overlays (scattered by a map, never baked in)

Every tile comes with its normal map (tangent space, OpenGL: green = up — what Godot's CanvasTexture and the scene kit
use). A tile set is written as an albedo atlas, a normal atlas and a manifest that names each tile's neighbour bits in
Godot's own words (top_side, top_right_corner, …) so the TileSet resource can be written from it.

A material passed in must already tile (make it seamless first). Two ways to draw with it, both written by build_set:

  baked      each tile carries its own pixels: the material resized so one tile shows one period (what keeps the
             texture continuous from tile to tile). Simple, works anywhere — but a 1024 px material squeezed into one
             tile loses its detail and repeats every tile. Bake at 2x or more of the game's tile size for sharpness.
  world      the sharp way (William, 2026-11-12: "the highest resolution tiles, so the game looks vivid and sharp"):
             the material stays at its full resolution as one seamless texture laid across the whole map in world
             space (one period spans many tiles, so it doesn't repeat tile by tile), and the tiles carry only the
             transition masks. The game's tile shader samples A and B at full resolution and blends them by the mask;
             the lip and rim come from the mask too. Written as <name>_world_<a|b>.png (+ _n), <name>_masks.png.
"""
from __future__ import annotations
import json, math
from pathlib import Path

import numpy as np
from PIL import Image

# ---------------------------------------------------------------- neighbours
# bit order: N, NE, E, SE, S, SW, W, NW  (clockwise from the top)
DIRS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
OFFS = {"N": (0, -1), "NE": (1, -1), "E": (1, 0), "SE": (1, 1), "S": (0, 1), "SW": (-1, 1), "W": (-1, 0), "NW": (-1, -1)}
GODOT = {"N": "top_side", "NE": "top_right_corner", "E": "right_side", "SE": "bottom_right_corner", "S": "bottom_side",
         "SW": "bottom_left_corner", "W": "left_side", "NW": "top_left_corner"}
CORNERS = {"NE": ("N", "E"), "SE": ("S", "E"), "SW": ("S", "W"), "NW": ("N", "W")}


def bit(d: str) -> int:
    return 1 << DIRS.index(d)


def reduce_mask(m: int) -> int:
    """A corner counts only when both sides beside it are set (the blob rule): 256 masks → 47."""
    out = m
    for c, (a, b) in CORNERS.items():
        if not (m & bit(a) and m & bit(b)):
            out &= ~bit(c)
    return out


BLOB47 = sorted({reduce_mask(m) for m in range(256)})
assert len(BLOB47) == 47


def mask_of(cells, x: int, y: int, outside: int = 0) -> int:
    """The 8-neighbour mask of cell (x, y) in a 2D list of 0/1 (outside the map counts as `outside`)."""
    h, w = len(cells), len(cells[0])
    m = 0
    for d in DIRS:
        dx, dy = OFFS[d]
        xx, yy = x + dx, y + dy
        v = cells[yy][xx] if 0 <= xx < w and 0 <= yy < h else outside
        if v:
            m |= bit(d)
    return m


def peering(mask: int) -> list[str]:
    return [GODOT[d] for d in DIRS if mask & bit(d)]


# ---------------------------------------------------------------- edge-mask styles
STYLES = {
    # width of the transition (fraction of the tile), how ragged it is (fraction), the noise's frequency
    "soft":   {"w": 0.30, "rag": 0.00, "freq": 0},
    "hard":   {"w": 0.10, "rag": 0.00, "freq": 0},
    "ragged": {"w": 0.24, "rag": 0.05, "freq": 2},
    "crumbly": {"w": 0.26, "rag": 0.08, "freq": 4},
}


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / max(e1 - e0, 1e-6), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _ragged(u: np.ndarray, T: int, style: dict, phase: float) -> np.ndarray:
    """A wobble along an edge that is zero at both ends of the edge, so tiles still meet exactly at their corners
    and borders; the same function for every edge of every tile."""
    if not style["rag"]:
        return np.zeros_like(u)
    f = style["freq"]
    t = u / T
    win = np.sin(np.pi * t) ** 2
    wave = 0.6 * np.sin(2 * np.pi * f * t + phase) + 0.4 * np.sin(2 * np.pi * (2 * f + 1) * t + 1.7 * phase)
    return style["rag"] * T * win * wave


def blob_mask(mask: int, T: int, style: str = "ragged") -> np.ndarray:
    """Alpha of material A in a tile whose (reduced) neighbour mask is `mask`: 1 = A, 0 = B. Along every border the
    values depend only on what the two tiles sharing it agree on, so any two neighbours meet without a seam."""
    st = STYLES[style]
    w0 = st["rag"] * T + 0.5           # nothing of A reaches the edge where A stops (the wobble never crosses it)
    w1 = w0 + st["w"] * T
    yy, xx = np.mgrid[0:T, 0:T].astype(np.float64) + 0.5
    M = np.ones((T, T))
    side_dist = {"N": (yy, xx), "S": (T - yy, xx), "W": (xx, yy), "E": (T - xx, yy)}
    for d, (dist, along) in side_dist.items():
        if not mask & bit(d):
            M = np.minimum(M, _smooth(w0, w1, dist - _ragged(along, T, st, DIRS.index(d) * 0.7)))
    corner_at = {"NE": (T, 0), "SE": (T, T), "SW": (0, T), "NW": (0, 0)}
    for c, (a, b) in CORNERS.items():
        if mask & bit(a) and mask & bit(b) and not mask & bit(c):
            cx, cy = corner_at[c]
            r = np.hypot(xx - cx, yy - cy)
            ang = np.arctan2(np.abs(yy - cy), np.abs(xx - cx))          # 0 .. pi/2 inside the tile
            calm = {**st, "freq": max(1, st["freq"] // 2), "rag": st["rag"] * 0.6}   # a short arc: fewer, smaller wobbles
            wob = _ragged(ang / (np.pi / 2) * T, T, calm, DIRS.index(c) * 0.7)
            M = np.minimum(M, _smooth(w0, w1, r - wob))
    return M


def corner_mask(corners: tuple[int, int, int, int], T: int, style: str = "ragged") -> np.ndarray:
    """Alpha of A in a 16-set tile from its corners (top-left, top-right, bottom-right, bottom-left). Bilinear between
    the corners, so a border depends only on its two corners; the wobble is zero on every border."""
    st = STYLES[style]
    tl, tr, br, bl = (float(c) for c in corners)
    yy, xx = np.mgrid[0:T, 0:T].astype(np.float64) + 0.5
    u, v = xx / T, yy / T
    f = tl * (1 - u) * (1 - v) + tr * u * (1 - v) + br * u * v + bl * (1 - u) * v
    if st["rag"]:
        win = (np.sin(np.pi * u) * np.sin(np.pi * v)) ** 2
        f = f + st["rag"] * 2 * win * np.sin(2 * np.pi * st["freq"] * (u + 0.37 * v))
    half = max(st["w"], 0.05)
    return _smooth(0.5 - half, 0.5 + half, f)


SET16 = [(tl, tr, br, bl) for tl in (0, 1) for tr in (0, 1) for br in (0, 1) for bl in (0, 1)]


# ---------------------------------------------------------------- pixels
def as_tile(img: Image.Image, T: int) -> np.ndarray:
    """A seamless material at tile size, float RGB 0..1 (one period per tile)."""
    return np.asarray(img.convert("RGB").resize((T, T), Image.LANCZOS), dtype=np.float64) / 255.0


def lum(a: np.ndarray) -> np.ndarray:
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def normals_from_height(h: np.ndarray, strength: float = 4.0, wrap: bool = False) -> np.ndarray:
    """Height (0..1, brighter = nearer) → unit normals, OpenGL (+y up). wrap=True for a tile that tiles."""
    mode = "wrap" if wrap else "edge"
    p = np.pad(h, 1, mode=mode)
    gx = (p[1:-1, 2:] - p[1:-1, :-2]) / 2.0
    gy = (p[2:, 1:-1] - p[:-2, 1:-1]) / 2.0
    nx, ny, nz = -gx * strength, gy * strength, np.ones_like(h)   # image y runs down; OpenGL's runs up
    n = np.stack([nx, ny, nz], axis=-1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def encode_normals(n: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip((n * 0.5 + 0.5) * 255 + 0.5, 0, 255).astype(np.uint8), "RGB")


def to_img(a: np.ndarray, mode="RGB") -> Image.Image:
    return Image.fromarray(np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8), mode)


def compose(a: np.ndarray, b: np.ndarray, M: np.ndarray, lip: float = 0.08, strength: float = 4.0):
    """Albedo and normals of A over B through mask M. A little lip where A meets B (a raised edge, a darker rim),
    so the join catches the light."""
    rim = (M * (1 - M)) * 4.0                        # 1 at the middle of the transition
    albedo = a * M[..., None] + b * (1 - M[..., None])
    albedo = albedo * (1 - 0.12 * rim[..., None])
    h = lum(a) * M + lum(b) * (1 - M) + lip * M
    return albedo, normals_from_height(h, strength)


# ---------------------------------------------------------------- the sets
def blob_tiles(mat_a: Image.Image, mat_b: Image.Image, T: int, style: str = "ragged") -> list[dict]:
    a, b = as_tile(mat_a, T), as_tile(mat_b, T)
    out = []
    for m in BLOB47:
        M = blob_mask(m, T, style)
        alb, nrm = compose(a, b, M)
        out.append({"kind": "blob", "mask": m, "peering": peering(m), "albedo": alb, "normal": nrm, "alpha": M})
    alb, nrm = compose(a, b, np.zeros((T, T)))
    out.append({"kind": "fill", "mask": None, "peering": [], "albedo": alb, "normal": nrm, "alpha": np.zeros((T, T))})
    return out


def set16_tiles(mat_a: Image.Image, mat_b: Image.Image, T: int, style: str = "ragged") -> list[dict]:
    a, b = as_tile(mat_a, T), as_tile(mat_b, T)
    names = ("top_left_corner", "top_right_corner", "bottom_right_corner", "bottom_left_corner")
    out = []
    for cs in SET16:
        M = corner_mask(cs, T, style)
        alb, nrm = compose(a, b, M)
        out.append({"kind": "corner16", "corners": list(cs), "peering": [n for n, c in zip(names, cs) if c],
                    "albedo": alb, "normal": nrm, "alpha": M})
    return out


def wall_tiles(mat: Image.Image, T: int, top_shade: float = 0.78, lip: float = 0.12) -> list[dict]:
    """Top face, front face and cap, all from one crop of the wall material (so the columns line up between faces).
    The front faces the camera (its normal tips down the screen), the cap's lip catches light from above."""
    w = as_tile(mat, T)
    yy = (np.mgrid[0:T, 0:T][0] + 0.5) / T
    h = lum(w)
    top = w * top_shade
    n_top = normals_from_height(h, 3.0, wrap=True)
    shade = 1.0 - 0.35 * yy ** 1.5                                   # lighter at the top, darker toward the floor
    ao = 1.0 - 0.45 * _smooth(0.82, 1.0, yy)                         # contact shadow at the foot
    front = w * (shade * ao)[..., None]
    n_front = normals_from_height(h, 3.0, wrap=True)
    tilt = np.array([0.0, -0.55, 0.835])                             # faces the viewer: toward the bottom of the screen
    n_front = n_front * 0.5 + tilt * 0.5
    n_front /= np.linalg.norm(n_front, axis=-1, keepdims=True)
    cap = top.copy()
    band = _smooth(1 - lip * 2, 1 - lip, yy)                         # the lip along the cap's lower edge
    cap = cap * (1 - band[..., None]) + np.clip(w * 1.15, 0, 1) * band[..., None]
    n_cap = n_top.copy()
    up = np.array([0.0, 0.6, 0.8])
    n_cap = n_cap * (1 - band[..., None]) + up * band[..., None]
    n_cap /= np.linalg.norm(n_cap, axis=-1, keepdims=True)
    return [{"kind": "wall_top", "albedo": top, "normal": n_top, "blocking": True},
            {"kind": "wall_front", "albedo": front, "normal": n_front, "blocking": True},
            {"kind": "wall_cap", "albedo": cap, "normal": n_cap, "blocking": True}]


def variant_tiles(mat: Image.Image, T: int, n: int = 6, seed: int = 0, band: float = 0.18) -> list[dict]:
    """n versions of a material tile: the inside is rolled, turned and nudged in value; a band at the border stays the
    base's, so every variant still joins every other one and every transition tile."""
    rng = np.random.default_rng(seed)
    base = as_tile(mat, T)
    yy, xx = np.mgrid[0:T, 0:T].astype(np.float64) + 0.5
    edge = np.minimum.reduce([xx, yy, T - xx, T - yy]) / T
    keep = 1 - _smooth(band * 0.5, band * 1.5, edge)                 # 1 at the border, 0 inside
    out = [{"kind": "variant", "variant": 0, "albedo": base, "normal": normals_from_height(lum(base), 4.0, wrap=True)}]
    for i in range(1, n):
        v = np.roll(np.roll(base, int(rng.integers(0, T)), axis=0), int(rng.integers(0, T)), axis=1)
        k = int(rng.integers(0, 4))
        v = np.rot90(v, k, axes=(0, 1)).copy()
        v = np.clip(v * (1 + rng.uniform(-0.05, 0.05)) + rng.uniform(-0.02, 0.02), 0, 1)
        alb = base * keep[..., None] + v * (1 - keep[..., None])
        out.append({"kind": "variant", "variant": i, "albedo": alb, "normal": normals_from_height(lum(alb), 4.0, wrap=True)})
    return out


# ---------------------------------------------------------------- decals
def _blur(a: np.ndarray, r: int) -> np.ndarray:
    if r <= 0:
        return a
    k = np.ones(2 * r + 1) / (2 * r + 1)
    a = np.apply_along_axis(lambda v: np.convolve(np.pad(v, r, mode="edge"), k, "valid"), 0, a)
    return np.apply_along_axis(lambda v: np.convolve(np.pad(v, r, mode="edge"), k, "valid"), 1, a)


def decal(kind: str, T: int, seed: int) -> dict:
    """One RGBA overlay with its normals: crack · stain · scorch · debris. Seeded; transparent at its border."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:T, 0:T].astype(np.float64) + 0.5
    alpha = np.zeros((T, T))
    rgb = np.zeros((T, T, 3))
    height = np.zeros((T, T))
    if kind == "crack":
        x, y = T * rng.uniform(0.3, 0.7), T * rng.uniform(0.3, 0.7)
        ang = rng.uniform(0, 2 * np.pi)
        for _ in range(3):
            px, py, a = x, y, ang + rng.uniform(-2, 2)
            for _s in range(int(T * 0.6)):
                a += rng.normal(0, 0.25)
                px += math.cos(a)
                py += math.sin(a)
                if not (2 < px < T - 2 and 2 < py < T - 2):
                    break
                d = np.hypot(xx - px, yy - py)
                alpha = np.maximum(alpha, np.clip(1.6 - d, 0, 1))
        rgb[:] = (0.08, 0.07, 0.06)
        height = -alpha
    elif kind == "stain":
        cx, cy = T * rng.uniform(0.35, 0.65), T * rng.uniform(0.35, 0.65)
        r = T * rng.uniform(0.18, 0.32)
        noise = _blur(rng.random((T, T)), max(1, T // 16))
        d = np.hypot(xx - cx, yy - cy) / r + (noise - 0.5) * 0.9
        alpha = 0.55 * (1 - _smooth(0.6, 1.0, d))
        rgb[:] = (0.20, 0.16, 0.10)
    elif kind == "scorch":
        cx, cy = T * 0.5, T * 0.5
        noise = _blur(rng.random((T, T)), max(1, T // 12))
        d = np.hypot(xx - cx, yy - cy) / (T * 0.42) + (noise - 0.5) * 0.6
        alpha = 0.85 * (1 - _smooth(0.2, 1.0, d))
        rgb[:] = (0.04, 0.03, 0.03)
    elif kind == "debris":
        for _ in range(int(rng.integers(6, 14))):
            cx, cy = T * rng.uniform(0.15, 0.85), T * rng.uniform(0.15, 0.85)
            r = T * rng.uniform(0.02, 0.06)
            d = np.hypot((xx - cx) * rng.uniform(0.7, 1.3), (yy - cy) * rng.uniform(0.7, 1.3))
            chip = np.clip((r - d) / 1.5, 0, 1)
            alpha = np.maximum(alpha, chip)
            height = np.maximum(height, chip * np.clip(1 - d / max(r, 1e-6), 0, 1))
        shade = rng.uniform(0.35, 0.55)
        rgb[:] = (shade, shade * 0.95, shade * 0.9)
    else:
        raise ValueError(f"no decal kind '{kind}' (crack · stain · scorch · debris)")
    border = _smooth(0.0, 0.08, np.minimum.reduce([xx, yy, T - xx, T - yy]) / T)
    alpha = alpha * border
    rgba = np.concatenate([rgb, alpha[..., None]], axis=-1)
    return {"kind": f"decal_{kind}", "seed": int(seed), "rgba": rgba, "normal": normals_from_height(height * 0.5 + 0.5, 3.0)}


DECAL_KINDS = ("crack", "stain", "scorch", "debris")


# ---------------------------------------------------------------- writing a set
def atlas(tiles: list[dict], T: int, cols: int = 8, key: str = "albedo") -> Image.Image:
    rows = (len(tiles) + cols - 1) // cols
    mode = "RGBA" if key == "rgba" else "RGB"
    im = Image.new(mode, (cols * T, rows * T), (0, 0, 0, 0) if mode == "RGBA" else (0, 0, 0))
    for i, t in enumerate(tiles):
        a = t[key]
        piece = encode_normals(a) if key == "normal" else to_img(a, mode)
        im.paste(piece, ((i % cols) * T, (i // cols) * T))
    return im


def world_textures(img: Image.Image, max_px: int = 4096) -> tuple[Image.Image, Image.Image]:
    """A material at its own full resolution (capped), with its normals made to wrap — for world-space drawing."""
    im = img.convert("RGB")
    if max(im.size) > max_px:
        im = im.resize((max_px, max_px), Image.LANCZOS)
    a = np.asarray(im, dtype=np.float64) / 255.0
    return im, encode_normals(normals_from_height(lum(a), 4.0, wrap=True))


def mask_atlas(tiles: list[dict], T: int, cols: int = 8) -> Image.Image:
    rows = (len(tiles) + cols - 1) // cols
    im = Image.new("L", (cols * T, rows * T), 0)
    for i, t in enumerate(tiles):
        im.paste(Image.fromarray(np.clip(t["alpha"] * 255 + 0.5, 0, 255).astype(np.uint8), "L"), ((i % cols) * T, (i // cols) * T))
    return im


def build_set(name: str, out_dir: Path, *, floor: Image.Image, edge: Image.Image | None = None,
              wall: Image.Image | None = None, T: int = 192, style: str = "ragged", variants: int = 6,
              decals: int = 2, seed: int = 0, kind: str = "blob47", info: dict | None = None,
              world: bool = True, world_max_px: int = 4096) -> dict:
    """A whole tile set for one material: its variants, its transitions onto `edge` (blob47 or set16), the wall strip
    of `wall`, and decals. Writes <name>.png, <name>_n.png, <name>_decals.png, <name>_decals_n.png and <name>.json."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tiles = variant_tiles(floor, T, variants, seed)
    if edge is not None:
        tiles += blob_tiles(floor, edge, T, style) if kind == "blob47" else set16_tiles(floor, edge, T, style)
    if wall is not None:
        tiles += wall_tiles(wall, T)
    cols = 8
    atlas(tiles, T, cols).save(out_dir / f"{name}.png")
    atlas(tiles, T, cols, "normal").save(out_dir / f"{name}_n.png")
    dec = [decal(k, T, seed * 31 + i * 7 + j) for i, k in enumerate(DECAL_KINDS) for j in range(decals)]
    if dec:
        atlas(dec, T, cols, "rgba").save(out_dir / f"{name}_decals.png")
        atlas(dec, T, cols, "normal").save(out_dir / f"{name}_decals_n.png")
    world_rec = None
    if world:
        wa, wn = world_textures(floor, world_max_px)
        wa.save(out_dir / f"{name}_world_a.png")
        wn.save(out_dir / f"{name}_world_a_n.png")
        world_rec = {"a": f"{name}_world_a.png", "a_px": wa.width, "period_tiles_a": round(wa.width / T, 2)}
        if edge is not None:
            wb, wbn = world_textures(edge, world_max_px)
            wb.save(out_dir / f"{name}_world_b.png")
            wbn.save(out_dir / f"{name}_world_b_n.png")
            world_rec.update({"b": f"{name}_world_b.png", "b_px": wb.width, "period_tiles_b": round(wb.width / T, 2)})
            trans = [t for t in tiles if "alpha" in t]
            mask_atlas(trans, T, cols).save(out_dir / f"{name}_masks.png")
            world_rec["masks"] = f"{name}_masks.png"
            world_rec["mask_order"] = [t.get("mask", t.get("corners")) for t in trans]
    man = {"name": name, "tile_size": T, "columns": cols, "kind": kind, "style": style, "seed": seed, "world": world_rec,
           "normals": "tangent space, OpenGL (green = up)", "info": info or {},
           "tiles": [{"index": i, "col": i % cols, "row": i // cols, "kind": t["kind"],
                      **({"mask": t["mask"]} if t.get("mask") is not None else {}),
                      **({"corners": t["corners"]} if "corners" in t else {}),
                      **({"variant": t["variant"]} if "variant" in t else {}),
                      "peering": t.get("peering", []), "blocking": bool(t.get("blocking"))} for i, t in enumerate(tiles)],
           "decals": [{"index": i, "col": i % cols, "row": i // cols, "kind": d["kind"], "seed": d["seed"]}
                      for i, d in enumerate(dec)]}
    (out_dir / f"{name}.json").write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8", newline="\n")
    return man


def tile_for(cells, x: int, y: int) -> int | None:
    """Which blob tile a cell of material A takes (its reduced mask); None for a cell of B (the fill tile)."""
    return reduce_mask(mask_of(cells, x, y)) if cells[y][x] else None
