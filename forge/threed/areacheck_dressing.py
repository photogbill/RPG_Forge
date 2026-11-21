"""Every area checked (BUILD 83 Part B) — check 6 (Repeats) and check 7 (Dressing), built by BUILD 97 Part 5 / BUILD 98.

✦ William, 2026-11-20 23:30: "It looks like an empty neighborhood unlived in." BUILD 97 Part 5: "the checks that would have
caught this". This is the measure every dressing pass is judged by.

    zones(place, rules)                      -> the place cut into zones (kerb strips, front yards, back and side yards,
                                                porches, shop fronts, interiors, open lots), on a 0.5 m grid
    check_dressing(place, extra, rules, ...) -> check 7: things per 100 m² a zone against its kind's target, and the
                                                largest empty stretch; the kerb in metres between things
    check_repeats(place, extra, rules, ...)  -> check 6: the same model more than the limit in one map-camera view, or
                                                twice side by side at the same turn and size
    board(places_dir, ...)                   -> every place on one board (the areas board)
    draw_zones(...)                          -> the plan from above with its zones and its flags (stamped greybox)

Pure: reads a place plan (metres), the dresser's output beside it (`<place>.dressing_out.json`), the world lists' sizes, and
two rules files (`forge/threed/area_rules.json`, no game named; `<game>/area_rules.json`, the game's own). It changes
nothing but its own report files. Nothing here names a game.

Run by hand (any Python with numpy; Pillow for the picture):
    python -m forge.threed.areacheck_dressing --places <games/<id>/places> --rules-game <games/<id>/area_rules.json>
           [--wanted <games/<id>/wanted_3d>] [--stage <game>/project/data/stage.json] [--out <out/areas/<id>>] [place …]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CELL = 0.5                                       # metres a grid cell

# zone kinds (the grid holds their index)
Z_OUT, Z_ROAD, Z_BUILDING, Z_KERB, Z_FRONT, Z_BACK, Z_SHOP, Z_OPEN, Z_INTERIOR, Z_EXCLUDED = range(10)
ZONE_NAMES = {Z_OUT: "outside the plan", Z_ROAD: "road", Z_BUILDING: "building", Z_KERB: "kerb strip",
              Z_FRONT: "front yard", Z_BACK: "back / side yard", Z_SHOP: "shop front", Z_OPEN: "open lot",
              Z_INTERIOR: "interior", Z_EXCLUDED: "not dressed (fixed by William)"}
ZONE_KEYS = {Z_KERB: "kerb", Z_FRONT: "front_yard", Z_BACK: "back_yard", Z_SHOP: "shop_front", Z_OPEN: "open_lot",
             Z_INTERIOR: "interior"}
ZONE_COLOURS = {Z_OUT: (30, 30, 34), Z_ROAD: (62, 64, 70), Z_BUILDING: (190, 178, 160), Z_KERB: (150, 150, 146),
                Z_FRONT: (92, 140, 74), Z_BACK: (64, 110, 60), Z_SHOP: (176, 140, 92), Z_OPEN: (110, 120, 80),
                Z_INTERIOR: (150, 120, 100), Z_EXCLUDED: (70, 70, 110)}


# ------------------------------------------------------------------------------------------------ rules
def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        if k.startswith("_"):
            continue
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_rules(game_rules: Path | None = None, defaults: Path | None = None) -> dict:
    """The forge's defaults with the game's own rules over them (the game's file wins, key by key)."""
    base = json.loads((defaults or HERE / "area_rules.json").read_text(encoding="utf-8"))
    if game_rules and Path(game_rules).exists():
        base = _merge(base, json.loads(Path(game_rules).read_text(encoding="utf-8")))
    return base


def place_rules(rules: dict, pid: str) -> dict:
    return (rules.get("places") or {}).get(pid) or {}


# ------------------------------------------------------------------------------------------------ sizes
def load_sizes(wanted_dir: Path | None) -> dict:
    """id -> real_size_m (width / height / depth, metres) from every world list. A list file is read, never written."""
    sizes: dict = {}
    if not wanted_dir or not Path(wanted_dir).exists():
        return sizes
    for f in sorted(Path(wanted_dir).glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for e in (d.get("entries") if isinstance(d, dict) else d) or []:
            if isinstance(e, dict) and e.get("id") and isinstance(e.get("real_size_m"), dict):
                sizes[str(e["id"])] = e["real_size_m"]
    return sizes


def model_of(t: dict) -> str:
    return str(t.get("model") or t.get("id") or "")


def box_of(t: dict, sizes: dict, rules: dict, pid: str = "") -> tuple[float, float]:
    """(width, depth) of a thing on the ground, metres: its own box, then its world entry's real size, then the rules'
    default for the first keyword its id, model or label holds, then its kind's default."""
    for key in ("box_m", "size_m"):
        b = t.get(key)
        if isinstance(b, (list, tuple)) and len(b) >= 2:
            return float(b[0]), float(b[1])
    if isinstance(t.get("footprint"), (list, tuple)) and len(t["footprint"]) == 4:
        return float(t["footprint"][2]), float(t["footprint"][3])
    words = " ".join(str(t.get(k) or "") for k in ("id", "model", "label", "family")).lower()
    defaults = rules.get("default_box_m") or {}
    guess = None
    for kw, b in defaults.items():
        if kw in words:
            guess = (float(b[0]), float(b[1]))
            break
    if guess is None:
        b = defaults.get(str(t.get("kind") or "prop")) or [1.0, 1.0]
        guess = (float(b[0]), float(b[1]))
    rs = (sizes.get(model_of(t)) or sizes.get(str(t.get("id") or ""))
          or (sizes.get(f"{pid}_{t.get('id')}") if pid else None))   # the compiler names a plan's own things <place>_<id>
    if rs and rs.get("width"):
        w = float(rs["width"])
        d = float(rs.get("depth") or w * (guess[1] / guess[0] if guess[0] else 1.0))
        return w, d
    return guess


def corners(at, w: float, d: float, turn: float) -> list[tuple[float, float]]:
    a = math.radians(float(turn or 0))
    ca, sa = math.cos(a), math.sin(a)
    return [(at[0] + cx * ca - cy * sa, at[1] + cx * sa + cy * ca) for cx, cy in
            ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))]


