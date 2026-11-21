"""Play a number's resolved cue sheet (forge.film.cuesheet.resolve) on a built place, and render it (BUILD 43 part 4).

    blender --background <place.blend> --python cue_render.py -- --timeline <tl.json> --out <folder>
            [--preview | --final] [--render] [--frames A-B] [--save <out.blend>] [--conductor-track <track.json>]
            [--sfx-dir <folder>] [--audio <song file>]

Or from another script (a game's adapter): `run(timeline, out_dir, mode, render, ...)`.

What it does, on the song's clock (the sheet's `from` is frame 1):
  * **People**: each cast member is the object named by the cast entry's `object` (or its id); an armature found under
    it moves. `place` / `go` / `climb` / `swing` / `fall` / `rise` key where it stands and which way it faces (a mark's
    facing turns a -Y front about z, as the forge's places write them); `face` turns it. Every beat that names a `move`
    plays that motion as an NLA strip, looped until the next one, crossfaded over a few frames. A motion is looked up as
    "<who>|<move>" (an adapter imports each body's motions under its own name), then "<move>".
  * **Somebody missing** gets a grey stand-in with their name on it, and the report says so (greybox says it is greybox).
  * **Props**: `throw` flies the prop from the thrower's hand to the top of its arc and down to the catcher's, turning
    end over end (`spin`, turns), with gravity's timing; before it is held by the thrower's hand and after by the
    catcher's (Copy Location / Copy Rotation to the hand, their influence keyed). `burst` hides a thing and leaves a mark.
  * **Cameras**: one camera a shot, at a mark or a point, aimed at a person's head, a mark or a point, with its lens, its
    depth of field focused on a person when `focus` and `fstop` say so, moving if the shot moves; cut on timeline
    markers bound to each camera.
  * **The conductor**: his track (forge.film.conductor) keyed on his body by `key_conductor.py`.
  * **Sound**: the song as a strip from the sheet's `from`; each sfx on its frame when its file is found.
  * **Render**: `preview` = EEVEE, 960 × 540, the frames as PNG; `final` = the place's own engine and look, 3840 × 2160.
Writes `<out>/cue_render_report.json`. It never saves over the place: `--save` writes a new file.
"""
from __future__ import annotations

import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

XFADE = 4          # frames a motion crossfades into the next
REPORT = {"stand_ins": [], "missing_moves": {}, "missing_sfx": [], "cameras": 0, "strips": 0, "notes": []}


def frame_of(tl, t):
    return 1 + int(round((float(t) - float(tl["from"])) * int(tl["fps"])))


# ------------------------------------------------------------------------------------------------------------- people
def actor(who, entry):
    """(the object that moves, the armature or None) for a cast member; a labelled stand-in when nothing is there."""
    name = (entry or {}).get("object") or who
    obj = bpy.data.objects.get(name)
    if obj is None:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=1.75, location=(0, 0, 0.875))
        body = bpy.context.object
        body.name = f"STANDIN_{who}"
        mat = bpy.data.materials.get("STANDIN_grey") or bpy.data.materials.new("STANDIN_grey")
        mat.diffuse_color = (0.55, 0.55, 0.55, 1.0)
        body.data.materials.append(mat)
        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
        root = bpy.context.object
        root.name = name
        body.parent = root
        bpy.ops.object.text_add(location=(0, 0, 1.95))
        label = bpy.context.object
        label.data.body = f"stand-in: {who}"
        label.data.size = 0.25
        label.parent = root
        label.rotation_euler = (math.radians(90), 0, 0)
        REPORT["stand_ins"].append(who)
        return root, None
    arm = obj if obj.type == "ARMATURE" else next((c for c in obj.children_recursive if c.type == "ARMATURE"), None)
    return obj, arm


