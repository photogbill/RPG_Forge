"""BUILD 43 — filming a set piece to its music: beat maps, the conductor, cue sheets, encoding, and the Blender half
(cue_render, key_conductor, keyed_moves, merge_libraries) where Blender's Python is at hand (else those are skipped)."""
from __future__ import annotations

import json
import math
import shutil
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from forge.film import beatmap, conductor, cuesheet, encode

HERE = Path(__file__).resolve().parent
BLENDER_DIR = HERE.parent / "forge" / "threed" / "blender"
try:
    import librosa  # noqa: F401
    HAVE_LIBROSA = True
except Exception:  # noqa: BLE001
    HAVE_LIBROSA = False
# measuring a song needs librosa (requirements-film.txt: opera_film.bat installs it the first time); the rest does not
needs_librosa = pytest.mark.skipif(not HAVE_LIBROSA, reason="librosa is not installed (opera_film.bat installs it)")


def _clicks(path: Path, bpm_list, meter=4, sr=22050, gap=None, lead=0.5):
    """A click track: beats at the given tempi (one bpm a beat), the downbeat louder and lower, an optional silence."""
    t = lead
    times = []
    for b in bpm_list:
        times.append(t)
        t += 60.0 / b
    dur = t + 1.0
    y = np.zeros(int(dur * sr), dtype=np.float32)
    k = np.arange(int(0.05 * sr))
    for i, tt in enumerate(times):
        if gap and gap[0] <= tt < gap[1]:
            continue
        down = i % meter == 0
        f = 220.0 if down else 880.0
        seg = (0.9 if down else 0.45) * np.exp(-k / (0.01 * sr)) * np.sin(2 * np.pi * f * k / sr)
        a = int(tt * sr)
        y[a:a + len(seg)] += seg[: len(y) - a]
    # a quiet bed so loudness and silences mean something
    bed = 0.02 * np.sin(2 * np.pi * 110 * np.arange(len(y)) / sr)
    if gap:
        bed[int(gap[0] * sr):int(gap[1] * sr)] = 0.0
    y += bed.astype(np.float32)
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
    return times


@pytest.fixture(scope="module")
def steady(tmp_path_factory):
    if not HAVE_LIBROSA:
        pytest.skip("librosa is not installed (opera_film.bat installs it)")
    p = tmp_path_factory.mktemp("film") / "steady.wav"
    times = _clicks(p, [120.0] * 96, meter=4, gap=(26.0, 27.2))
    bm = beatmap.analyse(p, meter=4, bpm_hint=120)
    return p, times, bm


def test_a_steady_track_is_measured_at_its_tempo_with_its_bar_lines(steady):
    p, times, bm = steady
    assert abs(bm["tempo"]["median_bpm"] - 120) < 3
    assert bm["checks"]["grid_ms_median"] < 15
    assert len(bm["bars"]) >= 20
    # the bar lines fall on the loud low clicks (every fourth from the first)
    downs = [b["t"] for b in bm["beats"] if b["down"]]
    real_downs = times[::4]
    near = sum(1 for d in downs if min(abs(d - r) for r in real_downs) < 0.06)
    assert near / len(downs) > 0.8
    assert bm["meter"][0]["beats_per_bar"] == 4


def test_a_silence_in_the_track_is_found(steady):
    _p, _t, bm = steady
    assert any(s["from"] < 26.6 < s["to"] for s in bm["silences"]), bm["silences"]


def test_by_hand_bar_lines_survive_a_rerun(steady, tmp_path):
    p, _t, bm = steady
    out = tmp_path / "x.beats.json"
    beatmap.write(bm, out)
    old = beatmap.read(out)
    old["by_hand"] = {"bars": {"3": 9.999}, "moments": {"crash": 12.0}}
    out.write_text(json.dumps(old), encoding="utf-8")
    beatmap.write(beatmap.analyse(p, meter=4, bpm_hint=120), out)
    new = beatmap.read(out)
    assert new["by_hand"]["moments"]["crash"] == 12.0
    assert abs(beatmap.bar_time(new, 3) - 9.999) < 1e-6
    assert beatmap.moments(new)["crash"] == 12.0


