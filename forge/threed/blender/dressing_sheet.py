"""A picture of every dressing kind the stage compiler makes (BUILD 63, part 8b) — for docs/DRESSING_KINDS.md.

    <Blender's Python> dressing_sheet.py --out <folder>            (one <kind>.png a kind, 320 px, Cycles on the processor)

Each kind is made by build_stage.py's own dress() at the origin, lit by one soft key and a fill, and seen from the stage
camera's angle (high, looking north). The colours are plain stand-ins by material word: the game dresses them with its
own surfaces. Prints one machine line at the end: SHEET {"kinds": n, "out": folder}.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_stage as B  # noqa: E402

ITEMS = {
    "mug": {"kind": "mug"}, "book_stack": {"kind": "book_stack", "n": 4}, "book_row": {"kind": "book_row", "w": 0.5},
    "newspaper": {"kind": "newspaper"}, "clock": {"kind": "clock"}, "candlestick": {"kind": "candlestick", "lit": True},
    "photo": {"kind": "photo"}, "plant": {"kind": "plant"}, "coffee_maker": {"kind": "coffee_maker"}, "kettle": {"kind": "kettle"},
    "jars": {"kind": "jars", "n": 3}, "fruit_bowl": {"kind": "fruit_bowl"}, "cushion": {"kind": "cushion"},
    "toolbox": {"kind": "toolbox"}, "parts": {"kind": "parts", "n": 8}, "desk_lamp": {"kind": "desk_lamp"},
    "cable": {"kind": "cable", "pts": [[-0.3, 0.0, 0.01], [0.0, -0.15, 0.01], [0.3, 0.05, 0.01]]},
    "rope": {"kind": "rope", "h": 0.8}, "logs": {"kind": "logs", "n": 5},
    "box": {"kind": "box", "w": 0.3, "d": 0.2, "h": 0.15, "mat": "paper"},
}
COLOURS = {"ceramic": (0.85, 0.83, 0.78), "ceramic_blue": (0.3, 0.45, 0.75), "coffee": (0.18, 0.1, 0.05), "paper": (0.88, 0.86, 0.8),
           "wood": (0.45, 0.28, 0.15), "brass": (0.75, 0.6, 0.25), "wax": (0.92, 0.9, 0.8), "photo": (0.6, 0.55, 0.5),
           "terracotta": (0.65, 0.33, 0.2), "garden": (0.25, 0.18, 0.1), "houseplant": (0.2, 0.45, 0.2), "rack": (0.15, 0.15, 0.17),
           "steel": (0.6, 0.62, 0.65), "paint_red": (0.65, 0.12, 0.1), "paint_green": (0.2, 0.4, 0.25), "rope": (0.65, 0.55, 0.38),
           "bark": (0.3, 0.22, 0.15), "cloth_blue": (0.3, 0.38, 0.6), "fruit_red": (0.7, 0.12, 0.1), "fruit_yellow": (0.85, 0.7, 0.2),
           "book_red": (0.55, 0.12, 0.1), "book_green": (0.15, 0.35, 0.2), "book_blue": (0.15, 0.22, 0.45), "book_tan": (0.6, 0.5, 0.35),
           "book_black": (0.08, 0.08, 0.09)}


def material(word):
    m = bpy.data.materials.get(word) or bpy.data.materials.new(word)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if word.startswith("glow_"):
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.7, 0.35, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 6.0
    c = COLOURS.get(word, (0.55, 0.55, 0.55))
    bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
    bsdf.inputs["Roughness"].default_value = 0.25 if word in ("ceramic", "ceramic_blue", "steel", "brass") else 0.7
    return m


def shoot(kind, item, out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    B.GROUPS.clear()
    B.LAYER = ""
    B.dress([dict(item, at=[0.0, 0.0], z=0.0)])
    B.flush()
    obs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in obs:
        for i, slot in enumerate(o.material_slots):
            if slot.material is not None:
                o.material_slots[i].material = material(slot.material.name)
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in obs:
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    mid = (lo + hi) * 0.5
    size = max((hi - lo).length, 0.15)
    bpy.ops.mesh.primitive_plane_add(size=size * 6, location=(mid.x, mid.y, lo.z - 0.001))
    bpy.context.object.data.materials.append(material("paper"))
    scn = bpy.context.scene
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scn.collection.objects.link(cam)
    cam.data.lens = 70
    yaw, pitch = math.radians(10.0), math.radians(35.0)           # the stage camera: high, looking north
    d = size * 2.6
    cam.location = mid + Vector((math.sin(yaw) * math.cos(pitch) * d, -math.cos(yaw) * math.cos(pitch) * d, math.sin(pitch) * d))
    cam.rotation_euler = (mid - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scn.camera = cam
    for name, loc, energy, sz in (("key", (-1.5, -2.0, 3.0), 120.0, 1.2), ("fill", (2.5, 1.0, 2.0), 40.0, 2.0)):
        li = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        li.data.energy = energy * size
        li.data.size = sz
        li.location = mid + Vector(loc) * size
        li.rotation_euler = (mid - li.location).to_track_quat('-Z', 'Y').to_euler()
        scn.collection.objects.link(li)
    scn.world = bpy.data.worlds.new("w")
    scn.world.color = (0.05, 0.05, 0.06)
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 24
    scn.render.resolution_x = scn.render.resolution_y = 320
    scn.render.filepath = os.path.join(out, kind + ".png")
    bpy.ops.render.render(write_still=True)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    opt = dict(zip(args[::2], args[1::2]))
    out = opt["--out"]
    os.makedirs(out, exist_ok=True)
    for kind, item in ITEMS.items():
        shoot(kind, item, out)
        print("shot", kind, flush=True)
    print("SHEET " + json.dumps({"kinds": len(ITEMS), "out": out}), flush=True)


if __name__ == "__main__":
    main()
