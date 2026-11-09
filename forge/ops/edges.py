"""Edges on the CPU (numpy only): Canny for ControlNet, and an overlay to check a painting kept its layout.

A greybox render has crisp flat-colour edges, so a plain Canny is all ControlNet needs — no preprocessor node,
no extra download. `overlay` draws the control edges over the result so a person can see at a glance whether
the walls stayed where the greybox put them.
"""
from __future__ import annotations
import math

import numpy as np
from PIL import Image


def _gauss_kernel(sigma: float) -> np.ndarray:
    r = max(1, int(math.ceil(3 * sigma)))
    x = np.arange(-r, r + 1, dtype=np.float32)
    k = np.exp(-(x * x) / (2 * sigma * sigma))
    return k / k.sum()


def _convolve1d(a: np.ndarray, k: np.ndarray, axis: int) -> np.ndarray:
    r = len(k) // 2
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r, r)
    p = np.pad(a, pad, mode="edge")
    out = np.zeros_like(a, dtype=np.float32)
    n = a.shape[axis]
    for i, w in enumerate(k):
        sl = [slice(None)] * a.ndim
        sl[axis] = slice(i, i + n)
        out += w * p[tuple(sl)]
    return out


def blur(a: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return a.astype(np.float32)
    k = _gauss_kernel(sigma)
    return _convolve1d(_convolve1d(a.astype(np.float32), k, 0), k, 1)


def sobel(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = np.pad(a, 1, mode="edge").astype(np.float32)
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    return gx, gy


def luminance(img: Image.Image) -> np.ndarray:
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def canny(img: Image.Image, low: float = 0.08, high: float = 0.2, sigma: float = 1.2) -> Image.Image:
    """White edges on black ('L' image, same size). low/high are fractions of the strongest gradient."""
    g = blur(luminance(img), sigma)
    gx, gy = sobel(g)
    mag = np.hypot(gx, gy)
    mmax = float(mag.max())
    if mmax <= 1e-9:
        return Image.new("L", img.size, 0)
    mag /= mmax
    ang = (np.rad2deg(np.arctan2(gy, gx)) + 180.0) % 180.0
    p = np.pad(mag, 1, mode="constant")
    c = p[1:-1, 1:-1]
    # neighbours along the gradient direction, quantised to 0/45/90/135 degrees
    e, w = p[1:-1, 2:], p[1:-1, :-2]
    n, s = p[:-2, 1:-1], p[2:, 1:-1]
    ne, sw = p[:-2, 2:], p[2:, :-2]
    nw, se = p[:-2, :-2], p[2:, 2:]
    d0 = (ang < 22.5) | (ang >= 157.5)
    d45 = (ang >= 22.5) & (ang < 67.5)
    d90 = (ang >= 67.5) & (ang < 112.5)
    d135 = (ang >= 112.5) & (ang < 157.5)
    keep = (d0 & (c >= e) & (c >= w)) | (d90 & (c >= n) & (c >= s)) | (d45 & (c >= sw) & (c >= ne)) | (d135 & (c >= nw) & (c >= se))
    nms = np.where(keep, mag, 0.0)
    strong = nms >= high
    weak = (nms >= low) & ~strong
    # hysteresis: grow strong edges into connected weak pixels
    edges = strong.copy()
    for _ in range(2000):
        q = np.pad(edges, 1)
        grown = (q[:-2, :-2] | q[:-2, 1:-1] | q[:-2, 2:] | q[1:-1, :-2] | q[1:-1, 2:] | q[2:, :-2] | q[2:, 1:-1] | q[2:, 2:]) & weak & ~edges
        if not grown.any():
            break
        edges |= grown
    return Image.fromarray((edges * 255).astype(np.uint8), "L")


def overlay(base: Image.Image, edges: Image.Image, color: tuple = (255, 40, 40), dim: float = 0.65) -> Image.Image:
    """The painting slightly dimmed, with the control edges drawn on top in `color` (resized to fit)."""
    b = base.convert("RGB")
    e = edges.convert("L").resize(b.size, Image.NEAREST)
    arr = (np.asarray(b, dtype=np.float32) * dim).astype(np.uint8)
    m = np.asarray(e) > 127
    arr[m] = color
    return Image.fromarray(arr, "RGB")


def edge_agreement(painting: Image.Image, control_edges: Image.Image, radius: int = 6) -> float:
    """Fraction of control-edge pixels that have a painting edge within `radius` px — a rough 'did the layout hold'
    number (1.0 = every greybox edge is matched). Not a judge of quality; a tripwire for drift."""
    ce = np.asarray(control_edges.convert("L").resize(painting.size, Image.NEAREST)) > 127
    if not ce.any():
        return 1.0
    pe = np.asarray(canny(painting)) > 127
    grown = pe.copy()
    for _ in range(max(1, radius)):
        q = np.pad(grown, 1)
        grown = q[1:-1, 1:-1] | q[:-2, 1:-1] | q[2:, 1:-1] | q[1:-1, :-2] | q[1:-1, 2:]
    return float((grown & ce).sum()) / float(ce.sum())
