"""Tileable surfaces: seam scoring, making a texture seamless, jittered variants.

Autotile *rules* (corners, edges, transitions) are deliberately not generated — they are built by
code from a base tile and an edge mask so every material in the game joins up the same way. That
builder lands with the first real tileset (see docs/ROADMAP.md).
"""
from __future__ import annotations
import numpy as np
from PIL import Image


def seam_score(img: Image.Image) -> float:
    """Mean absolute difference across the wrap seams (left↔right, top↔bottom), 0 = perfect tile.
    Normalised to the image's own internal neighbour difference, so 1.0 ≈ 'the seam is as rough as
    the texture itself' and > 1.5 means a visible line."""
    a = np.asarray(img.convert("RGB"), dtype=np.float64)
    inner = (np.abs(np.diff(a, axis=1)).mean() + np.abs(np.diff(a, axis=0)).mean()) / 2.0 + 1e-6
    lr = np.abs(a[:, 0, :] - a[:, -1, :]).mean()
    tb = np.abs(a[0, :, :] - a[-1, :, :]).mean()
    return float(((lr + tb) / 2.0) / inner)


def make_seamless(img: Image.Image, blend: float = 0.25) -> Image.Image:
    """Offset by half in both axes and cross-blend the (now central) seams with a smooth mask.
    Classic, deterministic, good enough for ground textures; architectural tiles are built, not blended."""
    a = np.asarray(img.convert("RGB"), dtype=np.float64)
    h, w = a.shape[:2]
    rolled = np.roll(np.roll(a, h // 2, axis=0), w // 2, axis=1)
    # weights fade toward the centre lines where the old borders now meet
    yy = np.abs((np.arange(h) - h / 2) / (h / 2))[:, None]
    xx = np.abs((np.arange(w) - w / 2) / (w / 2))[None, :]
    band = blend
    wy = np.clip(yy / band, 0, 1)
    wx = np.clip(xx / band, 0, 1)
    wgt = np.minimum(wy, wx)[..., None]  # 0 at the seams, 1 away from them
    out = rolled * wgt + a * (1.0 - wgt)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def jitter_variants(tile: Image.Image, n: int = 4, seed: int = 0, strength: int = 6) -> Image.Image:
    """N variants of a tile with small per-pixel value jitter (breaks the repeating-tile look).
    Returns a horizontal strip. Pixel art stays pixel art: nearest colours are preserved by a later snap."""
    rng = np.random.default_rng(seed)
    a = np.asarray(tile.convert("RGBA")).astype(np.int32)
    strip = Image.new("RGBA", (tile.width * n, tile.height), (0, 0, 0, 0))
    for i in range(n):
        v = a.copy()
        if i > 0:
            noise = rng.integers(-strength, strength + 1, size=a.shape[:2])[..., None]
            v[..., :3] = np.clip(v[..., :3] + noise, 0, 255)
            # also roll a few pixels so texture features move
            v = np.roll(v, rng.integers(0, tile.width), axis=1)
            v = np.roll(v, rng.integers(0, tile.height), axis=0)
        strip.paste(Image.fromarray(v.astype(np.uint8), "RGBA"), (i * tile.width, 0))
    return strip