# ------------------------------------------------------------------------------------------------ the grid
class Grid:
    def __init__(self, size, cell: float = CELL):
        self.cell = cell
        self.W = max(1, int(math.ceil(float(size[0]) / cell)))
        self.H = max(1, int(math.ceil(float(size[1]) / cell)))
        xs = (np.arange(self.W) + 0.5) * cell
        ys = (np.arange(self.H) + 0.5) * cell
        self.X, self.Y = np.meshgrid(xs, ys)           # [H, W] cell centres in metres

    def rect(self, r) -> np.ndarray:
        x, y, w, h = (float(v) for v in r)
        return (self.X >= x) & (self.X < x + w) & (self.Y >= y) & (self.Y < y + h)

    def poly(self, pts) -> np.ndarray:
        """Cells whose centre is inside a convex or simple polygon (even-odd)."""
        inside = np.zeros(self.X.shape, bool)
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            cond = (y1 > self.Y) != (y2 > self.Y)
            with np.errstate(divide="ignore", invalid="ignore"):
                xint = (x2 - x1) * (self.Y - y1) / ((y2 - y1) if y2 != y1 else 1e-9) + x1
            inside ^= cond & (self.X < xint)
        return inside

    def ground(self, g: dict) -> np.ndarray | None:
        if "rect" in g and g["rect"]:
            return self.rect(g["rect"])
        if "poly" in g and g["poly"]:
            return self.poly(g["poly"])
        if "ellipse" in g and g["ellipse"]:
            x, y, rx, ry = (float(v) for v in g["ellipse"])
            return ((self.X - x) / max(rx, 1e-6)) ** 2 + ((self.Y - y) / max(ry, 1e-6)) ** 2 <= 1.0
        return None


def distance(mask_occupied: np.ndarray, cell: float) -> np.ndarray:
    """Metres from every cell to the nearest occupied cell (a two-pass chamfer, 1 and √2; no scipy needed)."""
    INF = 1e9
    H, W = mask_occupied.shape
    d = np.where(mask_occupied, 0.0, INF)
    r2 = math.sqrt(2.0)
    # rows as numpy vectors, columns in a python loop: fast enough for a 300 × 100 m plan at 0.5 m
    for y in range(H):
        row = d[y]
        if y > 0:
            up = d[y - 1]
            row = np.minimum(row, up + 1.0)
            row[1:] = np.minimum(row[1:], up[:-1] + r2)
            row[:-1] = np.minimum(row[:-1], up[1:] + r2)
        for x in range(1, W):
            if row[x - 1] + 1.0 < row[x]:
                row[x] = row[x - 1] + 1.0
        d[y] = row
    for y in range(H - 1, -1, -1):
        row = d[y]
        if y < H - 1:
            dn = d[y + 1]
            row = np.minimum(row, dn + 1.0)
            row[1:] = np.minimum(row[1:], dn[:-1] + r2)
            row[:-1] = np.minimum(row[:-1], dn[1:] + r2)
        for x in range(W - 2, -1, -1):
            if row[x + 1] + 1.0 < row[x]:
                row[x] = row[x + 1] + 1.0
        d[y] = row
    return d * cell


# ------------------------------------------------------------------------------------------------ buildings
def building_kind(t: dict, rules: dict, prules: dict) -> str:
    if t.get("zone_kind"):
        return str(t["zone_kind"])
    if prules.get("kind"):
        return str(prules["kind"])
    words = " ".join(str(t.get(k) or "") for k in ("id", "label", "model")).lower()
    for kind, kws in (rules.get("building_kinds") or {}).items():
        if any(k in words for k in kws):
            return kind
    return "home"


