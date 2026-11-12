"""The generator: a town sheet + an archetype + an era + a seed → a plan (and its interiors and levels).

Macro (districts): the footprint, the arteries first, then districts — by the archetype's layout rule.
Meso (lots and buildings): the sheet's required buildings first, then the archetype's signature, the upgrade places,
then filler. Doors face streets; every door is joined to the street by a path; nothing blocks an artery.
Micro (interiors): each door opens into a kit room (kits.py), ruined or underground as the archetype says.
Texture last: WFC filler on the empty ground (wfc.py), never on a path.

The same sheet, archetype, era and seed always give the same plan. A plan that fails its checks is tried again with
the next attempt number (still deterministic); the plan records which attempt passed.
"""
from __future__ import annotations
import math

from . import archetypes, kits, tiles as T, wfc
from .grid import Grid, Rect, rng_for
from .plan import Plan

SIZES = {"hamlet": (56, 36), "town": (80, 52), "city": (100, 64)}   # tiles (William 2026-11-12: "slightly larger")
STREET = frozenset({T.ROAD, T.PATH, T.FLOOR, T.BRIDGE, T.GLASS})
BUILDABLE = frozenset({T.GROUND})
NO_DOOR = {"shanty", "tent", "silo", "tower", "booth", "lookout", "ruin", "memorial"}


class Ctx:
    def __init__(self, sheet: dict, aid: str, era: str, seed: int, attempt: int, pid: str, size=None):
        self.sheet, self.aid, self.era, self.seed, self.attempt = sheet, aid, era, seed, attempt
        self.a = archetypes.get(aid)
        self.after = era == "after"
        self.rng = rng_for(sheet.get("id", ""), aid, era, seed, attempt, pid)
        W, H = size or SIZES.get(str(sheet.get("size") or "town"), SIZES["town"])
        self.g = Grid(W, H, T.GROUND)
        self.g.border_wall()
        self.plan = Plan(id=pid, kind="town", grid=self.g, archetype=aid, era=era, seed=seed, attempt=attempt,
                         name=str(sheet.get("name") or sheet.get("id") or pid))
        self.districts: list[dict] = []
        self.occupied: set = set()
        self.clear: set = set()          # cells that must stay walkable (fronts, paths, gates, the story element)
        self.entrances: list = []        # (border cell, inward cell, door id)
        self.story_rect: Rect | None = None
        self.story_what = ""
        self.face = None                 # a point doors prefer to face
        self.bseq = 0
        self.levels: list = []           # other plans of the same place (a level below)

    # ---------- drawing
    def interior(self, x, y) -> bool:
        return 0 < x < self.g.w - 1 and 0 < y < self.g.h - 1

    def road(self, x0, y0, x1, y1, w=2, t=T.ROAD):
        """An L-shaped street of width w; never paints the map's border."""
        sx = 1 if x1 >= x0 else -1
        for x in range(x0, x1 + sx, sx):
            for k in range(w):
                if self.interior(x, y0 + k):
                    self.g.set(x, y0 + k, t)
        sy = 1 if y1 >= y0 else -1
        for y in range(y0, y1 + sy, sy):
            for k in range(w):
                if self.interior(x1 + k, y):
                    self.g.set(x1 + k, y, t)

    def thick(self, a, b, w=2, t=T.ROAD, only=None):
        (x0, y0), (x1, y1) = a, b
        n = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(n + 1):
            x = round(x0 + (x1 - x0) * i / n)
            y = round(y0 + (y1 - y0) * i / n)
            for dx in range(w):
                for dy in range(w):
                    xx, yy = x + dx - w // 2, y + dy - w // 2
                    if self.interior(xx, yy) and (only is None or self.g.get(xx, yy) in only):
                        self.g.set(xx, yy, t)

    def gate(self, x, y, did=None):
        """An entrance: a gap in the map's border at (x, y), facing in."""
        g = self.g
        g.set(x, y, T.DOOR)
        ix = x + (1 if x == 0 else -1 if x == g.w - 1 else 0)
        iy = y + (1 if y == 0 else -1 if y == g.h - 1 else 0)
        if g.get(ix, iy) in T.BLOCKING:
            g.set(ix, iy, T.PATH)
        did = did or ("out" if not self.entrances else f"out_{len(self.entrances) + 1}")
        self.entrances.append(((x, y), (ix, iy), did))
        self.clear |= {(x, y), (ix, iy)}

    def district(self, rect: Rect, role: str, name: str = "", on=BUILDABLE, dress=None) -> dict:
        d = {"id": f"d{len(self.districts) + 1}", "role": role, "name": name or role, "rect": rect,
             "on": frozenset(on), "dress": dress}
        self.districts.append(d)
        return d

    def bsp(self, r: Rect, min_w=14, min_h=9, depth=3, alley=T.PATH) -> list[Rect]:
        """Split a block into lots with alleys between them (the alleys reach the block's edge)."""
        if depth == 0 or (r.w < 2 * min_w + 1 and r.h < 2 * min_h + 1):
            return [r]
        horiz = r.h >= 2 * min_h + 1 and (r.w < 2 * min_w + 1 or self.rng.random() < r.h / (r.w + r.h))
        if horiz:
            cut = self.rng.randint(r.y + min_h, r.y2 - min_h - 1)
            for x in range(r.x, r.x2):
                if self.g.get(x, cut) == T.GROUND:
                    self.g.set(x, cut, alley)
            return (self.bsp(Rect(r.x, r.y, r.w, cut - r.y), min_w, min_h, depth - 1, alley)
                    + self.bsp(Rect(r.x, cut + 1, r.w, r.y2 - cut - 1), min_w, min_h, depth - 1, alley))
        cut = self.rng.randint(r.x + min_w, r.x2 - min_w - 1)
        for y in range(r.y, r.y2):
            if self.g.get(cut, y) == T.GROUND:
                self.g.set(cut, y, alley)
        return (self.bsp(Rect(r.x, r.y, cut - r.x, r.h), min_w, min_h, depth - 1, alley)
                + self.bsp(Rect(cut + 1, r.y, r.x2 - cut - 1, r.h), min_w, min_h, depth - 1, alley))

    def story(self, x, y, what=None, w=2, h=2):
        r = Rect(max(1, min(x, self.g.w - 1 - w)), max(1, min(y, self.g.h - 1 - h)), w, h)
        self.story_rect = r
        self.story_what = what or self.a["story"][self.era]
        for c in r.cells():
            if self.g.get(*c) in T.BLOCKING or self.g.get(*c) == T.GROUND:
                self.g.set(*c, T.FLOOR)
            self.clear.add(c)
            self.occupied.add(c)

    # ---------- buildings
    def _street_dist(self):
        """Distance from every cell to the nearest street cell, through ground (not through buildings). Cached until
        the next building or path is put down (a failed placement changes nothing)."""
        if getattr(self, "_dist_ver", None) == self.bseq and getattr(self, "_dist", None) is not None:
            return self._dist
        from collections import deque
        g = self.g
        W, H = g.w, g.h
        INF = 10 ** 6
        occ = self.occupied
        dist = [[INF] * W for _ in range(H)]
        q = deque()
        cells = g.c
        for y in range(H):
            row = cells[y]
            for x in range(W):
                if row[x] in STREET and (x, y) not in occ:
                    dist[y][x] = 0
                    q.append((x, y))
        open_ = (T.GROUND, T.FIELD, T.RUBBLE)
        while q:
            x, y = q.popleft()
            d1 = dist[y][x] + 1
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 < nx < W - 1 and 0 < ny < H - 1 and dist[ny][nx] == INF and cells[ny][nx] in open_ \
                        and (nx, ny) not in occ:
                    dist[ny][nx] = d1
                    q.append((nx, ny))
        self._dist, self._dist_ver = dist, self.bseq
        return dist

    def _fits(self, r: Rect, on) -> bool:
        g = self.g
        if r.x < 1 or r.y < 1 or r.x2 > g.w - 1 or r.y2 > g.h - 1:
            return False
        occ, clear, cells = self.occupied, self.clear, g.c
        for y in range(r.y, r.y2):
            row = cells[y]
            for x in range(r.x, r.x2):
                if row[x] not in on or (x, y) in occ or (x, y) in clear:
                    return False
        for c in r.grow(1).border():
            if c in occ:
                return False
        return True

    def _doors(self, r: Rect):
        """(door cell, outside cell, side) for every non-corner border cell."""
        for x in range(r.x + 1, r.x2 - 1):
            yield (x, r.y2 - 1), (x, r.y2), "S"
            yield (x, r.y), (x, r.y - 1), "N"
        for y in range(r.y + 1, r.y2 - 1):
            yield (r.x, y), (r.x - 1, y), "W"
            yield (r.x2 - 1, y), (r.x2, y), "E"

    def place(self, kind: str, district: dict | None = None, label=None, upgrades=None, required=True,
              size=None, near=None, face=None, tries=500) -> dict | None:
        spec = archetypes.KINDS[kind]
        rng = self.rng
        mnw, mnh, mxw, mxh = spec["size"]
        w, h = size or (rng.randint(mnw, mxw), rng.randint(mnh, mxh))
        if not size and rng.random() < 0.5 and w != h:
            w, h = h, w                       # turned a quarter: the same building facing another street
        areas = [district] if district else list(self.districts)
        cands = []
        for d in areas:
            R = d["rect"]
            for y in range(R.y, R.y2 - h + 1):
                for x in range(R.x, R.x2 - w + 1):
                    cands.append((x, y, d))
        rng.shuffle(cands)
        needs_door = kind not in NO_DOOR
        dist = self._street_dist() if needs_door else None
        face = face or self.face
        best = None
        seen = 0
        for x, y, d in cands:
            r = Rect(x, y, w, h)
            if not self._fits(r, d["on"]):
                continue
            seen += 1
            if not needs_door:
                score = 0 if near is None else abs(r.cx - near[0]) + abs(r.cy - near[1])
                if best is None or score < best[0]:
                    best = (score, r, None, None, d)
                if near is None or seen > 40:
                    break
                continue
            for door, out, side in self._doors(r):
                ox, oy = out
                if not self.interior(ox, oy):
                    continue
                dd = dist[oy][ox]
                if dd >= 10 ** 6 or dd > 8:
                    continue
                score = dd * 4
                if face is not None:
                    vx, vy = face[0] - r.cx, face[1] - r.cy
                    nx, ny = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}[side]
                    score += 0 if vx * nx + vy * ny > 0 else 10
                if near is not None:
                    score += (abs(r.cx - near[0]) + abs(r.cy - near[1])) // 2
                if best is None or score < best[0]:
                    best = (score, r, door, out, d)
            if best and best[0] == 0 and near is None and face is None:
                break
            if seen >= tries:
                break
        if best is None:
            if required:
                self.plan.problems.append(f"couldn't place the {label or kind} ({kind}) in "
                                          f"{(district or {}).get('name', 'any district')}")
            return None
        _, r, door, out, d = best
        self.bseq += 1
        bid = f"{kind}_{self.bseq}"
        g = self.g
        if kind in ("ruin",):
            g.outline(r, T.WALL)
            g.fill(Rect(r.x + 1, r.y + 1, r.w - 2, r.h - 2), T.RUBBLE)
            g.set(r.cx, r.y2 - 1, T.RUBBLE)
            g.set(r.x, r.cy, T.RUBBLE)
        elif kind == "stall":
            g.fill(r, T.FURNITURE)
        else:
            g.fill(r, T.ROOF)
            if r.w >= 3 and r.h >= 3:
                g.outline(r, T.WALL)
        for c in r.cells():
            self.occupied.add(c)
        b = {"id": bid, "kind": kind, "label": label if label is not None else spec["label"],
             "rect": r.as_list(), "district": d["id"], "required": required, "interior": spec["interior"],
             "upgrades": list(upgrades or spec.get("upgrade") or [])}
        if door:
            ox, oy = out
            if kind != "stall":
                g.set(*door, T.DOOR)
            b["door"] = list(door)
            b["front"] = [ox, oy]
            self._carve_to_street(out)
            self.clear.add(out)
        self.plan.buildings.append(b)
        return b

    def _carve_to_street(self, start):
        self._dist = None                 # a new path changes the distances
        g = self.g
        if g.get(*start) in STREET:
            return
        p = g.path(start, lambda x, y: g.get(x, y) in STREET and (x, y) not in self.occupied,
                   lambda x, y: self.interior(x, y) and (x, y) not in self.occupied
                   and g.get(x, y) in (T.GROUND, T.FIELD, T.RUBBLE))
        for c in (p or [start])[:-1] if p else [start]:
            if g.get(*c) in (T.GROUND, T.FIELD):
                g.set(*c, T.PATH)
            self.clear.add(c)


