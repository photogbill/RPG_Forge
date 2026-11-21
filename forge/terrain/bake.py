"""The terrain bakes (BUILD 77 part 3) — CPU only, numpy and Pillow. Every output carries a provenance file
(`<name>.json`) naming the window, the dials and "DTED Level 0"; what was invented (the added detail) and what was
edited (a crater, a pad) is said there and drawn apart on the page.

  window   -> a 16-bit height picture (`terrain_window`), with dials: shrink, exaggerate (a number, or a curve so
              mountains rise more than plains), sea_level, smooth, detail (seeded fine noise below the data's scale)
  shade    -> a shaded relief from a chosen sun, hypsometric tint optional (`terrain_shade`): the world map's base
  water    -> coast, rivers and lakes from Natural Earth GeoJSON the person drops in (`terrain_water`); without the
              files it says which it wants and does nothing
  edit     -> the story's changes as data: a crater (centre, radius, depth, rim), a flattened pad (`terrain_edit`)
  profile  -> the ground along a straight line, the rock over a line through it, where a line at a grade comes out
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

from .dted import M_PER_DEG_LAT, M_PER_DEG_LON_EQ, Library

SOURCE = "DTED Level 0 (NIMA/NGA, 30 arc-second posts, about 900 m)"
CREDIT = "This product was developed using DTED Level 0, a product of the National Imagery and Mapping Agency."
DISCLAIMER = ("Use of DTED Level 0 does not indicate endorsement or approval of this product by the Secretary of Defense, the "
              "former Defense Mapping Agency or the National Imagery and Mapping Agency. DTED Level 0 is provided as is.")


# ------------------------------------------------------------------------------------------------ dials
def exaggerated(h: np.ndarray, exaggerate, sea_level: float = 0.0) -> np.ndarray:
    """Heights above sea level times a factor — one number, or a curve [[metres, factor], ...] so mountains can rise more
    than plains. Below sea level is left as it is. Monotonic for any factor >= 0 that does not fall faster than 1/h."""
    a = h - sea_level
    if isinstance(exaggerate, (int, float)):
        f = np.full_like(a, float(exaggerate))
    else:
        pts = sorted((float(m), float(k)) for m, k in exaggerate)
        f = np.interp(np.maximum(a, 0), [p[0] for p in pts], [p[1] for p in pts])
    return np.where(a > 0, sea_level + a * f, h)


def smooth(h: np.ndarray, passes: int) -> np.ndarray:
    for _ in range(max(0, int(passes))):
        P = np.pad(h, 1, mode="edge")
        h = (P[1:-1, 1:-1] * 4 + P[:-2, 1:-1] + P[2:, 1:-1] + P[1:-1, :-2] + P[1:-1, 2:]) / 8.0
    return h


def soften(h: np.ndarray, k: int) -> np.ndarray:
    """A box blur of width k, twice (close to a Gaussian), edges held: takes the facets out of a window sampled much finer
    than the data's ~900 m posts, before any detail is added on top."""
    if k <= 1:
        return h
    def box(a, axis):
        r = k // 2
        P = np.pad(a, [(r, r) if i == axis else (0, 0) for i in range(2)], mode="edge")
        c = np.cumsum(P, axis=axis, dtype=np.float64)
        c = np.concatenate([np.zeros_like(np.take(c, [0], axis=axis)), c], axis=axis)
        n = a.shape[axis]
        return (np.take(c, np.arange(k, k + n), axis=axis) - np.take(c, np.arange(0, n), axis=axis)) / k
    for _ in range(2):
        h = box(box(h, 0), 1)
    return h