def facing_of(t: dict):
    """The way a placed building's model faces, from its turn (a model's front faces +y at turn 0): (ux, uy), or None
    when the plan gives no turn (a plan-built house faces by its door instead)."""
    if t.get("turn") is None or t.get("footprint"):
        return None
    a = math.radians(float(t["turn"]))
    return (-math.sin(a), math.cos(a))


def buildings_of(place: dict, sizes: dict, rules: dict, prules: dict) -> list[dict]:
    out = []
    for t in place.get("things") or []:
        if not isinstance(t, dict) or str(t.get("kind")) != "building":
            continue
        if isinstance(t.get("footprint"), (list, tuple)) and len(t["footprint"]) == 4:
            x, y, w, h = (float(v) for v in t["footprint"])
            cx, cy, turn = x + w / 2, y + h / 2, 0.0
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        else:
            at = t.get("at") or [0, 0]
            w, h = box_of(t, sizes, rules, str(place.get("id") or ""))
            cx, cy, turn = float(at[0]), float(at[1]), float(t.get("turn") or 0)
            pts = corners((cx, cy), w, h, turn)
        out.append({"id": t.get("id"), "thing": t, "pts": pts, "centre": (cx, cy), "w": w, "h": h, "turn": turn,
                    "kind": building_kind(t, rules, prules), "front": t.get("front") or t.get("door"),
                    "facing": facing_of(t),
                    "rooms": t.get("rooms") if t.get("enter") else None})
    return out


# ------------------------------------------------------------------------------------------------ zones
def zones(place: dict, rules: dict, sizes: dict | None = None) -> dict:
    """The place on a grid: zone kind per cell, the lot (building index) per cell, and the buildings."""
    sizes = sizes or {}
    pid = str(place.get("id") or "")
    prules = place_rules(rules, pid)
    g = Grid(place.get("size") or [40, 30], rules.get("cell_m", CELL))
    Z = np.full(g.X.shape, Z_OPEN, np.int8)
    lot = np.full(g.X.shape, -1, np.int16)
    road_mats = [str(m) for m in (rules.get("road_mats") or ["asphalt", "road"])]
    road = np.zeros(g.X.shape, bool)
    for gr in place.get("ground") or []:
        if isinstance(gr, dict) and any(m in str(gr.get("mat") or "") for m in road_mats):
            m = g.ground(gr)
            if m is not None:
                road |= m
    for r in prules.get("road_rects") or []:
        road |= g.rect(r)
    blds = buildings_of(place, sizes, rules, prules)
    bmask = np.zeros(g.X.shape, bool)
    per_b = []
    for b in blds:
        m = g.poly(b["pts"])
        per_b.append(m)
        bmask |= m
    # lots: every outdoor cell within reach of a building goes to the nearest one
    reach = float(rules.get("lot_reach_m", 14.0))
    best = np.full(g.X.shape, 1e9)
    for i, b in enumerate(blds):
        if per_b[i].any():
            dist_b = distance(per_b[i], g.cell)
        else:
            dist_b = np.hypot(g.X - b["centre"][0], g.Y - b["centre"][1])
        closer = (dist_b < best) & (dist_b <= reach)
        lot[closer] = i
        best = np.where(closer, dist_b, best)
    road_dist = distance(road, g.cell) if road.any() else np.full(g.X.shape, 1e9)
    for i, b in enumerate(blds):
        cells = lot == i
        if not cells.any():
            continue
        cx, cy = b["centre"]
        fd = None
        if b["front"]:
            fx, fy = float(b["front"][0]), float(b["front"][1])
            fd = (fx - cx, fy - cy)
        elif b.get("facing"):
            fd = b["facing"]
        elif road.any():
            # toward the nearest road cell
            ry, rx = np.unravel_index(np.argmin(np.where(road, np.hypot(g.X - cx, g.Y - cy), 1e9)), road.shape)
            fd = (g.X[ry, rx] - cx, g.Y[ry, rx] - cy)
        if not fd or math.hypot(*fd) < 1e-6:
            Z[cells] = Z_BACK
            continue
        n = math.hypot(*fd)
        ux, uy = fd[0] / n, fd[1] / n
        # the building's half extent along that direction
        half = max(abs((px - cx) * ux + (py - cy) * uy) for px, py in b["pts"])
        along = (g.X - cx) * ux + (g.Y - cy) * uy
        front = cells & (along > half - 0.25)
        if b["kind"] in ("shop", "bar"):
            depth = float(rules.get("shop_front_depth_m", 4.0))
            Z[front & (along <= half + depth)] = Z_SHOP
            Z[front & (along > half + depth)] = Z_OPEN
            Z[cells & ~front] = Z_BACK
        else:
            Z[front] = Z_FRONT
            Z[cells & ~front] = Z_BACK
    kerb_w = float(rules.get("kerb_strip_m", 2.5))
    kerb = (~road) & (road_dist <= kerb_w) & (str((place.get("road") or {}).get("type") or "street") != "none")
    Z[kerb & (Z != Z_SHOP)] = Z_KERB
    Z[road] = Z_ROAD
    Z[bmask] = Z_BUILDING
    # interiors of buildings the player enters
    for i, b in enumerate(blds):
        for r in b["rooms"] or []:
            Z[g.rect(r)] = Z_INTERIOR
            lot[g.rect(r)] = i
    # what William fixed: whole lots (his yard), or rectangles
    excl = np.zeros(g.X.shape, bool)
    for bid in prules.get("exclude_lots") or []:
        for i, b in enumerate(blds):
            if b["id"] == bid:
                excl |= (lot == i) & (Z != Z_ROAD) & ((Z != Z_KERB) | bool(prules.get("exclude_kerb_too")))
                excl |= per_b[i]
    for r in prules.get("exclude_rects") or []:
        excl |= g.rect(r)
    Z[excl & (Z != Z_ROAD)] = Z_EXCLUDED
    return {"grid": g, "Z": Z, "lot": lot, "buildings": blds, "road": road, "excluded": excl, "place": pid}


