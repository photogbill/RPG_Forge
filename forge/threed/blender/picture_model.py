"""Picture one made model: an icon of a thing, or a head-and-shoulders portrait of a body (BUILD 91).

    <Blender's Python> picture_model.py <spec.json>
    blender --background --python picture_model.py -- <spec.json>

Rendered with Cycles on the PROCESSOR (never the graphics card), on a clear background, so it can run beside anything.
The spec (every field but `model` and `out` has a default):

    {"model": "thing.glb", "out": "thing.png", "kind": "icon" | "portrait", "pixels": 1024, "samples": 40,
     "az": 35, "el": 22, "auto_view": true, "margin": 0.07,
     "light": {"preset": "key" | "candle", "key": [r, g, b], "key_power": 1.0, "rim": [r, g, b], "rim_power": 1.0,
               "ambient": 0.2},
     "clip": "Idle_Loop", "frame": 0, "shape_key": null, "head_share": 0.3}

icon      The whole thing fitted into the frame, seen three-quarter: from `az` degrees round its front and `el` degrees
          up, through a camera with no perspective (so every icon is on one scale-free footing). `auto_view` applies
          one rule to everything: the thing's longer ground side is laid across the frame, and a thing that lies flat
          (a pistol on the ground) is looked at from higher up, so it is seen and not sighted along. One fixed key
          light from the upper left, the same for all, and a low even fill so no side is black.
portrait  A body's head and shoulders: the top `head_share` of its height, face on and a little to one side, through a
          long lens. If the body has an armature it is put at rest in the motion named by `clip` (its first frame);
          `shape_key` sets one expression if the body has any. Light preset "candle": one warm key close to the face,
          falling off to dark, and a faint rim from behind in the colour given.

Prints one line "PICTURE {json}": the file, what view and clip were used, the body's motions and expressions, seconds.
"""
from __future__ import annotations

import json
import math
import sys
import time

import bpy                      # first: as a module, Blender's own packages come with it
from mathutils import Matrix, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def world_points(objs, dg, step: int = 1):
    """Every mesh vertex where it really is (after the armature and shape keys), as a list of Vectors."""
    pts = []
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ev.matrix_world
        vs = me.vertices
        for i in range(0, len(vs), step):
            pts.append(mw @ vs[i].co)
        ev.to_mesh_clear()
    return pts


def bounds(pts):
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def long_axis_angle(pts, centre):
    """The direction (radians, in the ground plane) of the thing's longer side: the main axis of its points seen from above."""
    sxx = syy = sxy = 0.0
    for p in pts:
        dx, dy = p.x - centre.x, p.y - centre.y
        sxx += dx * dx
        syy += dy * dy
        sxy += dx * dy
    return 0.5 * math.atan2(2.0 * sxy, sxx - syy), (max(sxx, syy) / max(min(sxx, syy), 1e-12)) ** 0.5


def look_from(target: Vector, az: float, el: float, dist: float) -> tuple[Vector, Matrix]:
    """A camera `dist` away, `az` degrees round from the front (-Y is the front of a model as Blender imports a .glb;
    positive az goes round to its left as we look at it) and `el` degrees up, looking at `target`."""
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    pos = target + d * dist
    fwd = (target - pos).normalized()
    right = fwd.cross(Vector((0, 0, 1)))
    if right.length < 1e-6:
        right = Vector((1, 0, 0))
    right.normalize()
    up = right.cross(fwd)
    rot = Matrix((right, up, -fwd)).transposed()
    return pos, rot


def add_light(name, kind, pos, target, colour, watts, size):
    li = bpy.data.lights.new(name, kind)
    li.color = colour[:3]
    li.energy = watts
    if kind == "AREA":
        li.size = size
    else:
        li.shadow_soft_size = size
    ob = bpy.data.objects.new(name, li)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = pos
    d = (Vector(target) - Vector(pos)).normalized()
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def set_world(strength: float) -> None:
    sc = bpy.context.scene
    w = bpy.data.worlds.new("even")
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:  # noqa: BLE001 - newer Blenders always use nodes
        pass
    bg = w.node_tree.nodes.get("Background") if w.node_tree else None
    if bg is not None:
        bg.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
        bg.inputs[1].default_value = float(strength)


