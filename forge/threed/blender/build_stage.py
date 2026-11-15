"""Compile a scene plan into a stage model.

    <Blender's Python> build_stage.py --plan <plan.json> --out <model.glb> [--skip id,id]
    blender --background --factory-startup --python build_stage.py -- --plan <plan.json> --out <model.glb> [--skip id,id]

Moved into the forge from the game's stage proof (BUILD 34; Fable wrote it, 2026-11-12) as the `compile_place` step;
it prints one machine line at the end, `STAGE {"faces", "meshes", "solids", "out"}`.

A scene plan (the same JSON the block-out reads) lists solids: a rectangle or a circle on the floor, a height, a
material word and an id. This turns each one into a modelled thing of the same footprint and height -- a chair has
legs and a back, a counter has doors, a wall has window frames -- and writes one .glb. Lights, floors and people are
not in the model: the engine reads those from the plan itself.

Built with bmesh (no bpy.ops while modelling), one mesh per material. The mesh carries the plan's material word as
its material name, and the engine dresses it by that name. A mesh whose name starts with N_ casts no shadow (a lamp
shade, a screen). Plan east is +X, plan north is +Y, up is +Z; the exporter turns that to the engine's Y-up.
"""
import json
import math
import random
import sys

import bpy                      # first: the others come with it
import bmesh
from mathutils import Matrix, Vector, noise

GROUPS = {}          # (material word, casts a shadow) -> {"v": [...], "f": [...]}
WALL_H = 3.0
RNG = random.Random(33)


# ------------------------------------------------------------------------------------------------ primitives
class Piece:
    """Parts modelled around the origin (front = south = -Y), then set down at a place and turned."""

    def __init__(self, x=0.0, y=0.0, rot=0.0):
        self.m = Matrix.Translation(Vector((x, -y, 0.0))) @ Matrix.Rotation(rot, 4, 'Z')

    def _emit(self, bm, mat, cast, local=None):
        m = self.m @ local if local is not None else self.m
        g = GROUPS.setdefault((mat, cast), {"v": [], "f": []})
        base = len(g["v"])
        bm.verts.index_update()
        g["v"].extend(tuple(m @ v.co) for v in bm.verts)
        g["f"].extend(tuple(base + v.index for v in f.verts) for f in bm.faces)
        bm.free()

    def box(self, x, y, w, d, z0, h, mat, bevel=0.012, seg=2, cast=True, turn=0.0):
        """A box centred on (x, y), w wide (east-west), d deep, standing from z0 to z0 + h."""
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(w, d, h), verts=bm.verts)
        b = min(bevel, 0.45 * min(w, d, h))
        if b > 0.0015:
            bmesh.ops.bevel(bm, geom=bm.edges[:], offset=b, offset_type='OFFSET', segments=seg, profile=0.5,
                            affect='EDGES', clamp_overlap=True)
        local = Matrix.Translation(Vector((x, y, z0 + h * 0.5))) @ Matrix.Rotation(turn, 4, 'Z')
        self._emit(bm, mat, cast, local)

    def rect(self, x, y, w, d, z0, h, mat, **kw):
        """The same, given the way a plan gives it: the north-west corner, in plan coordinates."""
        self.box(x + w * 0.5, -(y + d * 0.5), w, d, z0, h, mat, **kw)

    def cyl(self, x, y, r, z0, h, mat, seg=20, r_top=None, caps=True, cast=True, axis='Z'):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=seg, radius1=r,
                              radius2=r if r_top is None else r_top, depth=h)
        local = Matrix.Translation(Vector((x, y, z0 + h * 0.5)))
        if axis == 'X':
            local = Matrix.Translation(Vector((x, y, z0))) @ Matrix.Rotation(math.radians(90.0), 4, 'Y')
        elif axis == 'Y':
            local = Matrix.Translation(Vector((x, y, z0))) @ Matrix.Rotation(math.radians(90.0), 4, 'X')
        self._emit(bm, mat, cast, local)

    def blob(self, x, y, z, r, mat, squash=(1.0, 1.0, 0.8), rough=0.2, sub=2, cast=True):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
        off = Vector((RNG.uniform(-50, 50), RNG.uniform(-50, 50), RNG.uniform(-50, 50)))
        for v in bm.verts:
            v.co *= 1.0 + rough * noise.noise(v.co * 1.6 + off)
        bmesh.ops.scale(bm, vec=(r * squash[0], r * squash[1], r * squash[2]), verts=bm.verts)
        self._emit(bm, mat, cast, Matrix.Translation(Vector((x, y, z))) @ Matrix.Rotation(RNG.uniform(0, 6.28), 4, 'Z'))

    def torus(self, x, y, z, big, small, mat, upright=False, seg=20, ring=8):
        bm = bmesh.new()
        rows = []
        for i in range(seg):
            a = math.tau * i / seg
            rows.append([bm.verts.new(((big + small * math.cos(math.tau * j / ring)) * math.cos(a),
                                       (big + small * math.cos(math.tau * j / ring)) * math.sin(a),
                                       small * math.sin(math.tau * j / ring))) for j in range(ring)])
        for i in range(seg):
            for j in range(ring):
                bm.faces.new((rows[i][j], rows[(i + 1) % seg][j], rows[(i + 1) % seg][(j + 1) % ring], rows[i][(j + 1) % ring]))
        local = Matrix.Translation(Vector((x, y, z)))
        if upright:
            local = local @ Matrix.Rotation(math.radians(90.0), 4, 'X')
        self._emit(bm, mat, True, local)


