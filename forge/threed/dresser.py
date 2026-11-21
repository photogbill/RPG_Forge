"""The dresser (BUILD 97 Part 2, inside BUILD 98): fills a place's outside zones from a town's kit, the way people would.

✦ William, 2026-11-20 23:30: "It looks like an empty neighborhood unlived in." 23:38: "And there should be walls, fences".

    python -m forge.threed.dresser dress <place> --kit <kit.json> [--seed N] [--dry]
    python -m forge.threed.dresser kit-list <kit.json> --out <wanted_3d/kit_<kit>.json>     the kit's new models, worded

It reads the place plan and writes `<place>.dressing_out.json` beside it: the plan file is never rewritten, and nothing
already in the plan is moved (a plan thing is fixed, "by": "hand" or not). The compiler places the output like the plan's own
things; a model not yet delivered stands as a labelled grey box until it is.

How it dresses (BUILD 97 Part 2): zones come from the plan (forge/threed/areacheck_dressing.zones: kerb strips, front yards,
back and side yards, porches, open lots). Each home's lot draws a character from its seed (◆ 1 in 4 a little overgrown, 1 in 6
immaculate, the rest kept) and is dressed in groups people make — a porch set, foundation planting along the front, a patio
by the back door, a kids' corner, a work corner, fences along the back and side lot lines with a gate left by the house —
then filled toward the zone's density target. The kerb gets something every 6–10 m and cars park along it. Shaded, disturbed
edges get Japanese stiltgrass. It keeps every anchor, door, path and story spot clear by 0.4 m past the body, puts nothing
on the road but parked cars, nothing inside a building, and no dressing model more than twice in one map-camera view.
The same seed gives the same yard every time.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
from datetime import datetime
from pathlib import Path

import numpy as np

from . import areacheck_dressing as ad

CLEAR_M = 0.4                     # anchors, doors, paths: kept clear by the body's width plus this
GAP_M = 0.25                      # between two dressed things
SIDEWALK_STRIP_M = 1.0                  # the sidewalk's furniture strip at the kerb
KEEP_CLEAR_MATS = ("path", "sidewalk", "flagstone", "porch", "deck", "drive", "gravel", "plank", "checker", "rug", "garden")
STRUCTURE_FAMILIES = ("boundary",)


# ------------------------------------------------------------------------------------------------ the kit
def load_kit(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def model_id(v: dict) -> str:
    return str(v.get("model") or v["id"])


def kit_world_list(kit: dict, existing_ids: set | None = None) -> dict:
    """The kit's new models (those with words) as a world list, in the place's story order, released."""
    out = []
    existing_ids = existing_ids or set()
    for k, v in enumerate(kit["variants"]):
        if v.get("model") or v.get("skip_world"):
            continue
        is_tree = v.get("kind") == "tree" and v.get("species")
        if not v.get("words") and not is_tree:
            continue
        if v["id"] in existing_ids:
            continue
        kind = {"vehicle": "prop"}.get(v.get("kind", "prop"), v.get("kind", "prop"))   # the world list has no vehicle kind
        e = {"id": v["id"], "kind": kind, "tier": v.get("tier", "small_prop"),
             "first": {"where": kit.get("where") or kit.get("town"), "order": float(kit.get("order", 50)) + k / 1000.0},
             "real_size_m": v.get("real_size_m") or {"width": max(v["box_m"])},
             **({"species": v["species"], "seed": int(v.get("seed") or 11)} if is_tree else {"words": v["words"]}),
             "kit": f"{kit.get('town')}_{kit.get('era')}", "family": v["family"],
             "note": "BUILD 97/98 dressing kit (Claude Opus, 2026-11-21): ✦ William 2026-11-20 23:30 'It looks like an empty "
                     "neighborhood unlived in.' Look words, not canon." + (f" {v['note']}" if v.get("note") else "")}
        out.append(e)
    return {"_about": f"Dressing kit models for {kit.get('town')} ({kit.get('era')}), written by forge/threed/dresser.py "
                      f"kit-list from games/<game>/dressing/kits/. Every one is placed by the dresser as soon as it is "
                      f"delivered; until then it stands as a grey box.", "entries": out}


# ------------------------------------------------------------------------------------------------ geometry
def face_turn(ux: float, uy: float) -> float:
    """The turn that makes a model's front (toward +y at 0) face the direction (ux, uy)."""
    return float(math.degrees(math.atan2(-ux, uy)) % 360)