def test_bar_time_and_strong_beats(steady):
    _p, _t, bm = steady
    t1 = beatmap.bar_time(bm, 5)
    t3 = beatmap.bar_time(bm, 5, 3)
    assert t3 > t1
    assert beatmap.strong(bm, t1) and beatmap.strong(bm, t3)
    t2 = beatmap.bar_time(bm, 5, 2)
    assert not beatmap.strong(bm, t2)
    with pytest.raises(ValueError):
        beatmap.bar_time(bm, 10_000)


@needs_librosa
def test_an_accelerando_is_followed(tmp_path):
    p = tmp_path / "acc.wav"
    bpms = list(np.linspace(100, 135, 120))
    _clicks(p, bpms, meter=4)
    bm = beatmap.analyse(p, meter=4, bpm_hint=110)
    assert bm["checks"]["tempo_moves"]
    assert bm["tempo"]["method"] == "plp"
    assert bm["tempo"]["last_bars_bpm"] > bm["tempo"]["first_bars_bpm"] + 15


def test_the_picture_is_drawn(steady, tmp_path):
    p, _t, bm = steady
    png = beatmap.draw(bm, tmp_path / "bm.png", audio=p)
    from PIL import Image
    assert Image.open(png).size[0] == 2400


# ------------------------------------------------------------------------------------------------------- the conductor
def test_the_conductor_beats_each_ictus_a_tenth_before_the_sound_at_the_bottom_of_his_fall(steady):
    _p, _t, bm = steady
    tr = conductor.make(bm)
    assert conductor.check(tr, bm) == []
    ic = tr["ictus"][10]
    assert abs((ic["beat_t"] - ic["t"]) - 0.10) < 1e-6
    # four in a bar at 120: positions down, left, right, up
    pats = {i["pattern"] for i in tr["ictus"]}
    assert pats == {4}


@needs_librosa
def test_fast_beats_are_beaten_in_half_and_a_freeze_hangs_the_baton(tmp_path):
    p = tmp_path / "fast.wav"
    _clicks(p, [150.0] * 120, meter=4)
    bm = beatmap.analyse(p, meter=4, bpm_hint=150)
    tr = conductor.make(bm, acting=[{"do": "freeze", "from": 20.0, "to": 23.0}, {"do": "late", "from": 10.0, "to": 14.0}])
    assert {i["pattern"] for i in tr["ictus"]} == {2}
    assert conductor.check(tr, bm) == []
    f = int(21.5 * tr["fps"])
    assert tr["right"][f][2] < -0.3                       # the baton hanging
    assert tr["head"][f][1] > 10                          # eyes on the stage
    late = [i for i in tr["ictus"] if i["late"]]
    assert late and all(i["t"] > i["beat_t"] for i in late)


def test_the_conductor_refuses_an_acting_beat_he_does_not_have(steady):
    with pytest.raises(ValueError):
        conductor.make(steady[2], acting=[{"do": "juggle", "at": 1.0}])


def test_a_tampered_track_fails_the_check(steady):
    _p, _t, bm = steady
    tr = conductor.make(bm)
    tr["ictus"][5]["t"] += 0.2
    assert conductor.check(tr, bm)


# --------------------------------------------------------------------------------------------------------- cue sheets
MARKS = {"a": {"pos": [0, 0, 0], "facing_deg": 0}, "b": {"pos": [3, 2, 0], "facing_deg": 90}, "cam": {"pos": [0, -8, 2]}}


def _sheet(**over):
    sh = {"number": "t", "track": "x.ogg", "fps": 24, "from": 0.0, "to": 40.0,
          "cast": {"lead": {"body": "x"}, "foil": {"body": "y"}, "maestro": {"body": "z", "role": "conductor"}},
          "moments": {"clash": {"t": 20.0}},
          "beats": [{"at": 0.0, "who": "lead", "do": "place", "mark": "a"},
                    {"at": {"bar": 3}, "who": "lead", "do": "go", "to": "b", "dur": 1.5, "move": "Walk_Loop"},
                    {"at": "clash", "offset": -0.5, "who": "foil", "do": "attack", "at_who": "lead", "parried_by": "lead",
                     "move": "Sword_Attack"}],
          "camera": [{"at": 0.0, "shot": "wide", "pos": "cam", "look_at": "lead", "lens": 35, "with": ["maestro"]}],
          "conductor": [{"at": 0.2, "do": "raise"}], "singers": ["lead"]}
    sh.update(over)
    return sh