# ------------------------------------------------------------------------------------------------ things
def things_of(place: dict, extra: list | None, sizes: dict, rules: dict, interior_items: list | None = None) -> list[dict]:
    """Every placed small thing (not buildings), with its box. `extra` is the dresser's output; `interior_items` the
    plan's own small-things list (the look's dressing)."""
    out = []
    for src, items in (("plan", place.get("things") or []), ("dresser", extra or []), ("look", interior_items or [])):
        for t in items:
            if not isinstance(t, dict) or str(t.get("kind")) == "building" or t.get("plan_built"):
                continue
            at = t.get("at")
            if not (isinstance(at, (list, tuple)) and len(at) >= 2):
                continue
            w, d = box_of(t, sizes, rules, str(place.get("id") or ""))
            if src == "look":
                w, d = (float(t.get("r", 0.15)) * 2,) * 2 if t.get("r") else (0.3, 0.3)
            out.append({"id": str(t.get("id") or f"{src}_{len(out)}"), "model": model_of(t) or str(t.get("kind")),
                        "kind": str(t.get("kind") or "prop"), "at": (float(at[0]), float(at[1])), "w": w, "d": d,
                        "turn": float(t.get("turn") or 0), "src": src, "by": t.get("by") or src,
                        "label": t.get("label") or t.get("family") or t.get("kind"), "crowd": bool(t.get("crowd")),
                        "family": t.get("family")})
    return out


def _cell_of(g: Grid, at) -> tuple[int, int] | None:
    x, y = int(at[0] / g.cell), int(at[1] / g.cell)
    if 0 <= x < g.W and 0 <= y < g.H:
        return y, x
    return None


def occupied_mask(g: Grid, things: list[dict]) -> np.ndarray:
    m = np.zeros(g.X.shape, bool)
    for t in things:
        w, d = max(t["w"], g.cell), max(t["d"], g.cell)
        m |= g.poly(corners(t["at"], w, d, t["turn"]))
        c = _cell_of(g, t["at"])
        if c:
            m[c] = True
    return m


