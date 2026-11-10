"""What changed between two greyboxes of the same map (Night 3, G4) — the mask a `scene_state` repaints.

    changed(base, state, threshold=12, min_blob=3)  → binary mask (L, 255 = changed): any channel differs by more
                                                      than `threshold`; specks smaller than ~min_blob px removed
    grow_feather(mask, grow=24, feather=12)         → the repaint mask: grown (room for the new thing's edges and
                                                      shadow), then feathered (a soft join). 0 = untouched.
    state_mask(base, state, …)                      → (mask, binary, share, report); raises StateTooBig when more
                                                      than `max_share` (default 35 %) of the frame changed —
                                                      that is a new painting, not a state of this one.
    composite(base, painted, mask)                  → painted where mask = 255, base where mask = 0, a blend in the
                                                      feather; outside the mask the result is bit-identical to base.
"""
from __future__ import annotations
import numpy as np
from PIL import Image, ImageFilter

MAX_SHARE = 0.35


class StateTooBig(ValueError):
    pass


def _size_match(a: Image.Image, b: Image.Image) -> None:
    if a.size != b.size:
        raise ValueError(f"the two greyboxes are different sizes ({a.size} vs {b.size}) — render both from the same map")


def changed(base: Image.Image, state: Image.Image, threshold: int = 12, min_blob: int = 3) -> Image.Image:
    _size_match(base, state)
    a = np.asarray(base.convert("RGB"), dtype=np.int16)
    b = np.asarray(state.convert("RGB"), dtype=np.int16)
    m = (np.abs(a - b).max(axis=2) > int(threshold))
    img = Image.fromarray((m * 255).astype(np.uint8), "L")
    if min_blob and min_blob > 1:            # opening: drop specks (antialiasing noise), keep real shapes
        k = int(min_blob) | 1
        img = img.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))
    return img


def grow_feather(binary: Image.Image, grow: int = 24, feather: float = 12.0) -> Image.Image:
    m = binary.convert("L")
    g = int(grow)
    while g > 0:                             # MaxFilter sizes are odd and capped; grow in steps
        step = min(g, 25)
        m = m.filter(ImageFilter.MaxFilter(2 * step + 1))
        g -= step
    if feather and feather > 0:
        # blur only outward: keep the grown core at 255, let the blur add the soft edge outside it
        soft = m.filter(ImageFilter.GaussianBlur(float(feather)))
        m = Image.fromarray(np.maximum(np.asarray(m), np.asarray(soft)))
        a = np.asarray(m).astype(np.int32)
        a[a < 3] = 0                         # blur tails below 1 % are 0, so "untouched" is really untouched
        m = Image.fromarray(a.astype(np.uint8), "L")
    return m


def state_mask(base: Image.Image, state: Image.Image, threshold: int = 12, grow: int = 24, feather: float = 12.0,
               max_share: float = MAX_SHARE, min_blob: int = 3):
    binary = changed(base, state, threshold, min_blob)
    share_raw = float((np.asarray(binary) > 0).mean())
    mask = grow_feather(binary, grow, feather)
    share = float((np.asarray(mask) > 0).mean())
    report = {"changed_share": round(share_raw, 4), "mask_share": round(share, 4), "threshold": threshold, "grow": grow,
              "feather": feather, "max_share": max_share, "bbox": list(binary.getbbox() or [])}
    if share_raw == 0:
        raise ValueError("the two greyboxes are identical — nothing changed, so there is no state to paint")
    if share > max_share:
        raise StateTooBig(f"{share:.0%} of the frame changed (limit {max_share:.0%}) — this is a new painting, not a state. "
                          "Paint it with scene_kit, or split the change into smaller states.")
    return mask, binary, share, report


def composite(base: Image.Image, painted: Image.Image, mask: Image.Image) -> Image.Image:
    """base outside the mask (bit-identical), painted inside, a linear blend across the feather."""
    mode = base.mode if base.mode in ("RGB", "RGBA", "L", "I;16", "I") else "RGB"
    b = np.asarray(base.convert(mode) if base.mode != mode else base)
    p = np.asarray(painted.convert(mode).resize(base.size, Image.LANCZOS) if painted.size != base.size or painted.mode != mode
                   else painted)
    m = np.asarray(mask.convert("L").resize(base.size, Image.LANCZOS) if mask.size != base.size else mask.convert("L")).astype(np.float64) / 255.0
    if b.ndim == 3:
        m = m[..., None]
    out = np.round(b.astype(np.float64) * (1.0 - m) + p.astype(np.float64) * m)
    out = out.astype(b.dtype)
    zero = (m[..., 0] if b.ndim == 3 else m) == 0
    out[zero] = b[zero]                       # exact, whatever the float path did
    return Image.fromarray(out, mode)


def bbox_for(mask: Image.Image, pad: int = 96, min_side: int = 768, multiple: int = 8) -> tuple[int, int, int, int]:
    """The region to repaint: the mask's bounding box, padded for context, at least min_side, inside the picture."""
    W, H = mask.size
    bb = mask.getbbox()
    if not bb:
        return (0, 0, W, H)
    x0, y0, x1, y1 = bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad
    def fix(a, b, L):
        if b - a < min_side:
            c = (a + b) / 2
            a, b = c - min_side / 2, c + min_side / 2
        a, b = max(0, int(a)), min(L, int(b))
        if b - a < min(min_side, L):          # hit an edge: slide
            if a == 0:
                b = min(L, min_side)
            else:
                a = max(0, L - min_side)
        w = (b - a) // multiple * multiple
        return a, a + max(multiple, w)
    x0, x1 = fix(x0, x1, W)
    y0, y1 = fix(y0, y1, H)
    return (x0, y0, x1, y1)


def difference(a: Image.Image, b: Image.Image, gain: float = 4.0) -> tuple[Image.Image, float]:
    """A picture of |a - b| (amplified) and the largest raw difference outside nothing — for the contact sheet."""
    x = np.asarray(a.convert("RGB"), dtype=np.int16)
    y = np.asarray(b.convert("RGB"), dtype=np.int16)
    d = np.abs(x - y)
    return Image.fromarray(np.clip(d * gain, 0, 255).astype(np.uint8)), float(d.max())
