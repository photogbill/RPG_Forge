"""A small Mixamo-named rig for the film tests (Blender's Python only). Faces -Y, T-pose, 1.75 m."""
import bpy
from mathutils import Vector


def make_rig(name="conductor_test", at=(0.0, 0.0, 0.0)):
    bpy.ops.object.armature_add(enter_editmode=True, location=at)
    arm = bpy.context.object
    arm.name = name
    eb = arm.data.edit_bones
    for b in list(eb):
        eb.remove(b)
    P = "mixamorig:"

    def bone(n, h, t, parent=None):
        b = eb.new(P + n)
        b.head, b.tail = Vector(h), Vector(t)
        if parent:
            b.parent = eb[P + parent]
            b.use_connect = False
        return b
    bone("Hips", (0, 0, 1.0), (0, 0, 1.1))
    bone("Spine", (0, 0, 1.1), (0, 0, 1.22), "Hips")
    bone("Spine1", (0, 0, 1.22), (0, 0, 1.34), "Spine")
    bone("Spine2", (0, 0, 1.34), (0, 0, 1.44), "Spine1")
    bone("Neck", (0, 0, 1.44), (0, 0, 1.55), "Spine2")
    bone("Head", (0, 0, 1.55), (0, 0, 1.75), "Neck")
    for side, sx in (("Left", 1.0), ("Right", -1.0)):          # facing -Y: the left hand is on +X
        bone(f"{side}Shoulder", (0.03 * sx, 0, 1.42), (0.17 * sx, 0, 1.42), "Spine2")
        bone(f"{side}Arm", (0.17 * sx, 0, 1.42), (0.46 * sx, 0, 1.42), f"{side}Shoulder")
        bone(f"{side}ForeArm", (0.46 * sx, 0, 1.42), (0.73 * sx, 0, 1.42), f"{side}Arm")
        bone(f"{side}Hand", (0.73 * sx, 0, 1.42), (0.80 * sx, 0, 1.42), f"{side}ForeArm")
        for k, f in enumerate(("Index", "Middle", "Ring", "Pinky")):
            y = -0.012 + 0.008 * k
            for j in (1, 2, 3):
                x0 = 0.80 + 0.025 * (j - 1)
                bone(f"{side}Hand{f}{j}", (x0 * sx, y, 1.42), ((x0 + 0.025) * sx, y, 1.42),
                     f"{side}Hand" if j == 1 else f"{side}Hand{f}{j - 1}")
        bone(f"{side}UpLeg", (0.1 * sx, 0, 1.0), (0.1 * sx, 0, 0.55), "Hips")
        bone(f"{side}Leg", (0.1 * sx, 0, 0.55), (0.1 * sx, 0, 0.1), f"{side}UpLeg")
        bone(f"{side}Foot", (0.1 * sx, 0, 0.1), (0.1 * sx, -0.12, 0.02), f"{side}Leg")
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def make_action(arm, name, frames=24, wave=0.0):
    """A plain motion: the hips bob (and the arms come down a little) so a strip's presence is measurable."""
    import math
    arm.animation_data_create()
    act = bpy.data.actions.new(name)
    arm.animation_data.action = act
    hips = arm.pose.bones["mixamorig:Hips"]
    for f in range(0, frames + 1, 6):
        hips.location = (0, 0, 0.02 * math.sin(2 * math.pi * f / frames) + wave)
        hips.keyframe_insert("location", frame=f)
    act.use_fake_user = True
    arm.animation_data.action = None
    return act
