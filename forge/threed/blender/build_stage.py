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

BUILD 34 (the door rule — "As you run up to buildings, they usually show the exterior and then the interior when you
open the door"): a solid may say "building": <id> and "show": "outside" (its roof, its whole outer walls) or "inside"
(the walls cut low so a room can be seen into). Those go in meshes of their own, named OUTSIDE_<id>__M_<word> /
INSIDE_<id>__M_<word>, and the game shows one set or the other as the player crosses the threshold. A solid with
"roof": {"rect": [x, y, w, d], "ridge": "x" | "y", "pitch": degrees, "eave": height, "overhang": m, "gable": word}
is a pitched roof over that rectangle (its gable ends in the "gable" material). A plan without these is built as before.

BUILD 63 (the look — 35_The_Look.md; Fable's look proof, 2026-11-16, tools/build_stage_look.py): five changes, each marked
"LOOK" below and each behind a switch a place plan can set (or the command line: --windows, --trim, --bevel, --pictures,
--dress), so a plan that sets none is built exactly as before:
  1. "windows": "open"      windows are real openings in the wall, with glass set back, a curtain each side and a rod —
                            so the moon and the sun come through them (and a kitchen's hanging lamp gets its own word);
  2. "trim": true           walls get a crown, and boards to chair height where the paper is the old warm one;
  3. "bevel": 1.6           every bevel is scaled: a wider bevel catches the light at the distance a stage is seen from;
  4. "pictures": "engine"   the frames and canvases are left to the engine, which hangs real pictures;
  5. "dressing": <file>     the small things that make a room lived in, each made by rule from a short list.

BUILD 44 (a large hall — the first place that is round): three more shapes, used only by a plan that
names them, so every older plan is built exactly as before:
  - "arc": [cx, cy, r_in, r_out, a0, a1]   a curved band (a tier's slab, a box front, a rail, a ring of the ceiling),
                            from z to z + h; angles in degrees in plan terms (0 east, 90 south, 180 west; a1 > a0; a
                            full ring is 0 to 360). A band with r_in = r_out is not made.
  - "seats": {pitch, people, seed, back, cloth, skin, empty}   on an arc or a rect solid: a row of theatre seats along the arc
                            (or the rect's long side), each facing the arc's centre (a rect's own "facing": n|s|e|w); a
                            share of them ("people", 0–1) with a seated figure — a body and a head, plain stand-ins in a
                            few cloth colours, so a hall reads as full from the stage. Nobody in it is a person.
                            "empty": [[x, y], ...] keeps the seats at those plan points empty.
  - "top_r": m               on a round solid (cyl): its top radius (0 makes a cone — a pine, a spire).
"""
import json
import math
import random
import sys

import bpy                      # first: the others come with it
import bmesh
from mathutils import Matrix, Vector, noise

GROUPS = {}          # (material word, casts a shadow, layer) -> {"v": [...], "f": [...]}
LAYER = ""           # BUILD 34: "" (always shown) · "OUTSIDE_<building>__" · "INSIDE_<building>__" — set per solid
WALL_H = 3.0
RNG = random.Random(33)
BEVEL = 1.0          # LOOK 3: every bevel is multiplied by this (--bevel; a plan's "bevel")
PICTURES = True      # LOOK 4: False leaves the frames and canvases to the engine (--pictures engine)
WINDOWS = "card"     # LOOK 1: "open" builds each window as a hole in its wall (--windows open)
TRIM = False         # LOOK 2: a crown under the cut and a wainscot under the warm paper (--trim on)


# ------------------------------------------------------------------------------------------------ primitives
class Piece:
    """Parts modelled around the origin (front = south = -Y), then set down at a place and turned."""

    def __init__(self, x=0.0, y=0.0, rot=0.0):
        self.m = Matrix.Translation(Vector((x, -y, 0.0))) @ Matrix.Rotation(rot, 4, 'Z')

    def _emit(self, bm, mat, cast, local=None):
        m = self.m @ local if local is not None else self.m
        g = GROUPS.setdefault((mat, cast, LAYER), {"v": [], "f": []})
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
        b = min(bevel * BEVEL, 0.45 * min(w, d, h))                 # LOOK 3
        if b > 0.017 and seg < 3:
            seg = 3
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
    if WINDOWS == "open":
        # LOOK 1: the pane is glass set back in a real opening (the wall is built round it), not a lit card on the wall
        p.box(cx, fy + 0.05, w, 0.008, z0, h, "glass", bevel=0.0, cast=False)
        curtains(p, cx, fy, w, z0, h)
    else:
        p.box(cx, fy - 0.012, w, 0.02, z0, h, pane, bevel=0.0, cast=False)
    f = 0.07
    for dx in (-(w * 0.5 + f * 0.5), w * 0.5 + f * 0.5):
        p.box(cx + dx, fy - 0.03, f, 0.07, z0 - f, h + 2 * f, "wood_light", bevel=0.01)
    for zz in (z0 - f, z0 + h):
        p.box(cx, fy - 0.03, w, 0.07, zz, f, "wood_light", bevel=0.01)
    p.box(cx, fy - 0.025, 0.035, 0.035, z0, h, "wood_light", bevel=0.005)
    p.box(cx, fy - 0.025, w, 0.035, z0 + h * 0.5 - 0.017, 0.035, "wood_light", bevel=0.005)
    p.box(cx, fy - 0.07, w + 0.24, 0.14, z0 - f - 0.035, 0.035, "wood_light", bevel=0.01)


def curtains(p, cx, fy, w, z0, h):
    """LOOK 1: a rod over the window and a gathered curtain each side of it, hanging a hand in front of the wall."""
    rod_z = z0 + h + 0.16
    p.cyl(cx, fy - 0.1, 0.011, rod_z, w + 0.56, "brass", seg=8, axis='X')
    for sx in (-1, 1):
        p.blob(cx + sx * (w * 0.5 + 0.29), fy - 0.1, rod_z, 0.03, "brass", squash=(1, 1, 1), rough=0.0, sub=1)
    pw = max(0.26, w * 0.24)                                   # one curtain, gathered open
    n = 14
    for sx in (-1, 1):
        x_out = cx + sx * (w * 0.5 + 0.2)
        bm = bmesh.new()
        top, bot = [], []
        ph = RNG.uniform(0.0, 3.0)
        for i in range(n + 1):
            t = i / n
            x = x_out - sx * pw * t
            wave = 0.028 * math.sin(t * 15.0 + ph) + 0.012 * math.sin(t * 31.0 + ph * 2.0)
            sway = 0.02 * math.sin(t * 5.0 + ph)                # the hem hangs a little differently from the top
            top.append(bm.verts.new((x, fy - 0.1 + wave * 0.7, rod_z - 0.012)))
            bot.append(bm.verts.new((x + sway * 0.6, fy - 0.11 + wave * 1.25, z0 - 0.2 + 0.012 * math.sin(t * 9.0 + ph))))
        for i in range(n):
            bm.faces.new((bot[i], bot[i + 1], top[i + 1], top[i]))
        bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.3], cuts=5)
        p._emit(bm, "curtain", True)


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
def gable_roof(spec, mat, cast=True):
    """A pitched roof over spec["rect"] (plan coordinates): two slabs meeting at a ridge, and the two gable ends."""
    x, y, w, d = [float(v) for v in spec["rect"]]
    ridge = spec.get("ridge", "x" if w >= d else "y")
    pitch = math.radians(float(spec.get("pitch", 35.0)))
    eave = float(spec.get("eave", WALL_H))
    over = float(spec.get("overhang", 0.3))
    t = float(spec.get("thick", 0.14))
    gable = spec.get("gable") or mat
    # work in a frame where the ridge runs along u (length L) and the slopes fall along v (half-width H)
    if ridge == "x":
        cu, cv, L, H = x + w * 0.5, y + d * 0.5, w, d * 0.5
    else:
        cu, cv, L, H = y + d * 0.5, x + w * 0.5, d, w * 0.5
    rise = H * math.tan(pitch)
    top = eave + rise
    low = eave - over * math.tan(pitch)

    def P(u, v, z):                      # frame -> Blender (plan x east, plan y south -> -Y)
        if ridge == "x":
            return Vector((cu + u, -(cv + v), z))
        return Vector((cv + v, -(cu + u), z))

    for side in (-1.0, 1.0):             # the two slabs
        bm = bmesh.new()
        a0, a1 = -L * 0.5 - over, L * 0.5 + over
        ridge_pts = [P(a0, 0.0, top), P(a1, 0.0, top)]
        eave_pts = [P(a0, side * (H + over), low), P(a1, side * (H + over), low)]
        up = Vector((0, 0, t))
        vs = [bm.verts.new(p) for p in (ridge_pts[0], ridge_pts[1], eave_pts[1], eave_pts[0])]
        vt = [bm.verts.new(p + up) for p in (ridge_pts[0], ridge_pts[1], eave_pts[1], eave_pts[0])]
        bm.faces.new(vt)
        bm.faces.new(list(reversed(vs)))
        for i in range(4):
            bm.faces.new((vs[i], vs[(i + 1) % 4], vt[(i + 1) % 4], vt[i]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        Piece()._emit(bm, mat, cast)
    for end in (-1.0, 1.0):              # the gable ends: a wall from the eave line up to the ridge
        bm = bmesh.new()
        u = end * L * 0.5
        tri = [P(u, -H, eave), P(u, H, eave), P(u, 0.0, top)]
        inset = Vector((0, 0, 0))
        off = (P(u - end * 0.12, 0.0, 0.0) - P(u, 0.0, 0.0))
        a = [bm.verts.new(p) for p in tri]
        b = [bm.verts.new(p + off + inset) for p in tri]
        bm.faces.new(a)
        bm.faces.new(list(reversed(b)))
        for i in range(3):
            bm.faces.new((a[i], a[(i + 1) % 3], b[(i + 1) % 3], b[i]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        Piece()._emit(bm, gable, cast)


# ------------------------------------------------------------------------------------------------ BUILD 44: round halls
ARC_STEP = 0.5       # metres of the outer edge per segment of an arc band


def arc_point(cx, cy, r, a_deg):
    """A point on a circle in plan coordinates (0 east, 90 south) — returned in model space (y north)."""
    a = math.radians(a_deg)
    return cx + r * math.cos(a), -(cy + r * math.sin(a))


def arc_band(spec, z0, h, mat, cast=True):
    """A curved band: inner and outer walls, its top and its bottom, the two ends."""
    cx, cy, ri, ro, a0, a1 = (float(v) for v in spec[:6])
    if ro <= ri or a1 <= a0 or h <= 0.0:
        return
    full = (a1 - a0) >= 359.999
    n = max(4, int(math.ceil(math.radians(a1 - a0) * ro / ARC_STEP)))
    bm = bmesh.new()
    rows = []
    for i in range(n + 1):
        if full and i == n:
            break
        a = a0 + (a1 - a0) * i / n
        xi, yi = arc_point(cx, cy, ri, a)
        xo, yo = arc_point(cx, cy, ro, a)
        rows.append([bm.verts.new((xi, yi, z0)), bm.verts.new((xo, yo, z0)), bm.verts.new((xo, yo, z0 + h)), bm.verts.new((xi, yi, z0 + h))])
    segs = len(rows) if full else len(rows) - 1
    for i in range(segs):
        p, q = rows[i], rows[(i + 1) % len(rows)]
        for k in range(4):                                   # inner bottom-outer bottom, outer wall, top, inner wall
            k2 = (k + 1) % 4
            bm.faces.new((p[k], q[k], q[k2], p[k2]))
    if not full:
        bm.faces.new(rows[0][::-1])
        bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    WORLD._emit(bm, mat, cast)


CLOTH = ["cloth_black", "cloth_navy", "cloth_wine", "cloth_grey", "cloth_cream", "cloth_brown", "cloth_green"]


def seat_spots(s):
    """Where each seat of a row stands and which way it faces: [(x, y in model space, turn about z)]."""
    seats = s["seats"]
    pitch = max(0.3, float(seats.get("pitch", 0.55)))
    out = []
    if "arc" in s:
        cx, cy, ri, ro, a0, a1 = (float(v) for v in s["arc"][:6])
        r = (ri + ro) * 0.5
        span = math.radians(a1 - a0) * r
        n = max(1, int(span // pitch))
        pad = (span - n * pitch) * 0.5
        for i in range(n):
            a = a0 + math.degrees((pad + (i + 0.5) * pitch) / r)
            x, y = arc_point(cx, cy, r, a)
            cxm, cym = cx, -cy
            out.append((x, y, math.atan2(cym - y, cxm - x) - math.radians(-90.0)))   # the seat's front (-Y) toward the centre
        return out
    x, y, w, d = (float(v) for v in s["rect"][:4])
    facing = str(s.get("facing", "n"))
    along_x = w >= d
    span = w if along_x else d
    n = max(1, int(span // pitch))
    pad = (span - n * pitch) * 0.5
    turn = {"s": 0.0, "n": math.pi, "e": math.radians(90.0), "w": math.radians(-90.0)}.get(facing, 0.0)
    for i in range(n):
        t = pad + (i + 0.5) * pitch
        px, py = (x + t, y + d * 0.5) if along_x else (x + w * 0.5, y + t)
        out.append((px, -py, turn))
    return out


def seat_row(s, z0, mat):
    """A row of theatre seats (a cushion and a back each), and on a share of them a seated stand-in figure."""
    seats = s["seats"]
    rng = random.Random(int(seats.get("seed", 1)))
    share = float(seats.get("people", 0.0))
    back_h = float(seats.get("back", 0.85))
    pitch = max(0.3, float(seats.get("pitch", 0.55)))
    cloth = seats.get("cloth") or CLOTH
    skin = seats.get("skin", "skin_crowd")
    empty = [(float(e[0]), -float(e[1])) for e in seats.get("empty", [])]     # seats kept empty (plan points)
    w = pitch * 0.86
    for (x, y, turn) in seat_spots(s):
        p = Piece()
        p.m = Matrix.Translation(Vector((x, y, 0.0))) @ Matrix.Rotation(turn, 4, 'Z')
        p.box(0.0, 0.0, w, 0.46, z0 + 0.36, 0.1, mat, bevel=0.0)                 # the cushion (front = -Y)
        p.box(0.0, 0.24, w, 0.08, z0 + 0.36, back_h - 0.36, mat, bevel=0.0)      # the back
        taken = rng.random() < share
        if any((x - ex) ** 2 + (y - ey) ** 2 < 0.16 for ex, ey in empty):
            taken = False
        if share > 0.0 and taken:
            c = cloth[rng.randrange(len(cloth))]
            lean = rng.uniform(-0.06, 0.06)
            hgt = rng.uniform(0.56, 0.68)
            p.box(0.0, 0.05, w * 0.72, 0.26, z0 + 0.46, hgt, c, bevel=0.0, turn=lean)          # the body
            p.box(0.0, -0.17, w * 0.62, 0.34, z0 + 0.42, 0.12, c, bevel=0.0)                 # the lap
            hb = bmesh.new()
            bmesh.ops.create_icosphere(hb, subdivisions=1, radius=1.0)
            bmesh.ops.scale(hb, vec=(0.095, 0.11, 0.125), verts=hb.verts)
            p._emit(hb, skin, True, Matrix.Translation(Vector((rng.uniform(-0.02, 0.02), 0.03, z0 + 0.46 + hgt + 0.14))))


def _layer_of(s):
    show, bld = s.get("show"), s.get("building")
    if show in ("outside", "inside") and bld:
        return ("OUTSIDE_" if show == "outside" else "INSIDE_") + str(bld) + "__"
    return ""


def build(plan, skip=()):
    global LAYER
    solids = [s for s in plan.get("solids", []) if s.get("id") not in set(skip)]
    by_id = {s.get("id", ""): s for s in solids}
    tables = [s for s in solids if any(k in s.get("id", "") for k in ("table", "desk")) and "rect" in s]
    canopies = {i.replace("_canopy", ""): s for i, s in by_id.items() if i.endswith("_canopy")}
    for s in solids:
        LAYER = _layer_of(s)
        sid, mat = s.get("id", ""), s["mat"]
        z0, h = float(s.get("z", 0.0)), float(s.get("h", 0.0))
        if s.get("roof"):                                         # BUILD 34: a pitched roof
            gable_roof(s["roof"], mat)
            continue
        if s.get("seats") and ("arc" in s or "rect" in s):          # BUILD 44: a row of seats (and the house in it)
            seat_row(s, z0, mat)
            continue
        if "arc" in s:                                             # BUILD 44: a curved band
            arc_band(s["arc"], z0, h, mat, cast=not mat.startswith("glow_"))
            continue
        cx, cy = centre(s)
        glow = mat.startswith("glow_")
        if s.get("show") == "outside" and "rect" in s:            # BUILD 34: an outer wall seen from outside, plain
            r = s["rect"]
            WORLD.rect(r[0], r[1], r[2], r[3], z0, h, mat, bevel=0.01)
            continue

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
            holes = sorted((float(f["x"]), float(f["x"]) + float(f["w"]), float(f.get("z", 0.0)),
                            float(f.get("z", 0.0)) + float(f["h"]))
                           for f in s.get("face", []) if f["mat"].startswith("window")) if WINDOWS == "open" else []
            if holes:
                # LOOK 1: the wall is built round its windows, so each window is a hole light can come through
                at = r[0]
                for (x0, x1, hz0, hz1) in holes:
                    if x0 > at:
                        WORLD.rect(at, r[1], x0 - at, r[3], 0.0, h, mat, bevel=0.0)
                    WORLD.rect(x0, r[1], x1 - x0, r[3], 0.0, hz0, mat, bevel=0.0)
                    if h > hz1:
                        WORLD.rect(x0, r[1], x1 - x0, r[3], hz1, h - hz1, mat, bevel=0.0)
                    t = 0.02                                               # the opening is lined with board
                    WORLD.rect(x0, r[1], t, r[3], hz0, hz1 - hz0, "trim", bevel=0.0)
                    WORLD.rect(x1 - t, r[1], t, r[3], hz0, hz1 - hz0, "trim", bevel=0.0)
                    WORLD.rect(x0, r[1], x1 - x0, r[3], hz0, t, "trim", bevel=0.0)
                    WORLD.rect(x0, r[1], x1 - x0, r[3], hz1 - t, t, "trim", bevel=0.0)
                    at = x1
                if r[0] + r[2] > at:
                    WORLD.rect(at, r[1], r[0] + r[2] - at, r[3], 0.0, h, mat, bevel=0.0)
            else:
                WORLD.rect(r[0], r[1], r[2], r[3], 0.0, h, mat, bevel=0.01)
            if s.get("top"):
                WORLD.rect(r[0], r[1], r[2], r[3], h, 0.02, s["top"], bevel=0.0)
            face_y = r[1] + r[3]
            if TRIM:
                warm = mat == "wallpaper_warm"
                WORLD.rect(r[0], face_y, r[2], 0.03, 0.0, 0.15, "wood" if warm else "trim", bevel=0.008)
                # LOOK 2: a crown under the cut, and boards to chair height where the paper is the old warm one
                WORLD.rect(r[0], face_y, r[2], 0.045, h - 0.11, 0.11, "wood" if warm else "trim", bevel=0.02, seg=3)
                if warm:
                    WORLD.rect(r[0], face_y, r[2], 0.016, 0.15, 0.8, "wainscot", bevel=0.0)
                    WORLD.rect(r[0], face_y, r[2], 0.05, 0.95, 0.05, "wood", bevel=0.012)
                    x = r[0] + 0.3
                    while x < r[0] + r[2] - 0.2:
                        WORLD.rect(x, face_y + 0.016, 0.06, 0.012, 0.15, 0.8, "wood", bevel=0.004)
                        x += 0.62
            else:
                WORLD.rect(r[0], face_y, r[2], 0.025, 0.0, 0.14, "wood_light", bevel=0.008)
            for f in s.get("face", []):
                fz = float(f.get("z", 0.0))
                if f["mat"].startswith("window"):
                    window(WORLD, f["x"], face_y, f["w"], fz, f["h"], f["mat"])
                elif PICTURES:                                       # LOOK 4: or left to the engine
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
        elif glow:                                                  # a hanging lamp (LOOK 1: a kitchen's has its own word, so it can be lit apart)
            word = "glow_pendant" if (WINDOWS == "open" and "kitchen" in sid) else mat
            WORLD.cyl(x, -y, rr, z0, h, word, seg=24, r_top=rr * 0.3, caps=False, cast=False)
            WORLD.cyl(x, -y, 0.008, z0 + h, max(0.1, WALL_H - z0 - h), "rack", seg=6, cast=False)
        else:
            WORLD.cyl(x, -y, rr, z0, h, mat, seg=20, r_top=(float(s["top_r"]) if s.get("top_r") is not None else None))   # BUILD 44: a cone
            if s.get("top") and s["top"] != mat:
                WORLD.cyl(x, -y, rr * 0.98, z0 + h, 0.012, s["top"], seg=20)


# ------------------------------------------------------------------------------------------------ LOOK 5: dressing
def _tube(p, a, b, r, mat, seg=8):
    """A round bar from one point to another (plan x, plan y, height)."""
    va, vb = Vector((a[0], -a[1], a[2])), Vector((b[0], -b[1], b[2]))
    d = vb - va
    if d.length < 1e-5:
        return
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r, depth=d.length)
    local = Matrix.Translation((va + vb) * 0.5) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    p._emit(bm, mat, True, local)


BOOKS = ("book_red", "book_green", "book_blue", "book_tan", "book_black")


def dress(items):
    """The small things. Each item: {"kind", "at": [x, y], "z": height it stands on, "turn": degrees, ...}."""
    for it in items:
        k = it["kind"]
        x, y = it.get("at", [0.0, 0.0])
        z = float(it.get("z", 0.0))
        p = Piece(x, y, math.radians(float(it.get("turn", 0.0))))
        if k == "mug":
            p.cyl(0, 0, 0.042, z, 0.095, it.get("mat", "ceramic"), seg=14)
            p.cyl(0, 0, 0.036, z + 0.085, 0.012, "coffee", seg=14)
            p.torus(0.052, 0, z + 0.05, 0.026, 0.008, it.get("mat", "ceramic"), upright=True, seg=12, ring=6)
        elif k == "book_stack":
            zz = z
            for i in range(int(it.get("n", 3))):
                bh = RNG.uniform(0.024, 0.045)
                p.box(RNG.uniform(-0.012, 0.012), RNG.uniform(-0.012, 0.012), RNG.uniform(0.15, 0.2), RNG.uniform(0.21, 0.26),
                      zz, bh, RNG.choice(BOOKS), bevel=0.004, turn=RNG.uniform(-0.3, 0.3))
                zz += bh
        elif k == "book_row":
            xx = -float(it.get("w", 0.5)) * 0.5
            while xx < float(it.get("w", 0.5)) * 0.5:
                t = RNG.uniform(0.022, 0.05)
                bh = RNG.uniform(0.19, 0.27)
                lean = RNG.uniform(-0.04, 0.04) if RNG.random() < 0.8 else RNG.uniform(0.12, 0.2)
                bm = bmesh.new()
                bmesh.ops.create_cube(bm, size=1.0)
                bmesh.ops.scale(bm, vec=(t, RNG.uniform(0.13, 0.17), bh), verts=bm.verts)
                bmesh.ops.bevel(bm, geom=bm.edges[:], offset=0.003, offset_type='OFFSET', segments=1, affect='EDGES')
                local = Matrix.Translation(Vector((xx + t * 0.5, 0.0, z + bh * 0.5))) @ Matrix.Rotation(lean, 4, 'Y')
                p._emit(bm, RNG.choice(BOOKS), True, local)
                xx += t + 0.002
        elif k == "newspaper":
            p.box(0, 0, 0.44, 0.3, z, 0.008, "paper", bevel=0.002)
            p.box(0.0, 0.0, 0.22, 0.3, z + 0.008, 0.008, "paper", bevel=0.002, turn=0.03)
        elif k == "clock":
            p.box(0, 0, 0.24, 0.1, z, 0.05, "wood", bevel=0.012)
            p.box(0, 0, 0.2, 0.085, z + 0.05, 0.2, "wood", bevel=0.03, seg=4)
            p.cyl(0, -0.046, 0.07, z + 0.15, 0.008, "paper", seg=24, axis='Y')
            p.cyl(0, -0.05, 0.078, z + 0.15, 0.006, "brass", seg=24, axis='Y', caps=False)
        elif k == "candlestick":
            p.cyl(0, 0, 0.038, z, 0.014, "brass", seg=14)
            p.cyl(0, 0, 0.011, z + 0.014, 0.13, "brass", seg=10)
            p.cyl(0, 0, 0.022, z + 0.144, 0.012, "brass", seg=12)
            p.cyl(0, 0, 0.011, z + 0.156, float(it.get("h", 0.14)), "wax", seg=10)
            if it.get("lit"):
                p.blob(0, 0, z + 0.156 + float(it.get("h", 0.14)) + 0.024, 0.012, "glow_candle", squash=(1, 1, 2.3), rough=0.0, sub=2, cast=False)
        elif k == "photo":
            w, hh = float(it.get("w", 0.16)), float(it.get("h", 0.2))
            lean = Matrix.Rotation(math.radians(-10.0), 4, 'X')
            for (bw, bd, bh, mat, off) in ((w, 0.016, hh, "wood", 0.0), (w - 0.04, 0.004, hh - 0.04, "photo", -0.011)):
                bm = bmesh.new()
                bmesh.ops.create_cube(bm, size=1.0)
                bmesh.ops.scale(bm, vec=(bw, bd, bh), verts=bm.verts)
                p._emit(bm, mat, True, Matrix.Translation(Vector((0, 0, z))) @ lean @ Matrix.Translation(Vector((0, off, hh * 0.5))))
        elif k == "plant":
            r = float(it.get("r", 0.11))
            p.cyl(0, 0, r * 0.7, z, r * 1.5, "terracotta", seg=14, r_top=r)
            p.cyl(0, 0, r * 0.92, z + r * 1.42, 0.015, "garden", seg=14)
            for i in range(int(it.get("n", 9))):
                a = RNG.uniform(0, math.tau)
                d = RNG.uniform(0.0, r * 1.3)
                p.blob(math.cos(a) * d, math.sin(a) * d, z + r * 1.6 + RNG.uniform(0.0, r * 2.4), r * RNG.uniform(0.45, 0.8),
                       "houseplant", squash=(1.0, 1.0, 0.7), rough=0.35, sub=1)
        elif k == "coffee_maker":
            p.box(0, 0, 0.2, 0.24, z, 0.035, "rack", bevel=0.008)
            p.box(0, 0.085, 0.18, 0.07, z + 0.035, 0.27, "rack", bevel=0.01)
            p.box(0, 0, 0.2, 0.24, z + 0.3, 0.06, "rack", bevel=0.012)
            p.cyl(0, -0.02, 0.07, z + 0.035, 0.15, "coffee", seg=16, r_top=0.06)
            p.box(0.07, -0.123, 0.016, 0.006, z + 0.325, 0.012, "glow_red", bevel=0.0, cast=False)
        elif k == "kettle":
            p.blob(0, 0, z + 0.085, 0.1, "steel", squash=(1.0, 1.0, 0.85), rough=0.0, sub=3)
            p.cyl(0, 0, 0.03, z + 0.16, 0.02, "rack", seg=10)
            p.torus(0, 0, z + 0.2, 0.075, 0.008, "rack", upright=True, seg=14, ring=6)
            _tube(p, (x + 0.08, y, z + 0.1), (x + 0.17, y, z + 0.17), 0.014, "steel")
        elif k == "jars":
            for i in range(int(it.get("n", 3))):
                rr = 0.055 - i * 0.008
                p.cyl(i * 0.125, 0, rr, z, 0.16 - i * 0.025, "ceramic", seg=14)
                p.cyl(i * 0.125, 0, rr * 0.8, z + 0.16 - i * 0.025, 0.02, "wood", seg=12)
        elif k == "fruit_bowl":
            p.cyl(0, 0, 0.07, z, 0.02, "ceramic_blue", seg=18)
            p.cyl(0, 0, 0.09, z + 0.02, 0.07, "ceramic_blue", seg=18, r_top=0.16, caps=False)
            for i in range(5):
                a = math.tau * i / 5
                p.blob(math.cos(a) * 0.07, math.sin(a) * 0.07, z + 0.085, 0.043, "fruit_red" if i % 2 else "fruit_yellow",
                       squash=(1, 1, 0.95), rough=0.05, sub=2)
            p.blob(0, 0, z + 0.125, 0.043, "fruit_red", squash=(1, 1, 0.95), rough=0.05, sub=2)
        elif k == "cushion":
            p.box(0, 0, float(it.get("w", 0.42)), float(it.get("d", 0.4)), z, 0.13, it.get("mat", "cloth_blue"), bevel=0.06, seg=4)
        elif k == "toolbox":
            p.box(0, 0, 0.42, 0.2, z, 0.17, "paint_red", bevel=0.012)
            p.box(0, 0, 0.44, 0.22, z + 0.17, 0.03, "paint_red", bevel=0.012)
            p.torus(0, 0, z + 0.2, 0.06, 0.008, "steel", upright=True, seg=12, ring=6)
        elif k == "parts":
            for i in range(int(it.get("n", 6))):
                px, py = RNG.uniform(-0.3, 0.3), RNG.uniform(-0.18, 0.18)
                if RNG.random() < 0.5:
                    p.box(px, py, RNG.uniform(0.03, 0.09), RNG.uniform(0.03, 0.07), z, RNG.uniform(0.015, 0.05),
                          RNG.choice(("steel", "rack", "brass")), bevel=0.004, turn=RNG.uniform(0, 3.1))
                else:
                    p.cyl(px, py, RNG.uniform(0.012, 0.03), z, RNG.uniform(0.02, 0.07), RNG.choice(("steel", "brass", "rack")), seg=10)
        elif k == "desk_lamp":                                    # a bench lamp on an arm, its head out over the work
            p.cyl(0, 0, 0.075, z, 0.022, "rack", seg=16)
            _tube(WORLD, (x, y, z + 0.02), (x + 0.03, y, z + 0.3), 0.008, "steel")
            _tube(WORLD, (x + 0.03, y, z + 0.3), (x + 0.2, y, z + 0.43), 0.008, "steel")
            WORLD.cyl(x + 0.2, -y, 0.075, z + 0.35, 0.09, "paint_green", seg=16, r_top=0.022, caps=False)
            WORLD.blob(x + 0.2, -y, z + 0.385, 0.02, "glow_bench", squash=(1, 1, 1), rough=0.0, sub=2, cast=False)
        elif k == "cable":
            pts = it["pts"]                                       # [[x, y, z], ...] in plan coordinates
            for a, b in zip(pts[:-1], pts[1:]):
                _tube(WORLD, a, b, float(it.get("r", 0.012)), it.get("mat", "rack"))
                WORLD.blob(b[0], -b[1], b[2], float(it.get("r", 0.012)) * 1.02, it.get("mat", "rack"), squash=(1, 1, 1), rough=0.0, sub=1)
        elif k == "rope":
            _tube(WORLD, (x, y, z), (x, y, z + float(it.get("h", 2.4))), 0.014, "rope", seg=6)
            WORLD.blob(x, -y, z, 0.035, "rope", squash=(1, 1, 1.3), rough=0.2, sub=1)
        elif k == "logs":
            for i in range(int(it.get("n", 5))):
                row, col = divmod(i, 3)
                p.cyl(-0.12 + col * 0.12 + row * 0.06, 0, 0.055, z + 0.055 + row * 0.1, 0.36, "bark", seg=10, axis='Y')
        elif k == "box":                                          # anything else: a plain thing of a given size
            p.box(0, 0, float(it["w"]), float(it["d"]), z, float(it["h"]), it["mat"], bevel=float(it.get("bevel", 0.01)),
                  cast=not it["mat"].startswith("glow_"))


def flush(collection=None):
    global LAYER
    LAYER = ""
    """One mesh per material; edges sharper than 25 degrees stay crisp, everything else is smooth."""
    collection = collection or bpy.context.scene.collection
    for (mat, cast, layer), g in sorted(GROUPS.items()):
        me = bpy.data.meshes.new(layer + ("M_" if cast else "N_") + mat)
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


def switches(plan, opt):
    """BUILD 63: the five LOOK switches — the command line wins, then the plan's own words, then as before."""
    def word(key, default):
        return opt.get("--" + key, plan.get(key, default))
    w = str(word("windows", "card")).lower()
    t = word("trim", False)
    t = t if isinstance(t, bool) else str(t).lower() in ("1", "true", "on", "yes")
    pic = str(word("pictures", "model")).lower()
    d = word("dress", plan.get("dressing") or "")
    return {"windows": "open" if w == "open" else "card", "trim": t, "bevel": float(word("bevel", 1.0)),
            "pictures": pic not in ("engine", "off"), "dressing": str(d) if d else ""}


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    opt = dict(zip(args[::2], args[1::2]))
    plan = json.load(open(opt["--plan"], encoding="utf-8"))
    global BEVEL, PICTURES, WINDOWS, TRIM, LAYER
    look = switches(plan, opt)
    BEVEL, PICTURES, WINDOWS, TRIM = look["bevel"], look["pictures"], look["windows"], look["trim"]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build(plan, skip=[i for i in opt.get("--skip", "").split(",") if i])
    if look["dressing"]:
        LAYER = ""                                                  # the small things show inside and out
        dress(json.load(open(look["dressing"], encoding="utf-8")).get("items", []))     # LOOK 5
    faces = flush()
    bpy.ops.export_scene.gltf(filepath=opt["--out"], export_format='GLB', export_yup=True, export_apply=True,
                              export_materials='EXPORT', export_normals=True, export_texcoords=False)
    print("stage model: %d faces in %d meshes -> %s" % (faces, len(GROUPS), opt["--out"]))
    print("STAGE " + json.dumps({"faces": faces, "meshes": len(GROUPS), "solids": len(plan.get("solids", [])),
                                 "out": opt["--out"], "look": {k: v for k, v in look.items()}}), flush=True)


if __name__ == "__main__":
    main()
