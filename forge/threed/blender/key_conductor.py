"""Put a conductor's track (forge.film.conductor) on a rigged body: hands, head, torso and the left fist, keyed per frame.

    blender --background <scene.blend> --python key_conductor.py -- --armature <name> --track <track.json>
            [--action Conduct] [--frame-start 1] [--base-action Idle_Loop] [--base-frame 0] [--step 1] [--save <out.blend>]

Or from another Blender script: `key(arm, track, ...)`.

The arms are reached by a two-bone solve written here (shoulder and elbow turned, the elbow kept in the plane it
already bends in), not by Blender's IK: a generated rig's scale defeats Blender's IK (found on the opera house's
glasses poses, BUILD 44), and a solve keyed as rotations exports to a .glb and plays in any engine as an ordinary motion.
Bones are the Mixamo names the forge's rigs carry ("mixamorig:RightArm" …); a rig without the prefix works too.

The track's space is the conductor's own: x to his right, y forward, z up, from the point between his shoulders at the
first frame of his base pose. Forward is the way the body faces (`--forward -Y` for the forge's bodies, which face -Y);
the track is scaled to the body's arm length (the track is written for an arm of 0.58 m).
"""
from __future__ import annotations

import json
import math
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

TRACK_ARM = 0.58


def _bone(arm, name):
    pb = arm.pose.bones.get("mixamorig:" + name)
    return pb if pb is not None else arm.pose.bones.get(name)


def _rotate(pb, frm, to):
    q = frm.normalized().rotation_difference(to.normalized())
    h = pb.head.copy()
    pb.matrix = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h) @ pb.matrix


def _two_bone(arm, side, target_arm_space):
    """Put the wrist of one arm on a point (armature space)."""
    up, lo, hand = (_bone(arm, f"{side}{n}") for n in ("Arm", "ForeArm", "Hand"))
    if not (up and lo and hand):
        return False
    T = Vector(target_arm_space)
    S, E, W = up.head.copy(), lo.head.copy(), hand.head.copy()
    a, b = (E - S).length, (W - E).length
    d = max(abs(a - b) + 1e-4, min((T - S).length, a + b - 1e-4))
    t = (T - S).normalized()
    pole = (E - S) - t * (E - S).dot(t)
    if pole.length < 1e-6:
        pole = Vector((0, 0, -1)) - t * t.z
    n = pole.normalized()
    cos_a = max(-1.0, min(1.0, (a * a + d * d - b * b) / (2 * a * d)))
    E2 = S + (t * cos_a + n * math.sqrt(max(0.0, 1 - cos_a * cos_a))) * a
    _rotate(up, E - S, E2 - S)
    bpy.context.view_layer.update()
    E, W = lo.head.copy(), hand.head.copy()
    _rotate(lo, W - E, (S + t * d) - E)
    return True


def _key(pbs, frame):
    for pb in pbs:
        if pb is None:
            continue
        pb.rotation_mode = "QUATERNION"
        pb.keyframe_insert("rotation_quaternion", frame=frame, group=pb.name)


def _frame_axes(arm, forward_axis: str):
    """Forward, right and up in armature space."""
    ax = {"-Y": Vector((0, -1, 0)), "Y": Vector((0, 1, 0)), "+Y": Vector((0, 1, 0)), "X": Vector((1, 0, 0)),
          "+X": Vector((1, 0, 0)), "-X": Vector((-1, 0, 0))}[forward_axis]
    up = Vector((0, 0, 1))
    right = ax.cross(up)
    return ax, right.normalized(), up