class Board:
    """What is taken on the 0.5 m grid, and what may be used."""

    def __init__(self, zz: dict, place: dict, things: list, rules: dict):
        self.g, self.Z, self.lot = zz["grid"], zz["Z"], zz["lot"]
        g = self.g
        self.taken = np.zeros(g.X.shape, bool)
        self.taken |= self.Z == ad.Z_BUILDING
        self.taken |= self.Z == ad.Z_EXCLUDED
        # ground kept clear: paths, porches, drives, decks; a sidewalk's last metre at the kerb is its furniture
        # strip (where a town puts its hydrants, poles and bins out), so only the walking width is kept clear
        rd = ad.distance(zz["road"], g.cell) if zz["road"].any() else None
        for gr in place.get("ground") or []:
            if isinstance(gr, dict) and any(m in str(gr.get("mat") or "") for m in KEEP_CLEAR_MATS):
                m = g.ground(gr)
                if m is not None:
                    if "sidewalk" in str(gr.get("mat") or "") and rd is not None:
                        m = m & (rd > SIDEWALK_STRIP_M)
                    self.taken |= m
        for name, at in (place.get("anchors") or {}).items():
            if isinstance(at, (list, tuple)) and len(at) >= 2:
                self.taken |= np.hypot(g.X - float(at[0]), g.Y - float(at[1])) <= 0.8 + CLEAR_M
        for b in zz["buildings"]:
            for key in ("door", "front"):
                p = b["thing"].get(key)
                if p:
                    self.taken |= np.hypot(g.X - float(p[0]), g.Y - float(p[1])) <= 1.0 + CLEAR_M
        for t in things:                      # the plan's own things: fixed
            self.taken |= g.poly(ad.corners(t["at"], t["w"] + 2 * GAP_M, t["d"] + 2 * GAP_M, t["turn"]))
        self.road = self.Z == ad.Z_ROAD

    def fits(self, at, w, d, turn, allow_road=False, zones=None, gap=GAP_M) -> np.ndarray | None:
        g = self.g
        if not (0 <= at[0] < g.W * g.cell and 0 <= at[1] < g.H * g.cell):
            return None
        m = g.poly(ad.corners(at, w + 2 * gap, d + 2 * gap, turn))
        c = ad._cell_of(g, at)
        if c:
            m[c] = True
        if not m.any():
            return None
        # every corner inside the plan
        for x, y in ad.corners(at, w, d, turn):
            if not (0 <= x <= g.W * g.cell and 0 <= y <= g.H * g.cell):
                return None
        if (m & self.taken).any():
            return None
        if not allow_road and (m & self.road).any():
            return None
        if zones is not None:
            zc = self.Z[m]
            if not np.isin(zc, list(zones)).all():
                return None
        return m

    def take(self, m: np.ndarray) -> None:
        self.taken |= m