def test_a_good_sheet_checks_clean_and_resolves_with_offsets(steady):
    bm = steady[2]
    sh = _sheet()
    errs, warns = cuesheet.check(sh, bm, MARKS, {"Walk_Loop", "Sword_Attack"}, {"lead"})
    assert errs == [] and warns == []
    tl = cuesheet.resolve(sh, bm, MARKS)
    att = tl["tracks"]["foil"][0]
    assert abs(att["t"] - 19.5) < 1e-6
    assert abs(tl["tracks"]["lead"][1]["t"] - beatmap.bar_time(bm, 3)) < 1e-6


def test_nobody_lands_a_blow(steady):
    bm = steady[2]
    sh = _sheet()
    sh["beats"].append({"at": 21.0, "who": "lead", "do": "attack", "at_who": "foil", "move": "Sword_Attack"})
    sh["beats"].append({"at": 22.0, "who": "foil", "do": "strike", "target": "lead"})
    errs, _w = cuesheet.check(sh, bm, MARKS, None, None)
    assert sum("nobody lands a blow" in e for e in errs) == 2
    sh["beats"].append({"at": 23.0, "who": "foil", "do": "strike", "target": "sandbags"})
    errs2, _w = cuesheet.check(sh, bm, MARKS, None, None)
    assert len(errs2) == 2                                 # a thing may be struck


def test_unknown_marks_people_moves_and_impossible_places_are_caught(steady):
    bm = steady[2]
    sh = _sheet()
    sh["beats"] += [{"at": 1.0, "who": "ghost", "do": "place", "mark": "a"},
                    {"at": 2.0, "who": "lead", "do": "place", "mark": "nowhere"},
                    {"at": 3.0, "who": "lead", "do": "play", "move": "Moonwalk"},
                    {"at": {"bar": 3}, "offset": 0.5, "who": "lead", "do": "go", "to": "a", "dur": 1.0}]
    errs, _w = cuesheet.check(sh, bm, MARKS, {"Walk_Loop", "Sword_Attack"}, None)
    text = " | ".join(errs)
    assert "ghost" in text and "nowhere" in text and "Moonwalk" in text and "two places at once" in text


def test_a_throw_obeys_gravity_is_caught_and_tops_out_on_a_strong_beat(steady):
    bm = steady[2]
    fit = cuesheet.fit_throw(bm, 20.0, 9.0)
    assert fit and beatmap.strong(bm, fit["apex"], tol=0.001)
    assert abs(fit["height_m"] - 0.5 * 9.81 * fit["up"] ** 2) < 0.05
    sh = _sheet(props=[{"at": fit["throw"], "do": "throw", "prop": "blade", "by": "foil", "height_m": fit["height_m"]},
                       {"at": 20.0, "do": "catch", "prop": "blade", "by": "foil"}])
    errs, warns = cuesheet.check(sh, bm, MARKS, None, None)
    assert errs == [] and warns == []
    bad = _sheet(props=[{"at": 10.0, "do": "throw", "prop": "blade", "by": "foil", "height_m": 9.0, "up": 0.5}])
    errs, _w = cuesheet.check(bad, bm, MARKS, None, None)
    assert any("takes" in e for e in errs) and any("nobody catches" in e for e in errs)


def test_stage_for_distance_one_test_closeup_only(steady):
    bm = steady[2]
    close = {"at": 5.0, "shot": "c", "pos": "cam", "look_at": "lead", "lens": 85, "framing": "close"}
    errs, _w = cuesheet.check(_sheet(camera=_sheet()["camera"] + [close]), bm, MARKS, None, {"lead"})
    assert any("stage for distance" in e for e in errs)
    ok = dict(close, test_closeup=True)
    errs, _w = cuesheet.check(_sheet(camera=_sheet()["camera"] + [ok]), bm, MARKS, None, {"lead"})
    assert errs == []
    errs, _w = cuesheet.check(_sheet(camera=_sheet()["camera"] + [ok, dict(ok, at=9.0)]), bm, MARKS, None, {"lead"})
    assert any("test close-ups" in e for e in errs)


def test_the_conductor_must_be_seen(steady):
    bm = steady[2]
    sh = _sheet(camera=[{"at": 0.0, "shot": "wide", "pos": "cam", "look_at": "lead", "lens": 35}])
    _e, warns = cuesheet.check(sh, bm, MARKS, None, None)
    assert any("conductor" in w for w in warns)


