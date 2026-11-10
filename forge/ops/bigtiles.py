"""Tiled refine for pictures larger than one diffusion pass (Night 3, G3) — the CPU half: plan, split, merge, seams.

(`forge/ops/tiles.py` is the older module for *tileable textures*; this one is about cutting one big picture into
overlapping working tiles and putting it back together without a visible join.)

    plan(size, tile, overlap)   → [(x0, y0, x1, y1)] covering the picture: every tile exactly `tile` (or the whole axis
                                  if the picture is smaller), neighbours overlapping by ≥ `overlap`, starts on a multiple
                                  of 8 where possible, the last tile flush with the edge — so there are no sliver tiles
    split(img, rects)           → the crops
    merge(tiles, rects, size)   → one picture; each tile weighted by a smooth ramp across every overlap it shares
                                  (weight 1 at the picture's own border), deterministic
    seams(tiles, rects)         → per overlap: mean colour and gradient difference between the two tiles' versions of
                                  the shared strip (0 = identical); `score` = their mean, in 0–255 units
    seam_sheet(img, rects, seams) → a ≤ 2,000 px overview with the tile grid drawn and the worst seams outlined
"""
from __future__ import annotations
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _axis(length: int, tile: int, overlap: int, snap: int = 8) -> list[int]:
    if length <= tile:
        return [0]
    overlap = max(0, min(int(overlap), tile - 1))
    n = math.ceil((length - overlap) / (tile - overlap))
    step = (length - tile) / (n - 1)
    starts = []
    for i in range(n):
        s = int(round(i * step))
        if 0 < i < n - 1:
            s = int(round(s / snap) * snap)
        starts.append(s)
    starts[-1] = length - tile
    # snapping can only shrink an overlap by < snap px; keep it ≥ the asked overlap by adding a tile if it broke
    if any(starts[i] + tile - starts[i + 1] < overlap for i in range(n - 1)):
        return _axis(length, tile, overlap + snap, snap)
    return starts


def plan(size, tile=(1344, 768), overlap: int = 128) -> list[tuple[int, int, int, int]]:
    W, H = int(size[0]), int(size[1])
    tw, th = min(int(tile[0]), W), min(int(tile[1]), H)
    xs, ys = _axis(W, tw, overlap), _axis(H, th, overlap)
    return [(x, y, x + tw, y + th) for y in ys for x in xs]


def grid_shape(rects) -> tuple[int, int]:
    return len({r[0] for r in rects}), len({r[1] for r in rects})


def split(img: Image.Image, rects) -> list[Image.Image]:
    return [img.crop(r) for r in rects]


def _ramp(n: int) -> np.ndarray:
    """0→1 smoothstep over n samples, never exactly 0 (so every pixel has some weight)."""
    if n <= 0:
        return np.ones(0)
    t = (np.arange(n) + 0.5) / n
    return np.clip(t * t * (3 - 2 * t), 1e-4, 1.0)


def weights(rect, rects, size) -> np.ndarray:
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    wx, wy = np.ones(w), np.ones(h)
    for o in rects:
        if o == rect:
            continue
        ox0, oy0, ox1, oy1 = o
        if oy0 < y1 and oy1 > y0:                       # shares rows → a left or right neighbour
            if x0 < ox1 <= x1 and ox0 < x0:              # neighbour on the left, overlapping our left edge
                n = ox1 - x0
                wx[:n] = np.minimum(wx[:n], _ramp(n))
            if x0 <= ox0 < x1 and ox1 > x1:              # on the right
                n = x1 - ox0
                wx[w - n:] = np.minimum(wx[w - n:], _ramp(n)[::-1])
        if ox0 < x1 and ox1 > x0:                       # shares columns → above or below
            if y0 < oy1 <= y1 and oy0 < y0:
                n = oy1 - y0
                wy[:n] = np.minimum(wy[:n], _ramp(n))
            if y0 <= oy0 < y1 and oy1 > y1:
                n = y1 - oy0
                wy[h - n:] = np.minimum(wy[h - n:], _ramp(n)[::-1])
    return wy[:, None] * wx[None, :]


def merge(tiles: list[Image.Image], rects, size, mode: str = "RGB") -> Image.Image:
    W, H = int(size[0]), int(size[1])
    acc = np.zeros((H, W, len(mode)), dtype=np.float64)
    wsum = np.zeros((H, W, 1), dtype=np.float64)
    for t, r in zip(tiles, rects):
        x0, y0, x1, y1 = r
        a = np.asarray(t.convert(mode).resize((x1 - x0, y1 - y0), Image.LANCZOS) if t.size != (x1 - x0, y1 - y0) else t.convert(mode),
                       dtype=np.float64).reshape(y1 - y0, x1 - x0, len(mode))
        wt = weights(r, rects, size)[..., None]
        acc[y0:y1, x0:x1] += a * wt
        wsum[y0:y1, x0:x1] += wt
    out = acc / np.maximum(wsum, 1e-12)
    return Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8).squeeze() if len(mode) == 1 else
                           np.clip(np.round(out), 0, 255).astype(np.uint8), mode)


