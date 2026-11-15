"""A small software renderer for the checks and the check pictures (BUILD 39): numpy only, no GPU, no Blender.

Orthographic views of a mesh from any azimuth and elevation, with a depth buffer and the colour texture, fast enough
for a 60,000-face model at a few hundred pixels (a fraction of a second). Used to compare a model's outline with the
picture it was made from, and to draw the plain pictures a person looks at when a check holds something back.
"""
from __future__ import annotations

import numpy as np


def view_matrix(az_deg: float, el_deg: float) -> np.ndarray:
    """Rows: screen right, screen up, into the screen. The camera stands at azimuth `az` (0 = on the +Z side, looking
    toward -Z; 90 = on the +X side) and `el` degrees above the horizon, looking at the middle of the thing."""
    az, el = np.radians(az_deg), np.radians(el_deg)
    fwd = -np.array([np.sin(az) * np.cos(el), np.sin(el), np.cos(az) * np.cos(el)])
    right = np.cross(fwd, [0.0, 1.0, 0.0])
    if np.linalg.norm(right) < 1e-9:
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    return np.stack([right, up, fwd])


def project(P: np.ndarray, R: np.ndarray, size: int, margin: float = 0.04, box=None):
    """Screen positions (x right, y down, depth) fitting the thing into a size x size frame. Returns (scr, box)."""
    S = P @ R.T
    if box is None:
        box = (S[:, :2].min(0), S[:, :2].max(0))
    lo, hi = box
    span = max(float(max(hi - lo)), 1e-12) * (1 + 2 * margin)
    c = (lo + hi) / 2
    px = (S[:, 0] - c[0]) / span * size + size / 2
    py = size / 2 - (S[:, 1] - c[1]) / span * size
    return np.c_[px, py, S[:, 2]], box


