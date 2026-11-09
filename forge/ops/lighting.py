"""Lighting helpers for painted maps (F11): a normal map from luminance, and an emissive mask.

The game's painted-map format has optional `<id>_n.png` (normal map → Godot's CanvasTexture normal) and
`<id>_e.png` (an additive glow layer) slots. These ops make a first version of each from the painting alone —
good enough to see lights respond; a painter can always do better by hand.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from .edges import blur, luminance, sobel


def normal_map(img: Image.Image, strength: float = 2.0, smooth: float = 1.0, invert_y: bool = False) -> Image.Image:
    """Height = luminance (brighter = nearer) → tangent-space normals, OpenGL convention (green = up), which is
    what Godot expects. `invert_y` for DirectX-style consumers. RGB image, same size."""
    h = blur(luminance(img), smooth)
    gx, gy = sobel(h)
    nx = -gx * float(strength)
    ny = gy * float(strength)          # image y runs down; OpenGL's runs up
    if invert_y:
        ny = -ny
    nz = np.ones_like(nx)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    rgb = np.stack([nx / norm, ny / norm, nz / norm], axis=-1) * 0.5 + 0.5
    return Image.fromarray(np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGB")


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def emissive_mask(img: Image.Image, threshold: float = 0.85, min_saturation: float = 0.25,
                  colors: list[str] | None = None, tolerance: int = 40, feather: float = 1.5) -> tuple[Image.Image, float]:
    """Pixels that glow: bright AND saturated (screens, neon, cores, lit windows), plus any pixel near one of
    `colors`. Returns (RGB image — the glowing colours on black, for an additive layer; fraction of pixels lit)."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    mx = rgb.max(axis=-1) / 255.0
    mn = rgb.min(axis=-1) / 255.0
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    mask = (mx >= threshold) & (sat >= min_saturation)
    for c in colors or []:
        r, g, b = _hex(c)
        d = np.abs(rgb - np.array([r, g, b], dtype=np.float32)).max(axis=-1)
        mask |= d <= tolerance
    m = mask.astype(np.float32)
    if feather > 0:
        m = np.clip(blur(m, feather) * 1.5, 0.0, 1.0)
    out = (rgb * m[..., None]).astype(np.uint8)
    return Image.fromarray(out, "RGB"), float(mask.mean())
