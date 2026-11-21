"""BUILD 73 — what the third run taught: the head check measures the face and not the hair; a head-only curve when a
whole-body match cannot mend a face; bodies matched instead of held; dark props allowed to be dark; one button for what is
left (Match and release, Straighten and release, which way is up); capes as their own piece; the gate nudging its words
before it refuses; chain-link asked as cut-outs; stale running jobs. No graphics card, nothing generated.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge import stale_jobs
from forge.threed import checks, cloth, gate, world
from forge.threed.env import RigEnv
from forge.threed.meshio import Glb

from test_threed_build40 import _coloured_body, box_mesh, save   # noqa: E402 — the BUILD 40 test meshes

REPO = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures" / "threed"
FAKE_BLENDER = [sys.executable, str(FIX / "fake_blender.py")]


@pytest.fixture(autouse=True)
def _pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))


# ------------------------------------------------------------------------------------------------ part 1: the face, not the hair
SKIN = np.array([196.0, 150.0, 122.0])
HAIR = np.array([60.0, 42.0, 30.0])
SHIRT = np.array([120.0, 140.0, 200.0])


def figure(face=SKIN, hair=HAIR, neck=SKIN, hat=None, size=280):
    """A front-on figure: a head (hair on top, the face below), a neck and hands of skin, a shirt."""
    img = np.full((size, size, 3), 232.0)
    m = np.zeros((size, size), bool)
    top, bot = 20, 260
    hb = (bot - top) // 7
    cx = size // 2
    # head: the top 40% of the band hair (or hat), the rest face
    m[top:top + hb, cx - 22:cx + 22] = True
    img[top:top + int(hb * 0.4), cx - 22:cx + 22] = hat if hat is not None else hair
    img[top + int(hb * 0.4):top + hb, cx - 22:cx + 22] = face
    img[top + int(hb * 0.4):top + hb, cx - 22:cx - 18] = hair          # hair at the sides
    img[top + int(hb * 0.4):top + hb, cx + 18:cx + 22] = hair
    m[top + hb:top + hb + 12, cx - 9:cx + 9] = True                     # neck
    img[top + hb:top + hb + 12, cx - 9:cx + 9] = neck
    m[top + hb + 12:bot, cx - 45:cx + 45] = True                        # shirt
    img[top + hb + 12:bot, cx - 45:cx + 45] = SHIRT
    for x0 in (cx - 75, cx + 55):                                       # hands
        m[180:200, x0:x0 + 20] = True
        img[180:200, x0:x0 + 20] = neck
    return img, m


def test_hair_darker_than_the_picture_does_not_hold_a_face_that_matches():
    pic = checks.face_split(*figure())
    model = checks.face_split(*figure(hair=HAIR * 0.45))            # the bake darkened the hair, not the face
    v = checks.face_verdict(model, pic)
    assert v["ok"] and 0.95 < v["face_ratio"] < 1.05 and v["hair_ratio"] < 0.7 and not v["shadowed"]


def test_a_hats_shadow_in_the_picture_is_said_and_does_not_hold_on_the_head_alone():
    pic = checks.face_split(*figure(face=SKIN * 0.5, hat=np.array([40.0, 40.0, 40.0])))   # face in the brim's shadow
    model = checks.face_split(*figure(face=SKIN * 1.0, hat=np.array([40.0, 40.0, 40.0])))
    v = checks.face_verdict(model, pic)
    assert v["shadowed"] and v["ok"] and not v["inside"]


def test_a_face_that_really_is_darker_is_held():
    pic = checks.face_split(*figure())
    model = checks.face_split(*figure(face=SKIN * 0.5, neck=SKIN * 0.5))
    v = checks.face_verdict(model, pic)
    assert not v["ok"] and v["face_ratio"] < 0.6


def test_the_head_band_and_the_new_numbers_are_settings():
    for k in ("head_shadow_share", "face_chroma_tol", "face_luma_band", "head_fix", "head_feather", "prop_highlight_pct",
              "prop_dark_floor", "prop_detail_min", "prop_shadow_min", "neutral_drift_max"):
        assert k in checks.DEFAULTS


# ------------------------------------------------------------------------------------------------ part 2: the head alone
def test_head_weights_are_one_on_the_head_none_below_the_neck_and_feathered_between():
    P, F = box_mesh((0.5, 1.8, 0.25), sub=12)
    uv = np.c_[(P[:, 0] - P[:, 0].min()) / np.ptp(P[:, 0]), 1 - (P[:, 1] - P[:, 1].min()) / np.ptp(P[:, 1])]
    m = {"P": P, "F": F, "UV": uv}
    top = P[:, 1].max()
    W = checks.head_weights(m, (64, 64), head_line=top - 0.26, feather=0.05)
    assert W.max() == pytest.approx(1.0) and W.min() == 0.0
    assert W[2:6].mean() > 0.9 and W[-10:].max() == 0.0               # the top rows of the texture are the head (v down)


def test_a_match_may_not_turn_whites_into_a_colour():
    rng = np.random.default_rng(3)
    white = np.clip(rng.normal(225, 6, (2000, 3)), 0, 255)
    assert checks.neutral_drift(white, white) == pytest.approx(0.0, abs=1e-9)
    pink = white.copy()
    pink[:, 1] *= 0.75                                                     # white shoes gone pink
    assert checks.neutral_drift(white, pink) > checks.DEFAULTS["neutral_drift_max"]
    ly = checks.luma_curve(white * 0.6, white)
    out = checks.apply_luma(np.array([[[100.0, 50.0, 25.0], [90.0, 90.0, 90.0]]]), ly)
    assert out[0, 0, 0] > out[0, 0, 1] > out[0, 0, 2] and out[0, 1, 0] == out[0, 1, 1] == out[0, 1, 2]   # order kept, grey grey


def test_a_dark_bake_is_matched_and_the_result_keeps_its_whites(tmp_path):
    glbp, pic = _coloured_body(tmp_path, "body", 2.2)
    fr = checks.fix_colour(glbp, tmp_path / "m.glb", Image.open(pic), None, "body")
    # BUILD 84: one gain for a body — a white cannot turn into a colour under it, nor any hue move
    assert fr["mode"] == "one_gain" and fr["drift"] == 0.0 and fr["hue_ok"] and fr["gain"] > 1.0


# ------------------------------------------------------------------------------------------------ part 4: dark props
def _px(mean, spread, n=4000, seed=0):
    rng = np.random.default_rng(seed)
    y = np.clip(rng.normal(mean, spread, n), 0, 255)
    return np.c_[y, y, y]


def test_a_black_thing_with_its_detail_passes_and_one_without_is_held():
    s = checks.settings(None)
    pic = np.r_[_px(40, 18), _px(235, 8, 300)]                    # a black chair, and studio highlights on it
    with_detail, flat = _px(30, 14, seed=1), _px(14, 1.5, seed=2)
    a = checks.prop_check(checks._stats(with_detail), checks._stats(pic), with_detail, pic, s)
    b = checks.prop_check(checks._stats(flat), checks._stats(pic), flat, pic, s)
    assert a["dark"] and a["ok"]
    assert b["dark"] and not b["ok"] and "lost its detail" in b["why"]


def test_highlights_are_taken_out_of_a_props_picture():
    s = checks.settings(None)
    pic = np.r_[_px(110, 20), _px(250, 2, 900)]                    # a fifth of it shining
    model = _px(104, 20, seed=4)
    r = checks.prop_check(checks._stats(model), checks._stats(pic), model, pic, s)
    assert r["ok"] and 0.85 < r["r50"] < 1.15


# ------------------------------------------------------------------------------------------------ part 7: the gate's nudges
def test_the_nudge_words_chosen_for_each_miss():
    low = {"lines": ["Picture gate — pose: the arms are at 16° and at 16° (from the body's line); an A-pose (about 45°) was asked "
                     "(32–76°). Made again."], "measures": {"arms": {"left": {"angle": 16.0}, "right": {"angle": 16.0}}},
           "expects": {"pose": "a", "band": "adult"}}
    high = dict(low, measures={"arms": {"left": {"angle": 88.0}, "right": {"angle": 106.0}}})
    clear = {"lines": ["Picture gate — limbs: no arm stands clear of the body (held against the sides, or not there); the words "
                       "ask for two. Made again."], "measures": {"arms": {}}, "expects": {"pose": "a", "band": "adult"}}
    head = {"lines": ["Picture gate — limbs: 2 arms, as asked.", "Picture gate — pose: the arms are at 45°, an A-pose as asked.",
                      "Picture gate — proportions: the head is 20% of the figure's height (1 in 4.9); for an adult it is 10–16%. "
                      "Made again."], "measures": {"arms": {}}, "expects": {"pose": "a", "band": "adult"}}
    assert gate.nudge(low) == ("arms_low", gate.NUDGES["arms_low"])
    assert gate.nudge(high) == ("arms_high", gate.NUDGES["arms_high"])
    assert gate.nudge(clear)[0] == "arms_low"
    assert gate.nudge(head) == ("proportions", gate.NUDGES["proportions"])
    assert gate.nudge({"lines": ["Picture gate — limbs: two arms stand out from the body; the words ask for one. Made again."],
                       "measures": {}, "expects": {"arms": 1}}) == (None, None)


def test_the_next_try_is_painted_with_the_nudge_and_the_try_says_so(tmp_path):
    from forge.threed import bodies
    out = tmp_path / "o"
    (out / "pictures").mkdir(parents=True)
    target = out / "pictures" / "p.png"
    sent = []

    def paint(url, pic, obj, tgt, batch, cfg):
        sent.append(obj.get("prompt"))
        Image.fromarray(np.full((64, 64, 3), 232, np.uint8)).save(tgt)    # nothing on it: the gate skips it
        return {"prompt": obj.get("prompt"), "seed": obj["seed"]}
    Image.fromarray(np.full((64, 64, 3), 232, np.uint8)).save(target)
    real = gate.judge
    calls = iter([{"ok": False, "lines": ["Picture gate — pose: the arms are at 16° and at 16°; an A-pose was asked. Made again."],
                   "measures": {"arms": {"l": {"angle": 16.0}}}, "expects": {"pose": "a", "band": "adult"}},
                  {"ok": True, "lines": ["fine"], "measures": {}, "expects": {}}])
    gate.judge = lambda *a, **k: next(calls)
    try:
        rec = bodies.gate_picture("http://x", {"seed": 5}, {"id": "p", "prompt": "A man of forty."}, target, "b", None, out,
                                  paint_fn=paint)
    finally:
        gate.judge = real
    assert rec["ok"] and len(rec["tries"]) == 2
    assert gate.NUDGES["arms_low"][1:] in sent[0] and rec["tries"][1]["nudge"] == "arms_low"


# ------------------------------------------------------------------------------------------------ part 6 and 8: the list
def _list(tmp_path, entries, name="l.json"):
    cfg = {"_root": str(tmp_path), "threed": {"out_root": str(tmp_path / "out3d"), "blender_python": FAKE_BLENDER}}
    d = tmp_path / "games" / "g1" / "wanted_3d"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return cfg


RAVEN = {"id": "raven", "kind": "body", "tier": "principal", "real_size_m": {"height": 2.03}, "first": {"order": 20.03},
         "words": "Fantastic realism. A tall man. He wears a black doublet with silver buttons, a mantle of glossy black raven "
                  "feathers across the shoulders, a short deep red velvet cape to the waist, black gloves and tall boots.",
         "worn_over": [{"id": "cape_raven", "kind": "cape", "words": "A short deep red velvet cape"},
                       {"id": "mantle_raven", "kind": "mantle", "words": "A mantle of glossy black raven feathers"}]}


def test_a_worn_over_entry_plans_two_items_and_takes_the_capes_words_out_of_the_bodys(tmp_path):
    cfg = _list(tmp_path, [RAVEN])
    items, problems = world.load(cfg, "g1")
    assert not problems
    by = {e["id"]: e for e in items}
    assert set(by) == {"raven", "cape_raven", "mantle_raven"}
    cape = by["cape_raven"]
    assert cape["kind"] == "cloth" and cape["hold"] and cape["worn_by"] == "raven" and "dressmaker's stand" in cape["words"]
    assert cape["first"]["order"] > 20.03
    words, taken = world.worn_words_out(RAVEN["words"], RAVEN)
    assert "cape" not in words.split("Shown without")[0] and "feathers" not in words and "silver buttons" in words
    assert "Shown without the cape and mantle" in words and len(taken) == 2
    world.set_fields(cfg, "g1", "cape_raven", {"hold": None})       # taking a planned piece off hold: written in its body
    assert not {e["id"]: e for e in world.load(cfg, "g1")[0]}["cape_raven"]["hold"]


def test_a_mesh_word_plans_a_cut_out_and_a_superseded_thing_stops_counting_as_held(tmp_path):
    cfg = _list(tmp_path, [
        {"id": "fence", "kind": "prop", "words": "A section of chain-link fence with barbed wire."},
        {"id": "crate", "kind": "prop", "words": "A wooden crate."},
        {"id": "old_gate", "kind": "prop", "words": "A gate", "adopt": "x.glb"},
        {"id": "old_gate_cut", "kind": "panel", "panel": {"texture": "t.png"}}])
    by = {e["id"]: e for e in world.load(cfg, "g1")[0]}
    assert by["fence"]["needs_panel"] and by["fence"]["hold"] and not by["crate"].get("needs_panel")
    world.write_state(cfg, "g1", "old_gate", {"state": "held", "why": ["Thin parts: 64% open"]})
    r = world.supersede(cfg, "g1", "old_gate", "old_gate_cut", "Opus")
    assert r["ok"]
    st = {e["id"]: e for e in world.merged(cfg, "g1")[0]}
    assert st["old_gate"]["shown"] == "superseded" and world.status(cfg, "g1")["counts"].get("held", 0) == 0


def test_a_cape_is_pinned_into_the_body_and_the_sheet_gets_its_cloth_block(tmp_path):
    body = save(tmp_path / "b.glb", [box_mesh((0.5, 1.8, 0.3))], {})
    (tmp_path / "b.json").write_text(json.dumps({"motions": {"Idle_Loop": {}}}), encoding="utf-8")
    cape = save(tmp_path / "c.glb", [box_mesh((0.6, 0.9, 0.02))], {})
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig", port=1, command=[], out=tmp_path / "o")
    piece = world.worn_pieces({**RAVEN, "_file": "l.json", "_seq": (0, 0)})[0]
    r = cloth.pin(env, body, cape, tmp_path / "worn.glb", piece, python=FAKE_BLENDER)
    assert r["ok"], r
    sheet = json.loads((tmp_path / "worn.json").read_text())
    blk = sheet["cloth"][0]
    assert blk["mesh"] == "cape_raven" and blk["pinned_vertices"] > 0 and blk["spring"]["not"] == "a cloth simulation"
    assert sheet["motions"] == {"Idle_Loop": {}}
    nosk = tmp_path / "NOSKELETON.glb"
    nosk.write_bytes(body.read_bytes())
    bad = cloth.pin(env, nosk, cape, tmp_path / "worn2.glb", piece, python=FAKE_BLENDER)
    assert bad["ok"] is False and "skeleton" in bad["error"]


# ------------------------------------------------------------------------------------------------ part 5: one button
def _held_prop(tmp_path, cfg, eid="crank_radio"):
    out = world.item_dir(cfg, "g1", eid)
    out.mkdir(parents=True, exist_ok=True)
    glbp, pic = _coloured_body(out, eid, 2.2)
    rel = lambda p: os.path.relpath(p, tmp_path).replace("\\", "/")
    world.write_state(cfg, "g1", eid, {"state": "held", "kind": "prop", "tier": "small_prop", "model_raw": rel(glbp),
                                       "picture": rel(pic), "why": ["Colours hold: 39% as bright as its picture"],
                                       "check_results": [{"check": "loose", "ok": True},
                                                         {"check": "colour", "ok": False, "mean_ratio": 0.39}]})
    return glbp


def test_match_and_release_needs_a_person_journals_and_starts_no_job(tmp_path):
    cfg = _list(tmp_path, [{"id": "crank_radio", "kind": "prop", "words": "A crank radio.", "real_size_m": {"width": 0.3}},
                           {"id": "walker", "kind": "body", "words": "A man of fifty."}])
    _held_prop(tmp_path, cfg)
    lists = world.release_lists(cfg, "g1")
    assert [r["id"] for r in lists["match"]] == ["crank_radio"]
    with pytest.raises(world.WorldError):
        world.match_and_release(cfg, "g1", ["crank_radio"], "")
    jobs_before = list((tmp_path / "jobs").rglob("*.json")) if (tmp_path / "jobs").exists() else []
    r = world.match_and_release(cfg, "g1", ["crank_radio", "walker"], "William")
    assert [d["id"] for d in r["released"]] == ["crank_radio"] and r["refused"][0]["id"] == "walker"
    st = world.read_state(cfg, "g1", "crank_radio")
    assert st["state"] == "made" and st["colour_released"]["by"] == "William"
    assert any(h["state"] == "matched and released" and h["by"] == "William" for h in st["history"])
    assert (list((tmp_path / "jobs").rglob("*.json")) if (tmp_path / "jobs").exists() else []) == jobs_before


def test_a_released_body_goes_back_for_its_skeleton_only(tmp_path):
    cfg = _list(tmp_path, [{"id": "walker", "kind": "body", "words": "A man of fifty."}])
    out = world.item_dir(cfg, "g1", "walker")
    out.mkdir(parents=True, exist_ok=True)
    glbp, pic = _coloured_body(out, "walker", 2.2)
    rel = lambda p: os.path.relpath(p, tmp_path).replace("\\", "/")
    world.write_state(cfg, "g1", "walker", {"state": "held", "kind": "body", "tier": "named", "model_raw": rel(glbp), "picture": rel(pic),
                                            "check_results": [{"check": "colour", "ok": False, "mean_ratio": 0.6}]})
    r = world.match_and_release(cfg, "g1", ["walker"], "Fable")
    assert r["released"][0]["to"].startswith("the queue")
    st = world.read_state(cfg, "g1", "walker")
    assert st["state"] == "wanted" and st["reuse_body"].endswith("__one_gain.glb") and st["colour_released"]["by"] == "Fable"
    assert st["colour_mode"] == "one_gain" and st["colour_gain"] > 1.0                  # BUILD 84: one gain, never a curve


# ------------------------------------------------------------------------------------------------ part 9: stale jobs
def test_a_stale_running_job_is_moved_and_a_fresh_one_is_not(tmp_path):
    for d in ("running", "failed"):
        (tmp_path / d).mkdir()
    old = tmp_path / "running" / "20261112-180511-ffp.json"
    old.write_text(json.dumps({"id": "ffp", "started_at": "2026-11-12T18:05:11"}), encoding="utf-8")
    new = tmp_path / "running" / "fresh.json"
    new.write_text(json.dumps({"id": "fresh", "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}), encoding="utf-8")
    now = time.mktime(time.strptime("2026-11-17 20:00", "%Y-%m-%d %H:%M"))
    assert stale_jobs.move_stale(tmp_path, True, now=now)["moved"] == []          # a worker is running: nothing moves
    assert stale_jobs.move_stale(tmp_path, None, now=now)["moved"] == []          # can't tell: nothing moves
    r = stale_jobs.move_stale(tmp_path, False, now=now)
    assert r["moved"] == ["ffp"] and new.exists() and not old.exists()
    moved = json.loads((tmp_path / "failed" / old.name).read_text())
    assert moved["error"] == stale_jobs.REASON
