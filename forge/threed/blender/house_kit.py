"""The house and shop kit (BUILD 98 Part 4): a house built in Blender from settings, not words.

✦ William, 2026-11-19: "Cheap blocks is a turn off for me." 2026-11-21: "I want every town to look like a developer took a
decade making it." So every house carries what real houses carry: a foundation course, siding with its shadow lines, corner
boards, fascia and soffit under the eaves, gutters and downspouts, windows set back in their frames with sills, muntins and
(by period) shutters, a door with its surround, a porch with posts, rail and steps, a garage with a panelled door, a chimney,
and bevels on every edge so light catches them.

    Run in Blender (5.x):  blender --background --factory-startup --python house_kit.py -- --settings s.json --out <folder>
    (or through the forge: blender.run {script: forge/threed/blender/house_kit.py, profile: buildings, args: [...]})
    or, in a live Blender:  import house_kit; house_kit.build(settings)

Settings (all optional; see DEFAULTS): storeys 1 | 1.5 | 2 · width, depth (m) · roof gable | hip | gambrel | dutch |
flat_parapet · pitch (degrees) · porch none | stoop | full | wraparound | screened · garage none | attached_single |
attached_double | carport · siding (an RGB), trim (an RGB), door (an RGB), roofing (an RGB) · windows six_over_six |
one_over_one | craftsman · shutters true/false · chimney none | left | right · dormers 0..3 · solar true/false ·
upkeep new | kept | tired | neglected · seed. Written with no add-on, so it runs in a --factory-startup Blender; the
buildings profile's add-ons (Archimesh, Bagapie, Buildify) are for the parts that come later (interiors, ivy, modular shops).
Writes <out>/<name>.glb (Godot reads glTF), <out>/<name>.blend, <out>/<name>_front.png and <out>/house.json (settings and
sizes). Nothing here names a game.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Vector

DEFAULTS = {
    "name": "house", "storeys": 2, "width": 11.0, "depth": 8.0, "storey_h": 2.75, "roof": "gable", "pitch": 34.0,
    "overhang": 0.38, "porch": "full", "porch_depth": 2.2, "garage": "attached_double", "siding": [0.80, 0.82, 0.80],
    "trim": [0.93, 0.93, 0.90], "door": [0.18, 0.22, 0.30], "roofing": [0.16, 0.16, 0.17], "foundation": [0.55, 0.32, 0.26],
    "windows": "six_over_six", "shutters": True, "shutter": [0.12, 0.16, 0.20], "chimney": "right", "dormers": 0,
    "solar": False, "upkeep": "kept", "seed": 1, "front": "+y",
}

COLL = "house_kit"


# ------------------------------------------------------------------------------------------------ materials
def mat(name, rgb, rough=0.6, metal=0.0, kind="plain", scale=1.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if kind in ("siding", "shingle", "brick"):
        # shadow lines baked in by a bump: siding laps every 0.18 m, shingle courses every 0.14 m, brick courses
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs[0])
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = {"siding": 1 / 0.18, "shingle": 1 / 0.14, "brick": 1 / 0.075}[kind]
        nt.links.new(sep.outputs["Z"], mul.inputs[0])
        fr = nt.nodes.new("ShaderNodeMath")
        fr.operation = "FRACT"
        nt.links.new(mul.outputs[0], fr.inputs[0])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.55 if kind == "siding" else 0.35
        bump.inputs["Distance"].default_value = 0.02
        nt.links.new(fr.outputs[0], bump.inputs["Height"])
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 18.0 * scale
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["Factor"].default_value = 0.12
        mix.inputs["A"].default_value = (*rgb, 1)
        mix.inputs["B"].default_value = (rgb[0] * 0.78, rgb[1] * 0.78, rgb[2] * 0.76, 1)
        nt.links.new(noise.outputs["Fac"], mix.inputs["Factor"])
        nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
        nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def weathered(rgb, upkeep):
    f = {"new": 1.0, "kept": 0.96, "tired": 0.88, "neglected": 0.78}[upkeep]
    return [c * f + (0.03 if upkeep == "neglected" else 0) for c in rgb]


# ------------------------------------------------------------------------------------------------ meshes
def coll():
    c = bpy.data.collections.get(COLL)
    if not c:
        c = bpy.data.collections.new(COLL)
        bpy.context.scene.collection.children.link(c)
    return c


def box(name, x, y, z, sx, sy, sz, m, bevel=0.012, rot=0.0, tilt=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = (x, y, z)
    o.rotation_euler[2] = rot
    o.rotation_euler[0] = tilt
    o.data.materials.append(m)
    coll().objects.link(o)
    if bevel:
        bv = o.modifiers.new("bevel", "BEVEL")
        bv.width = bevel
        bv.segments = 2
        bv.limit_method = "ANGLE"
    return o


def prism(name, verts2d, depth, m, axis="y", origin=(0, 0, 0), bevel=0.01):
    """Extrude a 2D outline (x, z pairs) along y (or x)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    a = [bm.verts.new((p[0], -depth / 2, p[1])) for p in verts2d]
    b = [bm.verts.new((p[0], depth / 2, p[1])) for p in verts2d]
    n = len(verts2d)
    bm.faces.new(a[::-1])
    bm.faces.new(b)
    for i in range(n):
        bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = origin
    if axis == "x":
        o.rotation_euler[2] = math.pi / 2
    o.data.materials.append(m)
    coll().objects.link(o)
    if bevel:
        bv = o.modifiers.new("bevel", "BEVEL")
        bv.width = bevel
        bv.segments = 2
        bv.limit_method = "ANGLE"
    return o


