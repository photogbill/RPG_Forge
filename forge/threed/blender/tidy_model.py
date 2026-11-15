"""Tidy one model: weld its seams, take off its loose scraps, set it to its real size in metres, stand it on the floor.

    <Blender's Python> tidy_model.py <in.glb> <out.glb> [--scraps 0.02] [--weld 0.00001] [--height M | --width M | --depth M]
                                     [--no-floor] [--keep-centre]
    blender --background --python tidy_model.py -- <the same arguments>

Written for the 3D workshop (BUILD 36): image-to-3D models come with crumbs floating around them (owed since
2026-11-12), at whatever size the model guessed, centred on nothing in particular. In order:

  weld    vertices closer than --weld metres are joined. A .glb splits every vertex along its texture seams, so
          without this every texture island counts as a separate piece; the textures are kept (they belong to the
          faces' corners, not the vertices). For animals, a larger weld closes the seams UniRig trips on.
  scraps  every loose piece with fewer than --scraps of the largest piece's vertices is removed (0 = keep all).
  size    the whole model is scaled, keeping its shape, so its height (or width, or depth) is the given metres.
  floor   its lowest point is put on the floor and it is centred over the origin (--no-floor / --keep-centre to skip).

Prints one line "TIDY {json}" with what it did: pieces before and after, vertices removed, its size before and after.
"""
from __future__ import annotations

import json
import sys

import bpy                      # first: as a module, Blender's own packages (bmesh, mathutils) come with it
import bmesh
from mathutils import Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def opt(flag, default=None):
    return ARGV[ARGV.index(flag) + 1] if flag in ARGV else default


def bounds(objs):
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def pieces(bm) -> list[list]:
    """Connected pieces of a mesh, as lists of its vertices."""
    seen = set()
    out = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, part = [v], []
        seen.add(v.index)
        while stack:
            x = stack.pop()
            part.append(x)
            for e in x.link_edges:
                y = e.other_vert(x)
                if y.index not in seen:
                    seen.add(y.index)
                    stack.append(y)
        out.append(part)
    return out


def main() -> None:
    src, dst = ARGV[0], ARGV[1]
    scraps = float(opt("--scraps", 0.02))
    weld = float(opt("--weld", 0.00001))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=src)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("TIDY " + json.dumps({"error": "the file has no mesh"}))
    lo0, hi0 = bounds(meshes)
    report = {"in": src, "out": dst, "size_before_m": [round(x, 4) for x in (hi0 - lo0)], "meshes": len(meshes),
              "welded": 0, "pieces_before": 0, "pieces_after": 0, "removed_vertices": 0}
    skinned = any(o.find_armature() for o in meshes)
    for o in meshes:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        n0 = len(bm.verts)
        if weld > 0:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
            report["welded"] += n0 - len(bm.verts)
        bm.verts.index_update()
        parts = pieces(bm)
        report["pieces_before"] += len(parts)
        if scraps > 0 and len(parts) > 1:
            big = max(len(p) for p in parts)
            gone = [v for p in parts if len(p) < scraps * big for v in p]
            report["removed_vertices"] += len(gone)
            bmesh.ops.delete(bm, geom=gone, context="VERTS")
            bm.verts.index_update()
            report["pieces_after"] += len(pieces(bm))
        else:
            report["pieces_after"] += len(parts)
        bm.to_mesh(o.data)
        bm.free()
        o.data.update()
    bpy.context.view_layer.update()
    lo, hi = bounds(meshes)
    size = hi - lo                                   # Blender is Z-up: x width, y depth, z height
    want = None
    for flag, axis in (("--height", 2), ("--width", 0), ("--depth", 1)):
        if opt(flag):
            want = (float(opt(flag)), axis, flag[2:])
            break
    roots = [o for o in bpy.context.scene.objects if o.parent is None]
    if want and size[want[1]] > 1e-9:
        k = want[0] / size[want[1]]
        for r in roots:
            r.scale = r.scale * k
            r.location = r.location * k
        report["scaled_by"] = round(k, 6)
        report["scaled_to"] = {want[2]: want[0]}
        bpy.context.view_layer.update()
        lo, hi = bounds(meshes)
    if "--no-floor" not in ARGV:
        shift = Vector((0.0 if "--keep-centre" in ARGV else -(lo.x + hi.x) / 2,
                        0.0 if "--keep-centre" in ARGV else -(lo.y + hi.y) / 2, -lo.z))
        for r in roots:
            r.location = r.location + shift
        bpy.context.view_layer.update()
        lo, hi = bounds(meshes)
    report["size_after_m"] = {"width": round(hi.x - lo.x, 4), "depth": round(hi.y - lo.y, 4), "height": round(hi.z - lo.z, 4)}
    report["floor"] = round(lo.z, 5)
    for o in bpy.context.scene.objects:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_yup=True,
                              export_animations=skinned, export_skins=skinned)
    print("TIDY " + json.dumps(report), flush=True)


if __name__ == "__main__":
    import os
    main()
    sys.stdout.flush()
    os._exit(0)                 # Blender 4.2's Python can fall over while shutting down, after the work is done and saved