def test_a_sheet_with_no_song_has_a_length(tmp_path):
    sh = {"number": "quiet", "track": None, "length": 6.0}
    bm = cuesheet.beat_map_for(sh, tmp_path)
    assert bm["duration"] == 6.0 and bm["beats"] == []
    with pytest.raises(cuesheet.SheetError):
        cuesheet.beat_map_for({"track": None}, tmp_path)


# ----------------------------------------------------------------------------------------------------------- encoding
def test_the_encode_command_and_the_click_track(steady, tmp_path):
    bm = steady[2]
    fr = tmp_path / "frames"
    fr.mkdir()
    from PIL import Image
    for i in range(1, 25):
        Image.new("RGB", (64, 36), (i * 10, 0, 0)).save(fr / f"{i:04d}.png")
    wav = encode.click_track(bm, tmp_path / "c.wav", 2.0, 3.0)
    with wave.open(str(wav)) as w:
        assert abs(w.getnframes() / w.getframerate() - 1.0) < 0.01
    cmd = encode.command(fr, tmp_path / "o.mp4", wav, 24, 0.0, 1.0, "final", muffled=True)
    assert "-crf" in cmd and "16" in cmd and "slow" in cmd and encode.MUFFLE in cmd
    assert cmd[cmd.index("-i") + 1].endswith("%04d.png")
    if encode.ffmpeg():
        r = encode.frames_to_film(fr, tmp_path / "o.mp4", wav, 24, 0.0, 1.0, "preview")
        assert r["ok"], r


def test_the_plugin_is_well_formed():
    from forge import plugins
    from forge.plugins import film
    assert plugins._check("film", film.HANDLERS, film.JOB_TYPES) is None


def test_the_film_command_is_registered():
    from forge import cli
    assert "film" in cli.COMMANDS


# --------------------------------------------------------------------------------------------- Blender's half (bpy)
bpy = None
try:  # Blender as a Python module, when this Python has it
    import bpy as _bpy  # noqa: F401
    bpy = _bpy
except Exception:  # noqa: BLE001
    pass
needs_bpy = pytest.mark.skipif(bpy is None, reason="Blender's Python (bpy) is not in this environment")


def _blender_paths():
    for p in (str(BLENDER_DIR), str(HERE)):
        if p not in sys.path:
            sys.path.insert(0, p)


@needs_bpy
def test_key_conductor_puts_the_hands_where_the_track_says(steady):
    _blender_paths()
    import key_conductor as K
    from _film_rig import make_rig
    from mathutils import Vector
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = make_rig()
    tr = conductor.make(steady[2], start=0.0, end=6.0)
    r = K.key(arm, tr, action="Conduct_t")
    assert r["misses"] == 0
    scn = bpy.context.scene
    for f in (30, 90, 150):
        scn.frame_set(1 + f)
        bpy.context.view_layer.update()
        rh = arm.matrix_world @ arm.pose.bones["mixamorig:RightHand"].head
        x, y, z = tr["right"][f]
        want = Vector((0, 0, 1.42)) + Vector((-1, 0, 0)) * x * r["scale"] + Vector((0, -1, 0)) * y * r["scale"] + Vector((0, 0, 1)) * z * r["scale"]
        assert (rh - want).length < 0.01


@needs_bpy
def test_keyed_moves_bake_on_any_rig():
    _blender_paths()
    import keyed_moves as KM
    from _film_rig import make_rig, make_action
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = make_rig("body")
    make_action(arm, "Idle_Loop")
    r = KM.bake(arm, only=["Bow_Stage", "Curtsey"], base_action="Idle_Loop")
    assert set(r["made"]) == {"Bow_Stage", "Curtsey"}
    scn = bpy.context.scene
    arm.animation_data.action = bpy.data.actions["Bow_Stage"]
    scn.frame_set(45)
    bpy.context.view_layer.update()
    head = arm.matrix_world @ arm.pose.bones["mixamorig:Head"].head
    assert head.y < -0.15                                  # bowed forward (the body faces -Y)
    arm.animation_data.action = bpy.data.actions["Curtsey"]
    scn.frame_set(48)
    bpy.context.view_layer.update()
    foot = arm.matrix_world @ arm.pose.bones["mixamorig:LeftFoot"].head
    hips = arm.matrix_world @ arm.pose.bones["mixamorig:Hips"].head
    assert hips.z < 0.82 and abs(foot.z - 0.1) < 0.01      # the hips sink, the feet stay planted
    assert "Bow_Stage" in KM.names()


