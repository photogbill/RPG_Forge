"""Fit a library of motions (Quaternius Universal Animation Library, CC0) to a body rigged with the Mixamo-named skeleton.

    <Blender's Python> fit_motions.py <library.glb> <rigged_body.fbx> <out.glb> [--clips A,B,C] [--skip D,E] [--height 1.72]
                       [--travel <library_root_motion.glb>] [--blend out.blend]
    blender --background --python fit_motions.py -- <the same arguments>

Needs Blender's Python (bpy). Proven 2026-11-13 under Blender 5.3 and Blender 4.2 (the version the rigging tools carry),
with the same result from both, on a light A-pose body rigged by Make-It-Animatable; then on 92 bodies in one night.
Copied into the forge from the first game's test script (BUILD 36); only the argument reading changed (it also takes
its arguments after "--", for a Blender program) and the body's name is no longer one character's.

Every joint of the body is made to point where the library's joint points, frame by frame: the library's turn of
each bone away from its own rest is applied to the body's bone, after lining the two rests up (they are both T-poses,
but their bones do not sit at exactly the same angles). The hips also carry the library's up-and-down and sway,
scaled by leg length. Writes the body with every motion as a named animation, standing on the floor, in metres,
and beside it <out>.json: for each motion its length, whether it loops, and (with --travel) how fast the ground has
to pass under the body so that its feet do not slide - read from the library's own root-motion file and scaled to its legs.
"""
from __future__ import annotations

import json
import os
import sys
import time

import bpy
from mathutils import Matrix, Vector

MAP = {  # library bone -> Mixamo bone (without the "mixamorig:" prefix)
    "pelvis": "Hips", "spine_01": "Spine", "spine_02": "Spine1", "spine_03": "Spine2", "neck_01": "Neck", "Head": "Head",
}
for side, S in (("l", "Left"), ("r", "Right")):
    MAP.update({f"clavicle_{side}": f"{S}Shoulder", f"upperarm_{side}": f"{S}Arm", f"lowerarm_{side}": f"{S}ForeArm",
                f"hand_{side}": f"{S}Hand", f"thigh_{side}": f"{S}UpLeg", f"calf_{side}": f"{S}Leg",
                f"foot_{side}": f"{S}Foot", f"ball_{side}": f"{S}ToeBase"})
    for finger, F in (("thumb", "Thumb"), ("index", "Index"), ("middle", "Middle"), ("ring", "Ring"), ("pinky", "Pinky")):
        for k in (1, 2, 3):
            MAP[f"{finger}_0{k}_{side}"] = f"{S}Hand{F}{k}"
# which joint a bone "points at" (for lining the two rests up); bones not listed keep their own rest angle
AIM = {"Spine": "Spine1", "Spine1": "Spine2", "Spine2": "Neck", "Neck": "Head"}
for S in ("Left", "Right"):
    AIM.update({f"{S}Shoulder": f"{S}Arm", f"{S}Arm": f"{S}ForeArm", f"{S}ForeArm": f"{S}Hand", f"{S}Hand": f"{S}HandMiddle1",
                f"{S}UpLeg": f"{S}Leg", f"{S}Leg": f"{S}Foot", f"{S}Foot": f"{S}ToeBase"})
    for F in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
        AIM.update({f"{S}Hand{F}1": f"{S}Hand{F}2", f"{S}Hand{F}2": f"{S}Hand{F}3"})
PRE = "mixamorig:"


def clean(name: str, owner: str) -> str:
    """Blender 4.2 names an imported motion "<motion>_<the figure it came on>"; later versions just "<motion>"."""
    return name[: -len(owner) - 1] if name.endswith("_" + owner) else name


def rot(m: Matrix) -> Matrix:
    return m.to_3x3().normalized()


ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def opt(flag, default=None):
    return ARGV[ARGV.index(flag) + 1] if flag in ARGV else default