# =================================================================== the layout rules (macro)
def _quadrants(c: Ctx, cx, cy, roles, on=BUILDABLE):
    W, H = c.g.w, c.g.h
    rects = [Rect(1, 1, cx - 1, cy - 1), Rect(cx + 2, 1, W - cx - 3, cy - 1),
             Rect(1, cy + 3, cx - 1, H - cy - 4), Rect(cx + 2, cy + 3, W - cx - 3, H - cy - 4)]
    out = []
    for i, r in enumerate(rects):
        if r.w > 4 and r.h > 3:
            out.append(c.district(r, roles[i % len(roles)], on=on))
    return out


def rule_grid(c: Ctx, box: Rect | None = None, roles=None, gates=True):
    """Main street across, a cross street, blocks split into lots."""
    g = c.g
    box = box or Rect(1, 1, g.w - 2, g.h - 2)
    roles = roles or c.a["roles"]
    my = box.y + box.h // 2 - 1 + c.rng.randint(-2, 2)
    cx = box.x + box.w // 2 - 1 + c.rng.randint(-4, 4)
    c.road(box.x, my, box.x2 - 1, my, w=3)
    c.road(cx, box.y, cx, box.y2 - 1, w=2)
    if gates:
        c.gate(0, my + 1)
        c.gate(g.w - 1, my + 1)
    blocks = [Rect(box.x, box.y, cx - box.x, my - box.y), Rect(cx + 2, box.y, box.x2 - cx - 2, my - box.y),
              Rect(box.x, my + 3, cx - box.x, box.y2 - my - 3), Rect(cx + 2, my + 3, box.x2 - cx - 2, box.y2 - my - 3)]
    i = 0
    for b in blocks:
        if b.w < 6 or b.h < 5:
            continue
        for lot in c.bsp(b, 13, 8, 2):
            if lot.w >= 5 and lot.h >= 4:
                c.district(lot, roles[i % len(roles)])
                i += 1
    return my, cx


