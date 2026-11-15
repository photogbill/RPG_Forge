"""Join a separate head onto a shared body at the collar (BUILD 39, part 7: crowds as one uniform body, many heads).

    <Blender's Python> join_head.py <body.glb> <head.glb> <out.glb> [--collar 0.86 | --collar-m 1.52] [--overlap 0.012]
    blender --background --python join_head.py -- <the same arguments>

The launch-site run's sixteen soldiers came out nearly one body with different heads — so make it that way on purpose:
one uniform body per build, and each person's own head (from a head-and-shoulders picture) joined at the collar.

  body   everything above the collar is cut away. The collar is the narrowest part of the neck, looked for between
         74% and 92% of the body's height (or given: --collar as a share of the height, --collar-m in metres).
  head   everything below its own neck (the narrowest slice in its lower two thirds) is cut away.
  join   the head is scaled so its neck is as wide as the body's, centred on it, and sunk --overlap (share of the
         body's height) into the collar so no gap shows; then the two become one mesh, each keeping its own textures.

Prints one line "JOINED {json}" with the collar height, both neck widths and the scale given to the head.
"""
from __future__ import annotations

import json
import sys

import bpy                      # first: as a module, Blender's own packages (bmesh, mathutils) come with it
import bmesh
from mathutils import Matrix, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def opt(flag, default=None):
    return ARGV[ARGV.index(flag) + 1] if flag in ARGV else default


def load(path: str):
    """Import a .glb and return one mesh object holding all of it, its transforms applied (world = local)."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    if not meshes:
        raise SystemExit(f"no mesh in {path}")
    for o in new:
        if o.type != "MESH":
            o.select_set(False)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    for o in meshes:                                       # skins and parents are dropped: the joined body is rigged afresh
        for m in list(o.modifiers):
            o.modifiers.remove(m)
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in new:
        if o is not obj and o.name in bpy.data.objects and o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    return obj


def slice_widths(obj, z0: float, z1: float, n: int = 40):
    """(z, width across x, centre x, centre y) for n thin slices between z0 and z1."""
    vs = [obj.matrix_world @ v.co for v in obj.data.vertices]
    dz = (z1 - z0) / n
    out = []
    for k in range(n):
        a, b = z0 + k * dz, z0 + (k + 1) * dz
        sl = [v for v in vs if a <= v.z < b]
        if len(sl) < 6:
            continue
        xs = sorted(v.x for v in sl)
        ys = [v.y for v in sl]
        lo, hi = xs[int(len(xs) * 0.02)], xs[int(len(xs) * 0.98) - 1]
        out.append(((a + b) / 2, hi - lo, (hi + lo) / 2, sum(ys) / len(ys)))
    return out


def cut(obj, z: float, keep_below: bool):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, z), plane_no=(0, 0, 1),
                           clear_outer=keep_below, clear_inner=not keep_below)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def ring(obj, z: float, tol: float):
    vs = [v.co for v in obj.data.vertices if abs(v.co.z - z) <= tol]
    if len(vs) < 3:
        return None
    xs = [v.x for v in vs]
    return {"width": max(xs) - min(xs), "cx": (max(xs) + min(xs)) / 2, "cy": sum(v.y for v in vs) / len(vs)}


def main() -> None:
    body_p, head_p, out_p = ARGV[0], ARGV[1], ARGV[2]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body = load(body_p)
    zs = [(body.matrix_world @ v.co).z for v in body.data.vertices]
    zmin, zmax = min(zs), max(zs)
    h = zmax - zmin
    if opt("--collar-m"):
        zc = zmin + float(opt("--collar-m"))
    elif opt("--collar"):
        zc = zmin + float(opt("--collar")) * h
    else:
        sl = slice_widths(body, zmin + 0.74 * h, zmin + 0.92 * h)
        zc = min(sl, key=lambda s: s[1])[0] if sl else zmin + 0.86 * h
    tol = h * 0.004
    cut(body, zc, keep_below=True)
    br = ring(body, zc, tol) or {"width": h * 0.07, "cx": 0.0, "cy": 0.0}

    head = load(head_p)
    hz = [v.co.z for v in head.data.vertices]
    hmin, hmax = min(hz), max(hz)
    hh = hmax - hmin
    sl = slice_widths(head, hmin + 0.05 * hh, hmin + 0.66 * hh)
    neck = min(sl, key=lambda s: s[1]) if sl else (hmin + 0.3 * hh, hh * 0.3, 0.0, 0.0)
    cut(head, neck[0], keep_below=False)
    hr = ring(head, neck[0], hh * 0.004) or {"width": neck[1], "cx": neck[2], "cy": neck[3]}
    s = br["width"] / max(hr["width"], 1e-9)
    overlap = float(opt("--overlap", 0.012)) * h
    m = (Matrix.Translation(Vector((br["cx"], br["cy"], zc - overlap))) @ Matrix.Scale(s, 4) @
         Matrix.Translation(Vector((-hr["cx"], -hr["cy"], -neck[0]))))
    head.data.transform(m)
    head.data.update()

    bpy.ops.object.select_all(action="DESELECT")
    head.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = "body_with_head"
    bpy.ops.object.select_all(action="DESELECT")
    joined.select_set(True)
    bpy.ops.export_scene.gltf(filepath=out_p, export_format="GLB", use_selection=True, export_yup=True)
    top = max((joined.matrix_world @ v.co).z for v in joined.data.vertices)
    print("JOINED " + json.dumps({"collar_m": round(zc - zmin, 4), "collar_share": round((zc - zmin) / h, 4),
                                  "body_neck_m": round(br["width"], 4), "head_neck_m": round(hr["width"], 4),
                                  "head_scale": round(s, 4), "height_before_m": round(h, 4), "height_after_m": round(top - zmin, 4),
                                  "materials": len(joined.data.materials), "vertices": len(joined.data.vertices)}), flush=True)


try:
    main()
except SystemExit as e:
    print("JOINED " + json.dumps({"error": str(e)}), flush=True)
    raise
except Exception as e:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    print("JOINED " + json.dumps({"error": f"{type(e).__name__}: {e}"}), flush=True)
    sys.exit(1)