# ------------------------------------------------------------------------------------------------ check 7
def check_dressing(place: dict, extra: list | None, rules: dict, sizes: dict | None = None,
                   interior_items: list | None = None, zz: dict | None = None) -> dict:
    sizes = sizes or {}
    zz = zz or zones(place, rules, sizes)
    g, Z, lot, blds = zz["grid"], zz["Z"], zz["lot"], zz["buildings"]
    things = things_of(place, extra, sizes, rules, interior_items)
    targets = rules.get("targets") or {}
    area_cell = g.cell * g.cell
    occ = occupied_mask(g, things)
    # fences, walls and hedges bound a yard but are not its dressing: they are not counted toward a density
    counted = [t for t in things if not is_structure(t, rules) and t.get("family") != "boundary"]
    zone_of = []
    for t in counted:
        c = _cell_of(g, t["at"])
        zone_of.append((int(Z[c]), int(lot[c])) if c else (Z_OUT, -1))
    # walls and buildings bound the emptiness of a yard; the road does not
    solid = occ | (Z == Z_BUILDING)
    zrows = []
    flags = []
    # every zone instance: (kind, lot)
    keys = sorted({(int(k), -1 if int(k) in (Z_KERB, Z_OPEN) else int(l))
                   for k, l in zip(Z.ravel(), lot.ravel()) if int(k) in ZONE_KEYS})
    for zk, li in keys:                        # the kerb and the open lot are one row a place; yards one a lot
        cells = (Z == zk) if li == -1 else ((Z == zk) & (lot == li))
        area = float(cells.sum()) * area_cell
        if area < float(rules.get("min_zone_m2", 6.0)):
            continue
        name = ZONE_KEYS[zk]
        kind_key = name
        if zk == Z_INTERIOR and 0 <= li < len(blds):
            kind_key = f"interior_{blds[li]['kind']}"
        prules = place_rules(rules, zz["place"])
        if prules.get("era") in ("war", "after", "ruin") and zk in (Z_FRONT, Z_BACK, Z_OPEN, Z_KERB):
            kind_key = "ruin"
        tgt = targets.get(kind_key) or targets.get(name) or {}
        n = sum(1 for (k, l) in zone_of if k == zk and (zk in (Z_KERB, Z_OPEN) or l == li))
        dens = n / (area / 100.0) if area else 0.0
        row = {"zone": ZONE_NAMES[zk], "rule": kind_key, "lot": blds[li]["id"] if 0 <= li < len(blds) else None,
               "area_m2": round(area, 1), "things": n, "per_100m2": round(dens, 2)}
        if zk == Z_KERB:
            length = area / float(rules.get("kerb_strip_m", 2.5))
            row["kerb_m"] = round(length, 1)
            row["m_between"] = round(length / n, 1) if n else None
            # the longest stretch of kerb with nothing on it, ignoring the strip's own edge
            dd = distance(occ, g.cell)
            gap = float((dd[cells]).max()) * 2.0 if cells.any() else 0.0
            gap = min(gap, length)             # nothing on it at all: the whole kerb is the empty stretch
            row["largest_empty_m"] = round(gap, 1)
            lo, hi = tgt.get("m_between", [6, 10])
            row["target"] = f"1 every {lo}–{hi} m, largest empty {tgt.get('largest_empty_m', 12)} m"
            ok = n > 0 and (length / n) <= float(hi) and gap <= float(tgt.get("largest_empty_m", 12)) + 0.01
        else:
            dd = distance(solid | ~cells, g.cell)
            gap = float(dd[cells].max()) * 2.0 if cells.any() else 0.0
            row["largest_empty_m"] = round(gap, 1)
            lo, hi = (tgt.get("per_100m2") or [0, 999])
            lim = tgt.get("largest_empty_m")
            row["target"] = f"{lo}–{hi} a 100 m²" + (f", largest empty {lim} m" if lim else "")
            ok = dens >= float(lo) and (lim is None or gap <= float(lim) + 0.01)
            if dens > float(hi) * 1.5:
                row["note"] = "denser than the target's top by half again — check it reads, not cluttered"
        row["ok"] = bool(ok)
        if not ok:
            # where: the centre of the emptiest spot
            dd2 = dd if zk == Z_KERB else distance(solid | ~cells, g.cell)
            masked = np.where(cells, dd2, -1)
            yy, xx = np.unravel_index(int(np.argmax(masked)), masked.shape)
            row["emptiest_at"] = [round(float(g.X[yy, xx]), 1), round(float(g.Y[yy, xx]), 1)]
            flags.append({"zone": row["zone"], "lot": row["lot"], "at": row["emptiest_at"],
                          "why": f"{row['things']} things, {row['per_100m2']} a 100 m² (target {row['target']}); "
                                 f"largest empty {row['largest_empty_m']} m"})
        zrows.append(row)
    # porches: things within reach of each home's front point
    pr = float(rules.get("porch_reach_m", 3.0))
    tp = targets.get("porch") or {"each": [2, 4]}
    for b in blds:
        if b["kind"] != "home":
            continue
        if b["id"] in (place_rules(rules, zz["place"]).get("exclude_lots") or []):
            continue
        fp = b["front"]
        if not fp and b.get("facing"):
            cx, cy = b["centre"]
            fx, fy = b["facing"]
            half = max(abs((px - cx) * fx + (py - cy) * fy) for px, py in b["pts"])
            fp = (cx + fx * (half + 1.0), cy + fy * (half + 1.0))
        if not fp:
            cx, cy = b["centre"]
            c_road = np.argwhere(zz["road"])
            if not len(c_road):
                continue
            # the front face's middle, toward the road
            ry, rx = min(((int(a), int(c)) for a, c in c_road), key=lambda p: (g.X[p] - cx) ** 2 + (g.Y[p] - cy) ** 2)
            vx, vy = g.X[ry, rx] - cx, g.Y[ry, rx] - cy
            n = math.hypot(vx, vy) or 1.0
            half = max(abs((px - cx) * vx / n + (py - cy) * vy / n) for px, py in b["pts"])
            fp = (cx + vx / n * (half + 1.0), cy + vy / n * (half + 1.0))
        k = sum(1 for t in things if math.hypot(t["at"][0] - fp[0], t["at"][1] - fp[1]) <= pr)
        row = {"zone": "porch / step", "rule": "porch", "lot": b["id"], "things": k, "at": [round(fp[0], 1), round(fp[1], 1)],
               "target": f"{tp['each'][0]}–{tp['each'][1]} a porch", "ok": k >= int(tp["each"][0])}
        zrows.append(row)
        if not row["ok"]:
            flags.append({"zone": "porch / step", "lot": b["id"], "at": row["at"], "why": f"{k} things at the porch "
                          f"(target {row['target']})"})
    area_plan = float(place["size"][0]) * float(place["size"][1]) if place.get("size") else 0.0
    measured = [r for r in zrows if r.get("area_m2")]
    ok_n = sum(1 for r in zrows if r["ok"])
    placed = [t for t in things if t["src"] != "look"]       # the look's small things indoors are not BUILD 97's count
    line = (f"Dressing: {ok_n} of {len(zrows)} zones meet their targets; {len(placed)} placed things, "
            f"{len(placed) / (area_plan / 100.0):.2f} a 100 m² of the whole plan (BUILD 97's measure)." if area_plan else
            "Dressing: the plan has no size.")
    return {"id": "dressing", "ok": (ok_n == len(zrows)) if zrows else None, "line": line, "zones": zrows, "flags": flags,
            "things": len(placed), "plan_m2": area_plan,
            "plan_per_100m2": round(len(placed) / (area_plan / 100.0), 2) if area_plan else None,
            "by_source": {s: sum(1 for t in things if t["src"] == s) for s in ("plan", "dresser", "look")},
            "measured_m2": round(sum(r["area_m2"] for r in measured), 1)}