def travel_of(path):
    """Metres a second each motion of the library covers, from its root-motion file ({} when it has none)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if "gltf" not in dir(bpy.ops.import_scene):
        import addon_utils
        addon_utils.enable("io_scene_gltf2", default_set=False)
    bpy.ops.import_scene.gltf(filepath=path)
    sc = bpy.context.scene
    arm = next(o for o in sc.objects if o.type == "ARMATURE")
    arm.animation_data_create()
    out = {}
    for act in bpy.data.actions:
        arm.animation_data.action = act
        if hasattr(arm.animation_data, "action_slot") and getattr(act, "slots", None):
            try:
                arm.animation_data.action_slot = act.slots[0]
            except Exception:
                pass
        a0, a1 = act.frame_range
        ends = []
        for at in (a0, a1):
            sc.frame_set(int(at // 1), subframe=at - (at // 1))
            ends.append((arm.matrix_world @ arm.pose.bones["root"].matrix.translation).copy())
        d = ends[1] - ends[0]
        d.z = 0.0
        secs = (a1 - a0) / sc.render.fps
        if d.length > 0.05 and secs > 0:
            out[clean(act.name, arm.name)] = d.length / secs
    return out


def main():
    lib_path, body_path, out_path = ARGV[0], ARGV[1], ARGV[2]
    travel = travel_of(opt("--travel")) if opt("--travel") else {}
    height = float(opt("--height", 1.72))
    only = [c for c in (opt("--clips", "") or "").split(",") if c]
    skip = [c for c in (opt("--skip", "") or "").split(",") if c]           # motions this character never does
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    if "gltf" not in dir(bpy.ops.import_scene):
        import addon_utils
        addon_utils.enable("io_scene_gltf2", default_set=False)
    bpy.ops.import_scene.gltf(filepath=lib_path)
    src = next(o for o in sc.objects if o.type == "ARMATURE")
    came_on = src.name
    src.name = "library"
    lib_objects = set(sc.objects)
    actions = sorted((a for a in bpy.data.actions), key=lambda a: a.name)
    lib_name = {}
    for a in actions:                       # the library's own actions step aside, so the fitted ones take the clean names
        lib_name[a] = clean(a.name, came_on)
        a.name = "lib:" + a.name
    fps = sc.render.fps
    if "fbx_import" in dir(bpy.ops.wm):                      # Blender 4.5 and later
        bpy.ops.wm.fbx_import(filepath=body_path)
    else:                                                   # Blender 4.2 (the rigging tools' own Blender)
        import addon_utils
        addon_utils.enable("io_scene_fbx", default_set=False)
        bpy.ops.import_scene.fbx(filepath=body_path)
    tgt = next(o for o in sc.objects if o.type == "ARMATURE" and o not in lib_objects)
    body = next(o for o in sc.objects if o.type == "MESH" and o not in lib_objects)
    tgt.name = "character"
    sc.render.fps = fps
    bpy.context.view_layer.update()

    inv = {v: k for k, v in MAP.items()}                       # Mixamo name -> library name
    tb = {b.name[len(PRE):]: b for b in tgt.data.bones if b.name.startswith(PRE)}
    sb = {b.name: b for b in src.data.bones}
    missing = [m for m in MAP.values() if m not in tb]
    print("BLENDER", bpy.app.version_string, flush=True)
    print("BONES body", len(tb), "library", len(sb), "mapped", len(MAP) - len(missing), "not in body:", missing[:8], flush=True)

    Mt, Ms = tgt.matrix_world.copy(), src.matrix_world.copy()
    t_rest = {n: rot(Mt @ b.matrix_local) for n, b in tb.items()}
    t_head = {n: Mt @ b.head_local for n, b in tb.items()}
    s_rest = {n: rot(Ms @ b.matrix_local) for n, b in sb.items()}
    s_head = {n: Ms @ b.head_local for n, b in sb.items()}
    t_scale = Mt.to_scale()[0]

    # line the rests up: the turn that takes the library bone's rest direction onto the body bone's rest direction
    fix = {}
    for n in tb:
        a = Matrix.Identity(3)
        if n in inv and n in AIM and AIM[n] in tb and inv.get(AIM[n]) in sb:
            ds = (s_head[inv[AIM[n]]] - s_head[inv[n]]).normalized()
            dt = (t_head[AIM[n]] - t_head[n]).normalized()
            a = ds.rotation_difference(dt).to_matrix()
        fix[n] = a.inverted() @ t_rest[n] if n in inv else None  # A^-1 . T_rest

    floor_t = min((body.matrix_world @ Vector(c)).z for c in body.bound_box)
    hips_t = t_head["Hips"]
    hips_s = s_head["pelvis"]
    k_leg = (hips_t.z - floor_t) / max(hips_s.z, 1e-6)
    print(f"REST hips: body {hips_t.z - floor_t:.3f} above its floor, library {hips_s.z:.3f}; leg scale {k_leg:.3f}", flush=True)

    order = [b.name[len(PRE):] for b in tgt.data.bones if b.name.startswith(PRE)]        # parents come first
    parent = {n: (tb[n].parent.name[len(PRE):] if tb[n].parent and tb[n].parent.name.startswith(PRE) else None) for n in order}
    pb_t = {n: tgt.pose.bones[PRE + n] for n in order}
    for p in pb_t.values():
        p.rotation_mode = "QUATERNION"
    tgt.animation_data_create()
    src.animation_data_create()
    made = []
    seconds = {}
    t0 = time.time()
    for act in actions:
        name = lib_name[act]
        if (only and name not in only) or name in skip:
            continue
        src.animation_data.action = act
        if hasattr(src.animation_data, "action_slot") and getattr(act, "slots", None):
            try:
                src.animation_data.action_slot = act.slots[0]
            except Exception:
                pass
        a0, a1 = act.frame_range[0], act.frame_range[1]
        count = max(int(round(a1 - a0)), 1)               # a clip that ends between two frames is read evenly, so a loop stays a loop
        new = bpy.data.actions.new(name)
        new.use_fake_user = True
        tgt.animation_data.action = new
        for f in range(0, count + 1):
            at = a0 + (a1 - a0) * f / count
            sc.frame_set(int(at // 1), subframe=at - (at // 1))
            sw = {n: rot(Ms @ src.pose.bones[n].matrix) for n in inv.values() if n in src.pose.bones}
            sp = Ms @ src.pose.bones["pelvis"].matrix.translation
            world = {}
            for n in order:
                p = parent[n]
                if fix[n] is not None and inv[n] in sw:
                    world[n] = sw[inv[n]] @ s_rest[inv[n]].inverted() @ fix[n]
                else:                                                     # not in the library: stays as it rests on its parent
                    world[n] = (world[p] @ t_rest[p].inverted() @ t_rest[n]) if p else t_rest[n]
                base = (world[p] @ t_rest[p].inverted() @ t_rest[n]) if p else t_rest[n]
                pb_t[n].rotation_quaternion = (base.inverted() @ world[n]).to_quaternion()
                pb_t[n].keyframe_insert("rotation_quaternion", frame=f)
            delta = Vector(((sp.x - hips_s.x) * k_leg, (sp.y - hips_s.y) * k_leg, (sp.z - hips_s.z) * k_leg))
            pb_t["Hips"].location = (t_rest["Hips"].inverted() @ delta) / t_scale
            pb_t["Hips"].keyframe_insert("location", frame=f)
        made.append((new, 0, count))
        seconds[name] = (a1 - a0) / fps
    print(f"FITTED {len(made)} motions in {time.time() - t0:.0f} s", flush=True)

    # every motion on its own track, so the file carries them all by name
    tgt.animation_data.action = None
    for new, f0, f1 in made:
        tr = tgt.animation_data.nla_tracks.new()
        tr.name = new.name
        st = tr.strips.new(new.name, f0, new)
        st.name = new.name
        tr.mute = True
    for a in actions:                                    # the library's actions do not belong in its file
        bpy.data.actions.remove(a)
    print("MOTIONS " + ", ".join(f"{a.name} {f1 - f0}f" for a, f0, f1 in made), flush=True)
    # the library's own figure is no longer needed
    for o in list(lib_objects):
        bpy.data.objects.remove(o, do_unlink=True)

    # stand the body on the floor, in metres
    s = height / max(max((body.matrix_world @ Vector(c)).z for c in body.bound_box) - floor_t, 1e-6)
    tgt.scale = tgt.scale * s
    tgt.location = Vector((tgt.location.x * s, tgt.location.y * s, tgt.location.z * s - floor_t * s))
    bpy.context.view_layer.update()
    lo = min((body.matrix_world @ Vector(c)).z for c in body.bound_box)
    hi = max((body.matrix_world @ Vector(c)).z for c in body.bound_box)
    print(f"STANDS feet at {lo:.3f} m, top at {hi:.3f} m", flush=True)

    if opt("--blend"):
        bpy.ops.wm.save_as_mainfile(filepath=opt("--blend"))
    for o in sc.objects:
        o.select_set(o in (tgt, body))
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=True, export_yup=True,
                              export_animations=True, export_animation_mode="NLA_TRACKS", export_force_sampling=True,
                              export_skins=True, export_def_bones=False, export_optimize_animation_size=True)
    print("WROTE", out_path, flush=True)
    k = k_leg * s                                         # its stride against the library figure's
    sheet = {"_comment": "Written by the motion fitter. speed = metres a second the ground passes at normal playing speed "
                         "(absent: the motion stays on the spot).",
             "body": os.path.basename(body_path), "library": os.path.basename(lib_path), "height_m": round(height, 3),
             "stride_scale": round(k, 4), "left_out": skip, "motions": {}}
    for new, f0, f1 in made:
        m = {"seconds": round(seconds[new.name], 4), "loop": new.name.endswith("_Loop")}
        if new.name in travel:
            m["speed"] = round(travel[new.name] * k, 3)
        sheet["motions"][new.name] = m
    with open(os.path.splitext(out_path)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(sheet, fh, indent=1)
    print("WROTE", os.path.splitext(out_path)[0] + ".json", flush=True)


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)                 # Blender 4.2's Python can fall over while shutting down, after the work is done and saved