def pose(arm, clip: str, frame: int) -> tuple[str | None, list[str]]:
    """Put an armature at one frame of one of its motions. Returns (the motion used, every motion it has)."""
    names = sorted(a.name for a in bpy.data.actions)
    if arm is None or not names:
        return None, names
    want = [clip] if clip else []
    want += ["Idle_Loop", "Idle", "idle"]
    act = None
    acts = sorted(bpy.data.actions, key=lambda a: (len(a.name), a.name))
    for w in want:                                # its own name; else "<motion>_<figure>", as Blender 4.2 names an imported motion;
        low = w.lower()                           # only then anything that holds the word (never Crouch_Idle_Loop for Idle_Loop)
        act = (next((a for a in acts if a.name == w), None)
               or next((a for a in acts if a.name.lower().startswith(low + "_") or a.name.lower() == low), None)
               or next((a for a in acts if low in a.name.lower()), None))
        if act is not None:
            break
    if act is None:
        return None, names
    if arm.animation_data is None:
        arm.animation_data_create()
    ad = arm.animation_data
    for t in ad.nla_tracks:                       # the importer parks every motion on its own track: silence them
        t.mute = True
    ad.action = act
    slots = getattr(act, "slots", None)           # Blender 4.4 and later: an action is played through a slot
    if slots is not None and len(slots) and hasattr(ad, "action_slot"):
        try:
            ad.action_slot = slots[0]
        except Exception:  # noqa: BLE001
            pass
    bpy.context.scene.frame_set(int(act.frame_range[0]) + int(frame))
    return act.name, names


def hold_pose(arm, level: bool) -> list[str]:
    """Keep the pose the motion gave, without the motion: every bone's own turn is written down and the motion taken
    off. With `level`, the head and neck are set back to how the body was built (looking straight ahead), so a portrait
    meets the eye whatever the idle motion was doing with the head. Returns the bones levelled."""
    done = []
    kept = {}
    for b in arm.pose.bones:
        b.rotation_mode = "QUATERNION" if b.rotation_mode == "QUATERNION" else b.rotation_mode
        kept[b.name] = (b.location.copy(), b.rotation_quaternion.copy(), b.rotation_euler.copy(), b.scale.copy())
    ad = arm.animation_data
    if ad is not None:
        ad.action = None
        for t in ad.nla_tracks:
            t.mute = True
    for b in arm.pose.bones:
        loc, quat, eul, sca = kept[b.name]
        b.location, b.rotation_quaternion, b.rotation_euler, b.scale = loc, quat, eul, sca
    bpy.context.view_layer.update()
    if level:
        for b in arm.pose.bones:
            if b.name.split(":")[-1].lower() == "head":     # the head as the body was built: upright, facing where the body faces
                m = b.matrix.copy()                         # (the spine may lean in an idle motion; the head must not follow it down)
                b.matrix = Matrix.Translation(m.to_translation()) @ b.bone.matrix_local.to_3x3().to_4x4()
                done.append(b.name)
        bpy.context.view_layer.update()
    return done


def smooth(meshes) -> None:
    """A body made from a picture comes with every face flat and every seam split. Join what touches and let the light
    run smoothly over it — a face seen close should not show its triangles."""
    for o in meshes:
        try:
            m = o.modifiers.new("join seams", "WELD")
            m.merge_threshold = 0.00002
            while o.modifiers[0] != m:                     # before the armature, so it works on the body as built
                bpy.context.view_layer.objects.active = o
                bpy.ops.object.modifier_move_up(modifier=m.name)
        except Exception:  # noqa: BLE001
            pass
        o.data.polygons.foreach_set("use_smooth", [True] * len(o.data.polygons))
        o.data.update()