# ------------------------------------------------------------------------------------------------ check 6
def is_structure(t: dict, rules: dict) -> bool:
    words = " ".join(str(t.get(k) or "") for k in ("model", "id", "label", "family")).lower()
    return any(k in words for k in (rules.get("repeats") or {}).get("structure_words", []))


def camera_view(stage_json: Path | None, rules: dict) -> tuple[float, float]:
    """The map camera's footprint on the ground (width, depth in metres) from the game's stage camera, as StageModel.reach
    works it out; the rules' fallback when there is none."""
    fb = (rules.get("repeats") or {}).get("view_m") or [20.0, 21.0]
    try:
        cam = json.loads(Path(stage_json).read_text(encoding="utf-8"))["camera"]
        p, fov, dist = math.radians(float(cam["pitch"])), math.radians(float(cam["fov"])), float(cam["dist"])
        aspect = 16.0 / 9.0
        h, back = dist * math.sin(p), dist * math.cos(p)
        far_a = max(math.radians(2.0), p - fov / 2)
        near_a = min(math.radians(89.0), p + fov / 2)
        north = h / math.tan(far_a) - back
        south = back - h / math.tan(near_a)
        half_w = dist * math.tan(math.atan(math.tan(fov / 2) * aspect))
        return round(2 * half_w, 1), round(north + south, 1)
    except Exception:  # noqa: BLE001 — no stage file: the fallback
        return float(fb[0]), float(fb[1])


def check_repeats(place: dict, extra: list | None, rules: dict, sizes: dict | None = None,
                  view: tuple[float, float] | None = None, things: list | None = None) -> dict:
    sizes = sizes or {}
    rr = rules.get("repeats") or {}
    limit = int(rr.get("per_view", 2))
    view = view or tuple(rr.get("view_m") or (20.0, 21.0))
    things = things if things is not None else things_of(place, extra, sizes, rules)
    dress = [t for t in things if not is_structure(t, rules) and not t["crowd"] and t["src"] != "look"]
    size = place.get("size") or [40, 30]
    step = float(rr.get("step_m", 4.0))
    vw, vd = min(view[0], float(size[0])), min(view[1], float(size[1]))
    worst: dict = {}
    x = 0.0
    while x <= max(0.0, float(size[0]) - vw) + 1e-6:
        y = 0.0
        while y <= max(0.0, float(size[1]) - vd) + 1e-6:
            counts: dict = {}
            for t in dress:
                if x <= t["at"][0] < x + vw and y <= t["at"][1] < y + vd:
                    counts.setdefault(t["model"], []).append(t["id"])
            for m, ids in counts.items():
                if len(ids) > limit and len(ids) > len(worst.get(m, {}).get("ids", [])):
                    worst[m] = {"model": m, "ids": ids, "view_at": [round(x, 1), round(y, 1)], "n": len(ids)}
            y += step
        x += step
    flags = [{"why": f"{w['model']} ×{w['n']} in one camera view (limit {limit})", "model": w["model"], "ids": w["ids"],
              "view": w["view_at"] + [vw, vd]} for w in worst.values()]
    # side by side at the same turn and size
    near = float(rr.get("side_by_side_m", 1.5))
    turn_tol = float(rr.get("same_turn_deg", 10.0))
    for i, a in enumerate(dress):
        for b in dress[i + 1:]:
            if a["model"] != b["model"]:
                continue
            d = math.hypot(a["at"][0] - b["at"][0], a["at"][1] - b["at"][1])
            dt = abs((a["turn"] - b["turn"] + 180) % 360 - 180)
            if d <= near * max(a["w"], a["d"], 0.5) and dt <= turn_tol and abs(a["w"] - b["w"]) < 0.05:
                flags.append({"why": f"{a['model']} twice side by side at the same turn and size", "model": a["model"],
                              "ids": [a["id"], b["id"]], "at": [round((a["at"][0] + b["at"][0]) / 2, 1),
                                                             round((a["at"][1] + b["at"][1]) / 2, 1)]})
    return {"id": "repeats", "ok": not flags, "view_m": [vw, vd], "limit": limit,
            "line": (f"Repeats: no dressing model more than {limit}× in any map-camera view ({vw:g} × {vd:g} m) and none "
                     "side by side." if not flags else f"Repeats: {len(flags)} flagged in map-camera views of "
                     f"{vw:g} × {vd:g} m."), "flags": flags,
            "structure_kits_not_counted": sorted({t["model"] for t in things if is_structure(t, rules)})}