def rasterize(scr: np.ndarray, F: np.ndarray, size: int, uv=None, tex=None, want_color: bool = False):
    """Depth-buffered triangles. Returns (mask, depth, colour or None, face index per pixel)."""
    npx = size * size
    depth = np.full(npx, np.inf)
    face_at = np.full(npx, -1, dtype=np.int64)
    if not len(F):
        return face_at.reshape(size, size) >= 0, depth.reshape(size, size), None, face_at.reshape(size, size)
    a, b, c = scr[F[:, 0]], scr[F[:, 1]], scr[F[:, 2]]
    xmin = np.floor(np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0])).astype(np.int64)
    xmax = np.ceil(np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0])).astype(np.int64)
    ymin = np.floor(np.minimum(np.minimum(a[:, 1], b[:, 1]), c[:, 1])).astype(np.int64)
    ymax = np.ceil(np.maximum(np.maximum(a[:, 1], b[:, 1]), c[:, 1])).astype(np.int64)
    onscreen = (xmax >= 0) & (ymax >= 0) & (xmin < size) & (ymin < size)
    ext = np.maximum(xmax - xmin, ymax - ymin) + 1
    lo_k = 0
    for k in (2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192):
        sel = np.nonzero(onscreen & (ext <= k) & (ext > lo_k))[0]
        lo_k = k
        if not len(sel):
            continue
        per = max(1, 3_000_000 // (k * k))
        ox, oy = np.meshgrid(np.arange(k), np.arange(k))
        ox, oy = ox.ravel()[None, :], oy.ravel()[None, :]
        for s in range(0, len(sel), per):
            chunk = sel[s: s + per]
            X = xmin[chunk, None] + ox + 0.5
            Y = ymin[chunk, None] + oy + 0.5
            A, B, C = a[chunk], b[chunk], c[chunk]
            d = (B[:, 1] - C[:, 1]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (A[:, 1] - C[:, 1])
            ok_d = np.abs(d) > 1e-12
            d = np.where(ok_d, d, 1.0)[:, None]
            w0 = ((B[:, 1, None] - C[:, 1, None]) * (X - C[:, 0, None]) + (C[:, 0, None] - B[:, 0, None]) * (Y - C[:, 1, None])) / d
            w1 = ((C[:, 1, None] - A[:, 1, None]) * (X - C[:, 0, None]) + (A[:, 0, None] - C[:, 0, None]) * (Y - C[:, 1, None])) / d
            w2 = 1.0 - w0 - w1
            inside = (w0 >= -1e-7) & (w1 >= -1e-7) & (w2 >= -1e-7) & ok_d[:, None]
            inside &= (X >= 0) & (X < size) & (Y >= 0) & (Y < size)
            ti, pi = np.nonzero(inside)
            if not len(ti):
                continue
            z = w0[ti, pi] * A[ti, 2] + w1[ti, pi] * B[ti, 2] + w2[ti, pi] * C[ti, 2]
            lin = Y[ti, pi].astype(np.int64) * size + X[ti, pi].astype(np.int64)
            order = np.lexsort((z, lin))
            lin_s = lin[order]
            first = np.r_[True, lin_s[1:] != lin_s[:-1]]
            pick = order[first]
            lin_u, z_u = lin[pick], z[pick]
            better = z_u < depth[lin_u]
            depth[lin_u[better]] = z_u[better]
            face_at[lin_u[better]] = chunk[ti[pick[better]]]
    mask = face_at >= 0
    color = None
    if want_color and tex is not None and uv is not None and mask.any():
        T = np.asarray(tex.convert("RGB"), dtype=np.float64)
        th, tw = T.shape[:2]
        pix = np.nonzero(mask)[0]
        fi = face_at[pix]
        X = (pix % size) + 0.5
        Y = (pix // size) + 0.5
        A, B, C = a[fi], b[fi], c[fi]
        d = (B[:, 1] - C[:, 1]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (A[:, 1] - C[:, 1])
        d = np.where(np.abs(d) > 1e-12, d, 1.0)
        w0 = ((B[:, 1] - C[:, 1]) * (X - C[:, 0]) + (C[:, 0] - B[:, 0]) * (Y - C[:, 1])) / d
        w1 = ((C[:, 1] - A[:, 1]) * (X - C[:, 0]) + (A[:, 0] - C[:, 0]) * (Y - C[:, 1])) / d
        w2 = 1.0 - w0 - w1
        u = w0 * uv[F[fi, 0], 0] + w1 * uv[F[fi, 1], 0] + w2 * uv[F[fi, 2], 0]
        v = w0 * uv[F[fi, 0], 1] + w1 * uv[F[fi, 1], 1] + w2 * uv[F[fi, 2], 1]
        tx = np.clip((u * tw).astype(np.int64), 0, tw - 1)
        ty = np.clip((v * th).astype(np.int64), 0, th - 1)
        col = np.zeros((npx, 3))
        col[pix] = T[ty, tx]
        color = col.reshape(size, size, 3)
    return mask.reshape(size, size), depth.reshape(size, size), color, face_at.reshape(size, size)


def shade(P: np.ndarray, F: np.ndarray, face_at: np.ndarray, R: np.ndarray) -> np.ndarray:
    """A simple light (from the upper left, toward the viewer) per pixel, 0.55..1.0, so shapes read in a check picture."""
    n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    light = R.T @ np.array([-0.45, 0.6, -0.66])
    light /= np.linalg.norm(light)
    lam = np.abs(n @ light)                                # double-sided
    out = np.ones(face_at.shape)
    m = face_at >= 0
    out[m] = 0.55 + 0.45 * lam[face_at[m]]
    return out


def render(P, F, az, el, size, uv=None, tex=None, background=(232, 232, 232), box=None) -> np.ndarray:
    """An RGB picture (uint8) of the mesh: its colours when a texture is given, else a plain grey, lit softly."""
    R = view_matrix(az, el)
    scr, _ = project(P, R, size, box=box)
    mask, _, col, face_at = rasterize(scr, F, size, uv, tex, want_color=tex is not None)
    s = shade(P, F, face_at, R)[..., None]
    base = col if col is not None else np.full((size, size, 3), 175.0)
    img = np.where(mask[..., None], np.clip(base * (0.75 + 0.25 * s), 0, 255), np.array(background, dtype=np.float64))
    return img.astype(np.uint8)


def splat(P: np.ndarray, az: float, el: float, size: int) -> np.ndarray:
    """A quick outline from the vertices alone (for searching the view a picture was taken from)."""
    R = view_matrix(az, el)
    S = P @ R.T
    lo, hi = S[:, :2].min(0), S[:, :2].max(0)
    span = max(float(max(hi - lo)), 1e-12)
    c = (lo + hi) / 2
    x = ((S[:, 0] - c[0]) / span * (size - 1) + (size - 1) / 2).astype(np.int64)
    y = ((size - 1) / 2 - (S[:, 1] - c[1]) / span * (size - 1)).astype(np.int64)
    m = np.zeros((size, size), bool)
    m[np.clip(y, 0, size - 1), np.clip(x, 0, size - 1)] = True
    return m


# ------------------------------------------------------------------------------------------------ binary pictures
def dilate(m: np.ndarray, r: int) -> np.ndarray:
    out = m.copy()
    for _ in range(max(0, int(r))):
        o = out.copy()
        o[1:] |= out[:-1]
        o[:-1] |= out[1:]
        o[:, 1:] |= out[:, :-1]
        o[:, :-1] |= out[:, 1:]
        out = o
    return out


def erode(m: np.ndarray, r: int) -> np.ndarray:
    return ~dilate(~m, r)


def closing(m: np.ndarray, r: int) -> np.ndarray:
    return erode(dilate(m, r), r)


def robust_box(m: np.ndarray, q: float = 0.015):
    """The box holding all but the outermost q of the pixels on each side (a hanging cable doesn't stretch it)."""
    ys, xs = np.nonzero(m)
    if not len(xs):
        return None
    x0, x1 = np.quantile(xs, [q, 1 - q])
    y0, y1 = np.quantile(ys, [q, 1 - q])
    return int(x0), int(y0), int(np.ceil(x1)) + 1, int(np.ceil(y1)) + 1


def fit_into(sil: np.ndarray, box, size: int, q: float = 0.015, stretch: float = 1.075) -> np.ndarray:
    """Move and scale an outline so it sits in `box` (its robust box centred on it), keeping its own proportions but for
    at most `stretch` along one side — a little room for the picture's perspective, none for blowing a frame seen
    edge-on up into a solid."""
    out = np.zeros((size, size), bool)
    b = robust_box(sil, q)
    if b is None or box is None:
        return out
    x0, y0, x1, y1 = b
    X0, Y0, X1, Y1 = box
    sx = (X1 - X0) / max(1, x1 - x0)
    sy = (Y1 - Y0) / max(1, y1 - y0)
    base = min(sx, sy)                    # fit inside the box with the outline's own proportions …
    sx, sy = min(sx, base * stretch), min(sy, base * stretch)     # … then at most `stretch` more along one side
    cx, cy, CX, CY = (x0 + x1) / 2, (y0 + y1) / 2, (X0 + X1) / 2, (Y0 + Y1) / 2
    ys, xs = np.nonzero(sil)
    nx = ((xs - cx) * sx + CX).astype(np.int64)
    ny = ((ys - cy) * sy + CY).astype(np.int64)
    ok = (nx >= 0) & (nx < size) & (ny >= 0) & (ny < size)
    out[ny[ok], nx[ok]] = True
    k = int(np.ceil(max(sx, sy)))
    return closing(out, k // 2 + 1) if k > 1 else out
