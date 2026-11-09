"""From a big generated picture to honest pixel art.

Diffusion models paint "pixel art" at 1024 px with a soft, slightly irregular grid. We find that grid
(its period and phase), then collapse each cell to one colour — the mode (most common colour, best for
flat shading), the median (robust to noise) or the centre sample. Clean pixels come out, not a blur.
"""
from __future__ import annotations
import numpy as np
from PIL import Image


def detect_grid(img: Image.Image, min_scale: int = 2, max_scale: int = 32) -> tuple[int, int, int, float]:
    """Return (scale, offset_x, offset_y, confidence). scale 1 = no grid found.

    Column/row difference energy peaks at cell boundaries; its autocorrelation peaks at the period.
    """
    gray = np.asarray(img.convert("L"), dtype=np.float64)
    h, w = gray.shape
    dx = np.abs(np.diff(gray, axis=1)).mean(axis=0)  # per column boundary
    dy = np.abs(np.diff(gray, axis=0)).mean(axis=1)  # per row boundary
    scores: dict[int, float] = {}
    for s in range(min_scale, min(max_scale, w // 4, h // 4) + 1):
        # comb score: energy on boundaries at period s (best phase) relative to the average boundary
        sx = max((dx[p::s].mean() for p in range(s)), default=0.0)
        sy = max((dy[p::s].mean() for p in range(s)), default=0.0)
        scores[s] = (sx / (dx.mean() + 1e-9) + sy / (dy.mean() + 1e-9)) / 2.0
    if not scores:
        return 1, 0, 0, 0.0
    top = max(scores.values())
    # multiples of the true period score about as well (every 2s-th boundary is also a boundary),
    # so take the SMALLEST period within 12% of the best
    s = min(k for k, v in scores.items() if v >= top * 0.88)
    score = scores[s]
    if score < 1.6:
        return 1, 0, 0, float(score)
    ox = int(np.argmax([dx[p::s].mean() for p in range(s)]))
    oy = int(np.argmax([dy[p::s].mean() for p in range(s)]))
    # boundaries sit between pixels: the cell starts one past the boundary
    return s, (ox + 1) % s, (oy + 1) % s, float(score)


def downscale_cells(img: Image.Image, scale: int, ox: int = 0, oy: int = 0, method: str = "mode") -> Image.Image:
    """Collapse each scale×scale cell (grid phase ox, oy) into one pixel."""
    rgba = np.asarray(img.convert("RGBA"))
    h, w = rgba.shape[:2]
    # crop to the grid phase, then to whole cells
    rgba = rgba[oy:, ox:]
    H = (rgba.shape[0] // scale) * scale
    W = (rgba.shape[1] // scale) * scale
    rgba = rgba[:H, :W]
    cells = rgba.reshape(H // scale, scale, W // scale, scale, 4).transpose(0, 2, 1, 3, 4)
    cells = cells.reshape(H // scale, W // scale, scale * scale, 4)
    if method == "center":
        out = cells[:, :, (scale * scale) // 2, :]
    elif method == "median":
        out = np.median(cells, axis=2).astype(np.uint8)
    else:  # mode — the most common colour in the cell (quantised a little so near-equal colours merge)
        q = (cells[..., :3] >> 3).astype(np.int32)
        key = (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]
        out = np.empty((cells.shape[0], cells.shape[1], 4), dtype=np.uint8)
        for y in range(cells.shape[0]):
            for x in range(cells.shape[1]):
                k = key[y, x]
                vals, counts = np.unique(k, return_counts=True)
                winner = vals[np.argmax(counts)]
                members = cells[y, x][k == winner]
                out[y, x, :3] = members[:, :3].mean(axis=0).round().astype(np.uint8)
                out[y, x, 3] = 255 if (cells[y, x][:, 3] > 127).mean() >= 0.5 else 0
    return Image.fromarray(np.ascontiguousarray(out), "RGBA")


def to_target(img: Image.Image, target: tuple[int, int], method: str = "lanczos") -> Image.Image:
    """Plain high-quality resize (for painted cards, not pixel art)."""
    resample = {"lanczos": Image.LANCZOS, "box": Image.BOX, "nearest": Image.NEAREST}[method]
    return img.convert("RGBA").resize(target, resample)
