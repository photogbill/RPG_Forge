"""Bake the keyed moves (keyed_moves.json) onto a rigged body as named actions (BUILD 43 part 3b).

    blender --background <scene.blend> --python keyed_moves.py -- --armature <name> [--prefix "<who>|"]
            [--only Bow_Stage,Curtsey] [--base-action Idle_Loop] [--forward -Y] [--save <out.blend>]
    blender --background --python keyed_moves.py -- --body <moves.glb> --out <moves_plus.glb> [--only ...]

Or from another script: `bake(arm, names=None, prefix="", base_action=None, forward="-Y")`.

A keyed move is described by where the hands go, how the spine bends, where the head looks and how far the hips sink
(the feet staying planted), not by bone angles - so one description fits every rig. The hands and the legs are reached
by the same two-bone solve as the conductor (key_conductor.py); between keys the pose eases. The base pose is the first
frame of the body's standing motion. Names are listed by `names()`; the cue sheets check moves against them.
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "keyed_moves.json")


def names() -> list[str]:
    with open(DATA, encoding="utf-8") as f:
        return sorted(json.load(f)["moves"])


def spec() -> dict:
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def _ease(u):
    return u * u * (3 - 2 * u)


def _interp(keys, t, part):
    """The value of one part (a list, or None = the standing pose) at time t, eased between the keys around it."""
    prev = keys[0]
    for k in keys[1:]:
        if t <= k["t"]:
            a, b = prev.get(part), k.get(part)
            u = _ease((t - prev["t"]) / max(k["t"] - prev["t"], 1e-6))
            if a is None and b is None:
                return None, 0.0
            if a is None:
                return list(b), u            # (target, weight): blend from the standing pose to b
            if b is None:
                return list(a), 1.0 - u
            if isinstance(a, list):
                return [a[i] + (b[i] - a[i]) * u for i in range(len(a))], 1.0
            return a + (b - a) * u, 1.0
        prev = k
    v = keys[-1].get(part)
    return (list(v) if isinstance(v, list) else v), (1.0 if v is not None else 0.0)


def bake(arm, only=None, prefix: str = "", base_action: str | None = None, forward: str = "-Y") -> dict:
    import bpy
    from mathutils import Quaternion, Vector
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import key_conductor as K

    data = spec()
    fps = int(data.get("fps", 30))
    scn = bpy.context.scene
    if arm.animation_data is None:
        arm.animation_data_create()
    if base_action:
        base = bpy.data.actions.get(base_action) or next((a for a in bpy.data.actions if a.name.endswith(base_action)
                                                          or a.name.startswith(base_action + "_")), None)
        if base is not None:
            arm.animation_data.action = base
    scn.frame_set(0)
    bpy.context.view_layer.update()
    rest_mat = {pb.name: pb.matrix.copy() for pb in arm.pose.bones}
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix = rest_mat[pb.name]
    bpy.context.view_layer.update()
    rest_q = {pb.name: (pb.rotation_quaternion.copy() if pb.rotation_mode == "QUATERNION" else pb.matrix_basis.to_quaternion())
              for pb in arm.pose.bones}
    hips = K._bone(arm, "Hips")
    rest_hips_loc = hips.location.copy() if hips else None
    ls, rs = K._bone(arm, "LeftArm"), K._bone(arm, "RightArm")
    centre = (ls.head + rs.head) / 2
    fwd, right, up = K._frame_axes(arm, forward)
    la = (K._bone(arm, "LeftForeArm").head - ls.head).length + (K._bone(arm, "LeftHand").head - K._bone(arm, "LeftForeArm").head).length
    scale = la / K.TRACK_ARM
    feet = {s: K._bone(arm, f"{s}Foot").head.copy() for s in ("Left", "Right") if K._bone(arm, f"{s}Foot")}
    hands_rest = {s: K._bone(arm, f"{s}Hand").head.copy() for s in ("Left", "Right")}
    spines = [b for b in (K._bone(arm, "Spine"), K._bone(arm, "Spine1"), K._bone(arm, "Spine2")) if b is not None]
    head_b, neck_b = K._bone(arm, "Head"), K._bone(arm, "Neck")
    limbs = [K._bone(arm, n) for n in ("LeftArm", "LeftForeArm", "RightArm", "RightForeArm",
                                       "LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg")]
    made = {}

    def leg(side, target):
        up_b, lo_b, end_b = K._bone(arm, f"{side}UpLeg"), K._bone(arm, f"{side}Leg"), K._bone(arm, f"{side}Foot")
        if not (up_b and lo_b and end_b):
            return
        S, E, W = up_b.head.copy(), lo_b.head.copy(), end_b.head.copy()
        a, b = (E - S).length, (W - E).length
        T = Vector(target)
        d = max(abs(a - b) + 1e-4, min((T - S).length, a + b - 1e-4))
        t = (T - S).normalized()
        pole = (E - S) - t * (E - S).dot(t)
        if pole.length < 1e-6:
            pole = fwd.copy()
        n = pole.normalized()
        cos_a = max(-1.0, min(1.0, (a * a + d * d - b * b) / (2 * a * d)))
        E2 = S + (t * cos_a + n * math.sqrt(max(0.0, 1 - cos_a * cos_a))) * a
        K._rotate(up_b, E - S, E2 - S)
        bpy.context.view_layer.update()
        E, W = lo_b.head.copy(), end_b.head.copy()
        K._rotate(lo_b, W - E, (S + t * d) - E)

    for name, mv in data["moves"].items():
        if only and name not in only:
            continue
        keys = mv["keys"]
        length = float(keys[-1]["t"])
        act = bpy.data.actions.new(prefix + name)
        act.use_fake_user = True
        arm.animation_data.action = act
        n = int(round(length * fps))
        for f in range(n + 1):
            t = f / fps
            for pb in arm.pose.bones:
                pb.rotation_mode = "QUATERNION"
                pb.rotation_quaternion = rest_q[pb.name]
            if hips is not None:
                hips.location = rest_hips_loc
            bpy.context.view_layer.update()
            sp, _w = _interp(keys, t, "spine")
            sp = sp or [0.0, 0.0]
            hd, _w = _interp(keys, t, "head")
            hd = hd or [0.0, 0.0]
            sink, _w = _interp(keys, t, "sink")
            sink = float(sink or 0.0)
            for b in spines:      # the bend is shared along the spine
                b.rotation_quaternion = rest_q[b.name] @ Quaternion((1, 0, 0), math.radians(sp[0]) / len(spines)) \
                                        @ Quaternion((0, 0, 1), math.radians(-sp[1]) / len(spines))
            if head_b is not None:
                head_b.rotation_quaternion = rest_q[head_b.name] @ Quaternion((0, 1, 0), math.radians(hd[0]) * 0.67) \
                                             @ Quaternion((1, 0, 0), math.radians(-hd[1]) * 0.67)
            if neck_b is not None:
                neck_b.rotation_quaternion = rest_q[neck_b.name] @ Quaternion((0, 1, 0), math.radians(hd[0]) * 0.33) \
                                             @ Quaternion((1, 0, 0), math.radians(-hd[1]) * 0.33)
            if hips is not None and sink:
                hips.location = rest_hips_loc.copy()
                # hips go down in the armature's space: move the pose bone so its head sinks by `sink`
                world_down = up * (-sink * scale)
                m = hips.matrix.copy()
                m.translation = m.translation + world_down
                hips.matrix = m
            bpy.context.view_layer.update()
            if sink:
                for s, fpos in feet.items():
                    leg(s, fpos)
                bpy.context.view_layer.update()
            ls2, rs2 = K._bone(arm, "LeftArm"), K._bone(arm, "RightArm")
            c_now = (ls2.head + rs2.head) / 2
            for side, part in (("Right", "right"), ("Left", "left")):
                v, w = _interp(keys, t, part)
                if v is None or w <= 0:
                    continue
                tgt = c_now + right * (v[0] * scale) + fwd * (v[1] * scale) + up * (v[2] * scale)
                if w < 1.0:
                    hand_now = K._bone(arm, f"{side}Hand").head.copy()
                    tgt = hand_now.lerp(tgt, w)
                K._two_bone(arm, side, tgt)
                bpy.context.view_layer.update()
            K._key(limbs + spines + [head_b, neck_b], f)
            if hips is not None:
                hips.keyframe_insert("location", frame=f, group=hips.name)
        act.frame_range = (0, max(1, n))
        made[name] = {"frames": n + 1, "loop": bool(mv.get("loop"))}
    arm.animation_data.action = None
    return {"made": made, "scale": round(scale, 3)}


def main(argv):
    import bpy

    def opt(flag, d=None):
        return argv[argv.index(flag) + 1] if flag in argv else d
    only = opt("--only").split(",") if opt("--only") else None
    if opt("--body"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=opt("--body"))
    arm = bpy.data.objects.get(opt("--armature")) if opt("--armature") else next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    if arm is None:
        print("NO ARMATURE")
        return 2
    base = opt("--base-action", "Idle_Loop")
    r = bake(arm, only, opt("--prefix", ""), base, opt("--forward", "-Y"))
    print("KEYED_MOVES", json.dumps(r))
    if opt("--out"):
        ad = arm.animation_data
        for a in bpy.data.actions:
            tr = ad.nla_tracks.new()
            # Blender 4.2 names an imported motion "<motion>_<figure>"; the file keeps the motion's own name
            tr.name = a.name[: -len(arm.name) - 1] if a.name.endswith("_" + arm.name) else a.name
            tr.strips.new(a.name, int(a.frame_range[0]), a)
            tr.mute = True
        bpy.ops.export_scene.gltf(filepath=opt("--out"), export_format="GLB", export_animations=True,
                                  export_animation_mode="NLA_TRACKS", export_force_sampling=True)
    if opt("--save"):
        bpy.ops.wm.save_as_mainfile(filepath=opt("--save"))
    return 0


if __name__ == "__main__":
    ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if ARGV:
        sys.exit(main(ARGV))