@needs_bpy
def test_cue_render_stages_people_props_cameras_and_sound(steady, tmp_path):
    _blender_paths()
    import cue_render as R
    from _film_rig import make_rig, make_action
    bpy.ops.wm.read_factory_settings(use_empty=True)
    a = make_rig("lead_body")
    for n in ("lead|Idle_Loop", "lead|Walk_Loop"):
        make_action(a, n)
    b = make_rig("foil_body", at=(2, 0, 0))
    make_action(b, "foil|Idle_Loop")
    tl = {"number": "t", "fps": 24, "from": 10.0, "to": 14.0, "duration": 30,
          "cast": {"lead": {"object": "lead_body"}, "foil": {"object": "foil_body"}, "extra": {"body": "none"}},
          "marks": MARKS,
          "tracks": {"lead": [{"t": 10.0, "do": "place", "mark": "a", "move": "Idle_Loop"},
                              {"t": 11.0, "do": "go", "to": "b", "dur": 1.0, "move": "Walk_Loop"}],
                     "foil": [{"t": 10.0, "do": "place", "mark": "b", "move": "Idle_Loop"}, {"t": 12.0, "do": "play", "move": "Nope"}],
                     "extra": [{"t": 10.0, "do": "place", "mark": "a"}]},
          "props": [{"t": 11.5, "do": "throw", "prop": "blade", "by": "foil", "height_m": 3.0},
                    {"t": 11.5 + 2 * math.sqrt(6 / 9.81), "do": "catch", "prop": "blade", "by": "foil"}],
          "camera": [{"t": 10.0, "shot": "wide", "pos": "cam", "look_at": "lead", "lens": 35},
                     {"t": 12.0, "shot": "near", "pos": [1, -3, 1.6], "look_at": "foil", "lens": 85}],
          "sfx": [{"t": 11.0, "sound": "nothing_here"}]}
    rep = R.run(tl, str(tmp_path), "preview", render=False, sfx_dir=str(tmp_path))
    assert "extra" in rep["stand_ins"] and rep["missing_moves"] == {"foil": ["Nope"]}
    assert rep["cameras"] == 2 and rep["missing_sfx"] == ["nothing_here"]
    scn = bpy.context.scene
    assert [m.frame for m in scn.timeline_markers if m.name.startswith("SHOT")] == [1, 49]
    scn.frame_set(R.frame_of(tl, 12.5))
    assert (bpy.data.objects["lead_body"].location - __import__("mathutils").Vector((3, 2, 0))).length < 1e-4
    blade = bpy.data.objects["blade"]
    top = R.frame_of(tl, 11.5 + math.sqrt(6 / 9.81))
    scn.frame_set(top)
    bpy.context.view_layer.update()
    assert blade.matrix_world.translation.z > 4.0          # 1.42 m hand + 3 m


@needs_bpy
def test_merge_libraries_joins_two_libraries_on_one_skeleton(tmp_path):
    _blender_paths()
    import merge_libraries as M
    from _film_rig import make_rig, make_action
    for name, acts in (("one.glb", ["Walk_Loop", "A_TPose"]), ("two.glb", ["Sword_Block", "A_TPose"])):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        arm = make_rig("Armature")
        bpy.ops.mesh.primitive_cube_add(size=0.2)
        cube = bpy.context.object
        cube.parent = arm
        m = cube.modifiers.new("Armature", "ARMATURE")
        m.object = arm
        vg = cube.vertex_groups.new(name="mixamorig:Hips")
        vg.add(list(range(len(cube.data.vertices))), 1.0, "REPLACE")
        ad = arm.animation_data_create()
        for i, a in enumerate(acts):
            act = make_action(arm, a, wave=0.01 * i)
            tr = ad.nla_tracks.new()
            tr.name = a
            tr.strips.new(a, 0, act)
        bpy.ops.export_scene.gltf(filepath=str(tmp_path / name), export_format="GLB", export_animation_mode="NLA_TRACKS")
    sheet = M.merge(str(tmp_path / "both.glb"), [str(tmp_path / "one.glb"), str(tmp_path / "two.glb")])
    assert {"Walk_Loop", "Sword_Block", "A_TPose"} <= set(sheet["motions"])
    assert sheet["motions"]["A_TPose"] == "one.glb"
    from forge.threed import glb
    names = glb.info(tmp_path / "both.glb")["motions"]
    assert "Sword_Block" in names and "Walk_Loop" in names