def tube(name, p0, p1, r, m):
    d = Vector(p1) - Vector(p0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=r, depth=d.length, location=(Vector(p0) + Vector(p1)) / 2)
    o = bpy.context.active_object
    o.name = name
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    o.data.materials.append(m)
    for c in o.users_collection:
        c.objects.unlink(o)
    coll().objects.link(o)
    return o


# ------------------------------------------------------------------------------------------------ parts
def window(s, M, x, y, z, w, h, face="front", shutters=None):
    """A window set into the wall: frame proud of the siding, sash recessed, glass, sill, muntins by period, shutters."""
    d = 0.06
    ny = 1 if face == "front" else -1
    fy = y + ny * 0.02
    t = 0.07
    box("win_frame_t", x, fy, z + h / 2 + t / 2, w + 2 * t, d, t, M["trim"])
    box("win_frame_b", x, fy, z - h / 2 - t / 2, w + 2 * t, d, t, M["trim"])
    box("win_frame_l", x - w / 2 - t / 2, fy, z, t, d, h, M["trim"])
    box("win_frame_r", x + w / 2 + t / 2, fy, z, t, d, h, M["trim"])
    box("win_sill", x, fy + ny * 0.05, z - h / 2 - t - 0.02, w + 2 * t + 0.1, 0.12, 0.04, M["trim"])
    box("win_glass", x, y - ny * 0.03, z, w, 0.01, h, M["glass"], bevel=0)
    # the meeting rail of a double-hung window, and the muntins
    box("win_rail", x, y - ny * 0.0, z, w, 0.035, 0.045, M["trim"], bevel=0.004)
    cols, rows = {"six_over_six": (3, 2), "one_over_one": (1, 1), "craftsman": (3, 1)}[s["windows"]]
    for half, top in ((-1, False), (1, True)):
        hz = z + half * h / 4
        rr = rows if (top or s["windows"] != "craftsman") else 1
        cc = cols if (top or s["windows"] != "craftsman") else 1
        for i in range(1, cc):
            box("muntin_v", x - w / 2 + w * i / cc, y, hz, 0.02, 0.025, h / 2, M["trim"], bevel=0)
        for j in range(1, rr):
            box("muntin_h", x, y, hz - h / 4 + h / 2 * j / rr, w, 0.025, 0.02, M["trim"], bevel=0)
    if shutters:
        sw = w * 0.45
        for side in (-1, 1):
            sx = x + side * (w / 2 + t + sw / 2 + 0.02)
            box("shutter", sx, fy + ny * 0.02, z, sw, 0.04, h + 2 * t, M["shutter"])
            for k in range(6):
                box("louver", sx, fy + ny * 0.045, z - h / 2 + (k + 0.5) * h / 6, sw * 0.86, 0.012, 0.03, M["shutter"], bevel=0)