def mark_pos(tl, m):
    if isinstance(m, (list, tuple)):
        return Vector(m), None
    if isinstance(m, dict):
        base, face = mark_pos(tl, m.get("from"))
        return base + Vector(m.get("offset", (0, 0, 0))), face
    a = (tl.get("marks") or {}).get(m)
    if a is None:
        raise KeyError(f"no mark called {m}")
    return Vector(a["pos"]), a.get("facing_deg")


def _key_loc(obj, frame, loc, constant=False):
    obj.location = loc
    obj.keyframe_insert("location", frame=frame)
    if constant:
        _interp(obj, "location", frame, "CONSTANT")


def _key_rot(obj, frame, deg):
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (0.0, 0.0, math.radians(deg))
    obj.keyframe_insert("rotation_euler", frame=frame)


def _fcurves(obj):
    """Every F-curve on an object's action (Blender 4.4+ keeps them in layers / channelbags; older ones in fcurves)."""
    ad = obj.animation_data
    act = ad.action if ad else None
    if act is None:
        return []
    if hasattr(act, "fcurves") and act.fcurves is not None and len(getattr(act, "layers", []) or []) == 0:
        try:
            return list(act.fcurves)
        except Exception:  # noqa: BLE001
            pass
    out = []
    for layer in getattr(act, "layers", []) or []:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []) or []:
                out += list(bag.fcurves)
    if not out and hasattr(act, "fcurves"):
        try:
            out = list(act.fcurves)
        except Exception:  # noqa: BLE001
            pass
    return out


def _interp(obj, path, frame, kind):
    for fc in _fcurves(obj):
        if fc.data_path == path:
            for kp in fc.keyframe_points:
                if int(round(kp.co.x)) == int(frame):
                    kp.interpolation = kind


def _yaw_to(src: Vector, dst: Vector) -> float:
    """The facing (degrees, a -Y front turned about z) that looks from src to dst."""
    d = dst - src
    return math.degrees(math.atan2(d.x, -d.y)) if d.length > 1e-6 else 0.0


def _who_pos(tl, who, at_frame):
    obj = bpy.data.objects.get(((tl.get("cast") or {}).get(who) or {}).get("object") or who)
    if obj is None:
        return None
    bpy.context.scene.frame_set(at_frame)
    return obj.matrix_world.translation.copy()