WORLD = Piece()                                        # parts given straight in plan coordinates


def centre(s):
    if "rect" in s:
        r = s["rect"]
        return r[0] + r[2] * 0.5, r[1] + r[3] * 0.5
    return s["cyl"][0], s["cyl"][1]


def turn_for(dx, dy):
    """The angle that turns a piece's front (south) to face along (dx, dy) in plan coordinates."""
    if abs(dx) > abs(dy):
        return math.radians(90.0) if dx > 0 else math.radians(-90.0)
    return 0.0 if dy > 0 else math.radians(180.0)


def local_size(s, rot):
    r = s["rect"]
    side = abs(math.sin(rot)) > 0.5
    return (r[3], r[2]) if side else (r[2], r[3])


# ------------------------------------------------------------------------------------------------ furniture
def legs(p, w, d, h, mat, t=0.05, inset=0.04):
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box(sx * (w * 0.5 - inset - t * 0.5), sy * (d * 0.5 - inset - t * 0.5), t, t, 0.0, h, mat, bevel=0.006)


def table(p, w, d, h, mat, shelf=False, planks=0):
    top = 0.05
    if planks:
        pw = w / planks
        for i in range(planks):
            p.box(-w * 0.5 + pw * (i + 0.5), 0.0, pw - 0.02, d, h - top, top, mat, bevel=0.008)
    else:
        p.box(0.0, 0.0, w, d, h - top, top, mat, bevel=0.012)
    p.box(0.0, 0.0, w - 0.16, d - 0.16, h - top - 0.09, 0.09, "wood", bevel=0.004)
    legs(p, w, d, h - top, "wood", t=0.07)
    if shelf:
        p.box(0.0, 0.0, w - 0.2, d - 0.2, 0.12, 0.03, mat, bevel=0.006)


def chair(p, w, d, h, mat, rockers=False):
    seat = max(0.42, h - 0.05)
    legs(p, w, d, seat, "wood", t=0.045, inset=0.02)
    p.box(0.0, 0.0, w, d, seat, 0.05, mat, bevel=0.014, seg=3)
    back_y = d * 0.5 - 0.045
    for sx in (-1, 1):
        p.box(sx * (w * 0.5 - 0.045), back_y, 0.045, 0.045, seat, 0.55, "wood", bevel=0.006)
    for z in (0.2, 0.38):
        p.box(0.0, back_y, w - 0.1, 0.025, seat + z, 0.1, mat, bevel=0.008)
    if rockers:
        for sx in (-1, 1):
            p.box(sx * (w * 0.5 - 0.04), 0.0, 0.04, d + 0.35, 0.0, 0.035, "wood", bevel=0.01)


def soft_seat(p, w, d, h, mat, arms=True):
    """The seat half of a couch or an armchair: a base, seat cushions, arms at the two ends."""
    arm = 0.17 if arms else 0.0
    p.box(0.0, 0.0, w, d, 0.06, h * 0.5, mat, bevel=0.03, seg=3)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box(sx * (w * 0.5 - 0.07), sy * (d * 0.5 - 0.07), 0.06, 0.06, 0.0, 0.07, "wood", bevel=0.004)
    inner = w - 2 * arm
    n = max(1, round(inner / 0.9))
    cw = inner / n
    for i in range(n):
        p.box(-inner * 0.5 + cw * (i + 0.5), -0.02, cw - 0.015, d - 0.02, h * 0.5 + 0.04, h * 0.5, mat, bevel=0.07, seg=4)
    if arms:
        for sx in (-1, 1):
            p.box(sx * (w * 0.5 - arm * 0.5), 0.0, arm, d + 0.04, 0.06, h + 0.2, mat, bevel=0.06, seg=4)


