"""Depth → parallax layers (roadmap N2, F15 promoted).

A painted scene becomes three planes for the game's HD-2D-feel pass (`21_Build_Plan_Night_2.md §3b`):

    <name>_back.png  the far plane — the painting with everything nearer than cut 1 lifted off and the holes filled,
                     opaque, wider than the painting by `overscan` px on each side for the parallax travel
    <name>.png       the walkable mid plane — the painting itself, UNCHANGED (walk polygons belong to it)
    <name>_over.png  the walk-behind plane — everything nearer than cut 2, RGBA, soft-edged

plus `layers.json` (cuts, suggested parallax factors, coverage) and, as an extra outside the six-file contract,
`<name>_mid_alpha.png` — the mid plane's own pixels (depth ≥ cut 1). The game may use it to let `_back` show through
the mid plane while the camera slides; nothing breaks if it doesn't.

Hole filling is deterministic by default (`extend`: a push-pull pyramid that pulls the nearest known colours into
the hole, smoothly) so a plane never shows a transparent ghost when it moves.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from .edges import blur

MIN_COVERAGE = 0.02          # a layer smaller than this fraction of the frame is dropped with a note
PARALLAX = {"back": 0.94, "mid": 1.0, "over": 1.06}


# ------------------------------------------------------------------ cuts
def auto_cuts(depth: np.ndarray, n_cuts: int = 2, bins: int = 64) -> list[float]:
    """Otsu-style multi-threshold on the depth histogram: the cut values that best separate depth into n_cuts+1
    bands (maximum between-class variance). Exhaustive over `bins` bins — exact and fast for 1–2 cuts."""
    hist, edges = np.histogram(np.clip(depth, 0, 1), bins=bins, range=(0.0, 1.0))
    p = hist.astype(np.float64) / max(1, hist.sum())
    centers = (edges[:-1] + edges[1:]) / 2.0
    w = np.concatenate([[0.0], np.cumsum(p)])
    m = np.concatenate([[0.0], np.cumsum(p * centers)])
    mu = m[-1]

    def term(a: int, b: int) -> float:       # bins a..b-1
        wk = w[b] - w[a]
        if wk <= 1e-12:
            return 0.0
        mk = (m[b] - m[a]) / wk
        return wk * (mk - mu) ** 2

    if n_cuts == 1:
        best = max(range(1, bins), key=lambda t: term(0, t) + term(t, bins))
        return [float(edges[best])]
    if n_cuts != 2:
        raise ValueError("auto cuts supports 1 or 2 cuts")
    best, best_v = (bins // 3, 2 * bins // 3), -1.0
    for t1 in range(1, bins - 1):
        a = term(0, t1)
        for t2 in range(t1 + 1, bins):
            v = a + term(t1, t2) + term(t2, bins)
            if v > best_v:
                best, best_v = (t1, t2), v
    return [float(edges[best[0]]), float(edges[best[1]])]


def resolve_cuts(depth: np.ndarray, cuts) -> list[float]:
    if cuts in (None, "auto"):
        return auto_cuts(depth, 2)
    c = sorted(float(x) for x in cuts)
    if len(c) != 2 or not (0.0 < c[0] < c[1] < 1.0):
        raise ValueError(f"cuts must be two values 0 < a < b < 1 (or \"auto\"), got {cuts}")
    return c


# ------------------------------------------------------------------ fill
def push_pull_fill(rgb: np.ndarray, known: np.ndarray, min_size: int = 2) -> np.ndarray:
    """Fill unknown pixels from known ones: average known colours down a pyramid (push), then pull the coarse
    colours back up into the holes, level by level. Deterministic, no seams at the hole edges. rgb HxWx3 float,
    known HxW bool (or 0..1 weight). Known pixels are returned unchanged."""
    w0 = known.astype(np.float32)
    if w0.max() <= 0:
        return rgb.copy()
    levels = [(rgb.astype(np.float32) * w0[..., None], w0)]
    while min(levels[-1][1].shape) > min_size:
        c, w = levels[-1]
        h, wd = w.shape
        if h % 2:
            c, w = np.concatenate([c, c[-1:]], 0), np.concatenate([w, w[-1:]], 0)
        if wd % 2:
            c, w = np.concatenate([c, c[:, -1:]], 1), np.concatenate([w, w[:, -1:]], 1)
        c2 = c[0::2, 0::2] + c[1::2, 0::2] + c[0::2, 1::2] + c[1::2, 1::2]
        w2 = w[0::2, 0::2] + w[1::2, 0::2] + w[0::2, 1::2] + w[1::2, 1::2]
        # normalise weight to ≤1 so a fully known block counts as one known pixel
        scale = np.maximum(w2, 1e-8)
        c2 = c2 / scale[..., None] * np.minimum(w2, 1.0)[..., None]
        levels.append((c2, np.minimum(w2, 1.0)))
    # pull
    c, w = levels[-1]
    col = c / np.maximum(w, 1e-8)[..., None]
    for c_l, w_l in reversed(levels[:-1]):
        h, wd = w_l.shape
        up = np.repeat(np.repeat(col, 2, 0), 2, 1)[:h, :wd]
        # light smoothing of the pulled-up colour so blocks don't show
        up = np.stack([blur(up[..., k], 0.8) for k in range(up.shape[-1])], axis=-1)
        here = c_l / np.maximum(w_l, 1e-8)[..., None]
        col = here * w_l[..., None] + up * (1.0 - w_l[..., None])
    out = col
    k = known.astype(bool)
    out[k] = rgb[k]
    return out


# ------------------------------------------------------------------ the split
def split_layers(painting: Image.Image, depth: np.ndarray, cuts=None, feather: float = 3.0, overscan: int = 48,
                 fill: str = "extend") -> dict:
    """Returns {"back": RGB image (wider by 2·overscan) or None, "over": RGBA image or None, "mid_alpha": L image,
    "info": {...for layers.json}}. The painting itself is the mid plane and is not returned or changed."""
    rgb_img = painting.convert("RGB")
    w, h = rgb_img.size
    if (depth.shape[1], depth.shape[0]) != (w, h):
        raise ValueError(f"depth is {depth.shape[1]}x{depth.shape[0]} but the painting is {w}x{h}")
    if fill not in ("extend", "inpaint"):
        raise ValueError(f"fill must be 'extend' or 'inpaint', got {fill!r}")
    c1, c2 = resolve_cuts(depth, cuts)
    rgb = np.asarray(rgb_img, dtype=np.float32)
    back_mask = depth < c1
    over_mask = depth >= c2
    cov = {"back": float(back_mask.mean()), "mid": float(((depth >= c1) & (depth < c2)).mean()), "over": float(over_mask.mean())}
    notes: list[str] = []
    out: dict = {"back": None, "over": None}

    # over: soft alpha from the hard mask
    if cov["over"] >= MIN_COVERAGE:
        a = over_mask.astype(np.float32)
        if feather > 0:
            a = np.clip(blur(a, feather), 0.0, 1.0)
        out["over"] = Image.fromarray((np.dstack([rgb, a * 255.0]) + 0.5).clip(0, 255).astype(np.uint8), "RGBA")
    else:
        notes.append(f"over plane dropped: covers {cov['over'] * 100:.1f}% of the frame (< {MIN_COVERAGE * 100:.0f}%)")

    # mid alpha (extra): the mid plane's own pixels, soft at the back cut
    ma = (~back_mask).astype(np.float32)
    if feather > 0:
        ma = np.clip(blur(ma, feather), 0.0, 1.0)
    out["mid_alpha"] = Image.fromarray((ma * 255.0 + 0.5).astype(np.uint8), "L")

    # back: lift off everything nearer than c1 (grown a little so no fringe of foreground colour stays), fill
    if cov["back"] >= MIN_COVERAGE:
        known = back_mask.copy()
        if feather > 0:
            known = blur(known.astype(np.float32), max(1.0, feather)) > 0.999
        if fill == "inpaint":
            notes.append("fill 'inpaint' is not built yet in this op — used 'extend' (the GPU inpaint is the job's stage)")
        filled = push_pull_fill(rgb, known)
        if overscan > 0:
            mode = "reflect" if overscan < w else "edge"
            filled = np.pad(filled, ((0, 0), (overscan, overscan), (0, 0)), mode=mode)
        out["back"] = Image.fromarray(np.clip(filled + 0.5, 0, 255).astype(np.uint8), "RGB")
    else:
        notes.append(f"back plane dropped: covers {cov['back'] * 100:.1f}% of the frame (< {MIN_COVERAGE * 100:.0f}%)")

    out["info"] = {"cuts": [round(c1, 4), round(c2, 4)], "cuts_mode": "auto" if cuts in (None, "auto") else "given",
                   "parallax": {k: v for k, v in PARALLAX.items() if k == "mid" or out.get(k) is not None},
                   "coverage": {k: round(v, 4) for k, v in cov.items()}, "feather_px": feather,
                   "overscan_px": overscan if out["back"] is not None else 0, "fill": "extend", "size": [w, h],
                   "notes": notes}
    return out


def slide_frames(painting: Image.Image, layers: dict, shift: int = 40) -> list[Image.Image]:
    """Three preview frames with the camera moved -shift, 0, +shift px: back × 0.94, mid × 1.0 (with mid_alpha),
    over × 1.06. A hole would show as magenta."""
    w, h = painting.size
    info = layers["info"]
    ov = info.get("overscan_px", 0)
    frames = []
    for dx in (-shift, 0, shift):
        f = Image.new("RGB", (w, h), (255, 0, 255))
        if layers.get("back") is not None:
            bx = int(round(-ov - dx * PARALLAX["back"]))
            f.paste(layers["back"], (bx, 0))
        mid = painting.convert("RGBA")
        mid.putalpha(layers["mid_alpha"])
        f.paste(mid, (int(round(-dx)), 0), mid)
        if layers.get("over") is not None:
            ox = int(round(-dx * PARALLAX["over"]))
            f.paste(layers["over"], (ox, 0), layers["over"])
        frames.append(f)
    return frames
