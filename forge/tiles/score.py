"""Scoring a material tile — automatically, before a person judges it.

  seam          forge/ops/tiles.seam_score on the wrap seams (about 1.0 = as rough as the texture itself = seamless; over 1.5 shows a line)
  repetition    how obviously it repeats when tiled: the share of the tile's contrast that is large-scale blotches
                (the thing the eye catches as a grid), 0 = none … 1 = all of it; lower is better
  normals       does it light believably from four directions: lit from the east and from the west should shade
                opposite sides of each bump (anti-correlated), and the normals must not be flat; 0 … 1, higher is better
  palette       distance in colour and texture statistics to the game's paintings (the closest one); lower sits better
  seconds       render time (from the job)
"""
from __future__ import annotations
import numpy as np
from PIL import Image, ImageDraw

from ..ops.tiles import seam_score

LIGHTS = {"N": (0.0, 1.0, 0.7), "E": (1.0, 0.0, 0.7), "S": (0.0, -1.0, 0.7), "W": (-1.0, 0.0, 0.7)}   # OpenGL: +y up


def _f(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.float64) / 255.0


def _lum(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def _wrap_blur(g: np.ndarray, r: int) -> np.ndarray:
    """Box blur with wrap-around (the tile tiles), separable, via cumulative sums."""
    if r < 1:
        return g
    k = 2 * r + 1
    p = np.concatenate([g[:, -r:], g, g[:, :r]], axis=1)
    c = np.cumsum(np.pad(p, ((0, 0), (1, 0))), axis=1)
    g = (c[:, k:] - c[:, :-k]) / k
    p = np.concatenate([g[-r:], g, g[:r]], axis=0)
    c = np.cumsum(np.pad(p, ((1, 0), (0, 0))), axis=0)
    return (c[k:] - c[:-k]) / k


def repetition(img: Image.Image) -> float:
    g = _lum(_f(img))
    sd = g.std() + 1e-6
    low = _wrap_blur(_wrap_blur(g, max(1, g.shape[0] // 12)), max(1, g.shape[0] // 12))
    return float(np.clip(low.std() / sd, 0.0, 1.0))


def decode(normals: Image.Image) -> np.ndarray:
    n = _f(normals) * 2 - 1
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-8)


def lit(albedo: Image.Image, normals: Image.Image, d: str, ambient: float = 0.3) -> Image.Image:
    n = decode(normals)
    l = np.asarray(LIGHTS[d], dtype=np.float64)
    l /= np.linalg.norm(l)
    s = ambient + (1 - ambient) * np.clip((n * l).sum(-1), 0, 1)
    return Image.fromarray(np.clip(_f(albedo) * s[..., None] * 255 + 0.5, 0, 255).astype(np.uint8), "RGB")


def normal_quality(normals: Image.Image) -> float:
    n = decode(normals)
    se = n[..., 0]                      # n·E ∝ nx (the z part is common to both and cancels in the correlation)
    sw = -n[..., 0]
    spread = float(n[..., 0].std() + n[..., 1].std())
    if spread < 1e-4:
        return 0.0
    c = np.corrcoef((se + 0.7 * n[..., 2]).ravel(), (sw + 0.7 * n[..., 2]).ravel())[0, 1]
    anti = float(np.clip(-c, 0.0, 1.0)) if np.isfinite(c) else 0.0
    return round(anti * min(1.0, spread / 0.15), 3)


def _stats(a: np.ndarray) -> np.ndarray:
    L = _lum(a)
    ca = a[..., 0] - a[..., 1]
    cb = (a[..., 0] + a[..., 1]) / 2 - a[..., 2]
    gx = np.abs(np.diff(L, axis=1)).mean()
    return np.array([L.mean(), ca.mean(), cb.mean(), L.std(), ca.std(), cb.std(), gx * 4])


def palette_distance(img: Image.Image, refs: list[Image.Image]) -> float | None:
    if not refs:
        return None
    s = _stats(_f(img.resize((256, 256))))
    best = min(float(np.abs(s - _stats(_f(r.convert("RGB").resize((256, 256))))).sum()) for r in refs)
    return round(best, 3)


def score(albedo: Image.Image, normals: Image.Image, refs: list[Image.Image] | None = None, seconds=None) -> dict:
    return {"seam": round(seam_score(albedo), 3), "repetition": round(repetition(albedo), 3),
            "normals": normal_quality(normals), "palette": palette_distance(albedo, refs or []),
            "seconds": round(float(seconds), 1) if seconds is not None else None}


def rank_key(s: dict) -> float:
    """One number to sort by (a suggestion; the person picks). Lower is better."""
    seam = min(s.get("seam") or 0.0, 3.0)
    pal = s.get("palette")
    return (seam * 1.0 + (s.get("repetition") or 0) * 2.0 + (1 - (s.get("normals") or 0)) * 1.0
            + (min(pal, 2.0) * 0.5 if pal is not None else 0.0))


def tiled(img: Image.Image, n: int = 3, size: int = 384) -> Image.Image:
    t = img.convert("RGB").resize((size // n, size // n), Image.LANCZOS)
    out = Image.new("RGB", (size // n * n, size // n * n))
    for y in range(n):
        for x in range(n):
            out.paste(t, (x * t.width, y * t.height))
    return out


def lit_strip(albedo: Image.Image, normals: Image.Image, size: int = 160) -> Image.Image:
    out = Image.new("RGB", (size * 4, size))
    a, n = albedo.convert("RGB").resize((size, size)), normals.convert("RGB").resize((size, size))
    for i, d in enumerate("NESW"):
        im = lit(a, n, d)
        ImageDraw.Draw(im).text((4, 2), f"lit {d}", fill=(255, 255, 255))
        out.paste(im, (i * size, 0))
    return out
