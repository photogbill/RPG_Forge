"""Backgrounds to alpha, trimming, padding — for props rendered on a flat key colour."""
from __future__ import annotations
from collections import deque
import numpy as np
from PIL import Image


def hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def remove_flat_background(img: Image.Image, key_color: tuple[int, int, int] | None = None,
                           tolerance: int = 28) -> Image.Image:
    """Flood-fill from the four corners through pixels near the key colour (default: the corner colour
    itself) and make them transparent. Interior pixels of the same colour (eyes, windows) survive
    because the fill cannot reach them — that is the point of flooding instead of keying globally.
    """
    rgba = np.array(img.convert("RGBA"))
    h, w = rgba.shape[:2]
    rgb = rgba[..., :3].astype(np.int32)
    if key_color is None:
        corners = [rgb[0, 0], rgb[0, w - 1], rgb[h - 1, 0], rgb[h - 1, w - 1]]
        key = np.median(np.stack(corners), axis=0)
    else:
        key = np.array(key_color, dtype=np.int32)
    near = (np.abs(rgb - key).sum(axis=2) <= tolerance * 3)
    visited = np.zeros((h, w), dtype=bool)
    q: deque = deque()
    for (y, x) in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)):
        if near[y, x]:
            q.append((y, x)); visited[y, x] = True
    while q:
        y, x = q.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and near[ny, nx]:
                visited[ny, nx] = True
                q.append((ny, nx))
    rgba[visited, 3] = 0
    # soften the one-pixel fringe: pixels adjacent to the removed area that are halfway to the key
    return Image.fromarray(rgba, "RGBA")


def trim(img: Image.Image, margin: int = 0) -> Image.Image:
    rgba = np.asarray(img.convert("RGBA"))
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    if len(ys) == 0:
        return img.convert("RGBA")
    y0, y1 = max(0, ys.min() - margin), min(rgba.shape[0], ys.max() + 1 + margin)
    x0, x1 = max(0, xs.min() - margin), min(rgba.shape[1], xs.max() + 1 + margin)
    return Image.fromarray(np.ascontiguousarray(rgba[y0:y1, x0:x1]), "RGBA")


def pad_to(img: Image.Image, size: tuple[int, int], anchor: str = "bottom") -> Image.Image:
    """Place `img` into a transparent canvas of `size`. anchor: bottom (feet on the floor), center, top-left."""
    w, h = size
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    src = img.convert("RGBA")
    if src.width > w or src.height > h:
        scale = min(w / src.width, h / src.height)
        src = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.NEAREST)
    if anchor == "bottom":
        pos = ((w - src.width) // 2, h - src.height)
    elif anchor == "top-left":
        pos = (0, 0)
    else:
        pos = ((w - src.width) // 2, (h - src.height) // 2)
    canvas.paste(src, pos, src)
    return canvas


def scale_to_height(img: Image.Image, target_h: int, resample=Image.LANCZOS) -> Image.Image:
    src = img.convert("RGBA")
    if src.height == 0:
        return src
    k = target_h / src.height
    return src.resize((max(1, round(src.width * k)), target_h), resample)