def key(arm, track: dict, action: str = "Conduct", frame_start: int = 1, base_action: str | None = None,
        base_frame: int = 0, step: int = 1, forward: str = "-Y") -> dict:
    """Key the track on `arm` as a new action (the base pose's other bones are kept as they are at base_frame)."""
    scn = bpy.context.scene
    if arm.animation_data is None:
        arm.animation_data_create()
    if base_action:
        base = bpy.data.actions.get(base_action)
        if base is None:
            base = next((a for a in bpy.data.actions if a.name.startswith(base_action)), None)
        if base is not None:
            arm.animation_data.action = base
    scn.frame_set(base_frame)
    bpy.context.view_layer.update()
    rest = {pb.name: pb.matrix.copy() for pb in arm.pose.bones}           # the base pose, armature space
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix = rest[pb.name]
    bpy.context.view_layer.update()
    rest_local = {pb.name: (pb.rotation_quaternion.copy() if pb.rotation_mode == "QUATERNION" else pb.matrix_basis.to_quaternion())
                  for pb in arm.pose.bones}
    act = bpy.data.actions.new(action)
    act.use_fake_user = True
    arm.animation_data.action = act

    ls, rs = _bone(arm, "LeftArm"), _bone(arm, "RightArm")
    if ls is None or rs is None:
        raise RuntimeError("the rig has no LeftArm / RightArm bones")
    centre = (ls.head + rs.head) / 2
    fwd, right, up = _frame_axes(arm, forward)
    la = (_bone(arm, "LeftForeArm").head - ls.head).length + (_bone(arm, "LeftHand").head - _bone(arm, "LeftForeArm").head).length
    scale = la / TRACK_ARM
    head_b, neck_b, spine_b = _bone(arm, "Head"), _bone(arm, "Neck"), _bone(arm, "Spine1") or _bone(arm, "Spine")
    fingers = [_bone(arm, f"LeftHand{f}{k}") for f in ("Index", "Middle", "Ring", "Pinky") for k in (1, 2, 3)]
    arms = [_bone(arm, n) for n in ("LeftArm", "LeftForeArm", "RightArm", "RightForeArm")]

    def to_arm_space(p):
        x, y, z = p
        return centre + right * (x * scale) + fwd * (y * scale) + up * (z * scale)

    n = int(track["frames"])
    fps = int(track["fps"])
    if scn.render.fps != fps:
        scn.render.fps = fps
    misses = 0
    for f in range(0, n, max(1, int(step))):
        for pb in arm.pose.bones:                                   # back to the base pose
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = rest_local[pb.name]
        bpy.context.view_layer.update()
        lean, sway = track["torso"][f]
        if spine_b is not None and (lean or sway):
            spine_b.rotation_quaternion = rest_local[spine_b.name] @ Quaternion((1, 0, 0), math.radians(lean)) @ Quaternion((0, 0, 1), math.radians(sway))
        yaw, pitch = track["head"][f]
        if head_b is not None:
            # head turns about its own up, nods about its own side; the neck takes a third of it
            q = Quaternion((0, 1, 0), math.radians(yaw) * 0.67) @ Quaternion((1, 0, 0), math.radians(-pitch) * 0.67)
            head_b.rotation_quaternion = rest_local[head_b.name] @ q
            if neck_b is not None:
                neck_b.rotation_quaternion = rest_local[neck_b.name] @ (Quaternion((0, 1, 0), math.radians(yaw) * 0.33)
                                                                       @ Quaternion((1, 0, 0), math.radians(-pitch) * 0.33))
        bpy.context.view_layer.update()
        ok_r = _two_bone(arm, "Right", to_arm_space(track["right"][f]))
        bpy.context.view_layer.update()
        ok_l = _two_bone(arm, "Left", to_arm_space(track["left"][f]))
        bpy.context.view_layer.update()
        misses += (not ok_r) + (not ok_l)
        curl = float(track["left_fist"][f]) * math.radians(80)
        for fb in fingers:
            if fb is not None:
                fb.rotation_quaternion = rest_local[fb.name] @ Quaternion((1, 0, 0), curl)
        frame = frame_start + f
        _key(arms + [head_b, neck_b, spine_b] + fingers, frame)
    act.frame_range = (frame_start, frame_start + n - 1)
    return {"action": act.name, "frames": n, "scale": round(scale, 3), "misses": misses}


def main(argv):
    def opt(flag, d=None):
        return argv[argv.index(flag) + 1] if flag in argv else d
    arm = bpy.data.objects.get(opt("--armature"))
    if arm is None or arm.type != "ARMATURE":
        print(f"NO ARMATURE called {opt('--armature')}")
        return 2
    with open(opt("--track"), encoding="utf-8") as f:
        track = json.load(f)
    r = key(arm, track, opt("--action", "Conduct"), int(opt("--frame-start", 1)), opt("--base-action"),
            int(opt("--base-frame", 0)), int(opt("--step", 1)), opt("--forward", "-Y"))
    print("KEYED", json.dumps(r))
    if opt("--save"):
        bpy.ops.wm.save_as_mainfile(filepath=opt("--save"))
    return 0


if __name__ == "__main__":
    ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if ARGV:
        sys.exit(main(ARGV))