def soft_back(p, w, d, h, mat):
    p.box(0.0, 0.0, w, d, 0.06, h * 0.82, mat, bevel=0.05, seg=4)
    inner = w - 0.34
    n = max(1, round(inner / 0.9))
    cw = inner / n
    for i in range(n):
        p.box(-inner * 0.5 + cw * (i + 0.5), -d * 0.35, cw - 0.02, d * 0.9, 0.42, h - 0.4, mat, bevel=0.09, seg=4)


def cabinet(p, w, d, z0, h, mat, top=None, kick=True, oven=None):
    """A run of cupboards: doors on the front, a toe space, a worktop if it has one."""
    k = 0.1 if (kick and z0 < 0.01) else 0.0
    p.box(0.0, 0.0, w, d, z0 + k, h - k, mat, bevel=0.006)
    if k:
        p.box(0.0, 0.03, w - 0.02, d - 0.08, z0, k, "cut", bevel=0.0)
    n = max(1, round(w / 0.6))
    dw = w / n
    for i in range(n):
        x = -w * 0.5 + dw * (i + 0.5)
        if oven and oven[0] - 0.01 <= x <= oven[1] + 0.01:
            continue
        p.box(x, -d * 0.5 - 0.009, dw - 0.03, 0.02, z0 + k + 0.03, h - k - 0.07, mat, bevel=0.01, seg=3)
        side = 1 if i % 2 == 0 else -1
        p.box(x + side * (dw * 0.5 - 0.07), -d * 0.5 - 0.03, 0.022, 0.03, z0 + (h * 0.72 if z0 < 0.5 else 0.12), 0.11,
              "metal", bevel=0.006)
    if oven:
        ox, ow = (oven[0] + oven[1]) * 0.5, oven[1] - oven[0]
        p.box(ox, -d * 0.5 - 0.012, ow - 0.02, 0.03, z0 + k, h - k - 0.02, "appliance", bevel=0.012, seg=3)
        p.box(ox, -d * 0.5 - 0.03, ow * 0.7, 0.012, z0 + 0.3, 0.34, "rack", bevel=0.006)
        p.box(ox, -d * 0.5 - 0.055, ow * 0.74, 0.025, z0 + 0.72, 0.025, "metal", bevel=0.008, seg=3)
    if top:
        p.box(0.0, -0.015, w + 0.03, d + 0.05, z0 + h, 0.045, top, bevel=0.012, seg=3)


def fridge(p, w, d, h):
    p.box(0.0, 0.0, w, d, 0.02, h - 0.02, "appliance", bevel=0.025, seg=3)
    split = h * 0.66
    p.box(0.0, -d * 0.5 - 0.012, w - 0.02, 0.03, 0.06, split - 0.07, "appliance", bevel=0.014, seg=3)
    p.box(0.0, -d * 0.5 - 0.012, w - 0.02, 0.03, split + 0.01, h - split - 0.03, "appliance", bevel=0.014, seg=3)
    for z0, hh in ((split - 0.55, 0.5), (split + 0.06, 0.3)):
        p.box(-w * 0.5 + 0.1, -d * 0.5 - 0.05, 0.025, 0.03, z0, hh, "metal", bevel=0.01, seg=3)


def bed(p, w, d, h):
    """w across, d from the head (north, +Y) to the foot (south)."""
    p.box(0.0, 0.0, w, d, 0.1, 0.2, "wood", bevel=0.012)
    legs(p, w, d, 0.1, "wood", t=0.08, inset=0.0)
    p.box(0.0, 0.0, w - 0.06, d - 0.06, 0.3, h - 0.3, "bed", bevel=0.07, seg=4)
    p.box(0.0, -d * 0.16, w + 0.05, d * 0.7, h - 0.07, 0.11, "quilt", bevel=0.05, seg=4)
    p.box(0.0, d * 0.19 + 0.02, w + 0.03, 0.2, h - 0.03, 0.09, "bed", bevel=0.04, seg=4)


