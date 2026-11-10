"""Depth-based lighting helpers (roadmap N1): depth maps in and out, normals from depth, detail blending, relight.

Conventions (the scene-set contract with the game, `21_Build_Plan_Night_2.md §3b`):
    depth   grey, white = near, black = far; saved as 16-bit PNG (`I;16`) so the focus shader and the layer cuts
            get smooth values instead of 256 bands.
    normals tangent-space, OpenGL convention (green = up) — what Godot's CanvasTexture expects.

Why depth beats luminance for normals: a bright poster is not nearer than the wall it hangs on and a dark doorway is
not a pit. Depth gives the light true surfaces to rake across; luminance (blended back in with `detail`) keeps the
brush texture.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .edges import blur, luminance, sobel


# ------------------------------------------------------------------ depth files
def load_depth(src: Image.Image | str | Path, size: tuple[int, int] | None = None) -> np.ndarray:
    """Any depth image (8-bit L/RGB, 16-bit I;16, 32-bit I/F) → float32 HxW in 0..1, white (1) = near.
    `size` (w, h) resamples to that size (bicubic on the float values, so an 8-bit source gains in-between values)."""
    img = Image.open(src) if not isinstance(src, Image.Image) else src
    mode = img.mode
    if mode in ("I;16", "I;16B", "I;16L"):
        a = np.asarray(img, dtype=np.float32) / 65535.0
    elif mode in ("I", "F"):
        a = np.asarray(img, dtype=np.float32)
        lo, hi = float(a.min()), float(a.max())
        a = (a - lo) / (hi - lo) if hi > lo else np.zeros_like(a)
    else:
        a = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    if size is not None and (a.shape[1], a.shape[0]) != tuple(size):
        a = np.asarray(Image.fromarray(a, "F").resize(tuple(size), Image.BICUBIC), dtype=np.float32)
    return np.clip(a, 0.0, 1.0)


def depth_image16(depth: np.ndarray) -> Image.Image:
    """float 0..1 → a 16-bit greyscale PIL image (saved as a 16-bit PNG)."""
    return Image.fromarray((np.clip(depth, 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16))


def depth_preview(depth: np.ndarray) -> Image.Image:
    """8-bit view of a depth map, for contact sheets."""
    return Image.fromarray((np.clip(depth, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), "L").convert("RGB")


# ------------------------------------------------------------------ normals
def _encode(nx: np.ndarray, ny: np.ndarray, nz: np.ndarray) -> Image.Image:
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    norm = np.where(norm > 1e-8, norm, 1.0)
    rgb = np.stack([nx / norm, ny / norm, nz / norm], axis=-1) * 0.5 + 0.5
    return Image.fromarray(np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGB")


def decode_normals(img: Image.Image) -> np.ndarray:
    """RGB normal map → float HxWx3 unit vectors (OpenGL: +y up)."""
    n = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0 * 2.0 - 1.0
    norm = np.linalg.norm(n, axis=-1, keepdims=True)
    return n / np.where(norm > 1e-8, norm, 1.0)


def _height_normals(h: np.ndarray, strength: float, smooth: float, invert_y: bool) -> tuple[np.ndarray, ...]:
    hb = blur(h, smooth) if smooth > 0 else h
    gx, gy = sobel(hb)
    nx = -gx * float(strength)
    ny = gy * float(strength)       # image y runs down; OpenGL's runs up
    if invert_y:
        ny = -ny
    return nx, ny, np.ones_like(nx)


# depth maps are smooth: their per-pixel gradient is ~1/size of a luminance edge's. This scale makes `strength`
# mean roughly the same thing for both sources at 1080p and keeps it resolution-independent.
DEPTH_REFERENCE_PX = 1080.0
DEBAND_PX = 3.0            # minimum blur (px at 1080p) before the depth gradient — removes 8-bit terracing


def _median1d(v: np.ndarray, win: int) -> np.ndarray:
    r = max(1, win // 2)
    p = np.pad(v, r, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(p, 2 * r + 1), axis=-1).astype(np.float32)


def depth_trend(depth: np.ndarray, percentile: float = 25.0, win_frac: float = 0.06) -> np.ndarray:
    """The slow trend of a depth map *up the screen*: each row's background level (a low percentile, so objects
    standing in the row do not pull it up), cleaned with a sliding median over ~6% of the height (it removes
    row-to-row noise, which would otherwise show as stripes, and keeps the sharp step at the horizon), then a
    whisper of blur. Broadcast across each row: nothing is blurred sideways, so big objects get no halo."""
    h, w = depth.shape
    rows = np.percentile(depth, percentile, axis=1).astype(np.float32)
    rows = _median1d(rows, max(3, int(win_frac * h)))
    rows = blur(rows[:, None], 1.0)[:, 0]
    return np.repeat(rows[:, None], w, axis=1)


def normals_from_depth(depth: np.ndarray, strength: float = 2.0, smooth: float = 1.5, invert_y: bool = False,
                       flatten: float = 0.85) -> Image.Image:
    """Tangent-space normals from a depth map (white = near), OpenGL convention.
    `flatten` (0..1) removes that much of the depth's trend up the screen first (`depth_trend`): a floor or a road that
    recedes from the camera has a steady depth ramp, which raw depth-as-height reads as one big tilted surface;
    flattening keeps object edges and local shape and leaves the floor facing the viewer. 0 = the raw depth gradient."""
    d = depth.astype(np.float32)
    f = float(np.clip(flatten, 0.0, 1.0))
    if f > 0:
        trend = depth_trend(d)
        # only where a pixel IS the background (depth within ~5% of its row's level): an upright object keeps its raw
        # depth, so it neither leans back with the floor's ramp nor tips the other way once the ramp is removed
        ground = np.clip(1.0 - (d - trend) / 0.05, 0.0, 1.0)
        ground = np.clip(blur(ground, 1.5), 0.0, 1.0)
        d = d - f * trend * ground
    scale = max(depth.shape) / DEPTH_REFERENCE_PX * 24.0
    # ComfyUI saves the depth preprocessor's output as 8-bit, so a smooth floor arrives as terraces one grey level
    # apart; their edges would print as contour lines/stripes in the normals. Blur at least this much first.
    deband = DEBAND_PX * max(depth.shape) / DEPTH_REFERENCE_PX
    nx, ny, nz = _height_normals(d, float(strength) * scale, max(float(smooth), deband), invert_y)
    return _encode(nx, ny, nz)


def normals_from_luminance(img: Image.Image, strength: float = 2.0, smooth: float = 1.0, invert_y: bool = False) -> Image.Image:
    """Same as ops.lighting.normal_map (kept here so this module stands alone)."""
    return _encode(*_height_normals(luminance(img), strength, smooth, invert_y))


def blend_detail(base: Image.Image, detail: Image.Image, amount: float) -> Image.Image:
    """Whiteout blend: the depth normals' shape with the luminance normals' brush texture on top.
    amount 0 = base only, 1 = full detail."""
    amount = float(np.clip(amount, 0.0, 1.0))
    if amount <= 0:
        return base
    b, d = decode_normals(base), decode_normals(detail)
    nx = b[..., 0] + d[..., 0] * amount
    ny = b[..., 1] + d[..., 1] * amount
    nz = b[..., 2] * (1.0 - amount + d[..., 2] * amount)
    return _encode(nx, ny, nz)


def normal_map(img: Image.Image, *, source: str = "luminance", depth: np.ndarray | None = None, strength: float = 2.0,
               smooth: float = 1.0, detail: float = 0.0, invert_y: bool = False, flatten: float = 0.85) -> Image.Image:
    """The N1 `normal_map`: source "luminance" (F11's behaviour, unchanged) or "depth" (needs `depth`, same size
    as img), optionally with `detail` of the luminance normals blended back in."""
    if source == "luminance":
        return normals_from_luminance(img, strength, smooth, invert_y)
    if source != "depth":
        raise ValueError(f"normal_map source must be 'luminance' or 'depth', got {source!r}")
    if depth is None:
        raise ValueError("normal_map source 'depth' needs a depth map (job field `depth`)")
    if (depth.shape[1], depth.shape[0]) != img.size:
        raise ValueError(f"depth is {depth.shape[1]}x{depth.shape[0]} but the painting is {img.size[0]}x{img.size[1]}")
    n = normals_from_depth(depth, strength, max(smooth, 0.0), invert_y, flatten)
    if detail > 0:
        n = blend_detail(n, normals_from_luminance(img, 2.0, 1.0, invert_y), detail)
    return n


# ------------------------------------------------------------------ relight (judge normals without Godot)
def relight(albedo: Image.Image, normals: Image.Image, light: tuple[float, float, float] = (-1.0, 0.25, 0.6),
            ambient: float = 0.35, intensity: float = 0.9, tint: tuple[float, float, float] = (1.0, 0.92, 0.8)) -> Image.Image:
    """A fixed directional light on the painting: albedo × (ambient + intensity·max(0, n·l)). Default light comes
    from the left, a little above, warm — "lit from the left" on the contact sheets."""
    n = decode_normals(normals)
    l = np.asarray(light, dtype=np.float32)
    l = l / np.linalg.norm(l)
    ndl = np.clip((n * l).sum(axis=-1), 0.0, 1.0)
    a = np.asarray(albedo.convert("RGB"), dtype=np.float32) / 255.0
    shade = ambient + intensity * ndl[..., None] * np.asarray(tint, dtype=np.float32)
    return Image.fromarray(np.clip(a * shade * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGB")