def detail_noise(shape, amplitude_m: float, seed: int, octaves: int = 4) -> np.ndarray:
    """Fine noise below the data's own scale, seeded (the same seed gives the same ground): value noise summed over
    octaves, so a walked slope is not a staircase. It is invention, and the provenance says so."""
    if amplitude_m <= 0:
        return np.zeros(shape)
    rng = np.random.default_rng(int(seed))
    out = np.zeros(shape)
    ny, nx = shape
    amp = 1.0
    for o in range(octaves):
        cells = 2 ** (o + 3)
        g = rng.standard_normal((cells + 1, cells + 1))
        y = np.linspace(0, cells, ny)
        x = np.linspace(0, cells, nx)
        y0, x0 = np.floor(y).astype(int).clip(0, cells - 1), np.floor(x).astype(int).clip(0, cells - 1)
        ty, tx = (y - y0)[:, None], (x - x0)[None, :]
        ty, tx = ty * ty * (3 - 2 * ty), tx * tx * (3 - 2 * tx)
        v = (g[y0][:, x0] * (1 - tx) * (1 - ty) + g[y0][:, x0 + 1] * tx * (1 - ty) + g[y0 + 1][:, x0] * (1 - tx) * ty
             + g[y0 + 1][:, x0 + 1] * tx * ty)
        out += v * amp
        amp *= 0.5
    return out / max(np.abs(out).max(), 1e-9) * amplitude_m


# ------------------------------------------------------------------------------------------------ edits
def _metres_grid(win: dict) -> tuple[np.ndarray, np.ndarray]:
    lats, lons = win["lats"], win["lons"]
    latc = (lats[0] + lats[-1]) / 2
    X = (lons[None, :] - lons[0]) * M_PER_DEG_LON_EQ * math.cos(math.radians(latc))
    Y = (lats[0] - lats[:, None]) * M_PER_DEG_LAT
    return np.broadcast_to(X, (len(lats), len(lons))), np.broadcast_to(Y, (len(lats), len(lons)))


def to_xy(win: dict, lat: float, lon: float) -> tuple[float, float]:
    latc = (win["lats"][0] + win["lats"][-1]) / 2
    return ((lon - win["lons"][0]) * M_PER_DEG_LON_EQ * math.cos(math.radians(latc)), (win["lats"][0] - lat) * M_PER_DEG_LAT)


def crater(h: np.ndarray, X: np.ndarray, Y: np.ndarray, cx: float, cy: float, radius_m: float, depth_m: float,
           rim_m: float) -> tuple[np.ndarray, np.ndarray]:
    """A crater: the centre lowered by `depth_m` in a bowl, a rim raised by `rim_m` at the radius falling off outside it
    to nothing at 1.6 radii. Nothing outside 1.6 radii is touched. Returns (heights, mask of what changed)."""
    r = np.hypot(X - cx, Y - cy) / max(radius_m, 1e-9)
    bowl = np.where(r < 1.0, -depth_m * (1 - r ** 2), 0.0)
    rim = np.where(r < 1.0, rim_m * r ** 4, np.where(r < 1.6, rim_m * (1 - (r - 1.0) / 0.6) ** 2, 0.0))
    d = bowl + rim
    return h + d, r < 1.6