def stage_people(tl):
    cast = tl.get("cast") or {}
    for who, events in (tl.get("tracks") or {}).items():
        root, arm = actor(who, cast.get(who))
        if root.animation_data is None:
            root.animation_data_create()
        cur_pos, cur_face = root.location.copy(), math.degrees(root.rotation_euler.z)
        for e in events:
            f = frame_of(tl, e["t"])
            do = e["do"]
            if do == "place":
                p, face = mark_pos(tl, e["mark"])
                face = e.get("facing", face if face is not None else cur_face)
                _key_loc(root, f, p, constant=True)
                _key_rot(root, f, face)
                cur_pos, cur_face = p, face
            elif do in ("go", "climb", "swing", "fall", "rise"):
                p, face = mark_pos(tl, e["to"])
                d = float(e.get("dur", 1.0))
                f2 = frame_of(tl, e["t"] + d)
                _key_loc(root, f, cur_pos)
                _key_rot(root, f, cur_face)
                if do == "go" and e.get("facing") is None:
                    _key_rot(root, f + min(6, max(1, (f2 - f) // 4)), _yaw_to(cur_pos, p))
                if do == "swing":                                    # a swing rises through an arc
                    mid = (cur_pos + p) / 2 + Vector((0, 0, float(e.get("arc_m", 2.0))))
                    _key_loc(root, (f + f2) // 2, mid)
                if do == "fall":
                    for k in range(1, 5):                           # falls accelerate
                        u = k / 5
                        _key_loc(root, f + int((f2 - f) * math.sqrt(u)), cur_pos.lerp(p, u))
                _key_loc(root, f2, p)
                final_face = e.get("facing", face if (face is not None and e.get("settle", True)) else _yaw_to(cur_pos, p))
                _key_rot(root, f2, final_face)
                cur_pos, cur_face = p, final_face
            elif do == "face":
                tgt = e.get("toward")
                if isinstance(tgt, (int, float)):
                    deg = float(tgt)
                elif tgt in cast:
                    other = _who_pos(tl, tgt, f)
                    deg = _yaw_to(cur_pos, other) if other is not None else cur_face
                else:
                    deg = _yaw_to(cur_pos, mark_pos(tl, tgt)[0])
                _key_rot(root, f, cur_face)
                _key_rot(root, f + max(1, int(0.3 * int(tl["fps"]))), deg)
                cur_face = deg
            elif do in ("hide", "show"):
                root.hide_render = (do == "hide")
                root.keyframe_insert("hide_render", frame=f)
        if arm is not None:
            motions(tl, who, arm, events)


def action_for(who, move):
    for name in (f"{who}|{move}", move):
        a = bpy.data.actions.get(name)
        if a is not None:
            return a
    for a in bpy.data.actions:
        if a.name.startswith(f"{who}|{move}") or a.name == move or a.name.startswith(move + "_"):
            return a
    return None


def motions(tl, who, arm, events):
    """One NLA strip a motion, in two alternating tracks so each can crossfade into the next."""
    if arm.animation_data is None:
        arm.animation_data_create()
    ad = arm.animation_data
    tracks = [ad.nla_tracks.new(), ad.nla_tracks.new()]
    tracks[0].name, tracks[1].name = f"{who}_moves_A", f"{who}_moves_B"
    plays = [e for e in events if e.get("move")]
    last = frame_of(tl, tl["to"])
    for i, e in enumerate(plays):
        act = action_for(who, e["move"])
        if act is None:
            REPORT["missing_moves"].setdefault(who, [])
            if e["move"] not in REPORT["missing_moves"][who]:
                REPORT["missing_moves"][who].append(e["move"])
            continue
        f0 = frame_of(tl, e["t"])
        f1 = frame_of(tl, plays[i + 1]["t"]) + XFADE if i + 1 < len(plays) else last
        if e.get("dur") and not e.get("loop", e["do"] in ("go", "play")):
            f1 = min(f1, f0 + int(float(e["dur"]) * int(tl["fps"])) + XFADE)
        tr = tracks[i % 2]
        st = tr.strips.new(f"{who}_{i:03d}_{e['move']}", f0, act)
        a0, a1 = act.frame_range
        length = max(1.0, a1 - a0)
        speed = float(e.get("speed", 1.0))
        st.scale = 1.0 / max(speed, 0.05)
        span = max(1, f1 - f0)
        loop = e.get("loop", e["do"] in ("go", "play"))
        st.repeat = max(1.0, span / (length * st.scale)) if loop else 1.0
        st.blend_in = XFADE if i else 0
        st.blend_out = XFADE if i + 1 < len(plays) else 0
        st.extrapolation = "HOLD_FORWARD" if i + 1 == len(plays) else "NOTHING"
        REPORT["strips"] += 1


# -------------------------------------------------------------------------------------------------------------- props
def _hand(arm, side="Right"):
    for n in (f"mixamorig:{side}Hand", f"{side}Hand"):
        if arm and arm.pose.bones.get(n):
            return n
    return None


def _prop_object(name):
    obj = bpy.data.objects.get(name)
    if obj is not None:
        return obj
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (0.03, 0.03, 0.9) if any(k in name for k in ("sword", "rapier", "blade")) else (0.15, 0.15, 0.15)
    REPORT["stand_ins"].append(f"prop {name}")
    return obj


def _hold(prop, arm, bone, frame_on, frame_off, label):
    for kind in ("COPY_LOCATION", "COPY_ROTATION"):
        c = prop.constraints.new(kind)
        c.name = f"{label}_{kind.lower()}"
        c.target = arm
        c.subtarget = bone
        for f, v in ((frame_on - 1, 0.0), (frame_on, 1.0), (frame_off, 1.0), (frame_off + 1, 0.0)):
            if f < 0:
                continue
            c.influence = v
            c.keyframe_insert("influence", frame=f)


def _hand_world(tl, who, frame, side="Right"):
    cast = tl.get("cast") or {}
    root, arm = actor(who, cast.get(who)) if who in cast else (None, None)
    bpy.context.scene.frame_set(frame)
    if arm is not None and _hand(arm, side):
        return arm.matrix_world @ arm.pose.bones[_hand(arm, side)].head
    if root is not None:
        return root.matrix_world.translation + Vector((0, 0, 1.45))
    return Vector((0, 0, 1.45))


def stage_props(tl):
    cast = tl.get("cast") or {}
    fps = int(tl["fps"])
    held = {}
    for p in tl.get("props") or []:
        if p["do"] == "take":
            held[p["prop"]] = (p.get("by"), frame_of(tl, p["t"]))
    for p in tl.get("props") or []:
        f = frame_of(tl, p["t"])
        if p["do"] == "throw":
            prop = _prop_object(p.get("object") or p["prop"])
            by = p.get("by") or p.get("from")
            up = float(p.get("up") or math.sqrt(2 * float(p.get("height_m", 3)) / 9.81))
            catch = next((c for c in tl.get("props") or [] if c["do"] == "catch" and c["prop"] == p["prop"] and c["t"] > p["t"]), None)
            f_land = frame_of(tl, catch["t"]) if catch else frame_of(tl, p["t"] + 2 * up)
            start = _hand_world(tl, by, f)
            end = _hand_world(tl, (catch or {}).get("by", by), f_land)
            h = float(p.get("height_m", 3.0))
            apex_z = max(start.z, end.z) + h
            turns = float(p.get("spin", 2.0))
            n = max(2, f_land - f)
            prop.rotation_mode = "XYZ"
            for k in range(n + 1):
                u = k / n
                t_s = u * (f_land - f) / fps
                # a parabola through start, apex (at the arc's top) and end, timed by gravity on the way up
                T = (f_land - f) / fps
                x = start.lerp(end, u)
                z0 = start.z + (apex_z - start.z) * (1 - (1 - min(1.0, t_s / up)) ** 2) if t_s <= up else \
                    apex_z - 0.5 * 9.81 * (t_s - up) ** 2
                if k == n:
                    z0 = end.z
                prop.location = (x.x, x.y, max(z0, min(start.z, end.z) - 0.5))
                prop.keyframe_insert("location", frame=f + k)
                prop.rotation_euler = (2 * math.pi * turns * u, 0.0, 0.0)
                prop.keyframe_insert("rotation_euler", frame=f + k)
            _, arm_by = actor(by, cast.get(by)) if by in cast else (None, None)
            if arm_by and _hand(arm_by):
                take_f = held.get(p["prop"], (by, 1))[1]
                _hold(prop, arm_by, _hand(arm_by), take_f, f - 1, f"held_by_{by}")
            if catch:
                cb = catch.get("by")
                _, arm_c = actor(cb, cast.get(cb)) if cb in cast else (None, None)
                if arm_c and _hand(arm_c):
                    nxt = next((q for q in tl.get("props") or [] if q["do"] == "throw" and q["prop"] == p["prop"] and q["t"] > catch["t"]), None)
                    off = frame_of(tl, nxt["t"]) - 1 if nxt else frame_of(tl, tl["to"])
                    _hold(prop, arm_c, _hand(arm_c), f_land, off, f"caught_by_{cb}")
        elif p["do"] == "burst":
            obj = bpy.data.objects.get(p.get("object") or p["prop"])
            if obj is None:
                REPORT["notes"].append(f"burst: no object called {p.get('object') or p['prop']}")
                continue
            obj.hide_render = False
            obj.keyframe_insert("hide_render", frame=f - 1)
            obj.hide_render = True
            obj.keyframe_insert("hide_render", frame=f)


# ------------------------------------------------------------------------------------------------------------ cameras
def _aim_target(tl, spec):
    """(object, bone) or a point for a camera to look at."""
    cast = tl.get("cast") or {}
    if isinstance(spec, str) and spec in cast:
        root, arm = actor(spec, cast[spec])
        if arm is not None:
            for n in ("mixamorig:Head", "Head"):
                if arm.pose.bones.get(n):
                    return arm, n
        return root, ""
    if isinstance(spec, (str, list, tuple, dict)):
        p, _ = mark_pos(tl, spec)
        e = bpy.data.objects.new(f"AIM_{abs(hash(str(spec))) % 10**8}", None)
        e.location = p
        bpy.context.scene.collection.objects.link(e)
        return e, ""
    return None, ""


def stage_cameras(tl):
    scn = bpy.context.scene
    for m in [m for m in scn.timeline_markers if m.name.startswith("SHOT ")]:
        scn.timeline_markers.remove(m)
    first = None
    for i, c in enumerate(tl.get("camera") or []):
        if c.get("use_camera"):                       # a camera the place already has (its own shot list)
            cam = bpy.data.objects.get(c["use_camera"]) or bpy.data.objects.get("cam_" + c["use_camera"])
            if cam is None or cam.type != "CAMERA":
                REPORT["notes"].append(f"no camera called {c['use_camera']} in this place")
                continue
            mk = scn.timeline_markers.new(f"SHOT {c.get('shot', i)}", frame=frame_of(tl, c["t"]))
            mk.camera = cam
            first = first or cam
            REPORT["cameras"] += 1
            continue
        name = f"CAM_{i:02d}_{c.get('shot', 'shot')}"
        cd = bpy.data.cameras.new(name)
        cam = bpy.data.objects.new(name, cd)
        scn.collection.objects.link(cam)
        cd.lens = float(c.get("lens", 35))
        cd.clip_end = 400.0
        p, _ = mark_pos(tl, c.get("pos", [0, -10, 2]))
        cam.location = p
        tgt, bone = _aim_target(tl, c.get("look_at"))
        if tgt is not None:
            con = cam.constraints.new("TRACK_TO")
            con.target = tgt
            if bone:
                con.subtarget = bone
            con.track_axis = "TRACK_NEGATIVE_Z"
            con.up_axis = "UP_Y"
        if c.get("fstop"):
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = float(c["fstop"])
            ft, fb = _aim_target(tl, c.get("focus") or c.get("look_at"))
            if ft is not None:
                cd.dof.focus_object = ft
                if fb and hasattr(cd.dof, "focus_subtarget"):
                    cd.dof.focus_subtarget = fb
        f = frame_of(tl, c["t"])
        if c.get("move"):
            mv = c["move"]
            p2, _ = mark_pos(tl, mv["to"])
            f2 = frame_of(tl, c["t"] + float(mv.get("dur", 2.0)))
            cam.location = p
            cam.keyframe_insert("location", frame=f)
            cam.location = p2
            cam.keyframe_insert("location", frame=f2)
        mk = scn.timeline_markers.new(f"SHOT {c.get('shot', i)}", frame=f)
        mk.camera = cam
        if first is None:
            first = cam
        REPORT["cameras"] += 1
    if first is not None:
        scn.camera = first


# -------------------------------------------------------------------------------------------------------------- sound
def _strips(se):
    return se.strips if hasattr(se, "strips") else se.sequences


def stage_sound(tl, audio=None, sfx_dir=None):
    scn = bpy.context.scene
    se = scn.sequence_editor_create()
    fps = int(tl["fps"])
    if audio and os.path.exists(audio):
        s = _strips(se).new_sound("song", audio, 1, 1)
        trim = int(round(float(tl["from"]) * fps))
        if trim > 0:
            s.frame_offset_start = trim
            s.frame_start = 1 - trim
    elif audio:
        REPORT["notes"].append(f"the song is not at {audio}: rendered silent")
    for i, x in enumerate(tl.get("sfx") or []):
        path = None
        for ext in ("", ".wav", ".ogg", ".flac", ".mp3"):
            cand = os.path.join(sfx_dir or "", str(x["sound"]) + ext)
            if sfx_dir and os.path.isfile(cand):
                path = cand
                break
        if path is None:
            REPORT["missing_sfx"].append(x["sound"])
            continue
        st = _strips(se).new_sound(f"sfx_{i:03d}_{x['sound']}", path, 2 + (i % 4), frame_of(tl, x["t"]))
        st.volume = float(x.get("gain", 1.0))


# --------------------------------------------------------------------------------------------------------- the render
def settings(tl, out_dir, mode):
    scn = bpy.context.scene
    scn.render.fps = int(tl["fps"])
    scn.frame_start = 1
    scn.frame_end = frame_of(tl, tl["to"])
    r = scn.render
    if mode == "preview":
        engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        r.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else ("BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else r.engine)
        r.resolution_x, r.resolution_y, r.resolution_percentage = 960, 540, 100
    else:
        r.resolution_x, r.resolution_y, r.resolution_percentage = 3840, 2160, 100
    r.image_settings.file_format = "PNG"
    r.filepath = os.path.join(out_dir, "frames", "")


def conductor(tl, track_path):
    if not track_path or not os.path.exists(track_path):
        return None
    import key_conductor
    cast = tl.get("cast") or {}
    who = next((k for k, v in cast.items() if v.get("role") == "conductor"), None)
    if who is None:
        REPORT["notes"].append("a conductor's track was given but nobody in the cast has role conductor")
        return None
    root, arm = actor(who, cast[who])
    if arm is None:
        REPORT["notes"].append(f"the conductor ({who}) has no skeleton here: his track is not keyed")
        return None
    with open(track_path, encoding="utf-8") as f:
        track = json.load(f)
    start = frame_of(tl, track.get("start", tl["from"]))
    base = action_for(who, "Idle_Loop")
    r = key_conductor.key(arm, track, action=f"{who}|Conduct_{tl.get('number')}", frame_start=start,
                          base_action=base.name if base else None, forward=cast[who].get("forward", "-Y"))
    return r


def run(tl: dict, out_dir: str, mode: str = "preview", render: bool = False, frames: str | None = None,
        conductor_track: str | None = None, audio: str | None = None, sfx_dir: str | None = None,
        save: str | None = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    for k in REPORT:
        REPORT[k] = [] if isinstance(REPORT[k], list) else ({} if isinstance(REPORT[k], dict) else 0)
    stage_people(tl)
    stage_props(tl)
    cond = conductor(tl, conductor_track)
    stage_cameras(tl)
    stage_sound(tl, audio, sfx_dir)
    settings(tl, out_dir, mode)
    scn = bpy.context.scene
    if frames:
        a, b = frames.split("-")
        scn.frame_start, scn.frame_end = int(a), int(b)
    report = {"number": tl.get("number"), "mode": mode, "frames": [scn.frame_start, scn.frame_end],
              "fps": scn.render.fps, "conductor": cond, **REPORT}
    with open(os.path.join(out_dir, "cue_render_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=save, copy=True)
    if render:
        bpy.ops.render.render(animation=True)
        report["rendered"] = True
    print("CUE_RENDER", json.dumps({k: v for k, v in report.items() if k != "conductor"}))
    return report


def main(argv):
    def opt(flag, d=None):
        return argv[argv.index(flag) + 1] if flag in argv else d
    with open(opt("--timeline"), encoding="utf-8") as f:
        tl = json.load(f)
    run(tl, opt("--out", "."), "final" if "--final" in argv else "preview", "--render" in argv, opt("--frames"),
        opt("--conductor-track"), opt("--audio"), opt("--sfx-dir"), opt("--save"))
    return 0


if __name__ == "__main__":
    ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if ARGV:
        sys.exit(main(ARGV))
