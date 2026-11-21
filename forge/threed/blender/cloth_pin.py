"""Pin a cape, cloak or long coat to a body (BUILD 73 part 6) — run by Blender:

    blender -b --python cloth_pin.py -- <body.glb (rigged, with its motions)> <cloth.glb> <out.glb>
            [--pin shoulder.L,shoulder.R,neck] [--share 0.14] [--stiffness 0.6] [--wind "a slow sway"] [--name cape_x]

The garment (made apart, hanging flat on a stand) is scaled to the body's shoulders, hung from them behind the body, and
written into the body's .glb as a mesh of its own with its own material. Its top band (`--share` of its height) is
weighted to the shoulder and collar bones — pinned; the rest follows the upper spine a little, fading to nothing at the
hem, so the game can swing the free edge on a simple spring (not a cloth simulation). Prints one line:
    CLOTH {"mesh": ..., "pinned": n, "free": n, "pin_bones": [...], "size_m": {...}}  or  CLOTH {"error": ...}
"""
import json
import sys

import bpy  # noqa: F401 — Blender's own module
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
body_p, cloth_p, out_p = argv[0], argv[1], argv[2]


def opt(flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


PIN = [p.strip() for p in (opt("--pin", "shoulder.L,shoulder.R,neck") or "").split(",") if p.strip()]
SHARE = float(opt("--share", "0.14"))
NAME = opt("--name", "cloth")


def say(d):
    print("CLOTH " + json.dumps(d), flush=True)


try:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=body_p)
    body_objs = list(bpy.context.scene.objects)
    arm = next((o for o in body_objs if o.type == "ARMATURE"), None)
    if arm is None:
        raise RuntimeError("the body has no skeleton")
    bpy.ops.import_scene.gltf(filepath=cloth_p)
    cloth = next((o for o in bpy.context.scene.objects if o not in body_objs and o.type == "MESH"), None)
    if cloth is None:
        raise RuntimeError("the cloth file has no mesh")
    # join every mesh of the cloth file into one
    for o in [o for o in bpy.context.scene.objects if o not in body_objs and o.type == "MESH" and o is not cloth]:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        cloth.select_set(True)
        bpy.context.view_layer.objects.active = cloth
        bpy.ops.object.join()
    cloth.name = NAME
    bpy.ops.object.select_all(action="DESELECT")
    cloth.select_set(True)
    bpy.context.view_layer.objects.active = cloth
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    def find_bone(word):
        w = word.lower().replace(".", "").replace("_", "")
        side = "l" if w.endswith("l") and len(w) > 4 else ("r" if w.endswith("r") and len(w) > 4 else "")
        stem = w[:-1] if side else w
        best = None
        for b in arm.data.bones:
            n = b.name.lower().replace(".", "").replace("_", "").replace(" ", "")
            alias = {"shoulder": ("shoulder", "clavicle", "collar"), "neck": ("neck",), "spine": ("spine2", "spine1", "chest", "spine")}
            if any(a in n for a in alias.get(stem, (stem,))):
                if side and not (n.endswith(side) or ("left" if side == "l" else "right") in n):
                    continue
                best = b
                break
        return best

    bones = {p: find_bone(p) for p in PIN}
    missing = [p for p, b in bones.items() if b is None]
    if missing:
        raise RuntimeError("no bone for " + ", ".join(missing))
    spine = find_bone("spine")
    W = arm.matrix_world
    heads = {p: W @ b.head_local for p, b in bones.items()}
    xs = [v.x for v in heads.values()]
    width = max(0.2, max(xs) - min(xs))
    top_z = max(v.z for v in heads.values())
    centre_x = sum(xs) / len(xs)
    body_mesh = [o for o in body_objs if o.type == "MESH"]
    back_y = max((W2 @ Vector(c)).y for o in body_mesh for W2 in [o.matrix_world] for c in o.bound_box) if body_mesh else 0.1
    # the cloth: scaled to the shoulders, its top at the collar, hung just behind the back (a glTF body faces +Y... in
    # Blender after import a glTF's +Z front becomes -Y, so "behind" is +Y)
    co = [v.co for v in cloth.data.vertices]
    cmin = Vector((min(c.x for c in co), min(c.y for c in co), min(c.z for c in co)))
    cmax = Vector((max(c.x for c in co), max(c.y for c in co), max(c.z for c in co)))
    k = (width * 1.25) / max(cmax.x - cmin.x, 1e-6)
    for v in cloth.data.vertices:
        c = v.co
        v.co = Vector(((c.x - (cmin.x + cmax.x) / 2) * k + centre_x, (c.y - cmin.y) * k * 0.3 + back_y + 0.01,
                       (c.z - cmax.z) * k + top_z))
    h = (cmax.z - cmin.z) * k
    # weights: the top band pinned to the nearest pin bone; below, a little of the upper spine, fading to the hem
    groups = {p: cloth.vertex_groups.new(name=b.name) for p, b in bones.items()}
    sg = cloth.vertex_groups.new(name=spine.name) if spine is not None and spine.name not in [b.name for b in bones.values()] else None
    pinned = free = 0
    for v in cloth.data.vertices:
        t = (top_z - v.co.z) / max(h, 1e-6)          # 0 at the top, 1 at the hem
        near = min(heads, key=lambda p: (heads[p] - v.co).length)
        if t <= SHARE:
            groups[near].add([v.index], 1.0, "REPLACE")
            pinned += 1
        else:
            w = max(0.0, 1.0 - (t - SHARE) / max(1.0 - SHARE, 1e-6))
            groups[near].add([v.index], 0.35 * w + 0.05, "REPLACE")
            if sg is not None:
                sg.add([v.index], 0.6 * w + 0.05, "REPLACE")
            free += 1
    mod = cloth.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    cloth.parent = arm
    for mat in cloth.data.materials:
        if mat is not None:
            mat.name = NAME + "_material"
    bpy.ops.export_scene.gltf(filepath=out_p, export_format="GLB", export_animations=True, export_skins=True)
    say({"mesh": NAME, "pinned": pinned, "free": free, "pin_bones": [b.name for b in bones.values()],
         "spine": spine.name if spine is not None else None, "size_m": {"width": round(width * 1.25, 3), "height": round(h, 3)}})
except Exception as e:  # noqa: BLE001
    say({"error": f"{type(e).__name__}: {e}"})