def flatten(h: np.ndarray, X: np.ndarray, Y: np.ndarray, cx: float, cy: float, radius_m: float, at_m: float | None = None,
            feather_m: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """A town's pad, flattened by its place plan: level at `at_m` (the mean under it when not given) within the radius,
    blended back over `feather_m`."""
    r = np.hypot(X - cx, Y - cy)
    inside = r < radius_m
    level = float(at_m) if at_m is not None else float(h[inside].mean()) if inside.any() else float(h.mean())
    f = float(feather_m or radius_m * 0.5)
    w = np.clip(1 - (r - radius_m) / f, 0, 1)
    return h * (1 - w) + level * w, w > 0


# ------------------------------------------------------------------------------------------------ the bakes
def _prov(out: Path, kind: str, win: dict, dials: dict, extra: dict | None = None) -> dict:
    p = {"kind": kind, "source": SOURCE, "credit": CREDIT, "disclaimer": DISCLAIMER, "window": win["window"], "size_m": win.get("size_m"), "m_per_post": round(win["m_per_post"], 2),
         "cells": len(win.get("cells") or []), "missing_cells": [list(k) for k in win.get("missing") or []][:50],
         "dials": dials, "made": time.strftime("%Y-%m-%d %H:%M"), **(extra or {})}
    out.with_suffix(".json").write_text(json.dumps(p, indent=1), encoding="utf-8")
    return p


def sea_mask(h: np.ndarray, nodata: np.ndarray, sea_level: float = 0.0, max_iter: int = 600) -> np.ndarray:
    """DTED has no sea: the ocean is missing cells, and the coastal cells' sea posts read sea level. The sea is what can be
    reached from a missing cell or the window's edge through posts at or below sea level — so a basin below sea level that
    the sea cannot reach (Death Valley, New Orleans behind its levees) stays dry."""
    low = (h <= sea_level + 0.5) | nodata
    m = nodata.copy()
    edge = np.zeros_like(m)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    m |= edge & low & (h <= sea_level + 0.5)
    for _ in range(max_iter):
        P = np.pad(m, 1)
        g = (P[:-2, 1:-1] | P[2:, 1:-1] | P[1:-1, :-2] | P[1:-1, 2:] | m) & low
        if (g == m).all():
            break
        m = g
    return m


def heights(lib: Library, w: dict, dials: dict | None = None) -> tuple[dict, np.ndarray, dict]:
    """The window's heights with the dials and the edits applied. Returns (window, heights, layers) — layers: masks of
    "invented" (detail added) and "edited" (craters, pads), for drawing how each height was produced."""
    d = {"posts": 512, "shrink": 1.0, "exaggerate": 1.0, "sea_level": 0.0, "smooth": 0, "detail_m": 0.0, "seed": 77,
         **(dials or {})}
    win = lib.window(w["south"], w["west"], w["north"], w["east"], posts=int(d["posts"]), sea=None)
    h = win["h"].copy()
    nodata = np.isnan(h)
    h = np.where(nodata, float(d["sea_level"]) - 1.0, h)            # DTED has no sea: no cell is water, just under sea level
    h = smooth(h, int(d["smooth"]))
    over = 900.0 / max(win["m_per_post"], 1e-6)            # how much finer than the data's posts this window is sampled
    if over > 3 and d.get("soften", True):
        h = np.where(nodata, h, soften(h, int(round(over))))
        d["softened_to_posts"] = round(over, 1)
    inv = np.zeros(h.shape, bool)
    if float(d["detail_m"]) > 0:
        n = detail_noise(h.shape, float(d["detail_m"]), int(d["seed"]))
        h = np.where(nodata, h, h + n)
        inv = ~nodata
    X, Y = _metres_grid(win)
    edited = np.zeros(h.shape, bool)
    for e in w.get("edits") or []:
        if e.get("at") is None:
            continue
        cx, cy = to_xy(win, *e["at"])
        if e.get("kind") == "crater":
            h, m = crater(h, X, Y, cx, cy, float(e["radius_m"]), float(e["depth_m"]), float(e.get("rim_m", e["depth_m"] * 0.3)))
        elif e.get("kind") == "flatten":
            h, m = flatten(h, X, Y, cx, cy, float(e["radius_m"]), e.get("at_m"), e.get("feather_m"))
        else:
            continue
        edited |= m
    h = exaggerated(h, d["exaggerate"], float(d["sea_level"]))
    sea = sea_mask(h, nodata, float(d["sea_level"]))
    return win, h, {"invented": inv, "edited": edited, "nodata": nodata, "sea": sea}


def terrain_window(lib: Library, w: dict, out: Path, dials: dict | None = None) -> dict:
    """a. The 16-bit height picture. Pixel 0 is `base_m`, 65535 is `base_m + range_m`; in game metres divide by shrink."""
    from PIL import Image
    d = {"posts": 512, "shrink": 1.0, "exaggerate": 1.0, "sea_level": 0.0, "smooth": 0, "detail_m": 0.0, "seed": 77, **(dials or {})}
    win, h, layers = heights(lib, w, d)
    base, top = float(np.nanmin(h)), float(np.nanmax(h))
    rng = max(top - base, 1e-6)
    px = np.round((h - base) / rng * 65535).astype(np.uint16)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(px).save(out)
    shrink = float(d["shrink"])
    return _prov(out, "terrain_window", win, d, {
        "picture": out.name, "base_m": round(base, 2), "range_m": round(rng, 2),
        "game": {"base": round(base / shrink, 3), "range": round(rng / shrink, 3), "m_per_px": round(win["m_per_post"] / shrink, 4)},
        "invented": "fine detail below the data's scale, seeded" if d["detail_m"] else None,
        "edits": [{k: v for k, v in e.items() if k != "note"} for e in w.get("edits") or [] if e.get("at") is not None]})


TINT = [(-500, (40, 70, 110)), (0, (70, 110, 80)), (300, (120, 150, 90)), (900, (175, 160, 110)), (1800, (150, 120, 95)),
        (3000, (200, 195, 190)), (4500, (250, 250, 250))]


def hillshade(h: np.ndarray, m_per_px: float, sun_az: float = 315.0, sun_el: float = 35.0) -> np.ndarray:
    gy, gx = np.gradient(h, m_per_px)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, el = math.radians(sun_az), math.radians(sun_el)
    s = np.sin(el) * np.cos(slope) + np.cos(el) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(s, 0, 1)


def terrain_shade(lib: Library, w: dict, out: Path, dials: dict | None = None, layers_out: Path | None = None) -> dict:
    """b. The shaded relief, lit from `sun_az`/`sun_el`, hypsometric tint optional; with `layers_out`, a second picture
    coloured by how each height was produced (measured, invented, edited — as ATK colours its results)."""
    from PIL import Image
    d = {"posts": 1024, "exaggerate": 1.0, "sea_level": 0.0, "sun_az": 315.0, "sun_el": 35.0, "tint": True, "relief_x": 6.0,
         **(dials or {})}
    win, h, layers = heights(lib, w, d)
    s = hillshade(h * float(d["relief_x"]), win["m_per_post"], float(d["sun_az"]), float(d["sun_el"]))
    if d["tint"]:
        hs = [t[0] for t in TINT]
        col = np.stack([np.interp(h, hs, [t[1][c] for t in TINT]) for c in range(3)], -1)
    else:
        col = np.full(h.shape + (3,), 200.0)
    img = col * (0.35 + 0.65 * s[..., None])
    img[layers["sea"]] = (52, 86, 128) * (0.85 + 0.15 * s[layers["sea"]][:, None])
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(out)
    extra = {"picture": out.name}
    if layers_out is not None:
        L = np.full(h.shape + (3,), (90, 160, 255), np.float64)        # measured: blue
        L[layers["invented"]] = (255, 200, 90)                          # invented: amber
        L[layers["edited"]] = (255, 80, 90)                             # edited: red
        L[layers["sea"]] = (30, 40, 60)
        Image.fromarray(np.clip(L * (0.4 + 0.6 * s[..., None]), 0, 255).astype(np.uint8)).save(layers_out)
        extra["layers_picture"] = Path(layers_out).name
        extra["layers"] = {"measured": "blue", "invented": "amber", "edited": "red", "sea (DTED has none)": "dark"}
    return _prov(out, "terrain_shade", win, d, extra)


NE_FILES = {"coast": "ne_10m_coastline.geojson", "rivers": "ne_10m_rivers_lake_centerlines.geojson", "lakes": "ne_10m_lakes.geojson"}


def terrain_water(base_picture: Path, w: dict, ne_dir: Path, out: Path, posts_hint: dict | None = None) -> dict:
    """c. Coast, rivers and lakes burned over a shaded picture from Natural Earth (public domain) GeoJSON files the person
    drops into `ne_dir`. Without them it says which it wants and does nothing."""
    from PIL import Image, ImageDraw
    ne_dir = Path(ne_dir)
    want = {k: ne_dir / f for k, f in NE_FILES.items()}
    have = {k: p for k, p in want.items() if p.exists()}
    if not have:
        return {"ok": False, "wants": [str(p) for p in want.values()],
                "message": "No Natural Earth files yet: drop " + ", ".join(NE_FILES.values()) + f" into {ne_dir} "
                           "(naturalearthdata.com, public domain; the GeoJSON copies are in the natural-earth-vector repository)."}
    im = Image.open(base_picture).convert("RGB")
    W, H = im.size
    dr = ImageDraw.Draw(im)

    def xy(lon, lat):
        return ((lon - w["west"]) / (w["east"] - w["west"]) * (W - 1), (w["north"] - lat) / (w["north"] - w["south"]) * (H - 1))
    drawn = {}
    for k, p in have.items():
        n = 0
        for f in json.loads(p.read_text(encoding="utf-8")).get("features") or []:
            g = f.get("geometry") or {}
            parts = {"LineString": [g.get("coordinates")], "MultiLineString": g.get("coordinates"),
                     "Polygon": g.get("coordinates"), "MultiPolygon": [r for poly in g.get("coordinates") or [] for r in poly]}.get(g.get("type"), [])
            for line in parts or []:
                pts = [xy(c[0], c[1]) for c in line if w["west"] - 1 <= c[0] <= w["east"] + 1 and w["south"] - 1 <= c[1] <= w["north"] + 1]
                if len(pts) < 2:
                    continue
                if k == "lakes":
                    dr.polygon(pts, fill=(60, 100, 150))
                else:
                    dr.line(pts, fill=(40, 80, 140) if k == "coast" else (70, 120, 180), width=2 if k == "coast" else 1)
                n += 1
        drawn[k] = n
    out = Path(out)
    im.save(out)
    out.with_suffix(".json").write_text(json.dumps({"kind": "terrain_water", "source": "Natural Earth (public domain)",
                                                    "window": w, "drawn": drawn, "files": {k: p.name for k, p in have.items()}},
                                                   indent=1), encoding="utf-8")
    return {"ok": True, "drawn": drawn, "picture": out.name}


# ------------------------------------------------------------------------------------------------ the ground along a line
def destination(lat: float, lon: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    R = 6_371_000.0
    b, d = math.radians(bearing_deg), dist_m / R
    la1, lo1 = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(b))
    lo2 = lo1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2))
    return math.degrees(la2), math.degrees(lo2)