def window(p, x, y, w, z0, h, pane):
    """A window on a wall's south face: x is its left edge and y the face, both in plan coordinates."""
    cx, fy = x + w * 0.5, -y
    p.box(cx, fy - 0.012, w, 0.02, z0, h, pane, bevel=0.0, cast=False)
    f = 0.07
    for dx in (-(w * 0.5 + f * 0.5), w * 0.5 + f * 0.5):
        p.box(cx + dx, fy - 0.03, f, 0.07, z0 - f, h + 2 * f, "wood_light", bevel=0.01)
    for zz in (z0 - f, z0 + h):
        p.box(cx, fy - 0.03, w, 0.07, zz, f, "wood_light", bevel=0.01)
    p.box(cx, fy - 0.025, 0.035, 0.035, z0, h, "wood_light", bevel=0.005)
    p.box(cx, fy - 0.025, w, 0.035, z0 + h * 0.5 - 0.017, 0.035, "wood_light", bevel=0.005)
    p.box(cx, fy - 0.07, w + 0.24, 0.14, z0 - f - 0.035, 0.035, "wood_light", bevel=0.01)


def fence(p, r, h):
    along_x = r[2] >= r[3]
    length = r[2] if along_x else r[3]
    n = max(2, int(length / 0.19))
    step = length / n
    for i in range(n):
        t = step * (i + 0.5)
        hh = h + RNG.uniform(-0.04, 0.03)
        if along_x:
            p.rect(r[0] + t - 0.075, r[1] + 0.05, 0.15, 0.03, 0.04, hh, "fence", bevel=0.008)
        else:
            p.rect(r[0] + 0.05, r[1] + t - 0.075, 0.03, 0.15, 0.04, hh, "fence", bevel=0.008)
    for z in (0.35, h - 0.3):
        if along_x:
            p.rect(r[0], r[1] + 0.08, r[2], 0.05, z, 0.09, "wood", bevel=0.006)
        else:
            p.rect(r[0] + 0.08, r[1], 0.05, r[3], z, 0.09, "wood", bevel=0.006)
    posts = max(2, int(length / 2.2) + 1)
    for i in range(posts):
        t = length * i / (posts - 1)
        px, py = (r[0] + t, r[1] + 0.1) if along_x else (r[0] + 0.1, r[1] + t)
        p.box(px, -py, 0.11, 0.11, 0.0, h + 0.08, "wood", bevel=0.01)
        p.box(px, -py, 0.15, 0.15, h + 0.08, 0.04, "wood", bevel=0.012)


def tree(p, s, canopy):
    x, y, r = s["cyl"]
    h = float(s["h"])
    p.cyl(x, -y, r * 0.62, 0.0, h + 0.6, "bark", seg=14, r_top=r * 0.36)
    p.cyl(x, -y, r * 0.95, 0.0, 0.5, "bark", seg=14, r_top=r * 0.6)
    for i in range(5):
        a = math.tau * i / 5 + 0.4
        p.blob(x + math.cos(a) * r * 0.8, -y + math.sin(a) * r * 0.8, 0.12, r * 0.42, "bark", squash=(1.3, 0.7, 0.5), rough=0.3)
    if canopy:
        cr, z = canopy["cyl"][2], float(canopy.get("z", h))
        for i in range(26):
            a = RNG.uniform(0, math.tau)
            d = math.sqrt(RNG.random()) * cr * 0.82
            up = RNG.uniform(0.2, 2.3) * (1.0 - 0.45 * d / cr)
            p.blob(x + math.cos(a) * d, -y + math.sin(a) * d, z + up, cr * RNG.uniform(0.27, 0.42), "leaves",
                   squash=(1.0, 1.0, 0.72), rough=0.34, sub=2)


