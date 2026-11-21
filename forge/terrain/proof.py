"""BUILD 77 part 2 — the reader proved against known ground, before anything is baked.

Each row: a well-known summit or low point with its published elevation, what the reader returns there, and the difference;
and the highest post within 2 km (a summit between 900 m posts reads low under bilinear interpolation, and a bounded search
says how low). A low point that reads as a large positive number means the sign handling is wrong: the table says STOP.
"""
from __future__ import annotations

import math

import numpy as np

from .dted import Library

KNOWN = [
    # name, lat, lon, published metres, what it is, source of the figure
    ("Mount Mitchell, North Carolina", 35.7650, -82.2652, 2037, "summit", "USGS / NGS"),
    ("Mount Elbert, Colorado", 39.1178, -106.4454, 4401, "summit", "USGS / NGS"),
    ("Mount Whitney, California", 36.5785, -118.2923, 4421, "summit", "USGS / NGS"),
    ("Pikes Peak, Colorado", 38.8409, -105.0423, 4302, "summit", "USGS / NGS"),
    ("Mount Washington, New Hampshire", 44.2706, -71.3033, 1917, "summit", "USGS / NGS"),
    ("Spruce Knob, West Virginia", 38.6998, -79.5328, 1482, "summit", "USGS"),
    ("Mont Ross, Kerguelen", -49.59222, 69.49583, 1850, "summit", "Peaklist / IGN (as cited by Wikipedia, read 2026-11-17)"),
    ("Badwater Basin, Death Valley", 36.2297, -116.7669, -86, "low point", "USGS"),
    ("New Orleans, Louisiana (city centre)", 29.9511, -90.0715, 0, "low ground", "about sea level (USGS: -2 to +5 m across the city)"),
    ("Denver, Colorado (State Capitol step)", 39.7393, -104.9848, 1609, "city", "the Capitol's 'one mile high' step"),
]


def peak_near(lib: Library, lat: float, lon: float, radius_m: float = 2000.0, step_m: float = 150.0) -> float | None:
    best = None
    k = int(radius_m // step_m)
    for i in range(-k, k + 1):
        for j in range(-k, k + 1):
            if (i * i + j * j) * step_m * step_m > radius_m * radius_m:
                continue
            la = lat + i * step_m / 110_574.0
            lo = lon + j * step_m / (111_320.0 * math.cos(math.radians(lat)))
            h, _ = lib.height_at(la, lo)
            if h is not None and (best is None or h > best):
                best = h
    return best


def table(lib: Library, extra: list | None = None) -> dict:
    rows, stop = [], []
    for name, lat, lon, pub, what, src in KNOWN + list(extra or []):
        h, cell = lib.height_at(lat, lon)
        near = peak_near(lib, lat, lon) if what == "summit" else None
        row = {"name": name, "lat": lat, "lon": lon, "published_m": pub, "what": what, "source": src,
               "reads_m": None if h is None else round(h), "cell": cell,
               "diff_m": None if (h is None or pub is None) else round(h - pub),
               "highest_within_2km_m": None if near is None else round(near)}
        if what in ("low point", "low ground") and h is not None and pub is not None and h - pub > 150:
            stop.append(name)
        rows.append(row)
    summits = [r for r in rows if r["what"] == "summit" and r["diff_m"] is not None]
    lows = [r for r in rows if r["what"] != "summit" and r["diff_m"] is not None]
    return {"rows": rows, "stop": stop,
            "summit_low_by_m": {"mean": round(float(np.mean([-r["diff_m"] for r in summits])), 0) if summits else None,
                                "worst": max((-r["diff_m"] for r in summits), default=None)},
            "low_ground_within_m": max((abs(r["diff_m"]) for r in lows), default=None)}


def markdown(t: dict) -> str:
    L = ["| place | published | the reader | difference | highest post within 2 km | cell |", "|---|---|---|---|---|---|"]
    for r in t["rows"]:
        L.append(f"| {r['name']} | {r['published_m'] if r['published_m'] is not None else '—'} m | "
                 f"{'no data' if r['reads_m'] is None else str(r['reads_m']) + ' m'} | "
                 f"{'' if r['diff_m'] is None else ('%+d m' % r['diff_m'])} | "
                 f"{'' if r['highest_within_2km_m'] is None else str(r['highest_within_2km_m']) + ' m'} | {str(r['cell'] or '').split('/', 1)[-1]} |")
    s = t["summit_low_by_m"]
    L.append("")
    L.append(f"Summits read low by {s['mean']:.0f} m on average (worst {s['worst']} m): Level 0's posts are about 900 m apart and "
             "a sharp summit falls between them. Low ground agrees within "
             f"{t['low_ground_within_m']} m." + (" **STOP — a low point reads high: the sign handling is wrong.**" if t["stop"] else
                                                 " Badwater reads below sea level: the sign-and-magnitude words are read right."))
    return "\n".join(L)