def main() -> int:
    t0 = time.time()
    spec = json.loads(open(ARGV[0], encoding="utf-8").read())
    kind = spec.get("kind", "icon")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=spec["model"])
    sc = bpy.context.scene
    arm = next((o for o in sc.objects if o.type == "ARMATURE"), None)
    helpers = {b.custom_shape.name for b in arm.pose.bones if b.custom_shape} if arm is not None else set()
    meshes = [o for o in sc.objects if o.type == "MESH" and o.name not in helpers and o.visible_get()]   # not the importer's bone shapes
    if not meshes:
        print("PICTURE " + json.dumps({"ok": False, "error": "the file has no mesh in it"}), flush=True)
        return 2
    used, motions = pose(arm, str(spec.get("clip") or ""), int(spec.get("frame") or 0)) if (kind == "portrait" or spec.get("clip")) else (None, sorted(a.name for a in bpy.data.actions))
    if kind == "portrait":
        if arm is not None and used:
            info_level = hold_pose(arm, bool(spec.get("level_head", True)))
        else:
            info_level = []
        if spec.get("smooth", True):
            smooth(meshes)
    else:
        info_level = []
    keys = sorted({k.name for o in meshes if o.data.shape_keys for k in o.data.shape_keys.key_blocks if k.name != "Basis"})
    if spec.get("shape_key"):
        for o in meshes:
            if o.data.shape_keys and spec["shape_key"] in o.data.shape_keys.key_blocks:
                o.data.shape_keys.key_blocks[spec["shape_key"]].value = 1.0
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    total = sum(len(o.data.vertices) for o in meshes)
    pts = world_points(meshes, dg, max(1, total // 60000))
    lo, hi = bounds(pts)
    size = hi - lo
    centre = (lo + hi) / 2
    info = {"ok": True, "kind": kind, "size_m": [round(size.x, 4), round(size.y, 4), round(size.z, 4)], "motions": motions,
            "motion_used": used, "expressions": keys, "armature": arm is not None, "head_levelled": bool(info_level)}
    light = spec.get("light") or {}
    cam = bpy.data.cameras.new("cam")
    cam_ob = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(cam_ob)
    sc.camera = cam_ob
    margin = float(spec.get("margin", 0.07))

    if kind == "portrait":
        top = hi.z
        neck = None
        if arm is not None:                               # a rigged body says where its head is
            bone = next((b for b in arm.pose.bones if b.name.split(":")[-1].lower() == "head"), None) or \
                next((b for b in arm.pose.bones if "head" in b.name.lower() and "top" not in b.name.lower()), None)
            if bone is not None:
                neck = (arm.matrix_world @ bone.head).z
        if neck is not None and 0.05 * size.z < top - neck < 0.3 * size.z:
            head_h = top - neck
            cut = neck - head_h * float(spec.get("below_chin", 0.8))       # the shoulders and the top of the chest
            top = top + head_h * 0.1
            info["framed_by"] = "the head bone"
        else:
            cut = top - size.z * float(spec.get("head_share", 0.27))
            info["framed_by"] = "the top of its height (no head bone found)"
        head = [p for p in pts if p.z >= hi.z - size.z * 0.12] or pts
        hx = sum(p.x for p in head) / len(head)
        hy = sum(p.y for p in head) / len(head)
        target = Vector((hx, hy, (top + cut) / 2))
        frame_h = (top - cut) * (1.0 + 2 * margin)
        cam.type = "PERSP"
        cam.lens = float(spec.get("lens", 85.0))
        cam.sensor_width = cam.sensor_height = 36.0
        fov = 2 * math.atan(18.0 / cam.lens)
        dist = (frame_h / 2) / math.tan(fov / 2)
        az, el = float(spec.get("az", 14.0)), float(spec.get("el", 2.0))
        pos, rot = look_from(target, az, el, dist)
        cam_ob.matrix_world = Matrix.Translation(pos) @ rot.to_4x4()
        cam.clip_start, cam.clip_end = dist * 0.05, dist * 20
        r = frame_h / 2
        info.update(view=[az, el], frame_m=round(frame_h, 3))
    else:
        az, el = float(spec.get("az", 35.0)), float(spec.get("el", 22.0))
        if spec.get("auto_view", True):
            ang, stretch = long_axis_angle(pts, centre)
            ground = max(size.x, size.y, 1e-6)
            flat = max(0.0, min(1.0, (0.45 - size.z / ground) / 0.45))
            el = el + (64.0 - el) * flat                  # a thing lying flat is looked at from above
            if stretch > 1.25:                             # lay its longer side across the frame, then the three-quarter turn
                az = math.degrees(ang) + az * (0.6 if flat > 0.5 else 1.0)
            info.update(flat=round(flat, 2), stretch=round(stretch, 2))
        r = max(size.length / 2, 1e-6)
        pos, rot = look_from(centre, az, el, r * 6)
        if spec.get("auto_view", True) and info.get("stretch", 1.0) > 2.2:
            rot = rot @ Matrix.Rotation(math.radians(float(spec.get("roll", -38.0))), 3, "Z")   # a long thing lies along the frame's diagonal
            info["rolled"] = True
        inv = (Matrix.Translation(pos) @ rot.to_4x4()).inverted()
        xs, ys = [], []
        for p in pts:
            c = inv @ p
            xs.append(c.x)
            ys.append(c.y)
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        shift = rot @ Vector(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, 0.0))
        cam_ob.matrix_world = Matrix.Translation(pos + shift) @ rot.to_4x4()
        cam.type = "ORTHO"
        cam.ortho_scale = max(w, h) * (1.0 + 2 * margin)
        cam.clip_start, cam.clip_end = r * 0.1, r * 14
        target = centre + shift
        info.update(view=[round(az, 1), round(el, 1)], frame_m=round(cam.ortho_scale, 4))

    # light: placed by the camera's own left, right and up, so it is the same picture-light for every model
    cm = cam_ob.matrix_world.to_3x3()
    right, up, back = cm @ Vector((1, 0, 0)), cm @ Vector((0, 1, 0)), cm @ Vector((0, 0, 1))
    preset = light.get("preset") or ("candle" if kind == "portrait" else "key")
    if preset == "candle":
        key_c = light.get("key") or (1.0, 0.86, 0.70)
        kpos = target + (right * 0.95 + up * 0.35 + back * 0.9).normalized() * r * 2.3
        add_light("key", "POINT", kpos, target, key_c, 85.0 * r * r * float(light.get("key_power", 1.0)), r * 0.10)
        rim_c = light.get("rim") or (0.55, 0.68, 1.0)
        rpos = target + (right * -0.9 + up * 0.55 + back * -1.0).normalized() * r * 3.0
        add_light("rim", "AREA", rpos, target, rim_c, 34.0 * r * r * float(light.get("rim_power", 1.0)), r * 1.2)
        set_world(float(light.get("ambient", 0.07)))
    else:
        key_c = light.get("key") or (1.0, 0.97, 0.92)
        kpos = target + (right * -0.75 + up * 0.95 + back * 0.85).normalized() * r * 4.0
        add_light("key", "AREA", kpos, target, key_c, 480.0 * r * r * float(light.get("key_power", 1.0)), r * 2.2)
        set_world(float(light.get("ambient", 0.32)))
    info["light"] = preset

    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = int(spec.get("samples", 40))
    for attr, val in (("use_denoising", True), ("use_adaptive_sampling", True)):
        try:
            setattr(sc.cycles, attr, val)
        except Exception:  # noqa: BLE001
            pass
    sc.render.film_transparent = True
    px = int(spec.get("pixels", 1024))
    sc.render.resolution_x = sc.render.resolution_y = px
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "8"
    try:
        sc.view_settings.view_transform = "Standard"       # the model's own colours, not a film look
        sc.view_settings.look = "None"
    except Exception:  # noqa: BLE001
        pass
    sc.render.filepath = spec["out"]
    try:
        bpy.ops.render.render(write_still=True)
    except Exception as e:  # noqa: BLE001
        if getattr(sc.cycles, "use_denoising", False):      # a Blender built without the denoiser: once more without it
            sc.cycles.use_denoising = False
            sc.cycles.samples = int(spec.get("samples", 40)) * 3
            bpy.ops.render.render(write_still=True)
            info["denoised"] = False
        else:
            print("PICTURE " + json.dumps({"ok": False, "error": str(e)[:300]}), flush=True)
            return 3
    info.update(out=spec["out"], pixels=px, seconds=round(time.time() - t0, 1), blender=bpy.app.version_string)
    print("PICTURE " + json.dumps(info), flush=True)
    return 0


if __name__ == "__main__":
    import os
    code = main()
    sys.stdout.flush()
    os._exit(code)              # Blender 4.2's Python can fall over while shutting down, after the picture is written