# ------------------------------------------------------------------------------------------------ the plan
def build(plan, skip=()):
    solids = [s for s in plan.get("solids", []) if s.get("id") not in set(skip)]
    by_id = {s.get("id", ""): s for s in solids}
    tables = [s for s in solids if any(k in s.get("id", "") for k in ("table", "desk")) and "rect" in s]
    canopies = {i.replace("_canopy", ""): s for i, s in by_id.items() if i.endswith("_canopy")}
    for s in solids:
        sid, mat = s.get("id", ""), s["mat"]
        z0, h = float(s.get("z", 0.0)), float(s.get("h", 0.0))
        cx, cy = centre(s)
        glow = mat.startswith("glow_")

        # ---- the shell
        if sid == "chimney":
            r = s["rect"]
            fb = next((f for f in s.get("face", []) if f["mat"] == "firebox"), None)
            rk = next((f for f in s.get("face", []) if f["mat"] == "rack"), None)
            if fb:
                x0, x1, fh = fb["x"], fb["x"] + fb["w"], fb["h"]
                WORLD.rect(r[0], r[1], x0 - r[0], r[3], 0.0, fh, mat, bevel=0.03)
                WORLD.rect(x1, r[1], r[0] + r[2] - x1, r[3], 0.0, fh, mat, bevel=0.03)
                WORLD.rect(r[0], r[1], r[2], r[3], fh, 0.5, mat, bevel=0.03)
                WORLD.rect(r[0] + 0.45, r[1], r[2] - 0.9, r[3] - 0.25, fh + 0.5, h - fh - 0.5, mat, bevel=0.03)
                WORLD.rect(x0, r[1], fb["w"], 0.3, 0.0, fh, "firebox", bevel=0.0)
                WORLD.rect(x0, r[1] + 0.3, fb["w"], r[3] - 0.3, 0.0, 0.03, "firebox", bevel=0.0)
                WORLD.rect(r[0] - 0.25, r[1] + r[3], r[2] + 0.5, 0.75, 0.0, 0.07, "stone", bevel=0.02)
            else:
                WORLD.rect(r[0], r[1], r[2], r[3], 0.0, h, mat, bevel=0.03)
            if rk:
                ry = r[1] + 0.38
                WORLD.rect(rk["x"], ry, rk["w"], r[3] - 0.5, rk.get("z", 0.0), rk["h"], "rack", bevel=0.02)
                front = ry + r[3] - 0.5
                for f in s.get("face", []):
                    if f["mat"].startswith("glow_"):
                        WORLD.rect(f["x"], front, f["w"], 0.02, f.get("z", 0.0), f["h"], f["mat"], bevel=0.004, cast=False)
                for i in range(8):                                    # the small lights of a machine that is awake
                    WORLD.rect(rk["x"] + 0.14 + i * 0.09, front, 0.03, 0.012, rk.get("z", 0.0) + rk["h"] - 0.14, 0.03,
                               "glow_cyan" if i % 3 else "glow_warm", bevel=0.0, cast=False)
            continue
        if sid.startswith("wall"):
            r = s["rect"]
            WORLD.rect(r[0], r[1], r[2], r[3], 0.0, h, mat, bevel=0.01)
            if s.get("top"):
                WORLD.rect(r[0], r[1], r[2], r[3], h, 0.02, s["top"], bevel=0.0)
            face_y = r[1] + r[3]
            WORLD.rect(r[0], face_y, r[2], 0.025, 0.0, 0.14, "wood_light", bevel=0.008)
            for f in s.get("face", []):
                fz = float(f.get("z", 0.0))
                if f["mat"].startswith("window"):
                    window(WORLD, f["x"], face_y, f["w"], fz, f["h"], f["mat"])
                else:
                    WORLD.rect(f["x"] - 0.03, face_y, f["w"] + 0.06, 0.03, fz - 0.03, f["h"] + 0.06, "wood", bevel=0.008)
                    WORLD.rect(f["x"], face_y + 0.02, f["w"], 0.015, fz, f["h"], f["mat"], bevel=0.0)
            continue
        if mat == "cut":
            r = s["rect"]
            WORLD.rect(r[0], r[1], r[2], r[3], 0.0, h, mat, bevel=0.02)
            continue
        if sid.startswith("fence"):
            fence(WORLD, s["rect"], h)
            continue
        if sid.startswith("stair"):
            r = s["rect"]
            WORLD.rect(r[0], r[1], r[2], r[3], 0.0, h - 0.04, mat, bevel=0.006)
            WORLD.rect(r[0] - 0.02, r[1], r[2] + 0.04, r[3] + 0.04, h - 0.04, 0.04, "wood_light", bevel=0.012, seg=3)
            continue
        if sid == "newel" or sid.startswith("porch_post"):
            t = 0.14
            WORLD.box(cx, -cy, t, t, 0.0, h, mat, bevel=0.012)
            WORLD.box(cx, -cy, t + 0.06, t + 0.06, 0.0, 0.16, mat, bevel=0.014)
            WORLD.box(cx, -cy, t + 0.06, t + 0.06, h, 0.05, mat, bevel=0.014)
            if sid == "newel":
                WORLD.blob(cx, -cy, h + 0.11, 0.075, mat, squash=(1, 1, 1), rough=0.0)
            continue

        # ---- things that grow, and the yard
        if sid.endswith("_trunk"):
            tree(WORLD, s, canopies.get(sid.replace("_trunk", "")))
            continue
        if sid.endswith("_canopy"):
            continue
        if sid == "well":
            x, y, rr = s["cyl"]
            WORLD.cyl(x, -y, rr, 0.0, h, mat, seg=18)
            WORLD.cyl(x, -y, rr + 0.05, h - 0.1, 0.1, mat, seg=18)
            WORLD.cyl(x, -y, rr - 0.08, h, 0.04, s.get("top", "wood"), seg=18)
            continue
        if sid == "pump":
            x, y, rr = s["cyl"]
            WORLD.cyl(x, -y, 0.05, z0, h, mat, seg=10)
            WORLD.box(x + 0.14, -y, 0.26, 0.05, z0 + h - 0.22, 0.05, mat, bevel=0.012, seg=3)
            WORLD.box(x - 0.2, -y, 0.4, 0.03, z0 + h - 0.06, 0.03, mat, bevel=0.01, seg=3)
            continue
        if sid == "fire_pit":
            x, y, rr = s["cyl"]
            WORLD.cyl(x, -y, rr * 0.8, 0.0, 0.05, "firebox", seg=16)
            for i in range(10):
                a = math.tau * i / 10
                WORLD.blob(x + math.cos(a) * rr * 0.85, -y + math.sin(a) * rr * 0.85, 0.11, 0.2, "stone", squash=(1.0, 1.0, 0.75), rough=0.3)
            for a in (0.3, 2.4, 4.4):
                WORLD.box(x, -y, rr * 1.1, 0.1, 0.06, 0.1, "bark", bevel=0.04, seg=3, turn=a)
            continue
        if sid == "tire_swing":
            x, y, rr = s["cyl"]
            WORLD.torus(x, -y, z0 + rr + 0.1, rr - 0.1, 0.1, "rack", upright=True)
            WORLD.cyl(x, -y, 0.014, z0 + 2 * rr + 0.05, 2.6, "wood_light", seg=6)
            continue
        if sid == "log_seat":
            r = s["rect"]
            WORLD.cyl(cx, -cy, r[3] * 0.5, h * 0.5 + 0.02, r[2], mat, seg=14, axis='X')
            continue
        if sid.startswith("bed_") and s.get("top") == "leaves":
            r = s["rect"]
            t = 0.07
            WORLD.rect(r[0], r[1], r[2], t, 0.0, h, mat, bevel=0.01)
            WORLD.rect(r[0], r[1] + r[3] - t, r[2], t, 0.0, h, mat, bevel=0.01)
            WORLD.rect(r[0], r[1], t, r[3], 0.0, h, mat, bevel=0.01)
            WORLD.rect(r[0] + r[2] - t, r[1], t, r[3], 0.0, h, mat, bevel=0.01)
            WORLD.rect(r[0] + t, r[1] + t, r[2] - 2 * t, r[3] - 2 * t, 0.0, h - 0.05, "garden", bevel=0.0)
            for row in range(2):
                for i in range(6):
                    WORLD.blob(r[0] + 0.25 + i * (r[2] - 0.5) / 5, -(r[1] + 0.3 + row * (r[3] - 0.6)), h + 0.06,
                               RNG.uniform(0.11, 0.17), "leaves", squash=(1.0, 1.0, 0.9), rough=0.4, sub=1)
            continue
        if sid == "ac_unit":
            r = s["rect"]
            WORLD.rect(r[0], r[1], r[2], r[3], 0.05, h - 0.05, mat, bevel=0.02)
            for i in range(9):
                WORLD.rect(r[0] + 0.08, r[1] + r[3], r[2] - 0.16, 0.015, 0.16 + i * 0.085, 0.03, "rack", bevel=0.0)
            WORLD.cyl(cx, -cy, min(r[2], r[3]) * 0.36, h, 0.02, "rack", seg=18)
            continue

        # ---- furniture: modelled facing south, then turned
        if "rect" in s:
            r = s["rect"]
            base = sid.rsplit("_", 1)[0]
            rot = 0.0
            if sid.endswith("_seat") and (base + "_back") in by_id:
                bx, by = centre(by_id[base + "_back"])
                rot = turn_for(cx - bx, cy - by)
            elif sid.endswith("_back") and (base + "_seat") in by_id:
                sx, sy = centre(by_id[base + "_seat"])
                rot = turn_for(sx - cx, sy - cy)
            elif "chair" in sid or sid == "rocker":
                near = min(tables, key=lambda t: (centre(t)[0] - cx) ** 2 + (centre(t)[1] - cy) ** 2, default=None)
                if near is not None and (centre(near)[0] - cx) ** 2 + (centre(near)[1] - cy) ** 2 < 6.0:
                    rot = turn_for(centre(near)[0] - cx, centre(near)[1] - cy)
            elif sid == "bed" and "headboard" in by_id:
                hx, hy = centre(by_id["headboard"])
                rot = turn_for(cx - hx, cy - hy)
            elif sid in ("headboard", "pillow") and "bed" in by_id:
                bx, by = centre(by_id["bed"])
                hx, hy = centre(by_id["headboard"]) if "headboard" in by_id else (cx, cy)
                rot = turn_for(bx - hx, by - hy)
            p = Piece(cx, cy, rot)
            w, d = local_size(s, rot)
            if sid.endswith("_seat") and (base + "_back") in by_id:
                soft_seat(p, w, d, h, mat)
            elif sid.endswith("_back") and (base + "_seat") in by_id:
                soft_back(p, w, d, h, mat)
            elif sid == "window_seat":
                p.box(0, 0, w, d, 0.0, h - 0.1, "wood", bevel=0.012)
                p.box(0, 0, w - 0.04, d - 0.04, h - 0.1, 0.12, mat, bevel=0.05, seg=4)
            elif sid == "porch_swing":
                p.box(0, 0, w, d, z0 + 0.42, 0.05, "wood_light", bevel=0.012)
                for i in range(4):
                    p.box(0, d * 0.5 - 0.03, w, 0.03, z0 + 0.55 + i * 0.13, 0.09, "wood_light", bevel=0.008)
                for sx in (-1, 1):
                    p.box(sx * (w * 0.5 - 0.03), 0.0, 0.05, d, z0 + 0.6, 0.05, "wood_light", bevel=0.01)
                    p.cyl(sx * (w * 0.5 - 0.03), 0.0, 0.012, z0 + 0.6, 1.9, "metal", seg=6)
            elif "chair" in sid or sid == "rocker":
                chair(p, w, d, h, mat, rockers=(sid == "rocker"))
            elif sid == "bed":
                bed(p, w, d, h)
            elif sid == "headboard":
                p.box(0, 0, w, d * 0.5, 0.25, h - 0.25, mat, bevel=0.02, seg=3)
                for sx in (-1, 1):
                    p.box(sx * (w * 0.5 - 0.04), 0, 0.09, 0.09, 0.0, h + 0.1, mat, bevel=0.012)
                    p.box(sx * (w * 0.5 - 0.04), 0, 0.12, 0.12, h + 0.1, 0.035, mat, bevel=0.012)
            elif sid == "pillow":
                n = 2 if w > 1.0 else 1
                pw = w / n
                for i in range(n):
                    p.box(-w * 0.5 + pw * (i + 0.5), 0.0, pw - 0.06, d, z0 + 0.02, h + 0.03, mat, bevel=0.07, seg=4,
                          turn=RNG.uniform(-0.12, 0.12))
            elif sid == "fridge":
                fridge(p, w, d, h)
            elif mat == "cabinet" or sid == "tv_console":
                ov = next((f for f in s.get("face", []) if f["mat"] == "appliance"), None)
                cabinet(p, w, d, z0, h, mat, top=s.get("top"), kick=(mat == "cabinet"),
                        oven=(ov["x"] - cx, ov["x"] + ov["w"] - cx) if ov else None)
            elif sid == "tv":
                p.box(0, 0, w, 0.06, z0 + 0.12, h - 0.12, mat, bevel=0.014, seg=3)
                p.box(0, -0.034, w - 0.07, 0.01, z0 + 0.155, h - 0.19, "screen", bevel=0.0, cast=False)
                p.box(0, 0, 0.5, 0.2, z0, 0.02, mat, bevel=0.008)
                p.box(0, 0.01, 0.07, 0.04, z0, 0.14, mat, bevel=0.006)
            elif "picnic" in sid:
                table(p, w, d, h, mat, planks=5)
            elif sid.startswith("bench_"):
                p.box(0, 0, w, d, h - 0.05, 0.05, mat, bevel=0.012)
                for sx in (-1, 1):
                    p.box(sx * (w * 0.5 - 0.2), 0, 0.07, d - 0.04, 0.0, h - 0.05, "wood", bevel=0.008)
            elif "table" in sid or sid == "desk" or sid == "hobby_bench":
                table(p, w, d, h, mat, shelf=(h < 0.5 or sid == "hobby_bench"))
                if sid == "desk":
                    p.box(w * 0.5 - 0.27, 0.0, 0.4, d - 0.14, h - 0.5, 0.36, mat, bevel=0.008)
                    for i in range(2):
                        p.box(w * 0.5 - 0.27, -d * 0.5 + 0.06, 0.34, 0.02, h - 0.47 + i * 0.17, 0.14, mat, bevel=0.008)
            elif sid == "toy_chest":
                p.box(0, 0, w, d, 0.0, h - 0.12, mat, bevel=0.014)
                p.box(0, 0, w + 0.04, d + 0.04, h - 0.12, 0.12, mat, bevel=0.04, seg=3)
                for sx in (-1, 1):
                    p.box(sx * w * 0.3, 0, 0.05, d + 0.06, 0.0, h + 0.005, "metal", bevel=0.004)
            elif sid == "mantel":
                p.box(0, 0, w, d + 0.1, z0, h, mat, bevel=0.02, seg=3)
                for sx in (-1, 1):
                    p.box(sx * (w * 0.5 - 0.5), 0.02, 0.16, d, z0 - 0.22, 0.22, mat, bevel=0.02, seg=3)
            else:
                p.box(0, 0, w, d, z0, h, mat, bevel=0.015, cast=not glow)
                if s.get("top") and s["top"] != mat:
                    p.box(0, 0, w, d, z0 + h, 0.012, s["top"], bevel=0.0)
            continue

        # ---- round things
        x, y, rr = s["cyl"]
        if sid == "lamp_pole":
            WORLD.cyl(x, -y, 0.2, 0.0, 0.035, mat, seg=20)
            WORLD.cyl(x, -y, 0.022, 0.0, h + 0.15, mat, seg=10, cast=False)
        elif sid == "lamp_shade":
            WORLD.cyl(x, -y, rr, z0, h, mat, seg=24, r_top=rr * 0.62, caps=False, cast=False)
        elif glow:                                                  # a hanging lamp
            WORLD.cyl(x, -y, rr, z0, h, mat, seg=24, r_top=rr * 0.3, caps=False, cast=False)
            WORLD.cyl(x, -y, 0.008, z0 + h, max(0.1, WALL_H - z0 - h), "rack", seg=6, cast=False)
        else:
            WORLD.cyl(x, -y, rr, z0, h, mat, seg=20)
            if s.get("top") and s["top"] != mat:
                WORLD.cyl(x, -y, rr * 0.98, z0 + h, 0.012, s["top"], seg=20)