def gable_roof(name, x0, x1, y0, y1, z, pitch, M, overhang, kind="gable"):
    """A roof over the box [x0..x1] × [y0..y1] at eave height z, ridge along x. Gable, hip, gambrel or Dutch."""
    w = (y1 - y0) / 2 + overhang
    rise = math.tan(math.radians(pitch)) * ((y1 - y0) / 2)
    cy = (y0 + y1) / 2
    L = (x1 - x0) + 2 * overhang
    th = 0.12
    if kind == "gambrel":
        k = 0.42
        lower = math.tan(math.radians(62)) * (w * k)
        outline = [(-w, 0), (-w * (1 - k), lower), (0, lower + math.tan(math.radians(24)) * w * (1 - k)),
                   (w * (1 - k), lower), (w, 0), (w - th, 0), (w * (1 - k) - th, lower - th * 0.6),
                   (0, lower + math.tan(math.radians(24)) * w * (1 - k) - th), (-w * (1 - k) + th, lower - th * 0.6), (-w + th, 0)]
    else:
        outline = [(-w, -0.02), (0, rise + overhang * math.tan(math.radians(pitch))), (w, -0.02),
                   (w - th, -0.02), (0, rise + overhang * math.tan(math.radians(pitch)) - th * 1.4), (-w + th, -0.02)]
    shell = prism(name, outline, L, M["roofing"], origin=((x0 + x1) / 2, cy, z))
    shell.rotation_euler[2] = math.pi / 2
    shell.scale = (1, 1, 1)
    ridge_h = max(p[1] for p in outline)
    # gable ends filled with siding (a triangle each side), set in under the roof
    if kind in ("gable", "gambrel", "dutch"):
        tri = [(p[0], p[1] - 0.05) for p in outline[: len(outline) // 2 + 1]]
        tri = [(-((y1 - y0) / 2), 0)] + [(max(min(px, (y1 - y0) / 2), -(y1 - y0) / 2), max(pz * ((y1 - y0) / 2) / w, 0)) for px, pz in tri[1:-1]] + [((y1 - y0) / 2, 0)]
        for gx in (x0 + 0.01, x1 - 0.01):
            g = prism(name + "_gable", tri, 0.2, M["siding"], origin=(gx, cy, z), bevel=0)
            g.rotation_euler[2] = math.pi / 2
            # a louvred vent in the gable
            box("gable_vent", gx + (0.11 if gx > x0 + 1 else -0.11), cy, z + ridge_h * 0.55, 0.04, 0.5, 0.5, M["trim"])
    if kind in ("hip", "dutch"):
        # the gable shell made above is replaced by a true hipped roof: four planes meeting a shortened ridge
        bpy.data.objects.remove(shell, do_unlink=True)
        ex0, ex1 = x0 - overhang, x1 + overhang
        ey0, ey1 = cy - w, cy + w
        rz = z + ridge_h
        inset = w * (0.55 if kind == "dutch" else 1.0)
        r0, r1 = ex0 + inset, ex1 - inset
        if r1 < r0:
            r0 = r1 = (ex0 + ex1) / 2
        hz = z + ridge_h * (inset / w) if kind == "dutch" else rz
        V = [(ex0, ey0, z), (ex1, ey0, z), (ex1, ey1, z), (ex0, ey1, z), (r0, cy, hz), (r1, cy, hz)]
        F = [(0, 1, 5, 4), (2, 3, 4, 5), (1, 2, 5), (3, 0, 4)]
        if kind == "dutch":
            V += [(r0, cy, rz), (r1, cy, rz)]
            # the upper gable part: two planes up to the full ridge, small vertical gablets at the ends
            F = [(0, 1, 5, 4), (2, 3, 4, 5), (1, 2, 5), (3, 0, 4)]
        me = bpy.data.meshes.new(name)
        me.from_pydata(V, [], F)
        me.update()
        o = bpy.data.objects.new(name, me)
        o.data.materials.append(M["roofing"])
        sol = o.modifiers.new("thick", "SOLIDIFY")
        sol.thickness = th
        coll().objects.link(o)
        if kind == "dutch":
            g = prism(name + "_gablet", [(-w * 0.45, 0), (0, ridge_h * 0.45), (w * 0.45, 0)], (r1 - r0) + 0.1, M["roofing"],
                      origin=((r0 + r1) / 2, cy, hz))
            g.rotation_euler[2] = math.pi / 2
    # fascia boards and gutters along both eaves; soffit under the overhang
    for side in (-1, 1):
        ey = cy + side * w
        box("fascia", (x0 + x1) / 2, ey, z - 0.08, L, 0.03, 0.2, M["trim"])
        box("soffit", (x0 + x1) / 2, ey - side * overhang / 2, z - 0.17, L, overhang, 0.02, M["trim"], bevel=0)
        tube("gutter", ((x0 + x1) / 2 - L / 2, ey + side * 0.06, z - 0.06), ((x0 + x1) / 2 + L / 2, ey + side * 0.06, z - 0.06),
             0.065, M["gutter"])
        for gx in (x0 + 0.15, x1 - 0.15):
            tube("downspout", (gx, cy + side * ((y1 - y0) / 2 + 0.08), 0.05), (gx, cy + side * ((y1 - y0) / 2 + 0.08), z - 0.1),
                 0.04, M["gutter"])
    return ridge_h


def porch(s, M, x0, x1, yf, depth, kind, rng):
    if kind == "none":
        return
    if kind == "stoop":
        w = 2.2
        cx = (x0 + x1) / 2 - (x1 - x0) * 0.18
        box("stoop", cx, yf + 0.7, 0.25, w, 1.4, 0.5, M["foundation"])
        for k in range(2):
            box("step", cx, yf + 1.55 + k * 0.3, 0.17 - k * 0.12 + 0.0, w * 0.8, 0.3, 0.34 - k * 0.17, M["foundation"])
        return
    px0, px1 = (x0 + 0.2, x1 - 0.2) if kind != "wraparound" else (x0 - depth, x1 - 0.2)
    deck_h = 0.55
    box("porch_deck", (px0 + px1) / 2, yf + depth / 2, deck_h - 0.05, px1 - px0, depth, 0.1, M["deck"])
    box("porch_skirt", (px0 + px1) / 2, yf + depth - 0.02, deck_h / 2 - 0.05, px1 - px0, 0.04, deck_h - 0.1, M["lattice"])
    # posts, rail, balusters
    n = max(3, int((px1 - px0) / 2.2) + 1)
    roof_z = deck_h + 2.55
    for i in range(n):
        x = px0 + 0.1 + (px1 - px0 - 0.2) * i / (n - 1)
        box("post", x, yf + depth - 0.12, deck_h + 1.27, 0.16, 0.16, 2.55, M["trim"])
        box("post_base", x, yf + depth - 0.12, deck_h + 0.12, 0.22, 0.22, 0.24, M["trim"])
    door_x = (x0 + x1) / 2 - (x1 - x0) * 0.18
    for i in range(n - 1):
        a = px0 + 0.1 + (px1 - px0 - 0.2) * i / (n - 1)
        b = px0 + 0.1 + (px1 - px0 - 0.2) * (i + 1) / (n - 1)
        if a < door_x < b:                                   # the steps come through here
            continue
        box("rail_top", (a + b) / 2, yf + depth - 0.12, deck_h + 0.9, b - a, 0.09, 0.05, M["trim"])
        box("rail_bot", (a + b) / 2, yf + depth - 0.12, deck_h + 0.12, b - a, 0.07, 0.04, M["trim"])
        k = int((b - a) / 0.13)
        for j in range(1, k):
            box("baluster", a + (b - a) * j / k, yf + depth - 0.12, deck_h + 0.5, 0.035, 0.035, 0.76, M["trim"], bevel=0.004)
    for k in range(3):                                   # solid steps: each a block down to the ground
        top = deck_h - 0.18 * (k + 1)
        box("porch_step", door_x, yf + depth + 0.16 + k * 0.3, top / 2, 1.6, 0.32, top, M["deck"])
    # its own roof: a shingled shed roof on a beam, falling from the wall to past the posts
    box("porch_beam", (px0 + px1) / 2, yf + depth - 0.12, roof_z, px1 - px0 + 0.2, 0.2, 0.25, M["trim"])
    run = depth + 0.35
    drop = 0.55
    ang = math.atan2(drop, run)
    length = math.hypot(run, drop)
    box("porch_roof", (px0 + px1) / 2, yf + run / 2, roof_z + 0.2 + drop / 2, px1 - px0 + 0.4, length, 0.1, M["roofing"],
        tilt=-ang)
    box("porch_fascia", (px0 + px1) / 2, yf + run, roof_z + 0.17, px1 - px0 + 0.4, 0.03, 0.18, M["trim"])
    box("porch_ceiling", (px0 + px1) / 2, yf + depth / 2, roof_z + 0.12, px1 - px0, depth, 0.02, M["porch_ceiling"], bevel=0)
    if kind == "wraparound":
        sd = depth
        sy0, sy1 = yf - 4.0, yf + depth
        box("porch_deck_side", x0 - sd / 2, (sy0 + sy1) / 2, deck_h - 0.05, sd, sy1 - sy0, 0.1, M["deck"])
        for py in (sy0 + 0.12, (sy0 + sy1) / 2):
            box("post", x0 - sd + 0.12, py, deck_h + 1.27, 0.16, 0.16, 2.55, M["trim"])
        box("rail_side", x0 - sd + 0.12, (sy0 + sy1) / 2, deck_h + 0.9, 0.09, sy1 - sy0, 0.05, M["trim"])
        box("porch_roof_side", x0 - (sd + 0.35) / 2, (sy0 + sy1) / 2, roof_z + 0.2 + 0.55 / 2, sd + 0.35, sy1 - sy0 + 0.2, 0.1,
            M["roofing"], rot=0.0, tilt=0.0)
    if kind == "screened":
        box("screen", (px0 + px1) / 2, yf + depth - 0.1, deck_h + 1.3, px1 - px0, 0.01, 2.3, M["screen"], bevel=0)


def garage(s, M, x1, y0, y1, rng):
    if s["garage"] == "none":
        return
    double = s["garage"] == "attached_double"
    gw = 6.4 if double else 3.8
    gd = min(y1 - y0, 7.0)
    gx = x1 + gw / 2
    gy = y1 - gd / 2
    if s["garage"] == "carport":
        for px in (x1 + 0.2, x1 + gw - 0.2):
            for py in (y1 - 0.2, y1 - gd + 0.2):
                box("carport_post", px, py, 1.2, 0.14, 0.14, 2.4, M["trim"])
        box("carport_roof", gx, gy, 2.48, gw + 0.4, gd + 0.4, 0.14, M["roofing"])
        return
    box("garage_found", gx, gy, 0.1, gw, gd, 0.2, M["foundation"])
    box("garage_wall", gx, gy, 1.45, gw, gd, 2.5, M["siding"], bevel=0.01)
    for cx in (x1 + 0.04, x1 + gw - 0.04):
        for cy in (y1 - 0.04, y1 - gd + 0.04):
            box("corner_board", cx, cy, 1.45, 0.14, 0.14, 2.5, M["trim"])
    # the panelled door(s)
    nd = 2 if double else 1
    dw = 2.6
    for i in range(nd):
        dx = gx - (gw / 4 if nd == 2 else 0) + (gw / 2 * i if nd == 2 else 0)
        box("garage_door", dx, y1 + 0.02, 1.08, dw, 0.05, 2.1, M["garage_door"])
        for r in range(4):
            for c in range(4):
                box("door_panel", dx - dw / 2 + dw * (c + 0.5) / 4, y1 + 0.07, 0.12 + 2.1 * (r + 0.5) / 4,
                    dw / 4 - 0.12, 0.04, 2.1 / 4 - 0.12, M["garage_panel"], bevel=0.02)
        box("door_trim", dx, y1 + 0.03, 2.2, dw + 0.2, 0.06, 0.12, M["trim"])
    gable_roof("garage_roof", x1, x1 + gw, y1 - gd, y1, 2.7, 26, M, 0.3, "gable")


def chimney(s, M, x, y, top, width=1.0, depth=0.7):
    box("chimney", x, y, top / 2, width, depth, top, M["brick"], bevel=0.01)
    box("chimney_cap", x, y, top + 0.05, width + 0.12, depth + 0.12, 0.1, M["foundation"])
    box("flue", x, y, top + 0.25, 0.3, 0.3, 0.3, M["flue"])


# ------------------------------------------------------------------------------------------------ the house
def build(settings: dict | None = None) -> dict:
    s = dict(DEFAULTS)
    s.update(settings or {})
    rng = random.Random(int(s["seed"]))
    up = s["upkeep"]
    M = {
        "siding": mat(f"siding_{s['name']}", weathered(s["siding"], up), 0.55, kind="siding"),
        "trim": mat(f"trim_{s['name']}", weathered(s["trim"], up), 0.5),
        "roofing": mat(f"roof_{s['name']}", s["roofing"], 0.85, kind="shingle"),
        "foundation": mat("foundation_brick", s["foundation"], 0.85, kind="brick"),
        "brick": mat("chimney_brick", [0.48, 0.24, 0.18], 0.9, kind="brick"),
        "glass": mat("glass_dark", [0.04, 0.05, 0.06], 0.05, 0.0),
        "door": mat(f"door_{s['name']}", s["door"], 0.35),
        "shutter": mat(f"shutter_{s['name']}", weathered(s["shutter"], up), 0.45),
        "gutter": mat("gutter_white", [0.85, 0.85, 0.83], 0.35, 0.2),
        "deck": mat("porch_deck_grey", [0.42, 0.42, 0.40], 0.7),
        "lattice": mat("porch_skirt", [0.85, 0.85, 0.82], 0.6),
        "porch_ceiling": mat("porch_ceiling_haint", [0.62, 0.78, 0.80], 0.5),
        "garage_door": mat("garage_door_white", [0.74, 0.74, 0.72], 0.45),
        "garage_panel": mat("garage_panel_white", [0.92, 0.92, 0.90], 0.4),
        "screen": mat("screen_mesh", [0.1, 0.1, 0.1], 0.6),
        "flue": mat("flue_clay", [0.55, 0.35, 0.25], 0.8),
    }
    W, D = float(s["width"]), float(s["depth"])
    storeys = float(s["storeys"])
    H = s["storey_h"] * math.ceil(storeys) - (s["storey_h"] * 0.45 if storeys == 1.5 else 0)
    x0, x1, y0, y1 = -W / 2, W / 2, -D / 2, D / 2
    base = 0.55
    box("foundation", 0, 0, base / 2, W + 0.06, D + 0.06, base, M["foundation"])
    box("walls", 0, 0, base + H / 2, W, D, H, M["siding"], bevel=0.008)
    for cx in (x0 + 0.04, x1 - 0.04):
        for cy in (y0 + 0.04, y1 - 0.04):
            box("corner_board", cx, cy, base + H / 2, 0.15, 0.15, H, M["trim"])
    box("frieze_front", 0, y1 + 0.02, base + H - 0.12, W, 0.03, 0.24, M["trim"])
    box("frieze_back", 0, y0 - 0.02, base + H - 0.12, W, 0.03, 0.24, M["trim"])
    if storeys >= 2:
        box("band_board", 0, y1 + 0.02, base + s["storey_h"], W, 0.03, 0.14, M["trim"])
    # windows: front and back, both floors; the door off-centre left, beside the porch steps
    door_x = -W * 0.18
    floors = [base + 1.45]
    if storeys >= 2:
        floors.append(base + s["storey_h"] + 1.35)
    bays = max(3, int(W / 2.4))
    for fi, fz in enumerate(floors):
        for i in range(bays):
            bx = x0 + W * (i + 0.5) / bays
            if fi == 0 and abs(bx - door_x) < 1.1:
                continue
            wh = 1.45 if fi == 0 else 1.3
            window(s, M, bx, y1, fz, 0.9, wh, "front", s["shutters"])
            if rng.random() < 0.8:
                window(s, M, bx, y0, fz, 0.9, wh, "back", False)
    # the front door: panel door, surround with a pediment, a light by it
    box("door", door_x, y1 + 0.01, base + 1.05, 0.95, 0.06, 2.1, M["door"])
    for k in range(3):
        box("door_panel", door_x, y1 + 0.045, base + 0.35 + k * 0.7, 0.7, 0.02, 0.55, M["door"], bevel=0.01)
    box("door_casing_l", door_x - 0.55, y1 + 0.03, base + 1.1, 0.14, 0.06, 2.2, M["trim"])
    box("door_casing_r", door_x + 0.55, y1 + 0.03, base + 1.1, 0.14, 0.06, 2.2, M["trim"])
    box("door_head", door_x, y1 + 0.05, base + 2.3, 1.4, 0.1, 0.18, M["trim"])
    box("porch_light", door_x + 0.8, y1 + 0.08, base + 1.85, 0.16, 0.12, 0.3, mat("lamp_brass", [0.45, 0.35, 0.18], 0.4, 0.8))
    ridge = gable_roof("roof", x0, x1, y0, y1, base + H, s["pitch"], M, s["overhang"], s["roof"])
    if s["roof"] == "flat_parapet":
        box("parapet", 0, 0, base + H + 0.4, W + 0.1, D + 0.1, 0.8, M["siding"])
    for k in range(int(s["dormers"])):
        dx = x0 + W * (k + 1) / (int(s["dormers"]) + 1)
        box("dormer", dx, y1 - 1.2, base + H + 1.0, 1.4, 1.6, 1.3, M["siding"])
        window(s, M, dx, y1 - 0.39, base + H + 1.0, 0.7, 0.8, "front", False)
        gable_roof("dormer_roof", dx - 0.7, dx + 0.7, y1 - 2.0, y1 - 0.4, base + H + 1.65, 40, M, 0.12, "gable")
    if s["chimney"] != "none":
        cx = (x1 + 0.36) if s["chimney"] == "right" else (x0 - 0.36)      # outside the gable wall, as real ones stand
        chimney(s, M, cx, 0.0, base + H + ridge + 0.9)
    if s["solar"]:
        for i in range(6):
            box("solar_panel", x0 + 1.2 + i * 1.1, y0 + D * 0.25, base + H + ridge * 0.45, 1.0, 1.6, 0.04,
                mat("solar", [0.05, 0.07, 0.12], 0.2, 0.4))
    porch(s, M, x0, x1, y1, s["porch_depth"], s["porch"], rng)
    garage(s, M, x1, y0, y1, rng)
    for o in coll().objects:
        if o.type == "MESH":
            wn = o.modifiers.new("wn", "WEIGHTED_NORMAL")
            wn.keep_sharp = True
    return {"settings": s, "size_m": {"width": W + (6.4 if s["garage"] == "attached_double" else 3.8 if s["garage"] != "none" else 0),
                                      "depth": D + s["porch_depth"], "height": base + H + ridge}}


def frame_and_render(path, size=(1200, 800), engine="BLENDER_EEVEE_NEXT"):
    sc = bpy.context.scene
    for e in (engine, "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        try:
            sc.render.engine = e
            break
        except TypeError:
            continue
    sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.film_transparent = False
    cam = bpy.data.objects.get("kit_cam") or bpy.data.objects.new("kit_cam", bpy.data.cameras.new("kit_cam"))
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    cam.location = (14.0, 19.0, 7.5)
    cam.data.lens = 40
    d = Vector((1.0, 0.0, 3.5)) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sun = bpy.data.objects.get("kit_sun") or bpy.data.objects.new("kit_sun", bpy.data.lights.new("kit_sun", "SUN"))
    if sun.name not in sc.collection.objects:
        sc.collection.objects.link(sun)
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(35))
    w = sc.world or bpy.data.worlds.new("kit_world")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.62, 0.72, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    if not any(o.name.startswith("kit_ground") for o in sc.objects):
        g = box("kit_ground", 0, 0, -0.01, 60, 60, 0.02, mat("kit_grass", [0.16, 0.24, 0.10], 0.9), bevel=0)
        g.name = "kit_ground"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            opts[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    out = opts.get("out") or os.environ.get("FORGE_RUN_DIR") or os.getcwd()
    os.makedirs(out, exist_ok=True)
    settings = json.load(open(opts["settings"], encoding="utf-8")) if opts.get("settings") else {}
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    info = build(settings)
    name = info["settings"]["name"]
    frame_and_render(os.path.join(out, f"{name}_front.png"))
    gl = bpy.data.objects.get("kit_ground")
    if gl:
        bpy.data.objects.remove(gl, do_unlink=True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, f"{name}.glb"), export_format="GLB", export_apply=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{name}.blend"))
    with open(os.path.join(out, "house.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    global result
    result = {"glb": f"{name}.glb", "picture": f"{name}_front.png", **info["size_m"]}


if __name__ == "__main__" and "--" in sys.argv:
    main()