# ------------------------------------------------------------------------------------------------ one place, the board
def read_place(places_dir: Path, pid: str) -> tuple[dict, list, list]:
    place = json.loads((places_dir / f"{pid}.place.json").read_text(encoding="utf-8"))
    extra: list = []
    out = places_dir / f"{pid}.dressing_out.json"
    if out.exists():
        d = json.loads(out.read_text(encoding="utf-8"))
        extra = d.get("items") if isinstance(d, dict) else d
    look = []
    if isinstance(place.get("dressing"), str) and (places_dir / place["dressing"]).exists():
        try:
            look = json.loads((places_dir / place["dressing"]).read_text(encoding="utf-8")).get("items") or []
        except (OSError, ValueError):
            look = []
    return place, extra or [], look


def check_place(places_dir: Path, pid: str, rules: dict, sizes: dict, view, out_dir: Path | None = None,
                picture: bool = True) -> dict:
    place, extra, look = read_place(places_dir, pid)
    zz = zones(place, rules, sizes)
    dres = check_dressing(place, extra, rules, sizes, look, zz)
    rep = check_repeats(place, extra, rules, sizes, view)
    res = {"place": pid, "at": datetime.now().isoformat(timespec="seconds"), "size": place.get("size"),
           "checks": [rep, dres]}
    if out_dir:
        d = Path(out_dir) / pid
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "dressing_check.json.part"
        tmp.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, d / "dressing_check.json")
        if picture:
            try:
                res["picture"] = str(draw_zones(place, zz, things_of(place, extra, sizes, rules, look), dres, rep,
                                                d / "zones.png"))
            except ImportError:
                pass
    return res


def board(places_dir: Path, rules: dict, sizes: dict, view, out_dir: Path | None = None, only: list | None = None,
          picture: bool = True) -> dict:
    rows = []
    for f in sorted(Path(places_dir).glob("*.place.json")):
        pid = f.name[: -len(".place.json")]
        if only and pid not in only:
            continue
        if place_rules(rules, pid).get("skip"):
            rows.append({"place": pid, "skipped": place_rules(rules, pid).get("_why") or "skipped by the rules"})
            continue
        try:
            r = check_place(Path(places_dir), pid, rules, sizes, view, out_dir, picture)
        except Exception as ex:  # noqa: BLE001 — one bad plan is a row, not a crash
            rows.append({"place": pid, "error": f"{type(ex).__name__}: {ex}"})
            continue
        rep, dres = r["checks"]
        zr = [z for z in dres["zones"] if z.get("area_m2")]
        rows.append({"place": pid, "size": r["size"], "things": dres["things"], "plan_per_100m2": dres["plan_per_100m2"],
                     "zones_ok": sum(1 for z in dres["zones"] if z["ok"]), "zones": len(dres["zones"]),
                     "worst_zone": min(zr, key=lambda z: z["per_100m2"], default=None),
                     "largest_empty_m": max((z["largest_empty_m"] for z in zr), default=None),
                     "repeats": len(rep["flags"]), "by_source": dres["by_source"],
                     "dressing_ok": dres["ok"], "repeats_ok": rep["ok"]})
    res = {"at": datetime.now().isoformat(timespec="seconds"), "view_m": list(view), "rows": rows}
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "board.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
        (Path(out_dir) / "board.md").write_text(board_md(res, rules), encoding="utf-8")
    return res