# ------------------------------------------------------------------------------------------------ the dresser
class Dresser:
    def __init__(self, place: dict, kit: dict, rules: dict, sizes: dict | None = None, seed: int = 1,
                 view=(20.0, 21.0), places_dir=None):
        self.place, self.kit, self.rules = place, kit, rules
        self.places_dir = places_dir
        self.sizes = sizes or {}
        self.seed = int(seed)
        self.view = view
        self.zz = ad.zones(place, rules, self.sizes)
        self.plan_things = ad.things_of(place, [], self.sizes, rules)
        self.board = Board(self.zz, place, self.plan_things, rules)
        self.items: list[dict] = []
        self.by_role: dict = {}
        for v in kit["variants"]:
            if not v.get("skip_world"):
                self.by_role.setdefault(v["role"], []).append(v)
        self.placed_models = [(t["model"], t["at"]) for t in self.plan_things]
        self.log: list[str] = []
        self.excluded = set(ad.place_rules(rules, self.zz["place"]).get("exclude_lots") or [])

    # ---- variety: no dressing model more than twice in one map-camera view
    def room_for(self, v: dict, at) -> bool:
        if v["family"] in STRUCTURE_FAMILIES:
            return True
        m = model_id(v)
        vw, vd = self.view
        n = sum(1 for mm, a in self.placed_models if mm == m and abs(a[0] - at[0]) < vw and abs(a[1] - at[1]) < vd)
        limit = int((self.rules.get("repeats") or {}).get("per_view", 2))
        if v.get("kind") in ("vehicle", "tree") or v["role"] in ("kids_big", "corner", "patio_big"):
            limit = 1                          # two identical cars (or swing sets, sheds) in one picture read as cheap
        return n < limit

    def put(self, v: dict, at, turn: float, zone: str, lot, rng, allow_road=False, zones=None, why="",
            gap=GAP_M) -> bool:
        w, d = (float(x) for x in v["box_m"][:2])
        if not self.room_for(v, at):
            return False
        if v.get("kind") == "tree" and not self.room_for_crown(v, at):
            return False
        m = self.board.fits(at, w, d, turn, allow_road=allow_road, zones=zones, gap=gap)
        if m is None:
            return False
        self.board.take(m)
        n = len(self.items) + 1
        self.items.append({"id": f"dz_{n:03d}_{v['id']}", "kind": "vehicle" if v.get("kind") == "vehicle" else
                           ("tree" if v.get("kind") == "tree" else "prop"), "model": model_id(v),
                           "at": [round(float(at[0]), 2), round(float(at[1]), 2)], "turn": round(float(turn) % 360, 1),
                           "box_m": [w, d], "family": v["family"], "variant": v["id"], "zone": zone, "lot": lot,
                           "label": v["id"].replace("_", " "),
                           **({"species": v["species"], "seed": v.get("seed"), "crown_m": v.get("crown_m")}
                              if v.get("kind") == "tree" else {}),
                           "by": "dresser", **({"why": why} if why else {})})
        self.placed_models.append((model_id(v), (float(at[0]), float(at[1]))))
        return True

    def room_for_crown(self, v: dict, at) -> bool:
        """A tree's crown keeps off roofs and out of other crowns: its trunk stands 0.7 of its crown from any building
        and 0.6 of the two crowns from any other tree."""
        cr = float(v.get("crown_m") or 3.0)
        g, Z = self.board.g, self.board.Z
        near = (np.hypot(g.X - at[0], g.Y - at[1]) <= cr * 0.7) & (Z == ad.Z_BUILDING)
        if near.any():
            return False
        for t in self.plan_things:
            if t["kind"] == "tree" and math.hypot(t["at"][0] - at[0], t["at"][1] - at[1]) < (cr + max(t["w"], 3.0) / 2) * 0.6:
                return False
        for it in self.items:
            if it["kind"] == "tree" and math.hypot(it["at"][0] - at[0], it["at"][1] - at[1]) < (cr + (it.get("crown_m") or 3.0)) * 0.6:
                return False
        return True

    def pick(self, rng, roles, avoid=()) -> dict | None:
        pool = [v for r in roles for v in self.by_role.get(r, []) if v["id"] not in avoid]
        return rng.choice(pool) if pool else None

    def try_role(self, rng, roles, spots, zone, lot, turn_of, tries=24, zones=None, avoid=(), allow_road=False) -> bool:
        for _ in range(tries):
            v = self.pick(rng, roles, avoid)
            if not v or not spots:
                return False
            at = spots[rng.randrange(len(spots))]
            if self.put(v, at, turn_of(at) + rng.uniform(-12, 12), zone, lot, rng, allow_road=allow_road, zones=zones):
                return True
        return False

    def cells(self, mask) -> list:
        ys, xs = np.nonzero(mask)
        g = self.board.g
        return [(float(g.X[y, x]), float(g.Y[y, x])) for y, x in zip(ys, xs)]

    # ---- one home's lot
    def dress_lot(self, i: int, b: dict, rng: random.Random, character: str) -> None:
        g, Z, lot = self.board.g, self.board.Z, self.board.lot
        cx, cy = b["centre"]
        front = b["front"]
        if front:
            ux, uy = float(front[0]) - cx, float(front[1]) - cy
        elif b.get("facing"):
            ux, uy = b["facing"]
        else:
            road = self.board.road
            if not road.any():
                ux, uy = 0.0, 1.0
            else:
                d = np.where(road, np.hypot(g.X - cx, g.Y - cy), 1e9)
                ry, rx = np.unravel_index(int(np.argmin(d)), d.shape)
                ux, uy = float(g.X[ry, rx]) - cx, float(g.Y[ry, rx]) - cy
        n = math.hypot(ux, uy) or 1.0
        ux, uy = ux / n, uy / n
        vx, vy = -uy, ux
        hd = max(abs((px - cx) * ux + (py - cy) * uy) for px, py in b["pts"])
        hw = max(abs((px - cx) * vx + (py - cy) * vy) for px, py in b["pts"])
        out_t = face_turn(ux, uy)                       # facing the street
        back_t = face_turn(-ux, -uy)
        lid = b["id"]
        mine = lot == i
        front_cells = mine & (Z == ad.Z_FRONT)
        back_cells = mine & (Z == ad.Z_BACK)
        # the porch set: along the front face, facing out
        door = b["thing"].get("door")
        pc = (float(door[0]) + ux * 1.2, float(door[1]) + uy * 1.2) if door else (cx + ux * (hd + 1.1), cy + uy * (hd + 1.1))
        n_porch = {"immaculate": 3, "kept": rng.choice([2, 3]), "overgrown": 2}[character]
        got = 0
        for k in range(14):
            if got >= n_porch:
                break
            off = rng.uniform(-min(hw - 0.8, 3.2), min(hw - 0.8, 3.2))
            dist = rng.uniform(0.0, 1.0)
            at = (pc[0] + vx * off + ux * dist, pc[1] + vy * off + uy * dist)
            roles = ["porch", "porch_pair"] if got < 2 else ["porch_step", "porch_pair"]
            v = self.pick(rng, roles)
            if v and self.put(v, at, out_t + rng.uniform(-14, 14), "porch / step", lid, rng, why="the porch set"):
                got += 1
        # foundation planting along the front face (immaculate: more; overgrown: shaggier)
        n_found = {"immaculate": 4, "kept": 3, "overgrown": 2}[character]
        spots = [(cx + ux * (hd + rng.uniform(0.7, 1.4)) + vx * s, cy + uy * (hd + rng.uniform(0.7, 1.4)) + vy * s)
                 for s in np.linspace(-hw + 0.8, hw - 0.8, 9)]
        roles = ["foundation"] + (["edge"] if character == "overgrown" else [])
        for _ in range(n_found):
            self.try_role(rng, roles, spots, "front yard", lid, lambda a: out_t)
        # trees: an ornamental in front, one or two in the back (fruit, shade, the redwoods), each a different species
        if rng.random() < 0.75:
            self.try_role(rng, ["front_tree"], self.cells(front_cells), "front yard", lid, lambda a: rng.uniform(0, 360),
                          tries=30)
        for _ in range(rng.choice([1, 2, 2])):
            self.try_role(rng, ["back_tree"], self.cells(back_cells), "back / side yard", lid, lambda a: rng.uniform(0, 360),
                          tries=40)
        # the front yard toward its target
        self.fill(rng, front_cells, "front yard", lid, ["bed", "yard", "yard_front", "foundation"] +
                  (["kids"] if character != "immaculate" else []), "front_yard", character, lambda a: out_t)
        # the back: a patio by the back door, a kids' corner, a work corner, then fill
        bc = [(cx - ux * (hd + rng.uniform(1.6, 3.2)) + vx * rng.uniform(-hw * 0.6, hw * 0.6),
               cy - uy * (hd + rng.uniform(1.6, 3.2)) + vy * rng.uniform(-hw * 0.6, hw * 0.6)) for _ in range(30)]
        self.try_role(rng, ["patio"], bc, "back / side yard", lid, lambda a: back_t, tries=30)
        self.try_role(rng, ["patio"], bc, "back / side yard", lid, lambda a: back_t + 180, tries=20)
        back_list = self.cells(back_cells)
        if rng.random() < (0.35 if character == "immaculate" else 0.6):
            self.try_role(rng, ["kids_big", "kids"], back_list, "back / side yard", lid, lambda a: rng.uniform(0, 360), tries=30)
        self.try_role(rng, ["work", "corner"], back_list, "back / side yard", lid, lambda a: rng.uniform(0, 360), tries=30)
        self.fill(rng, back_cells, "back / side yard", lid, ["work", "yard", "patio", "kids", "bed", "shade", "edge",
                                                            "corner"], "back_yard", character,
                  lambda a: rng.uniform(0, 360))
        # fences: the back and side lot lines, a gate left by the house; front yards stay open (HOA)
        self.fence_lot(i, b, rng, character, (ux, uy))

    def fill(self, rng, mask, zone, lid, roles, target_key, character, turn_of) -> None:
        area = float(mask.sum()) * self.board.g.cell ** 2
        if area < 6:
            return
        lo, hi = ((self.rules.get("targets") or {}).get(target_key) or {}).get("per_100m2", [4, 8])
        aim = {"immaculate": lo + (hi - lo) * 0.45, "kept": lo + (hi - lo) * 0.55, "overgrown": lo + (hi - lo) * 0.8}[character]
        want = int(math.ceil(aim * area / 100.0))
        have = self.count_in(mask)
        cells = self.cells(mask)
        tries = 0
        while have < want and tries < want * 30 and cells:
            tries += 1
            # the emptiest spot first: lay things where the largest empty stretch is
            if tries % 3 == 0:
                at = self.emptiest(mask) or cells[rng.randrange(len(cells))]
            else:
                at = cells[rng.randrange(len(cells))]
            v = self.pick(rng, roles)
            if v and self.put(v, at, turn_of(at) + rng.uniform(-15, 15), zone, lid, rng):
                have += 1
        # then the largest empty stretch: lay things where it is, until it is within the target (or nothing fits)
        lim = ((self.rules.get("targets") or {}).get(target_key) or {}).get("largest_empty_m")
        if lim:
            for _ in range(12):
                gap, at = self.gap(mask)
                if gap <= float(lim) or at is None:
                    break
                placed = False
                for _k in range(10):
                    v = self.pick(rng, roles)
                    jit = (at[0] + rng.uniform(-0.8, 0.8), at[1] + rng.uniform(-0.8, 0.8))
                    if v and self.put(v, jit, turn_of(jit) + rng.uniform(-15, 15), zone, lid, rng, why="the empty stretch"):
                        placed = True
                        break
                if not placed:
                    self.board.take(np.hypot(self.board.g.X - at[0], self.board.g.Y - at[1]) <= 0.8)   # nothing fits: skip it

    def count_in(self, mask) -> int:
        n = 0
        for t in self.plan_things + [{"at": it["at"], "family": it["family"]} for it in self.items]:
            if t.get("family") in STRUCTURE_FAMILIES or ad.is_structure(t, self.rules):
                continue
            c = ad._cell_of(self.board.g, t["at"])
            if c and mask[c]:
                n += 1
        return n

    def gap(self, mask):
        """The largest empty stretch in a zone (metres, as the check measures it) and where its middle is."""
        occ = np.zeros(mask.shape, bool)
        for t in self.plan_things + [dict(it, w=it["box_m"][0], d=it["box_m"][1]) for it in self.items]:
            occ |= self.board.g.poly(ad.corners(t["at"], max(t["w"], 0.5), max(t["d"], 0.5), t["turn"]))
        occ |= (self.board.Z == ad.Z_BUILDING) | ~mask
        d = ad.distance(occ, self.board.g.cell)
        dm = np.where(mask & ~self.board.taken, d, -1)
        full = float(np.where(mask, d, 0).max()) * 2.0
        if dm.max() <= 0:
            return full, None
        y, x = np.unravel_index(int(np.argmax(dm)), dm.shape)
        return full, (float(self.board.g.X[y, x]), float(self.board.g.Y[y, x]))

    def emptiest(self, mask):
        occ = np.zeros(mask.shape, bool)
        for t in self.plan_things:
            c = ad._cell_of(self.board.g, t["at"])
            if c:
                occ[c] = True
        for it in self.items:
            c = ad._cell_of(self.board.g, it["at"])
            if c:
                occ[c] = True
        occ |= ~mask
        d = ad.distance(occ, self.board.g.cell)
        d = np.where(mask & ~self.board.taken, d, -1)
        if d.max() <= 0:
            return None
        y, x = np.unravel_index(int(np.argmax(d)), d.shape)
        return float(self.board.g.X[y, x]), float(self.board.g.Y[y, x])

    def fence_lot(self, i, b, rng, character, u) -> None:
        g, Z, lot = self.board.g, self.board.Z, self.board.lot
        back = (lot == i) & (Z == ad.Z_BACK)
        if not back.any():
            return
        pool = self.by_role.get("lot_line_back", []) + self.by_role.get("lot_line", [])
        if not pool:
            return
        if character == "overgrown":
            pool = [v for v in pool if "arborvitae" in v["id"] or "cedar" in v["id"] or "privacy" in v["id"]] or pool
        v = rng.choice(pool)
        piece = float(v["box_m"][0])
        # the outer edge of the back yard: its cells that touch another lot, the plan's edge, or open ground
        edge = np.zeros(back.shape, bool)
        for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            sh = np.zeros(back.shape, bool)
            ys = slice(max(0, dy), back.shape[0] + min(0, dy))
            yd = slice(max(0, -dy), back.shape[0] + min(0, -dy))
            xs = slice(max(0, dx), back.shape[1] + min(0, dx))
            xd = slice(max(0, -dx), back.shape[1] + min(0, -dx))
            sh[yd, xd] = back[ys, xs]
            neighbour_other = np.zeros(back.shape, bool)
            neighbour_other[yd, xd] = ~back[ys, xs] & (Z[ys, xs] != ad.Z_BUILDING) & (Z[ys, xs] != ad.Z_EXCLUDED)
            edge |= back & neighbour_other
        edge[0, :] |= back[0, :]
        edge[-1, :] |= back[-1, :]
        edge[:, 0] |= back[:, 0]
        edge[:, -1] |= back[:, -1]
        cx, cy = b["centre"]
        pts = [(float(g.X[y, x]), float(g.Y[y, x])) for y, x in zip(*np.nonzero(edge))]
        if not pts:
            return
        # runs: walk the edge points in order of angle round the house, lay a piece every `piece` metres
        pts.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
        last = None
        placed = 0
        for p in pts:
            if last is not None and math.hypot(p[0] - last[0], p[1] - last[1]) < piece * 0.98:
                continue
            # leave a gate near the house corners (within 2 m of the building's sides)
            rel = ((p[0] - cx) * u[0] + (p[1] - cy) * u[1])
            if abs(rel) < 1.0 and rng.random() < 0.5:
                last = p
                continue
            # the run's direction: toward the next edge point a piece away
            nxt = min((q for q in pts if piece * 0.6 < math.hypot(q[0] - p[0], q[1] - p[1]) < piece * 1.6),
                      key=lambda q: abs(math.hypot(q[0] - p[0], q[1] - p[1]) - piece), default=None)
            if nxt is None:
                last = p
                continue
            ang = math.degrees(math.atan2(nxt[1] - p[1], nxt[0] - p[0]))
            mid = ((p[0] + nxt[0]) / 2, (p[1] + nxt[1]) / 2)
            if self.put(v, mid, ang, "boundary", b["id"], rng, zones={ad.Z_BACK, ad.Z_OPEN, ad.Z_KERB, ad.Z_OUT},
                        why="a lot line"):
                placed += 1
                last = nxt
            else:
                last = p
        self.log.append(f"{b['id']}: {placed} pieces of {v['id']} along its back and side lines")

    # ---- the kerb and the street
    def dress_kerb(self, rng) -> None:
        g, Z = self.board.g, self.board.Z
        kerb = Z == ad.Z_KERB
        if not kerb.any():
            return
        road = self.board.road
        ys, xs = np.nonzero(road)
        if not len(xs):
            return
        lo, hi = ((self.rules.get("targets") or {}).get("kerb") or {}).get("m_between", [6, 10])
        # each kerb cell knows which way its road lies; kerbs facing the same way are split into runs by their
        # distance across (the main road's far side and a loop road's near side are different runs)
        k = int(math.ceil(float(self.rules.get("kerb_strip_m", 1.5)) / g.cell)) + 1

        def toward(dy, dx):
            m = np.zeros(road.shape, bool)
            for s_ in range(1, k + 1):
                sh = np.roll(road, (-dy * s_, -dx * s_), axis=(0, 1))
                if dy > 0: sh[-s_:, :] = False
                if dy < 0: sh[:s_, :] = False
                if dx > 0: sh[:, -s_:] = False
                if dx < 0: sh[:, :s_] = False
                m |= sh
            return kerb & m
        hydrant_done = False
        for (dy, dx) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            mask = toward(dy, dx)
            if not mask.any():
                continue
            along_x = dy != 0
            ys_k, xs_k = np.nonzero(mask)
            across = ys_k if along_x else xs_k
            runs, cur = [], [int(across.min())]
            for v_ in sorted(set(int(a_) for a_ in across))[1:]:
                if v_ - cur[-1] > int(2.0 / g.cell):
                    runs.append(cur); cur = []
                cur.append(v_)
            runs.append(cur)
            # the road's cell axis maps to world y the same way the grid's rows do
            facing = face_turn(0, 1 if dy > 0 else -1) if along_x else face_turn(1 if dx > 0 else -1, 0)
            for run in runs:
                sel = (across >= run[0]) & (across <= run[-1])
                pts = sorted(((float(g.X[y_, x_]), float(g.Y[y_, x_])) for y_, x_ in zip(ys_k[sel], xs_k[sel])),
                             key=lambda p_: p_[0] if along_x else p_[1])
                if len(pts) < 4:
                    continue
                key = (lambda p_: p_[0]) if along_x else (lambda p_: p_[1])
                x0, x1 = key(pts[0]), key(pts[-1])
                x = x0 + rng.uniform(0.5, 3.0)
                recent: list = []
                while x < x1:
                    near = [p_ for p_ in pts if abs(key(p_) - x) < 1.5 and not self.board.taken[ad._cell_of(g, p_)]]
                    placed = False
                    if near:
                        roles = ["kerb"] + (["kerb_corner"] if (x - x0 < 6 or x1 - x < 6) else [])
                        for _ in range(8):
                            v = self.pick(rng, roles, avoid=(("lm_fire_hydrant",) if hydrant_done else ()) + tuple(recent[-2:]))
                            at = near[rng.randrange(len(near))]
                            if v and self.put(v, at, facing + rng.uniform(-10, 10), "kerb strip", None, rng,
                                              zones={ad.Z_KERB, ad.Z_FRONT, ad.Z_OPEN, ad.Z_BACK}, why="the kerb",
                                              gap=0.05):      # a hydrant stands at the kerb, not a step back from it
                                hydrant_done = hydrant_done or v["id"] == "lm_fire_hydrant"
                                recent.append(v["id"])
                                placed = True
                                break
                    x += rng.uniform(lo, hi) if placed else 1.0
        horizontal = (xs.max() - xs.min()) >= (ys.max() - ys.min())
        if horizontal:
            x0, x1 = float(xs.min() * g.cell), float((xs.max() + 1) * g.cell)
            # cars parked at the kerb, on the road, parallel to it
            band = road & (np.abs(g.Y - (ys.min() * g.cell)) < 1.8) | road & (np.abs(g.Y - ((ys.max() + 1) * g.cell)) < 1.8)
            spots = self.cells(band)
            for _ in range(int(max(1, (x1 - x0) / 22))):
                for _ in range(20):
                    if not spots:
                        break
                    at = spots[rng.randrange(len(spots))]
                    v = self.pick(rng, ["car"])
                    if not v:
                        break
                    edge_y = ys.min() * g.cell if abs(at[1] - ys.min() * g.cell) < 1.8 else (ys.max() + 1) * g.cell
                    at = (at[0], edge_y + (1.1 if edge_y == ys.min() * g.cell else -1.1))
                    c = ad._cell_of(g, at)
                    li = int(self.board.lot[c]) if c else -1
                    if 0 <= li < len(self.zz["buildings"]) and self.zz["buildings"][li]["id"] in self.excluded:
                        continue                   # not in front of a lot William has fixed (Bill's)
                    if self.put(v, at, 90 + (180 if rng.random() < 0.5 else 0) + rng.uniform(-2, 2), "kerb strip", None,
                                rng, allow_road=True, zones={ad.Z_ROAD}, why="parked at the kerb"):
                        break

    def dress_edges(self, rng) -> None:
        """Japanese stiltgrass in shaded, disturbed edges (under trees, along the plan's wild edges); the field edge."""
        g, Z = self.board.g, self.board.Z
        trees = [t for t in self.plan_things if t["kind"] == "tree"]
        shade = np.zeros(Z.shape, bool)
        for t in trees:
            shade |= np.hypot(g.X - t["at"][0], g.Y - t["at"][1]) <= max(3.5, t["w"] * 0.6)
        wild = (Z == ad.Z_OPEN) | (Z == ad.Z_BACK)
        edge = (g.X < 3) | (g.Y < 3) | (g.X > g.W * g.cell - 3) | (g.Y > g.H * g.cell - 3)
        spots = self.cells(wild & (shade | edge))
        for _ in range(max(2, len(spots) // 160)):
            self.try_role(rng, ["shade_edge"], spots, "open lot", None, lambda a: rng.uniform(0, 360), tries=20,
                          zones={ad.Z_OPEN, ad.Z_BACK})
        # the old field's fence-row trees along the wild edges: red cedars, a tulip poplar
        for _ in range(3):
            self.try_role(rng, ["field_tree"], self.cells(wild & edge), "open lot", None, lambda a: rng.uniform(0, 360),
                          tries=30, zones={ad.Z_OPEN, ad.Z_BACK})
        open_cells = self.cells((Z == ad.Z_OPEN) & edge)
        for _ in range(max(1, len(open_cells) // 200)):
            self.try_role(rng, ["field"], open_cells, "open lot", None, lambda a: rng.uniform(0, 360), tries=20,
                          zones={ad.Z_OPEN})
        self.fill(rng, Z == ad.Z_OPEN, "open lot", None, ["field", "shade_edge", "edge"], "open_lot", "kept",
                  lambda a: rng.uniform(0, 360))

    def run(self) -> list[dict]:
        rng = random.Random(self.seed)
        ch = self.kit.get("characters") or {}
        weights = [("kept", ch.get("kept", 0.58)), ("overgrown", ch.get("overgrown", 0.25)),
                   ("immaculate", ch.get("immaculate", 0.17))]
        excluded = set(ad.place_rules(self.rules, self.zz["place"]).get("exclude_lots") or [])
        self.characters = {}
        skip = set(ad.place_rules(self.rules, self.zz["place"]).get("skip_buildings") or [])
        homes = [(i, b) for i, b in enumerate(self.zz["buildings"])
                 if b["kind"] == "home" and b["id"] not in excluded and b["id"] not in skip]
        self.mirror(excluded)
        # ◆ one hot tub in the court's back yards: the lot with the most back yard
        tub_lot = None
        if homes:
            areas = {i: int(((self.board.lot == i) & (self.board.Z == ad.Z_BACK)).sum()) for i, _ in homes}
            tub_lot = max(areas, key=areas.get) if max(areas.values()) * self.board.g.cell ** 2 > 40 else None
        tub_variants = [v for v in self.kit["variants"] if v["role"] == "patio_big"]
        # the kit's feature trees go in first, where there is most room (✦ William's list: the dawn redwood first)
        frng = random.Random(f"{self.seed}:features")
        open_like = np.isin(self.board.Z, [ad.Z_BACK, ad.Z_FRONT, ad.Z_OPEN])
        d_free = ad.distance(~open_like | self.board.taken, self.board.g.cell)
        g_ = self.board.g
        edge_d = np.minimum.reduce([g_.X, g_.W * g_.cell - g_.X, g_.Y, g_.H * g_.cell - g_.Y])
        d_free = np.minimum(d_free, edge_d)        # a feature tree is seen: not pushed into a corner of the plan
        for fid in self.kit.get("feature_trees") or []:
            v = next((x for x in self.kit["variants"] if x["id"] == fid), None)
            if not v:
                continue
            ys_, xs_ = np.nonzero(open_like & (d_free > 1.2))
            order = sorted(zip(ys_, xs_), key=lambda c: -d_free[c])[:200]
            frng.shuffle(order)
            order.sort(key=lambda c: -d_free[c])
            for y_, x_ in order[:120]:
                at = (float(self.board.g.X[y_, x_]), float(self.board.g.Y[y_, x_]))
                z = int(self.board.Z[y_, x_])
                li = int(self.board.lot[y_, x_])
                lid = self.zz["buildings"][li]["id"] if 0 <= li < len(self.zz["buildings"]) else None
                if lid in excluded:
                    continue
                if self.put(v, at, frng.uniform(0, 360), ad.ZONE_NAMES[z], lid, frng, why="a feature tree"):
                    break
        for i, b in homes:
            r = random.Random(f"{self.seed}:{b['id']}")
            x = r.random()
            acc = 0.0
            character = "kept"
            for name, w in weights:
                acc += w
                if x < acc:
                    character = name
                    break
            self.characters[b["id"]] = character
            if i == tub_lot and tub_variants:
                self.dress_tub(i, b, r, tub_variants[0])
            self.dress_lot(i, b, r, character)
        for i, b in enumerate(self.zz["buildings"]):
            if b["kind"] in ("shop", "bar", "civic") and b["id"] not in excluded:
                self.dress_shop(i, b, random.Random(f"{self.seed}:{b['id']}"))
                self.dress_service(i, b, random.Random(f"{self.seed}:{b['id']}:back"))
        self.dress_lots(random.Random(f"{self.seed}:lots"))
        self.dress_kerb(random.Random(f"{self.seed}:kerb"))
        self.dress_edges(random.Random(f"{self.seed}:edges"))
        return self.items

    def mirror(self, excluded) -> None:
        """A place that holds another place inside it (the street holds the court) shows the same yards: the other
        place's dressing, moved by the offset the rules give, goes in first, unchanged; the rest of its ground is held."""
        m = ad.place_rules(self.rules, self.zz["place"]).get("mirror_from")
        if not m or not self.places_dir:
            return
        src, (ox, oy) = m["place"], m["offset"]
        try:
            sp = json.loads((Path(self.places_dir) / f"{src}.place.json").read_text(encoding="utf-8"))
            so = Path(self.places_dir) / f"{src}.dressing_out.json"
            sitems = json.loads(so.read_text(encoding="utf-8")).get("items") if so.exists() else []
        except (OSError, ValueError):
            return
        have = {(t["model"], round(t["at"][0], 1), round(t["at"][1], 1)) for t in self.plan_things}
        n = 0
        # only the held place's dressing: its plan's own things come in with the plan (make_linden_mills_street.py
        # sets the court down whole), and `have` skips any that are already here
        for t in list(sitems or []):
            at = (float(t["at"][0]) + ox, float(t["at"][1]) + oy)
            if (str(t.get("model")), round(at[0], 1), round(at[1], 1)) in have:
                continue
            c = ad._cell_of(self.board.g, at)
            if not c:
                continue
            li = int(self.board.lot[c])
            if 0 <= li < len(self.zz["buildings"]) and self.zz["buildings"][li]["id"] in excluded:
                continue
            box = t.get("box_m") or [float((t.get("size_m") or {}).get("width") or 1.0)] * 2
            v = {"id": str(t.get("variant") or t.get("id")), "model": t["model"], "family": t.get("family") or "mirrored",
                 "role": "mirrored", "box_m": box[:2], "kind": t.get("kind") or "prop",
                 **({"species": t.get("species"), "seed": t.get("seed"), "crown_m": t.get("crown_m")} if t.get("species") else {})}
            # the held place already proved its own layout: its things go in where they are, held ground or not
            m_ = self.board.g.poly(ad.corners(at, float(box[0]), float(box[1]), float(t.get("turn") or 0)))
            if not m_.any():
                continue
            self.board.take(m_)
            k = len(self.items) + 1
            self.items.append({"id": f"dz_{k:03d}_{v['id']}", "kind": "vehicle" if v["kind"] == "vehicle" else
                               ("tree" if v["kind"] == "tree" else "prop"), "model": v["model"],
                               "at": [round(at[0], 2), round(at[1], 2)], "turn": round(float(t.get("turn") or 0) % 360, 1),
                               "box_m": [float(box[0]), float(box[1])], "family": v["family"], "variant": v["id"],
                               "zone": "mirrored", "lot": None, "label": str(t.get("label") or v["id"]),
                               "by": "dresser", "why": f"the same as {src} (mirrored)",
                               **({"species": v["species"], "seed": v["seed"], "crown_m": v["crown_m"]} if v.get("species") else {})})
            self.placed_models.append((v["model"], at))
            n += 1
        # nothing new goes inside the held place: the street's court must be the court the player walked
        sw, sh = (sp.get("size") or [0, 0])[:2]
        if sw and sh:
            self.board.taken |= self.board.g.rect([ox, oy, float(sw), float(sh)])
        self.log.append(f"mirrored {n} things from {src}; the rest of {src}'s ground is held as it is")

    def dress_shop(self, i, b, rng) -> None:
        """A shop's front: something every 2–3 m of frontage (benches, planters, boards, an ice chest), facing out."""
        g, Z, lot = self.board.g, self.board.Z, self.board.lot
        cells = (lot == i) & (Z == ad.Z_SHOP)
        if not cells.any():
            return
        front = b["front"] or b.get("facing")
        cx, cy = b["centre"]
        if b["front"]:
            ux, uy = float(front[0]) - cx, float(front[1]) - cy
        elif b.get("facing"):
            ux, uy = b["facing"]
        else:
            ys, xs = np.nonzero(cells)
            ux, uy = float(g.X[ys, xs].mean()) - cx, float(g.Y[ys, xs].mean()) - cy
        n_ = math.hypot(ux, uy) or 1.0
        out_t = face_turn(ux / n_, uy / n_)
        roles = ["shop_front"] + (["civic_front"] if b["kind"] == "civic" else []) + \
                (["station_front"] if "station" in str(b["thing"].get("label") or "") or "gas" in b["id"] or
                 "canopy" in b["id"] or "convenience" in b["id"] else [])
        key = "forecourt" if b["id"] in (ad.place_rules(self.rules, self.zz["place"]).get("open_rooms") or []) else "shop_front"
        self.fill(rng, cells, "shop front", b["id"], roles, key, "kept", lambda a: out_t)

    def dress_service(self, i, b, rng) -> None:
        """Behind a shop: bins, pallets, a condenser and the staff's smoking spot against the back wall; the rest of
        the ground a mown verge with a tree or two and the stiltgrass at its edge — not a yard."""
        g, Z, lot = self.board.g, self.board.Z, self.board.lot
        back = (lot == i) & (Z == ad.Z_BACK)
        if back.sum() * g.cell ** 2 < 6:
            return
        wall = ad.distance(Z == ad.Z_BUILDING, g.cell) <= 4.0
        cx, cy = b["centre"]
        self.fill(rng, back & wall, "back / side yard", b["id"], ["shop_back"], "service_wall", "kept",
                  lambda a: face_turn(cx - a[0], cy - a[1]) + 180)      # backs to the wall
        self.fill(rng, back, "back / side yard", b["id"], ["back_tree", "edge", "shade_edge", "field_tree"],
                  "service_back", "kept", lambda a: rng.uniform(0, 360))

    def dress_lots(self, rng) -> None:
        """Parking lots the rules name: cars nosed in, a light pole, an island with a tree."""
        for r in ad.place_rules(self.rules, self.zz["place"]).get("lot_rects") or []:
            x, y, w, h = (float(v) for v in r["rect"])
            nose = float(r.get("nose", 0))
            area = w * h
            want = int(area / 30)
            for _ in range(want * 6):
                if want <= 0:
                    break
                v = self.pick(rng, ["car", "lot_car"])
                if not v:
                    break
                at = (rng.uniform(x + 1.5, x + w - 1.5), rng.uniform(y + 3.0, y + h - 3.0))
                if self.put(v, at, nose + (180 if rng.random() < 0.3 else 0) + rng.uniform(-3, 3), "lot", None, rng,
                            allow_road=True, zones={ad.Z_ROAD, ad.Z_OPEN, ad.Z_SHOP, ad.Z_KERB}, why="parked in the lot"):
                    want -= 1
            for _ in range(max(1, int(w / 30))):
                self.try_role(rng, ["lot_light"], self.cells(self.board.g.rect([x, y, w, h])), "lot", None,
                              lambda a: 0.0, tries=20, allow_road=True, zones={ad.Z_ROAD, ad.Z_OPEN, ad.Z_SHOP, ad.Z_KERB})

    def dress_tub(self, i, b, rng, v) -> None:
        g = self.board.g
        cells = self.cells((self.board.lot == i) & (self.board.Z == ad.Z_BACK))
        cx, cy = b["centre"]
        cells.sort(key=lambda p: math.hypot(p[0] - cx, p[1] - cy))
        for at in cells[: max(10, len(cells) // 3)][::3]:
            if self.put(v, at, rng.uniform(0, 90), "back / side yard", b["id"], rng, why="the court's hot tub (Part 6)"):
                return


# ------------------------------------------------------------------------------------------------ files
def dress_place(places_dir: Path, pid: str, kit_path: Path, rules: dict, sizes: dict, seed: int = 1, view=(20.0, 21.0),
                write: bool = True) -> dict:
    place = json.loads((Path(places_dir) / f"{pid}.place.json").read_text(encoding="utf-8"))
    kit = load_kit(kit_path)
    d = Dresser(place, kit, rules, sizes, seed, view, places_dir)
    items = d.run()
    doc = {"_about": f"The dresser's output for {pid} (BUILD 97 Part 2 / BUILD 98; forge/threed/dresser.py, "
                     f"{datetime.now().isoformat(timespec='seconds')}). Placed like the plan's own things by the compiler. "
                     "Never edit by hand: change the kit or the seed and dress again. The plan's own things are not here "
                     "and are never moved.", "place": pid, "kit": Path(kit_path).name, "seed": seed,
           "characters": d.characters, "log": d.log, "items": items}
    if write:
        p = Path(places_dir) / f"{pid}.dressing_out.json"
        tmp = p.with_suffix(".json.part")
        tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, p)
        doc["file"] = str(p)
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The dresser (BUILD 97 Part 2)")
    sub = ap.add_subparsers(dest="cmd")
    a1 = sub.add_parser("dress")
    a1.add_argument("place")
    a1.add_argument("--places", required=True)
    a1.add_argument("--kit", required=True)
    a1.add_argument("--rules-game", default="")
    a1.add_argument("--wanted", default="")
    a1.add_argument("--stage", default="")
    a1.add_argument("--seed", type=int, default=1)
    a1.add_argument("--dry", action="store_true")
    a2 = sub.add_parser("kit-list")
    a2.add_argument("kit")
    a2.add_argument("--out", required=True)
    a2.add_argument("--wanted", default="")
    a = ap.parse_args(argv)
    if a.cmd == "dress":
        rules = ad.load_rules(Path(a.rules_game) if a.rules_game else None)
        sizes = ad.load_sizes(Path(a.wanted) if a.wanted else None)
        view = ad.camera_view(Path(a.stage) if a.stage else None, rules)
        doc = dress_place(Path(a.places), a.place, Path(a.kit), rules, sizes, a.seed, view, write=not a.dry)
        from collections import Counter
        print(f"{a.place}: {len(doc['items'])} things dressed; characters {doc['characters']}")
        print(dict(Counter(i['family'] for i in doc['items'])))
        for ln in doc["log"]:
            print("  " + ln)
        return 0
    if a.cmd == "kit-list":
        existing = set()
        if a.wanted:
            for f in Path(a.wanted).glob("*.json"):
                if f.name == Path(a.out).name:
                    continue
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                    existing |= {e["id"] for e in (d.get("entries") or []) if isinstance(e, dict) and e.get("id")}
                except (OSError, ValueError, AttributeError):
                    pass
        doc = kit_world_list(load_kit(a.kit), existing)
        out = Path(a.out)
        if out.exists():
            raise SystemExit(f"{out} exists: a world list already on disk changes only through a waiting package")
        out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{len(doc['entries'])} new models -> {out}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