def flush(collection=None):
    """One mesh per material; edges sharper than 25 degrees stay crisp, everything else is smooth."""
    collection = collection or bpy.context.scene.collection
    for (mat, cast), g in sorted(GROUPS.items()):
        me = bpy.data.meshes.new(("M_" if cast else "N_") + mat)
        me.from_pydata(g["v"], [], g["f"])
        bm = bmesh.new()
        bm.from_mesh(me)
        sharp = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(25.0)]
        bmesh.ops.split_edges(bm, edges=sharp)
        for f in bm.faces:
            f.smooth = True
        bm.to_mesh(me)
        bm.free()
        m = bpy.data.materials.get(mat) or bpy.data.materials.new(mat)
        me.materials.append(m)
        ob = bpy.data.objects.new(me.name, me)
        collection.objects.link(ob)
    return sum(len(g["f"]) for g in GROUPS.values())


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    opt = dict(zip(args[::2], args[1::2]))
    plan = json.load(open(opt["--plan"], encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build(plan, skip=[i for i in opt.get("--skip", "").split(",") if i])
    faces = flush()
    bpy.ops.export_scene.gltf(filepath=opt["--out"], export_format='GLB', export_yup=True, export_apply=True,
                              export_materials='EXPORT', export_normals=True, export_texcoords=False)
    print("stage model: %d faces in %d meshes -> %s" % (faces, len(GROUPS), opt["--out"]))
    print("STAGE " + json.dumps({"faces": faces, "meshes": len(GROUPS), "solids": len(plan.get("solids", [])),
                                 "out": opt["--out"]}), flush=True)


if __name__ == "__main__":
    main()