def _grad(a: np.ndarray) -> np.ndarray:
    g = a.mean(axis=2)
    gx = np.zeros_like(g)
    gy = np.zeros_like(g)
    gx[:, 1:] = np.diff(g, axis=1)
    gy[1:, :] = np.diff(g, axis=0)
    return np.hypot(gx, gy)


def seams(tiles: list[Image.Image], rects) -> list[dict]:
    """One record per pair of overlapping neighbours (left/right or above/below — diagonals are covered by those)."""
    arrs = [np.asarray(t.convert("RGB"), dtype=np.float64) for t in tiles]
    out = []
    for i, a in enumerate(rects):
        for j in range(i + 1, len(rects)):
            b = rects[j]
            ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            side_by_side = a[1] == b[1] and a[3] == b[3]
            stacked = a[0] == b[0] and a[2] == b[2]
            if not (side_by_side or stacked):
                continue
            pa = arrs[i][iy0 - a[1]:iy1 - a[1], ix0 - a[0]:ix1 - a[0]]
            pb = arrs[j][iy0 - b[1]:iy1 - b[1], ix0 - b[0]:ix1 - b[0]]
            col = float(np.abs(pa - pb).mean())
            grd = float(np.abs(_grad(pa) - _grad(pb)).mean())
            out.append({"a": i, "b": j, "rect": [ix0, iy0, ix1, iy1], "dir": "h" if side_by_side else "v",
                        "colour": round(col, 3), "gradient": round(grd, 3), "score": round((col + grd) / 2, 3)})
    return out


def seam_sheet(img: Image.Image, rects, seam_list: list[dict], worst: int = 3, max_side: int = 2000) -> Image.Image:
    k = min(1.0, max_side / max(img.size))
    im = img.convert("RGB").resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS) if k < 1 else img.convert("RGB").copy()
    d = ImageDraw.Draw(im)
    for n, r in enumerate(rects):
        d.rectangle([int(c * k) for c in r], outline=(90, 200, 255), width=1)
        d.text((int(r[0] * k) + 4, int(r[1] * k) + 3), f"t{n}", fill=(90, 200, 255))
    ranked = sorted(seam_list, key=lambda s: -s["score"])
    for s in ranked[:worst]:
        bx = [int(c * k) for c in s["rect"]]
        d.rectangle(bx, outline=(255, 70, 70), width=3)
        d.text((bx[0] + 4, bx[1] + 4), f"{s['score']:.1f}", fill=(255, 90, 90))
    for s in ranked[worst:]:
        bx = [int(c * k) for c in s["rect"]]
        d.text((bx[0] + 4, bx[1] + 4), f"{s['score']:.1f}", fill=(200, 200, 200))
    return im


def fake_repaint(tile: Image.Image) -> Image.Image:
    """The tiles-demo stand-in for a diffusion repaint: deterministic, and different near a tile's edges (a blur
    sees the edge) — the same kind of disagreement a real repaint has, so the merge has something to hide."""
    t = tile.convert("RGB").filter(ImageFilter.GaussianBlur(2.0))
    a = np.asarray(t, dtype=np.float64)
    a = (a - 128.0) * 1.08 + 128.0
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def demo(src: Image.Image, tile=(1344, 768), overlap: int = 128, fn=fake_repaint):
    """Split → fn on every tile → merge, with seams. Returns (merged, rects, seams, naive) — `naive` pastes the tiles
    with no blend, for comparison."""
    rects = plan(src.size, tile, overlap)
    done = [fn(t) for t in split(src, rects)]
    merged = merge(done, rects, src.size)
    naive = Image.new("RGB", src.size)
    for t, r in zip(done, rects):
        naive.paste(t, r[:2])
    return merged, rects, seams(done, rects), naive


def test_picture(size=(6144, 3072)) -> Image.Image:
    """A deterministic picture with gradients, edges and fine texture — something a seam would show on."""
    W, H = size
    y, x = np.mgrid[0:H, 0:W].astype(np.float64)
    r = 128 + 100 * np.sin(x / 290.0) * np.cos(y / 410.0)
    g = 40 + 180 * (y / H)
    b = 128 + 90 * np.sin((x + y) / 97.0)
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 9, (H, W))
    a = np.stack([r + noise, g + noise, b + noise], axis=2)
    a[(x // 512 + y // 512) % 2 == 0] *= 0.85
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