def rule_rings(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    cx, cy = W // 2, H // 2
    sq = Rect(cx - 7, cy - 5, 14, 10)
    rings = [sq.grow(2), sq.grow(8)] if c.after else [sq.grow(2)]
    g.fill(sq, T.FLOOR)
    for r in rings:
        for x, y in r.border():
            if c.interior(x, y):
                g.set(x, y, T.ROAD)
        for x, y in r.grow(-1).border():
            if c.interior(x, y) and g.get(x, y) == T.GROUND:
                g.set(x, y, T.ROAD)
    # four street mouths
    for (a, b) in (((cx, 1), (cx, sq.y)), ((cx, sq.y2), (cx, H - 2)), ((1, cy), (sq.x, cy)), ((sq.x2, cy), (W - 2, cy))):
        c.road(a[0], a[1], b[0], b[1], w=2) if a[0] == b[0] else c.road(a[0], a[1], b[0], b[1], w=2)
    c.gate(cx, H - 1)
    c.gate(0, cy)
    if c.after:
        c.gate(W - 1, cy, "out_east")
    # checkpoints: a barrier across every street mouth where it meets a ring, one cell left open
    marks = 0
    for r in rings:
        for (x, y, horiz) in ((cx, r.y, True), (cx, r.y2 - 1, True), (r.x, cy, False), (r.x2 - 1, cy, False)):
            if not c.after and marks:
                break
            if horiz:
                for k in (-2, 2):
                    if g.get(x + k, y) in (T.ROAD, T.GROUND):
                        g.set(x + k, y, T.FENCE)
            else:
                for k in (-2, 2):
                    if g.get(x, y + k) in (T.ROAD, T.GROUND):
                        g.set(x, y + k, T.FENCE)
            c.plan.ent("label", text="CHECKPOINT", x=x, y=y)
            c.plan.ent("npc", id=f"guard_{marks + 1}", role="checkpoint guard", x=x + (1 if horiz else 0), y=y + (0 if horiz else 1))
            c.clear.add((x, y))
            marks += 1
    _quadrants(c, cx, cy, c.a["roles"][1:])
    c.district(sq, "square", on=frozenset({T.FLOOR}))
    if c.after:
        # the "recycling" yard at the edge everyone pretends not to see
        yd = Rect(W - 13, 2, 10, 6)
        if all(g.get(x, y) == T.GROUND for x, y in yd.cells()):
            g.outline(yd, T.FENCE)
            g.fill(Rect(yd.x + 1, yd.y + 1, yd.w - 2, yd.h - 2), T.RUBBLE)
            g.set(yd.cx, yd.y2 - 1, T.PATH)
            c._carve_to_street((yd.cx, yd.y2))
            for cc in yd.cells():
                c.occupied.add(cc)
            c.plan.ent("label", text="RECYCLING", x=yd.x + 1, y=yd.y + 1)
            c.plan.notes.append("the 'recycling' yard sits at the north-east edge, fenced, one gate")
        c.plan.ent("label", text="CRANE", x=sq.x + 1, y=sq.y + 1)
        c.story(cx - 1, rings[0].y + 1, w=2, h=1)      # the scanner arch, at the inner ring's north mouth
    else:
        c.story(cx - 1, rings[0].y2 - 2, w=2, h=1)     # until the clubhouse is placed (then: at its door)
        c._story_after = ("clubhouse", "front")
    c.face = (cx, cy)


def rule_radial(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    cx, cy = W // 2, H // 2
    cat = archetypes.KINDS["cathedral"]["size"]
    cr = Rect(cx - cat[0] // 2, cy - cat[1] // 2, cat[0], cat[1])
    plaza = cr.grow(3)
    g.fill(plaza, T.FLOOR)
    n = 6 if c.after else 4
    ends = []
    for i in range(n):
        ang = 2 * math.pi * i / n + c.rng.uniform(-0.2, 0.2)
        ex = int(cx + math.cos(ang) * W)
        ey = int(cy + math.sin(ang) * H)
        ex, ey = max(0, min(W - 1, ex)), max(0, min(H - 1, ey))
        ends.append((ex, ey))
        c.thick((cx, cy), (ex, ey), 2, T.ROAD, only={T.GROUND})
    bx, by = ends[1]
    gx = 0 if bx <= 0 else W - 1 if bx >= W - 1 else bx
    gy = 0 if by <= 0 else H - 1 if by >= H - 1 else by
    if gx in (0, W - 1):
        gy = max(1, min(H - 2, gy))
    else:
        gx = max(1, min(W - 2, gx))
    c.gate(gx, gy)
    g.fill(plaza, T.FLOOR)
    plaza_d = c.district(cr, "altar", on=frozenset({T.FLOOR}))
    b = c.place("cathedral", plaza_d, label="THE CATHEDRAL" if c.after else "THE CHURCH", size=(cr.w, cr.h))
    _quadrants(c, cx, cy, c.a["roles"][1:])
    if b and b.get("front"):
        fx, fy = b["front"]
        c.story(fx - 1, fy + (1 if fy >= cy else -2))
    else:
        c.story(cx - 1, plaza.y2 - 2)
    c.face = (cx, cy)
    c.plan.notes.append(f"{n} streets, every one pointing at the altar")


def rule_queues(c: Ctx):
    my, cx = rule_grid(c)
    g = c.g
    ch = archetypes.KINDS["counting_house"]["size"]
    # the counting house faces the main street; the queue lanes run up to its door
    hx, hy = cx - ch[0] - 1, my - ch[1] - 6
    hall = Rect(max(2, hx), max(2, hy), ch[0], ch[1])
    lanes = Rect(hall.x, hall.y2, hall.w, my - hall.y2)
    g.fill(lanes, T.FLOOR, only={T.GROUND, T.PATH})
    d = c.district(hall, "counting", on=frozenset({T.GROUND, T.PATH, T.FLOOR}))
    g.fill(hall, T.GROUND, only={T.PATH, T.FLOOR})
    b = c.place("counting_house", d, size=(hall.w, hall.h), face=(cx, my))
    if b:
        for x in range(lanes.x + 1, lanes.x2 - 1, 2):
            for y in range(lanes.y + 1, lanes.y2 - 1):
                if g.get(x, y) == T.FLOOR and (x, y) not in c.clear and x != b.get("front", [0])[0]:
                    g.set(x, y, T.FENCE)
        c.plan.notes.append("queue lanes of rope run from the main street to the counting house door")
        fx, fy = b.get("front", [cx, my - 1])
        c.story(fx - 1, min(fy + 1, my - 2), w=2, h=1)
    else:
        c.story(cx - 1, my - 2, w=2, h=1)


def rule_walls(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    streets = list(range(5, H - 4, 8))
    for y in streets:
        c.road(1, y, W - 2, y, w=2)
    c.road(3, 1, 3, H - 2, w=2)
    c.road(W - 5, 1, W - 5, H - 2, w=2)
    c.gate(0, streets[len(streets) // 2])
    mz = Rect(W // 2 - 9, streets[1] + 2, 18, max(6, streets[2] - streets[1] - 2) if len(streets) > 2 else 10)
    # the memorial maze: a recursive backtracker on a coarse grid, walls between
    g.fill(mz, T.WALL)
    cw, chh = (mz.w - 1) // 2, (mz.h - 1) // 2
    stack = [(0, 0)]
    seen = {(0, 0)}
    g.set(mz.x + 1, mz.y + 1, T.PATH)
    while stack:
        x, y = stack[-1]
        nbrs = [(x + dx, y + dy, dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if 0 <= x + dx < cw and 0 <= y + dy < chh and (x + dx, y + dy) not in seen]
        if not nbrs:
            stack.pop()
            continue
        nx, ny, dx, dy = c.rng.choice(nbrs)
        g.set(mz.x + 1 + 2 * x + dx, mz.y + 1 + 2 * y + dy, T.PATH)
        g.set(mz.x + 1 + 2 * nx, mz.y + 1 + 2 * ny, T.PATH)
        seen.add((nx, ny))
        stack.append((nx, ny))
    g.set(mz.x + 1, mz.y, T.PATH)        # the way in, from the street above
    ex = mz.x + 1 + 2 * (cw - 1)          # the way out, below the last column
    y = mz.y2 - 1
    while y > mz.y and g.get(ex, y) != T.PATH:
        g.set(ex, y, T.PATH)
        y -= 1
    for cc in mz.cells():
        c.occupied.add(cc)
    c.story(mz.x + 1, mz.y - 1, w=2, h=1)   # the newest name, on the maze's outer wall, at its way in
    c.plan.ent("label", text="THE MAZE", x=mz.x, y=mz.y)
    i = 0
    for k in range(len(streets) - 1):
        band = Rect(6, streets[k] + 2, W - 12, streets[k + 1] - streets[k] - 2)
        for part in ([Rect(band.x, band.y, mz.x - band.x - 1, band.h), Rect(mz.x2 + 1, band.y, band.x2 - mz.x2 - 1, band.h)]
                     if band.overlaps(mz) else [band]):
            if part.w >= 5 and part.h >= 4:
                c.district(part, c.a["roles"][1:][i % 3])
                i += 1
    c._face_walls = True


def rule_decks(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    core = Rect(1, 1, int(W * 0.58), H - 2)
    my, cx = rule_grid(c, core, roles=["core", "market", "core", "core"], gates=False)
    c.gate(0, my + 1)
    # the decks: platforms over a drop, joined by bridges
    dx0 = core.x2 + 1
    g.fill(Rect(dx0, 1, W - dx0 - 1, H - 2), T.DROP)
    decks = []
    rows = 3
    dh = (H - 2 - (rows + 1)) // rows
    for i in range(rows):
        r = Rect(dx0 + 2 + (i % 2) * 3, 2 + i * (dh + 1), W - dx0 - 7, dh)
        g.fill(r, T.FLOOR)
        decks.append(r)
        c.district(Rect(r.x + 1, r.y + 1, r.w - 2, r.h - 2), "decks", name=f"deck {i + 1}", on=frozenset({T.FLOOR}))
    # bridges: core → each deck, deck → deck
    for r in decks:
        y = r.cy
        for x in range(core.x2 - 1, r.x + 1):
            if g.get(x, y) in (T.DROP, T.GROUND):
                g.set(x, y, T.BRIDGE)
        c._carve_to_street((core.x2 - 2, y))
    for a, b in zip(decks, decks[1:]):
        x = (max(a.x, b.x) + min(a.x2, b.x2)) // 2
        for y in range(a.y2 - 1, b.y + 1):
            if g.get(x, y) == T.DROP:
                g.set(x, y, T.BRIDGE)
    c.plan.notes.append("three decks over the drop; bridges are the streets")
    top = decks[0]
    c.story(core.x2 - 3, top.cy, w=2, h=1)


def rule_gauntlet(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    my = H // 2 - 1
    terrain = str(c.sheet.get("terrain") or "river")
    rx0, rx1 = W // 2 - 3, W // 2 + 3
    if terrain in ("mountain", "pass"):
        g.fill(Rect(rx0 - 4, 1, 13, my - 2), T.ROCK)
        g.fill(Rect(rx0 - 4, my + 5, 13, H - my - 6), T.ROCK)
        crossing = "the pass"
    else:
        g.fill(Rect(rx0, 1, rx1 - rx0, H - 2), T.WATER)
        crossing = "the bridge"
    c.road(1, my, W - 2, my, w=3)
    for x in range(rx0, rx1):
        for k in range(3):
            if g.get(x, my + k) in (T.WATER, T.ROCK, T.ROAD):
                g.set(x, my + k, T.BRIDGE if terrain not in ("mountain", "pass") else T.ROAD)
    c.gate(0, my + 1)
    c.gate(W - 1, my + 1, "out_east")
    # the booths: a barrier across the road at both ends of the crossing, one lane open
    for bx in (rx0 - 2, rx1 + 1):
        for k in (0, 2):
            g.set(bx, my + k, T.FENCE)
        c.plan.ent("label", text="TOLL", x=bx, y=my - 1)
        c.plan.ent("npc", id=f"tollman_{bx}", role="toll keeper", x=bx, y=my + 3 if g.get(bx, my + 3) == T.GROUND else my + 1)
        c.clear.add((bx, my + 1))
    for i, r in enumerate([Rect(2, 2, rx0 - 6, my - 3), Rect(rx1 + 4, 2, W - rx1 - 6, my - 3),
                           Rect(2, my + 4, rx0 - 6, H - my - 6), Rect(rx1 + 4, my + 4, W - rx1 - 6, H - my - 6)]):
        if r.w > 5 and r.h > 4:
            c.district(r, ["gate", "market", "housing", "housing"][i])
    gate_d = c.districts[1] if len(c.districts) > 1 else None
    c.place("lord_house", gate_d, near=(rx1 + 6, my - 4))
    c.story(rx1 + 2, my - 2 if g.get(rx1 + 2, my - 2) == T.GROUND else my, w=2, h=1)
    c.plan.notes.append(f"the town is a gauntlet along {crossing}; you pay to cross both ways")


def rule_convoy(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    cx, cy = W // 2, H // 2
    rx, ry = W // 2 - 6, H // 2 - 5
    vehicles = list(c.sheet.get("vehicles") or ["truck", "bus", "tanker", "trailer", "van", "flatbed", "truck",
                                                "school bus", "trailer", "pickup", "box truck", "camper"])
    n = len(vehicles)
    sides = [i for i in range(n) if abs(math.cos(2 * math.pi * i / n)) > 0.8]
    gap_i = c.rng.choice(sides or list(range(n)))
    for i, v in enumerate(vehicles):
        if i == gap_i:
            continue
        ang = 2 * math.pi * i / n
        x = int(cx + math.cos(ang) * rx)
        y = int(cy + math.sin(ang) * ry)
        horiz = abs(math.sin(ang)) > 0.7
        r = Rect(x - 1, y, 3, 2) if horiz else Rect(x, y - 1, 2, 3)
        g.fill(r, T.VEHICLE)
        for cc in r.cells():
            c.occupied.add(cc)
        c.plan.ent("label", text=v.upper(), x=r.x, y=r.y)
        # an awning on the inside of each vehicle
        ix, iy = int(cx + math.cos(ang) * (rx - 3)), int(cy + math.sin(ang) * (ry - 3))
        g.fill(Rect(ix - 1, iy - 1, 2, 2), T.FLOOR, only={T.GROUND})
    ang = 2 * math.pi * gap_i / n
    gx, gy = int(cx + math.cos(ang) * rx), int(cy + math.sin(ang) * ry)
    ex = 0 if gx < cx else W - 1
    c.road(ex if ex == 0 else gx, gy, gx if ex == 0 else W - 2, gy, w=2)
    c.road(gx, gy, cx, cy, w=2)
    c.gate(ex, gy)
    market = Rect(cx - 6, cy - 4, 12, 8)
    g.fill(market, T.FLOOR, only={T.GROUND, T.ROAD})
    c.district(market, "market", on=frozenset({T.FLOOR}))
    c.district(Rect(cx - rx + 3, cy - ry + 3, 2 * rx - 6, 2 * ry - 6), "camp")
    c.story(cx - 1, cy - 1, w=2, h=1)
    c.plan.notes.append(f"{n - 1} vehicles circled (from the vehicle list); a different place each time")
    c.plan.metrics["vehicles"] = n - 1


def rule_symmetric(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    cx = W // 2 - 1
    c.road(cx, 1, cx, H - 2, w=2)
    for y in (H // 3, 2 * H // 3):
        c.road(1, y, W - 2, y, w=2)
    c.gate(cx, H - 1)
    left = [Rect(2, 2, cx - 4, H // 3 - 3), Rect(2, H // 3 + 3, cx - 4, H // 3 - 4), Rect(2, 2 * H // 3 + 3, cx - 4, H - 2 * H // 3 - 5)]
    roles = c.a["roles"]
    for i, r in enumerate(left):
        if r.w > 5 and r.h > 4:
            c.district(r, roles[i % len(roles)])
    c._mirror = True
    c.story(cx, H - 6, w=2, h=1)


def rule_nested(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    outer = Rect(3, 3, W - 6, H - 6)
    inner = Rect(W // 2 - 12, H // 2 - 7, 24, 14)
    g.outline(outer, T.WALL)
    g.outline(inner, T.WALL)
    gx = W // 2
    c.road(gx, H - 2, gx, inner.y2, w=2)
    c.road(4, outer.y2 - 2, W - 5, outer.y2 - 2, w=1, t=T.PATH)
    c.road(4, 4, 4, outer.y2 - 2, w=1, t=T.PATH)
    c.road(W - 5, 4, W - 5, outer.y2 - 2, w=1, t=T.PATH)
    c.road(4, 4, W - 5, 4, w=1, t=T.PATH)
    for k in range(2):
        g.set(gx + k, outer.y2 - 1, T.ROAD)
    c.gate(gx, H - 1)
    # the airlock: one gap in the inner wall, a short corridor of suits
    for k in range(2):
        g.set(gx + k, inner.y2 - 1, T.FLOOR)
    c.plan.ent("label", text="AIRLOCK", x=gx - 2, y=inner.y2)
    c.plan.ent("npc", id="suit_1", role="suit at the airlock", x=gx - 1, y=inner.y2 + 1)
    c.road(inner.x + 2, inner.cy, inner.x2 - 3, inner.cy, w=1, t=T.PATH)
    c.road(gx, inner.cy, gx, inner.y2 - 2, w=2, t=T.PATH)
    c.district(Rect(inner.x + 1, inner.y + 1, inner.w - 2, inner.cy - inner.y - 1), "inside")
    c.district(Rect(inner.x + 1, inner.cy + 1, inner.w - 2, inner.y2 - inner.cy - 2), "inside")
    for r in (Rect(5, 5, inner.x - 6, outer.y2 - 8), Rect(inner.x2 + 1, 5, outer.x2 - inner.x2 - 3, outer.y2 - 8),
              Rect(inner.x, 5, inner.w, inner.y - 6)):
        if r.w > 5 and r.h > 4:
            c.district(r, "outside")
    c.story(gx, inner.y2 + 1, w=2, h=1)
    c.plan.notes.append("a wall inside a wall; one airlock between the healthy and the touched")


def rule_wrecks(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    names = list(c.sheet.get("wrecks") or ["the big walker", "the tank line", "the rotor yard", "the gunship"])
    spots = [(W // 4, H // 3), (3 * W // 4, H // 3), (W // 4, 2 * H // 3 + 2), (3 * W // 4, 2 * H // 3 + 2)]
    c.road(1, H // 2, W - 2, H // 2, w=2)
    c.gate(0, H // 2)
    biggest = None
    for i, name in enumerate(names[:4]):
        sx, sy = spots[i]
        size = (8, 4) if i == 0 else (5, 3)
        r = Rect(sx - size[0] // 2, sy - size[1] // 2, *size)
        g.fill(r.grow(1), T.RUBBLE)
        g.fill(r, T.VEHICLE)
        for cc in r.grow(1).cells():
            c.occupied.add(cc)
        c.road(sx, sy + size[1] // 2 + 2 if sy < H // 2 else sy - size[1] // 2 - 2, sx, H // 2, w=2)
        c.plan.ent("label", text=name.upper(), x=r.x, y=r.y)
        quad = Rect(1 if sx < W // 2 else W // 2 + 1, 1 if sy < H // 2 else H // 2 + 2, W // 2 - 2, H // 2 - 3)
        c.district(quad, "wreck", name=f"{name} district")
        if biggest is None:
            biggest = r
    c.story(biggest.cx - 1, biggest.y2 + 1, w=2, h=1)
    c.plan.notes.append("each district is named for the wreck it was built from")


def rule_sanctuary(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    my, cx = rule_grid(c, Rect(4, 4, W - 8, H - 8), gates=False)
    for x, y in Rect(3, 3, W - 6, H - 6).border():        # the defenders' walk, just inside the fence
        if g.get(x, y) == T.GROUND:
            g.set(x, y, T.PATH)
    fence = Rect(2, 2, W - 4, H - 4)
    for x, y in fence.border():
        if g.get(x, y) == T.GROUND:
            g.set(x, y, T.FENCE)
    c.road(1, my + 1, 4, my + 1, w=1)
    g.set(2, my + 1, T.ROAD)
    c.gate(0, my + 1)
    for (x, y) in ((3, 3), (W - 4, 3), (3, H - 4), (W - 4, H - 4)):
        c.plan.ent("label", text="WATCH", x=x, y=y)
    # the tunnels out: hidden doors at the far edge
    for k, (x, y) in enumerate(((W - 1, 3 + c.rng.randint(0, 3)), (W - 1, H - 4 - c.rng.randint(0, 3)))):
        g.set(W - 2, y, T.PATH)
        g.set(W - 3, y, T.PATH)
        for xx in range(W - 3, 2, -1):
            if g.get(xx, y) in STREET:
                break
            if g.get(xx, y) in (T.GROUND, T.FENCE):
                g.set(xx, y, T.PATH)
        c.gate(x, y, f"tunnel_{k + 1}")
    c._story_after = ("bakery", "beside")
    c.story(cx - 1, my - 2, w=2, h=1)


def rule_fields(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    berm = Rect(2, 2, W - 4, H - 4)
    for x, y in berm.border():
        g.set(x, y, T.FENCE)
    my = H // 2
    c.road(1, my, W - 4, my, w=2, t=T.ROAD)
    c.gate(0, my)
    yard = Rect(W // 2 - 8, my - 9, 16, 8)
    for i, r in enumerate([Rect(4, 4, yard.x - 6, my - 6), Rect(yard.x2 + 2, 4, W - yard.x2 - 7, my - 6),
                           Rect(4, my + 3, W // 2 - 6, H - my - 7), Rect(W // 2 + 2, my + 3, W // 2 - 6, H - my - 7)]):
        if r.w > 5 and r.h > 4:
            c.district(r, "fields", dress="crops")
    c.district(yard, "yard")
    c.district(Rect(W // 2 - 8, my + 3, 16, 6), "housing")
    c.story(W // 2 - 1, my - 2, w=2, h=1)
    for (x, y) in ((3, 3), (W - 5, 3)):
        c.plan.ent("label", text="WATCHTOWER", x=x, y=y)
    c.plan.notes.append("the fields are the town; earthworks all round, one gate")
    c._few_houses = True


def rule_twostate(c: Ctx):
    my, cx = rule_grid(c)
    c.story(cx - 1, my - 2, w=2, h=1)
    c._two_state = True


def rule_rim(c: Ctx):
    g = c.g
    W, H = g.w, g.h
    cx, cy = W // 2, H // 2
    rx, ry = W // 2 - 14, H // 2 - 9
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
            if d <= 1.0:
                g.set(x, y, T.GLASS)
            elif d <= 1.45:
                g.set(x, y, T.ROAD if d <= 1.25 else T.GROUND)
    c.road(1, cy, cx - rx, cy, w=2)
    c.gate(0, cy)
    for i, r in enumerate([Rect(1, 1, W - 2, cy - ry - 3), Rect(1, cy + ry + 4, W - 2, H - cy - ry - 5),
                           Rect(1, 1, cx - rx - 4, H - 2), Rect(cx + rx + 4, 1, W - cx - rx - 5, H - 2)]):
        if r.w > 4 and r.h > 3:
            c.district(r, "rim" if i < 3 else "pilgrims")
    c.face = (cx, cy)
    for cc in Rect(cx - rx, cy - ry, 2 * rx, 2 * ry).cells():
        if g.get(*cc) == T.GLASS:
            c.clear.add(cc)
    c.story(cx - 1, cy - 1)
    c.plan.notes.append("nothing is built on the glass; the town faces in from its rim")


def rule_buried(c: Ctx):
    """The surface (a decoy in the After, a town digging in during the War) and the level below."""
    g = c.g
    W, H = g.w, g.h
    if c.after:
        g.fill(Rect(1, 1, W - 2, H - 2), T.RUBBLE)
        c.road(1, H // 2, W // 3, H // 2, w=2, t=T.PATH)
        c.gate(0, H // 2)
        for i in range(5):
            x, y = c.rng.randint(4, W - 5), c.rng.randint(3, H - 4)
            if g.get(x, y) == T.RUBBLE and (x, y) not in c.clear:
                g.set(x, y, T.ROCK)
                c.plan.ent("label", text="CHIMNEY (AIR SHAFT)", x=x, y=y)
        c.district(Rect(2, 2, W - 4, H - 4), "decoy", on=frozenset({T.RUBBLE}))
        hatch = c.place("ruin", c.districts[0], label="THE HATCH", near=(W // 3 + 4, H // 2), required=True)
        hx, hy = (hatch["rect"][0] + 2, hatch["rect"][1] + 2) if hatch else (W // 3 + 2, H // 2 + 2)
        c._down = (hx, hy)
        sx, sy = W // 3 - 1, H // 2 - 3
        c.story(sx, sy, what="the chimneys that are air shafts", w=2, h=1)
        g.set(sx, sy, T.ROCK)                       # the story element is a chimney and the ground beside it
        c.plan.ent("label", text="CHIMNEY (AIR SHAFT)", x=sx, y=sy)
    else:
        my, cx = rule_grid(c, gates=True)
        c._down = None
        c.story(cx - 1, my - 2, w=2, h=1)


RULES = {"grid": rule_grid, "rings": rule_rings, "radial": rule_radial, "queues": rule_queues, "walls": rule_walls,
         "decks": rule_decks, "gauntlet": rule_gauntlet, "convoy": rule_convoy, "symmetric": rule_symmetric,
         "nested": rule_nested, "wrecks": rule_wrecks, "sanctuary": rule_sanctuary, "fields": rule_fields,
         "twostate": rule_twostate, "rim": rule_rim, "buried": rule_buried}


# =================================================================== the level below (the Buried Town)
def build_below(c: Ctx, pid: str) -> Ctx:
    W, H = c.g.w, c.g.h
    b = Ctx(c.sheet, c.aid, c.era, c.seed, c.attempt, pid, size=(W, H))
    b.plan.kind = "level"
    b.plan.name = f"{c.plan.name} — below"
    g = b.g
    g.c = [[T.ROCK] * W for _ in range(H)]
    cx, cy = W // 2, H // 2
    full = c.after
    # the main shaft (a drop) with the freight elevator's platform on its rim
    for y in range(H):
        for x in range(W):
            d = math.hypot((x - cx) / 1.6, y - cy)
            if d <= 3:
                g.set(x, y, T.DROP)
            elif d <= (8 if full else 6):
                g.set(x, y, T.FLOOR)
    g.fill(Rect(cx + 4, cy - 1, 2, 2), T.FLOOR)
    b.plan.ent("label", text="FREIGHT ELEVATOR", x=cx + 4, y=cy - 1)
    caverns = [("market", Rect(cx - 13, 2, 26, 10)), ("housing", Rect(2, cy - 7, 17, 14)),
               ("hydroponics", Rect(cx - 11, H - 12, 22, 10)), ("workshop", Rect(W - 19, cy - 7, 17, 14))]
    if not full:
        caverns = caverns[:2]
    for role, r in caverns:
        g.fill(r, T.FLOOR)
        b.thick((r.cx, r.cy), (cx, cy), 2, T.PATH, only={T.ROCK})
        b.district(Rect(r.x + 1, r.y + 1, r.w - 2, r.h - 2), role, on=frozenset({T.FLOOR}))
        if role == "hydroponics":
            b.plan.ent("label", text="HYDROPONICS", x=r.x + 1, y=r.y + 1)
    # the entrance tunnel from the hatch, with the blast door
    ey = 3 if full else cy
    b.road(1, ey, cx - 10, ey, w=2, t=T.PATH)
    b.road(cx - 10, ey, cx - 10, cy - 5, w=2, t=T.PATH)
    b.thick((cx - 10, cy - 5), (cx - 4, cy - 3), 2, T.PATH, only={T.ROCK})
    g.set(0, ey, T.DOOR)
    b.entrances.append(((0, ey), (1, ey), "up"))
    b.clear |= {(0, ey), (1, ey)}
    if full:
        b.story(6, ey, what=c.a["story"]["after"], w=2, h=2)
        b.plan.ent("label", text="BLAST DOOR", x=6, y=ey - 1)
    else:
        b.story(cx + 4, cy + 1, what=c.a["story"]["war"], w=2, h=1)
        b.plan.notes.append("the War: two caverns dug, the rest still rock")
    b.plan.notes.append("the only way in is the hatch above and the blast door")
    return b


# =================================================================== placing the buildings (meso)
def _required(c: Ctx) -> list[dict]:
    out = []
    for s in c.sheet.get("required") or []:
        k = s.get("kind")
        if k not in archetypes.KINDS:
            c.plan.unknowns.append(f"the sheet asks for a '{k}', which no building kind covers — left out")
            continue
        out.append({"kind": k, "label": s.get("label"), "role": s.get("role"), "required": True, "ref": s.get("ref")})
    for s in c.a.get("signature") or []:
        if c.a["rule"] in ("radial",) and s["kind"] == "cathedral":
            continue
        if c.a["rule"] in ("queues",) and s["kind"] == "counting_house":
            continue
        if c.a["rule"] == "walls" and s["kind"] == "memorial":
            continue
        lbl = s.get("label")
        out.append({**s, "label": lbl.get(c.era) if isinstance(lbl, dict) else lbl, "required": True})
    sig = c.sheet.get("signature")
    if isinstance(sig, dict) and sig.get("kind") in archetypes.KINDS:
        out.append({"kind": sig["kind"], "label": sig.get("label"), "role": None, "required": True})
    up = c.a["upgrade"][c.era]
    acc = c.a["accessory"][c.era]
    out.append({"kind": "smith", "label": "ARMS", "role": "workshop", "required": True, "upgrade_note": up})
    out.append({"kind": "trinkets", "label": "TRINKETS", "role": "market", "required": True, "upgrade_note": acc})
    return out


def _tier(c: Ctx, kind: str):
    t = c.sheet.get("tiers") or {}
    if isinstance(t, dict) and t.get(kind) is not None:
        return t[kind]
    if c.sheet.get("tier") is not None:
        return c.sheet["tier"]
    return None


def place_all(c: Ctx, target: Ctx | None = None):
    """Required, signature and upgrade places, then filler. The Buried Town (After) builds below, not on top."""
    t = target or c
    for req in _required(c):
        role = req.get("role")
        ds = [d for d in t.districts if role and d["role"] == role] or [d for d in t.districts if d["role"] not in ("square",)] or t.districts
        b = None
        for d in sorted(ds, key=lambda d: -d["rect"].w * d["rect"].h)[:4]:
            b = t.place(req["kind"], d, label=req.get("label"), required=False)
            if b:
                break
        if b is None:
            b = t.place(req["kind"], None, label=req.get("label"), required=True)
        if b:
            if req.get("upgrade_note"):
                b["upgrade_note"] = req["upgrade_note"]
            if req.get("ref"):
                b["ref"] = req["ref"]
            if b["upgrades"]:
                b["tier"] = {k: _tier(c, k) for k in b["upgrades"]}
    if getattr(c, "_few_houses", False):
        quota = 3
    else:
        quota = 40
    filler = c.a["filler"]
    placed = 0
    for d in list(t.districts):
        if d["role"] in ("square", "altar", "counting") or quota <= 0:
            continue
        miss = 0
        while miss < 2 and placed < quota:
            kind = filler[(placed + len(d["id"])) % len(filler)]
            if t.plan.kind == "level":
                kind = "stall" if d["role"] == "market" else ("house" if d["role"] == "housing" else "stall")
            b = t.place(kind, d, required=False, tries=120)
            if b is None:
                miss += 1
            else:
                placed += 1
    if any(b.get("upgrades") and None in (b.get("tier") or {}).values() for b in t.plan.buildings):
        c.plan.unknowns.append("the upgrade tier this town sells is not on its sheet — the upgrade places carry tier null")


# =================================================================== finishing (texture, story, spawn, checks)
def _mirror(c: Ctx):
    g = c.g
    W = g.w
    g.mirror_x()
    mirrored = []
    for b in list(c.plan.buildings):
        x, y, w, h = b["rect"]
        mx = W - x - w
        nb = {"id": b["id"] + "_m", "kind": "house" if b["interior"] else b["kind"], "label": "", "rect": [mx, y, w, h],
              "district": b["district"], "required": False, "interior": archetypes.KINDS["house"]["interior"] if b["interior"] else None,
              "upgrades": []}
        if b.get("door"):
            nb["door"] = [W - 1 - b["door"][0], b["door"][1]]
            nb["front"] = [W - 1 - b["front"][0], b["front"][1]]
        mirrored.append(nb)
        for cc in Rect(mx, y, w, h).cells():
            c.occupied.add(cc)
    c.plan.buildings += mirrored
    # one wrong block: a mirrored lot becomes the locked street
    wrong = [b for b in mirrored if b["kind"] == "house"]
    if wrong:
        b = c.rng.choice(wrong)
        x, y, w, h = b["rect"]
        r = Rect(x, y, w, h)
        g.fill(r, T.RUBBLE)
        g.outline(r, T.FENCE)
        c.plan.buildings.remove(b)
        c.plan.ent("label", text="LOCKED STREET", x=r.x, y=r.y)
        gx, gy = (b.get("door") or [r.cx, r.y2 - 1])
        g.set(gx, gy, T.FENCE)
        c.plan.notes.append("perfect symmetry, with one wrong block: the locked street")
        if c.after:
            fx, fy = b.get("front") or [r.cx, r.y2]
            c.story(fx, fy, w=1, h=1)
    for e in list(c.plan.entities):
        if e["type"] == "label" and e["x"] < W // 2 and e.get("text") not in ("LOCKED STREET",):
            pass


def _face_walls(c: Ctx):
    """The Wall of Names: every empty strip of ground along a street becomes wall, for names."""
    g = c.g
    n = 0
    for y in range(1, g.h - 1):
        for x in range(1, g.w - 1):
            if g.c[y][x] != T.GROUND or (x, y) in c.clear:
                continue
            if any(g.get(*nn) == T.ROAD for nn in g.n4(x, y)) and (x + y) % 11 != 0:
                g.set(x, y, T.WALL)
                n += 1
    c.plan.metrics["name_wall_cells"] = n
    c.plan.notes.append(f"{n} cells of blank wall along the streets, for names")


def _dress(c: Ctx):
    """WFC texture on the empty ground of each district (never on or beside a path, door or the story)."""
    g = c.g
    kinds = list(c.a.get("dressing") or [])
    if not kinds:
        return
    used = 0
    for i, d in enumerate(c.districts):
        ts = d.get("dress") or kinds[i % len(kinds)]
        if ts not in wfc.TILESETS or d["role"] in ("square", "market", "altar", "counting"):
            continue
        cells = []
        for x, y in d["rect"].cells():
            if g.get(x, y) != T.GROUND or (x, y) in c.clear or (x, y) in c.occupied:
                continue
            near = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = g.get(x + dx, y + dy)
                    if q in (T.ROAD, T.PATH, T.DOOR, T.BRIDGE, T.FLOOR) or (x + dx, y + dy) in c.clear:
                        near = True
            if not near:
                cells.append((x, y))
        if len(cells) < 6:
            continue
        out = wfc.collapse(cells, ts, rng_for(c.plan.id, c.seed, c.attempt, d["id"], ts))
        for (x, y), t in sorted(out.items()):
            if t != T.GROUND:
                g.set(x, y, t)
                used += 1
        c.plan.kit.append(f"wfc:{ts}")
    c.plan.metrics["filler_cells"] = used


def _connect(c: Ctx, spawn) -> list:
    """Join every place that must be reachable to the spawn; filler that cuts a path turns to rubble."""
    g = c.g
    needs = [tuple(b["front"]) for b in c.plan.buildings if b.get("front")]
    needs += [inward for (_cell, inward, _id) in c.entrances]
    if c.story_rect:
        needs += [cc for cc in c.story_rect.cells() if g.walkable(*cc)]
    needs += [(e["x"], e["y"]) for e in c.plan.entities if e["type"] in ("npc", "upgrade")]
    for _ in range(3):
        reach = g.flood(spawn)
        missing = [p for p in needs if p not in reach]
        if not missing:
            return []
        for p in missing:
            if p in reach:
                continue
            path = g.path(p, lambda x, y: (x, y) in reach,
                          lambda x, y: c.interior(x, y) and (x, y) not in c.occupied
                          and g.get(x, y) in (T.GROUND, T.FIELD, T.RUBBLE, T.FENCE))
            if path:
                for cc in path:
                    if g.get(*cc) == T.FENCE:
                        g.set(*cc, T.RUBBLE)
                    elif g.get(*cc) in (T.GROUND, T.FIELD):
                        g.set(*cc, T.PATH)
                reach = g.flood(spawn)
    reach = g.flood(spawn)
    return [p for p in needs if p not in reach]


def _approach(c: Ctx) -> list:
    """The walkable cells near the way in, nearest first (where a spawn may stand)."""
    from collections import deque
    if not c.entrances:
        return []
    inward = c.entrances[0][1]
    g = c.g
    depth = max(18, g.w)          # wide enough for a city: the nearest cell with a view of the story element wins
    out, q, seen = [], deque([(inward, 0)]), {inward}
    while q:
        p, dd = q.popleft()
        if dd > depth:
            break
        out.append(p)
        for n in g.n4(*p):
            if n not in seen and g.walkable(*n) and c.interior(n[0], n[1]):
                seen.add(n)
                q.append((n, dd + 1))
    return out


def _seen_from_approach(c: Ctx, cells: list) -> bool:
    clear = set(cells)
    return any(c.g.sees(p, s, clear) for p in _approach(c) for s in cells)


def _spawn(c: Ctx):
    g = c.g
    if not c.entrances:
        c.plan.problems.append("no way in or out")
        return (1, 1)
    cell, inward, did = c.entrances[0]
    story = list(c.story_rect.cells()) if c.story_rect else []
    clear = set(story)
    for p in _approach(c):
        if not story or any(g.sees(p, s, clear) for s in story):
            return p
    c.plan.problems.append("the story element is not visible from anywhere near the way in")
    return inward


def finish(c: Ctx):
    g = c.g
    if getattr(c, "_mirror", False):
        _dress(c)                       # before the mirror, so the filler is symmetric too
        _mirror(c)
        gates = {cell for cell, _i, _d in c.entrances}
        for y in range(g.h):
            for x in range(g.w):
                if not c.interior(x, y) and g.c[y][x] == T.DOOR and (x, y) not in gates:
                    g.c[y][x] = T.WALL
    if getattr(c, "_face_walls", False):
        _face_walls(c)
    sa = getattr(c, "_story_after", None)
    if sa:
        bk = [b for b in c.plan.buildings if b["kind"] == sa[0] and b.get("front")]
        if bk:
            x, y, w, h = bk[0]["rect"]
            fx, fy = bk[0]["front"]
            spots = ((fx - 1, fy), (fx, fy), (fx - 1, fy + 1)) if sa[1] == "front" else \
                ((x + w + 1, y + h - 2), (x - 3, y + h - 2), (x, y + h + 1))
            for sx, sy in spots:
                r = Rect(sx, sy, 2, 1)
                if all(g.get(*cc) in (T.GROUND, T.PATH, T.FLOOR, T.ROAD) and cc not in c.occupied for cc in r.cells()) \
                        and _seen_from_approach(c, list(r.cells())):
                    if c.story_rect:
                        for cc in c.story_rect.cells():
                            c.occupied.discard(cc)
                    c.story(sx, sy, w=2, h=1)
                    c.plan.notes.append(f"the story element sits {'at the door of' if sa[1] == 'front' else 'beside'} the {sa[0]}")
                    break
    if not getattr(c, "_mirror", False):
        _dress(c)
    spawn = _spawn(c)
    lost = _connect(c, spawn)
    for p in lost:
        c.plan.problems.append(f"cell {p[0]},{p[1]} can't be reached from the spawn")
    # only a few houses open (the rest are shut doors): every open door is a map the game has to carry
    houses = [b for b in c.plan.buildings if b["kind"] == "house" and b.get("door") and b.get("interior")]
    for b in houses[c.a.get("enterable_houses", 3):]:
        g.set(*b["door"], T.WALL)
        b.pop("door")
        b["interior"] = None
        b["shut"] = True
    if len(houses) > c.a.get("enterable_houses", 3):
        c.plan.notes.append(f"{c.a.get('enterable_houses', 3)} of {len(houses)} houses open; the rest are shut doors")
    # entities: the way out, the spawn, the doors and the story
    for cell, inward, did in c.entrances:
        to = "travel" if not did.startswith("up") else "plan:surface"
        e = c.plan.ent("door", id=did, to=to, spawn="start", x=cell[0], y=cell[1])
        if did.startswith("tunnel"):
            e["hidden"] = True
    c.plan.ent("spawn", name="start", x=spawn[0], y=spawn[1])
    for b in c.plan.buildings:
        if b.get("door") and b.get("interior"):
            c.plan.ent("door", id=f"to_{b['id']}", to=f"interior:{b['id']}", spawn="start", x=b["door"][0], y=b["door"][1])
            c.plan.ent("spawn", name=f"from_{b['id']}", x=b["front"][0], y=b["front"][1])
        if b.get("label"):
            x, y, _w, _h = b["rect"]
            c.plan.ent("label", text=b["label"], x=x, y=y)
        if b["kind"] == "stall" and b.get("upgrades") and b.get("front"):
            for k in b["upgrades"]:
                c.plan.ent("upgrade", id=f"upgrade_{k}_{b['id']}", kind=k, tier=(b.get("tier") or {}).get(k),
                           label=b.get("label") or "", x=b["front"][0], y=b["front"][1])
    if c.story_rect:
        r = c.story_rect
        c.plan.story = {"what": c.story_what, "x": r.x, "y": r.y, "w": r.w, "h": r.h}
        c.plan.ent("story", id="story", what=c.story_what, w=r.w, h=r.h, x=r.x, y=r.y)
    c.plan.districts = [{"id": d["id"], "role": d["role"], "name": d["name"], "rect": d["rect"].as_list()}
                        for d in c.districts]
    c.plan.metrics.update({"buildings": len(c.plan.buildings), "doors": len(c.plan.of("door")),
                           "walkable": sum(1 for y in range(g.h) for x in range(g.w) if g.walkable(x, y))})
    if getattr(c, "_two_state", False):
        night = []
        for b in c.plan.buildings:
            if b.get("front"):
                night.append({"type": "npc", "id": f"night_{b['id']}", "role": "resident come up for the night",
                              "x": b["front"][0], "y": b["front"][1]})
        c.plan.states["night"] = {"entities": night, "note": "empty by day; at night the people come up"}
        c.plan.notes.append("two states: day (empty) and night (the people come up)")


# =================================================================== interiors (micro)
def interiors(c: Ctx, parent: Plan, underground=False):
    a = c.a
    ruined = bool(a["ruined"].get(c.era)) or bool(c.sheet.get("ruined"))
    for b in parent.buildings:
        if not (b.get("door") and b.get("interior")):
            continue
        variants = tuple(v for v, on in (("ruined", ruined and not underground and b["kind"] != "smith"),
                                         ("underground", underground)) if on)
        tier_k = (b.get("tier") or {})
        ip = kits.build(b["interior"], f"{parent.id}_{b['id']}", rng_for(parent.id, c.seed, c.attempt, b["id"]),
                        variants=variants, upgrades=b.get("upgrades"), tier=None,
                        label=b.get("label") or "", spawn_back=f"from_{b['id']}")
        for e in ip.of("upgrade"):
            e["tier"] = tier_k.get(e["kind"])
            if b.get("upgrade_note"):
                e["place"] = b["upgrade_note"]
        for e in ip.of("door"):
            e["to"] = f"plan:{parent.id}"
        ip.archetype, ip.era, ip.seed, ip.attempt = parent.archetype, parent.era, parent.seed, parent.attempt
        ip.for_building = b["id"]
        parent.children.append(ip)


# =================================================================== the whole thing
def _attempt(sheet: dict, aid: str, era: str, seed: int, attempt: int, pid: str) -> Plan:
    c = Ctx(sheet, aid, era, seed, attempt, pid)
    if sheet.get("look"):
        c.plan.notes.append(f"its look: {sheet['look']}")
    if sheet.get("music"):
        c.plan.notes.append(f"its theme music: {sheet['music']}")
    RULES[c.a["rule"]](c)
    below = None
    if c.a["rule"] == "buried":
        below = build_below(c, f"{pid}_below")
        if c.after:
            place_all(c, below)         # the town lives below; the surface is a decoy
        else:
            place_all(c)
            place_all_light(below)
    else:
        place_all(c)
    finish(c)
    interiors(c, c.plan)
    if below is not None:
        finish(below)
        interiors(c, below.plan, underground=True)
        # the hatch (After) or a cellar stair (War) joins the surface to the level below
        g = c.g
        hx, hy = getattr(c, "_down", None) or _free_spot(c)
        if g.walkable(hx, hy):
            g.set(hx, hy, T.DOOR)
        c.plan.ent("door", id="down", to=f"plan:{below.plan.id}", spawn="start", x=hx, y=hy)
        c.plan.ent("spawn", name="from_below", x=hx, y=hy + 1 if g.walkable(hx, hy + 1) else hy)
        for e in below.plan.of("door"):
            if e["id"] == "up":
                e["to"] = f"plan:{pid}"
                e["spawn"] = "from_below"
        below.plan.kit.append("level:below")
        c.plan.children.append(below.plan)
        for p in below.plan.problems:
            c.plan.problems.append(f"below: {p}")
        if not c.after:
            c.plan.notes.append("the War: the town above still stands; a cellar stair leads to the first shafts")
    return c.plan


def place_all_light(b: Ctx):
    for d in b.districts:
        b.place("stall", d, required=False, tries=80)


def _free_spot(c: Ctx):
    g = c.g
    for b in c.plan.buildings:
        if b["kind"] == "house" and b.get("front"):
            return tuple(b["front"])
    for y in range(2, g.h - 2):
        for x in range(2, g.w - 2):
            if g.get(x, y) == T.PATH:
                return (x, y)
    return (2, 2)


def generate(sheet: dict, archetype: str, era: str, seed: int, pid: str | None = None, max_attempts: int = 8) -> Plan:
    """The plan for `sheet` as `archetype` in `era`, from `seed`. Deterministic; retries until the checks pass."""
    from . import check
    if era not in archetypes.ERAS:
        raise ValueError(f"era must be one of {archetypes.ERAS}")
    pid = pid or f"{sheet.get('id', 'place')}__plan_{era}"
    last = None
    for attempt in range(max_attempts):
        p = _attempt(sheet, archetype, era, seed, attempt, pid)
        p.problems += check.problems(p)
        p.unknowns = sorted(set(p.unknowns) | set(sheet.get("unknowns") or []))
        if not p.problems:
            return p
        last = p
    last.notes.append(f"no attempt passed every check in {max_attempts} tries — the problems are listed")
    return last