def distance_m(a: tuple, b: tuple) -> float:
    R = 6_371_000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def profile(lib: Library, start: tuple, end: tuple | None = None, bearing_deg: float | None = None, length_m: float | None = None,
            step_m: float = 100.0, grade: float = 0.0, start_height_m: float | None = None, portal_floor_m: float | None = None) -> dict:
    """The ground along a straight line (start and end, or start, bearing and length): heights every `step_m`, the highest
    point, and — for a line driven from the start at `grade` (0.02 = a 2% climb), beginning at the ground there or at
    `start_height_m` — the rock over the line all the way, where it comes out (the first point after the highest where
    the ground is at or below the line), how far the ground falls away in front of it, and where the cover is thinnest
    (where a vent shaft would really go). Level 0's posts are about 900 m apart: coarse, but enough for a ridge."""
    if end is None:
        end = destination(start[0], start[1], float(bearing_deg), float(length_m))
    L = distance_m(start, end)
    n = max(2, int(L // step_m) + 1)
    ts = np.linspace(0, 1, n)
    pts = [(start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t) for t in ts]
    hs = np.array([lib.height_at(la, lo)[0] if lib.height_at(la, lo)[0] is not None else np.nan for la, lo in pts])
    dist = ts * L
    peak_i = int(np.nanargmax(hs))
    z0 = float(start_height_m) if start_height_m is not None else float(hs[0])
    line = z0 + dist * float(grade)
    cover = hs - line
    out_i = None
    for i in range(peak_i, n):
        if cover[i] <= 0.5:                 # (half a metre: Level 0 is not finer than that)
            out_i = i
            break
    # the way in: the last point before the highest where the line is still in the open
    in_i = 0
    for i in range(peak_i, -1, -1):
        if cover[i] <= 0.5:                 # (half a metre: Level 0 is not finer than that)
            in_i = i
            break
    end_i = out_i if out_i is not None else n
    under = slice(in_i + 1, end_i)
    thin = []
    if end_i - in_i > 2:
        seg = cover[in_i + 1:end_i]
        # the thinnest cover, one a kilometre (shafts are not all bunched at the two ends of the bore)
        order = [int(k) + in_i + 1 for k in np.argsort(seg)]
        taken = []
        for i in order:
            if dist[i] - dist[in_i] < 1000 or dist[end_i - 1] - dist[i] < 1000 or any(abs(dist[i] - dist[t]) < 1000 for t in taken):
                continue
            taken.append(i)
            thin.append({"km": float(round(dist[i] / 1000, 2)), "cover_m": int(round(float(cover[i]))),
                         "at": [float(round(pts[i][0], 5)), float(round(pts[i][1], 5))]})
            if len(thin) >= 5:
                break
    ahead = None
    if out_i is not None:
        j = min(n - 1, out_i + int(2000 // step_m))
        ahead = {"ground_at_door_m": int(round(float(hs[out_i]))), "ground_2km_on_m": int(round(float(hs[j]))),
                 "highest_in_next_8km_m": int(round(float(np.nanmax(hs[out_i:min(n, out_i + int(8000 // step_m))]))))}
    return {"start": [float(x) for x in start], "end": [float(round(end[0], 5)), float(round(end[1], 5))], "length_m": int(round(L)),
            "step_m": step_m, "grade": grade, "start_height_m": int(round(z0)), "posts_note": "DTED Level 0: posts about 900 m apart — a sharp crest reads low",
            "highest": {"km": float(round(dist[peak_i] / 1000, 2)), "m": int(round(float(hs[peak_i]))),
                        "at": [float(round(pts[peak_i][0], 5)), float(round(pts[peak_i][1], 5))]},
            "goes_in": {"km": float(round(dist[in_i] / 1000, 2)), "m": int(round(float(hs[in_i])))},
            "comes_out": None if out_i is None else {"km": float(round(dist[out_i] / 1000, 2)), "m": int(round(float(hs[out_i]))),
                                                     "at": [float(round(pts[out_i][0], 5)), float(round(pts[out_i][1], 5))],
                                                     "bore_m": int(round(float(dist[out_i] - dist[in_i]))),
                                                     "bore_miles": float(round(float(dist[out_i] - dist[in_i]) / 1609.344, 2))},
            "most_cover_m": int(round(float(np.nanmax(cover[under])))) if end_i - in_i > 1 else 0,
            "thinnest_cover": thin, "ahead_of_the_door": ahead,
            "samples": [{"km": round(float(d) / 1000, 3), "m": None if np.isnan(h) else round(float(h), 1)} for d, h in zip(dist, hs)]}


def profile_picture(p: dict, out: Path, title: str = "") -> Path:
    from PIL import Image, ImageDraw
    from ..threed.checks import _font
    font, plain = _font(14)
    W, H, pad = 1400, 520, 60
    km = np.array([s["km"] for s in p["samples"]])
    m = np.array([np.nan if s["m"] is None else s["m"] for s in p["samples"]])
    lo, hi = np.nanmin(m) - 50, np.nanmax(m) + 120
    X = lambda k: pad + (k / max(km[-1], 1e-6)) * (W - 2 * pad)
    Y = lambda z: H - pad - (z - lo) / (hi - lo) * (H - 2 * pad)
    im = Image.new("RGB", (W, H), (18, 20, 26))
    d = ImageDraw.Draw(im)
    poly = [(X(k), Y(z)) for k, z in zip(km, m) if not np.isnan(z)] + [(X(km[-1]), H - pad), (X(0), H - pad)]
    d.polygon(poly, fill=(92, 86, 70))
    z0, g = p["start_height_m"], p["grade"]
    if p.get("comes_out"):
        kx = p["comes_out"]["km"]
        d.line([(X(0), Y(z0)), (X(kx), Y(z0 + kx * 1000 * g))], fill=(255, 210, 90), width=3)
        d.ellipse([X(kx) - 6, Y(p["comes_out"]["m"]) - 6, X(kx) + 6, Y(p["comes_out"]["m"]) + 6], outline=(255, 90, 90), width=3)
    pk = p["highest"]
    d.text((X(pk["km"]) - 40, Y(pk["m"]) - 22), plain(f"{pk['m']} m"), fill=(240, 240, 240), font=font)
    for t in p.get("thinnest_cover") or []:
        d.line([(X(t["km"]), Y(z0 + t["km"] * 1000 * g)), (X(t["km"]), Y(z0 + t["km"] * 1000 * g + t["cover_m"]))], fill=(120, 200, 255), width=2)
    for k in range(0, int(km[-1]) + 1, max(1, int(km[-1] // 12) or 1)):
        d.text((X(k) - 8, H - pad + 8), plain(f"{k} km"), fill=(170, 170, 170), font=font)
    d.text((pad, 14), plain(title or "the ground along the line"), fill=(255, 220, 150), font=font)
    co = p.get("comes_out")
    d.text((pad, 34), plain((f"a line at {g * 100:.1f}% from {z0} m goes in at {p['goes_in']['km']} km and comes out at {co['km']} km — "
                             f"{co['bore_miles']} miles of rock — at {co['m']} m"
                             if co else "the line never comes out within this length") + " · " + p["posts_note"]),
           fill=(200, 200, 200), font=font)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out