def board_md(res: dict, rules: dict | None = None) -> str:
    before = (rules or {}).get("before_counts") or {}
    out = [f"# The areas board — dressing and repeats ({res['at']})", "",
           f"Map-camera view: {res['view_m'][0]:g} × {res['view_m'][1]:g} m. Targets: `area_rules.json`. "
           "Plan density is BUILD 97's measure (things per 100 m² of the whole plan).", "",
           "| Place | Size m | Things | Plan /100 m² | before this build | Zones meeting target | Thinnest zone | Largest empty m | Repeats |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        if r.get("skipped"):
            out.append(f"| {r['place']} | — | — | — | — | not an area to dress: {r['skipped']} | | | |")
            continue
        if r.get("error"):
            out.append(f"| {r['place']} | — | — | — | — | could not be read: {r['error']} | | | |")
            continue
        wz = r.get("worst_zone")
        wzs = f"{wz['zone']}{' (' + str(wz['lot']) + ')' if wz.get('lot') else ''} {wz['per_100m2']}" if wz else "—"
        b = before.get(r["place"])
        out.append(f"| {r['place']} | {r['size'][0]:g} × {r['size'][1]:g} | {r['things']} | {r['plan_per_100m2']} | "
                   f"{b if b is not None else '—'} | {r['zones_ok']} of {r['zones']} | {wzs} | {r['largest_empty_m']} | "
                   f"{r['repeats']} |")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------------ the picture
def draw_zones(place: dict, zz: dict, things: list, dres: dict, rep: dict, dest: Path, px: float = 12.0) -> Path:
    from PIL import Image, ImageDraw
    g, Z = zz["grid"], zz["Z"]
    rgb = np.zeros((g.H, g.W, 3), np.uint8)
    for k, c in ZONE_COLOURS.items():
        rgb[Z == k] = c
    im = Image.fromarray(rgb, "RGB").resize((int(g.W * g.cell * px), int(g.H * g.cell * px)), Image.NEAREST)
    pad = 26
    canvas = Image.new("RGB", (im.width, im.height + pad + 60), (20, 20, 24))
    canvas.paste(im, (0, pad))
    dr = ImageDraw.Draw(canvas)

    def P(x, y):
        return (x * px, y * px + pad)
    for t in things:
        pts = [P(*q) for q in corners(t["at"], max(t["w"], 0.3), max(t["d"], 0.3), t["turn"])]
        colour = (250, 210, 90) if t["src"] == "dresser" else (230, 230, 230) if t["src"] == "plan" else (200, 160, 220)
        dr.polygon(pts, outline=colour)
    for f in dres.get("flags") or []:
        x, y = P(*f["at"])
        dr.ellipse([x - 22, y - 22, x + 22, y + 22], outline=(255, 70, 70), width=3)
    for f in rep.get("flags") or []:
        if f.get("at"):
            x, y = P(*f["at"])
            dr.ellipse([x - 16, y - 16, x + 16, y + 16], outline=(255, 140, 40), width=3)
        elif f.get("view"):
            vx, vy, vw, vd = f["view"]
            dr.rectangle([P(vx, vy), P(vx + vw, vy + vd)], outline=(255, 140, 40), width=2)
    size = place.get("size") or [0, 0]
    dr.rectangle([0, 0, canvas.width, pad], fill=(20, 20, 24))
    dr.text((8, 7), f"{place.get('id', '')} · {size[0]} × {size[1]} m · greybox — stand-in art (the plan from above: "
                    f"zones and flags)", fill=(255, 200, 120))
    y0 = im.height + pad + 6
    x0 = 8
    for k in (Z_KERB, Z_FRONT, Z_BACK, Z_SHOP, Z_OPEN, Z_INTERIOR, Z_EXCLUDED, Z_ROAD):
        dr.rectangle([x0, y0, x0 + 12, y0 + 12], fill=ZONE_COLOURS[k])
        dr.text((x0 + 16, y0), ZONE_NAMES[k], fill=(230, 230, 230))
        x0 += 16 + 7 * len(ZONE_NAMES[k]) + 14
        if x0 > canvas.width - 160:
            x0, y0 = 8, y0 + 18
    dr.text((8, canvas.height - 18), "white: the plan's things · yellow: the dresser's · red circle: a thin zone · "
            "orange: a repeat", fill=(200, 200, 200))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp.png")
    canvas.save(tmp)
    os.replace(tmp, dest)
    return dest


# ------------------------------------------------------------------------------------------------ by hand
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--places", required=True)
    ap.add_argument("--rules-game", default="")
    ap.add_argument("--wanted", default="")
    ap.add_argument("--stage", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--no-picture", action="store_true")
    ap.add_argument("place", nargs="*")
    a = ap.parse_args(argv)
    rules = load_rules(Path(a.rules_game) if a.rules_game else None)
    sizes = load_sizes(Path(a.wanted) if a.wanted else None)
    view = camera_view(Path(a.stage) if a.stage else None, rules)
    res = board(Path(a.places), rules, sizes, view, Path(a.out) if a.out else None, a.place or None, not a.no_picture)
    print(board_md(res, rules))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
