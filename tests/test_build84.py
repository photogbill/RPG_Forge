"""BUILD 84 — what the first day around the clock taught.

Part 1: a body's colours by brightness only — one gain for the whole colour picture, never a curve, never a hue; the colour
sheet starts with the body as made; metal is left out of the colour check; bodies released with a curve put right.
Part 2: the picture gate repairs a pose before it rerolls; Make again carries the nudge and a new seed; a thing held twice
running for the same reason goes to NEEDS_BETTER_WORDS.md. (The pose band itself: tests/test_build84_gate.py.)
Part 3: animals never reach the people's skeleton, motions or checks.
No graphics card: meshes and pictures are made here; the stand-in paints the figures.
"""
from __future__ import annotations

import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge.threed import bodies, checks, gate, raster, redo, standin, world
from forge.threed.meshio import Glb

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_world_build39 import box_mesh, save  # noqa: E402


@pytest.fixture(autouse=True)
def _pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))


def fig(**kw) -> Image.Image:
    im = Image.open(io.BytesIO(standin.png(**kw)))
    im.load()
    return im


def _cfg(tmp_path, entries, gid="g1"):
    d = tmp_path / "games" / gid / "wanted_3d"
    d.mkdir(parents=True, exist_ok=True)
    (d / "list.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return {"_root": str(tmp_path), "threed": {"out_root": str(tmp_path / "out3d")},
            "paths": {"games": str(tmp_path / "games"), "out": str(tmp_path / "out"), "jobs": str(tmp_path / "jobs")},
            "allow_external_paths": True}


def _rel(tmp_path, p):
    return os.path.relpath(p, tmp_path).replace("\\", "/")


# ================================================================================================ Part 2: the picture gate
def test_a_pose_miss_is_repaired_not_rerolled(tmp_path):
    out = tmp_path / "o"
    (out / "pictures").mkdir(parents=True)
    target = out / "pictures" / "clerk.png"
    fig(arm_deg=3).save(target)                                   # arms against the body: the one miss a repair can mend
    painted, repaired = [], []

    def paint(url, pic, obj, tgt, batch, cfg):
        painted.append(obj["seed"])
        fig().save(tgt)
        return {"prompt": obj.get("prompt"), "seed": obj["seed"]}

    def repair(url, pic, obj, tgt, batch, cfg, o, n):
        repaired.append(n)
        p = o / "pictures" / f"{obj['id']}__repair{n}.png"
        fig(arm_deg=45).save(p)
        return p
    rec = bodies.gate_picture("http://x", {"seed": 5}, {"id": "clerk", "prompt": "Hyperrealistic. A man of fifty."}, target, "b",
                              None, out, paint_fn=paint, repair_fn=repair)
    assert rec["ok"] and not rec["held"] and painted == [] and repaired == [1]
    assert rec["tries"][-1]["repair"] is True and rec["repaired"]["picture"] == "clerk__repair1.png"
    assert target.read_bytes() == (out / "pictures" / "clerk__repair1.png").read_bytes()     # the body is made from the repair


def test_a_repair_that_misses_falls_back_to_a_new_picture_and_other_misses_are_never_repaired(tmp_path):
    out = tmp_path / "o"
    (out / "pictures").mkdir(parents=True)
    target = out / "pictures" / "rep.png"
    fig(arm_deg=3).save(target)
    painted, repaired = [], []

    def paint(url, pic, obj, tgt, batch, cfg):
        painted.append(obj.get("prompt"))
        fig().save(tgt)
        return {"prompt": obj.get("prompt"), "seed": obj["seed"]}

    def repair(url, pic, obj, tgt, batch, cfg, o, n):
        repaired.append(n)
        p = o / "pictures" / f"{obj['id']}__repair{n}.png"
        fig(arm_deg=2).save(p)                                       # the repair did not move the arms
        return p
    rec = bodies.gate_picture("http://x", {"seed": 5}, {"id": "rep", "prompt": "Hyperrealistic. A man of fifty."}, target, "b",
                              None, out, paint_fn=paint, repair_fn=repair)
    assert rec["ok"] and repaired == [1] and len(painted) == 1
    assert painted[0].startswith("Hyperrealistic. Arms held out from the body at sixty degrees")   # the nudge, near the front
    # a cartoon head is not a pose: no repair, a new picture
    fig(head=0.11).save(target)
    repaired.clear()
    rec2 = bodies.gate_picture("http://x", {"seed": 5}, {"id": "kid", "prompt": "A woman of thirty."}, target, "b", None, out,
                               paint_fn=paint, repair_fn=repair)
    assert repaired == [] and rec2["tries"]


def test_the_nudge_goes_after_the_style_start_and_asks_for_sixty_degrees():
    assert gate.with_nudge("Fantastic realism. A tall man.", "arms lowered") == "Fantastic realism. Arms lowered. A tall man."
    assert gate.with_nudge("A man with no style start, a long first sentence that goes on and on and on past sixty letters.",
                           "x").startswith("X. A man")
    assert "sixty degrees" in gate.NUDGES["arms_low"]
    assert gate.pose_miss_only({"lines": ["Picture gate — pose: the arms are at 8°; asked. Made again."]})
    assert not gate.pose_miss_only({"lines": ["Picture gate — pose: … Made again.", "Picture gate — proportions: … Made again."]})


def _held_round(tmp_path, cfg, eid, line, ntries=2):
    out = world.item_dir(cfg, "g1", eid)
    (out / "pictures").mkdir(parents=True, exist_ok=True)
    tries = [{"try": n, "seed": 1000 + n, "ok": False, "picture": f"{eid}__try{n}.png", "lines": [line],
              "measures": {"arms": {"left": {"angle": 5.0}, "right": {"angle": 6.0}}}} for n in (1, 2, 3)]
    for t in tries:
        fig(arm_deg=2).save(out / "pictures" / t["picture"])
    (out / "pictures" / f"{eid}.gate.json").write_text(json.dumps({"tries": tries, "held": True, "ok": False,
                                                                    "expects": {"pose": "a", "band": "adult"}}), encoding="utf-8")
    world.write_state(cfg, "g1", eid, {"state": "held", "kind": "body", "tier": "crowd", "held_by": "picture gate", "tries": ntries,
                                       "why": ["Picture gate: " + line.replace("Picture gate — ", "").replace(" Made again.", "")]})
    return out


POSE = "Picture gate — pose: the arms are at 5° and at 6° (from the body's line); an A-pose (about 45°) was asked (14–90°). Made again."
PROP = "Picture gate — proportions: the head is 21% of the figure's height (1 in 4.7); for an adult it is 10–16% — cartoon proportions. Made again."


def test_make_again_carries_the_nudge_and_a_new_seed(tmp_path):
    cfg = _cfg(tmp_path, [{"id": "clerk", "kind": "body", "tier": "crowd", "words": "Hyperrealistic. A man of fifty, a polo shirt.",
                           "real_size_m": {"height": 1.8}}])
    _held_round(tmp_path, cfg, "clerk", POSE)
    e = world.load(cfg, "g1")[0][0]
    seed_before = world._paint_spec(cfg, "g1", e, "trellis2")["spec"]["objects"][0]["seed"]
    r = world.make_again(cfg, "g1", "clerk", "the daily redo")
    assert r["ok"] and "nudged" in r["message"]
    st = world.read_state(cfg, "g1", "clerk")
    assert st["gate_carry"]["nudge"] == gate.NUDGES["arms_low"]
    st["tries"] = 3                                               # make() counts the new try before painting
    world.write_state(cfg, "g1", "clerk", st)
    p = world._paint_spec(cfg, "g1", e, "trellis2")
    obj = p["spec"]["objects"][0]
    assert obj["prompt"].startswith("Hyperrealistic. Arms held out from the body at sixty degrees")
    assert obj["seed"] != seed_before and obj["gate_nudge"] == gate.NUDGES["arms_low"]
    assert any("near their front" in n for n in p["notes"])


@pytest.fixture
def no_approvals(monkeypatch):
    from forge.suite import approve_all
    monkeypatch.setattr(approve_all, "world_plan", lambda cfg, gid: {"count": 0, "lines": [], "left": [],
                                                                     "groups": {"repair": [], "unclear": []}})
    monkeypatch.setattr(approve_all, "may_approve", lambda cfg, gid, who: True)
    monkeypatch.setattr(approve_all, "world_approve_all", lambda cfg, gid, who: {"done": [], "refused": []})


def test_held_twice_running_for_the_same_reason_is_not_made_a_third_time(tmp_path, no_approvals):
    cfg = _cfg(tmp_path, [{"id": "clerk", "kind": "body", "tier": "crowd", "words": "A man of fifty.", "real_size_m": {"height": 1.8}},
                          {"id": "kid", "kind": "body", "tier": "crowd", "words": "A boy of nine.", "real_size_m": {"height": 1.3}}])
    _held_round(tmp_path, cfg, "clerk", POSE)
    _held_round(tmp_path, cfg, "kid", POSE)
    r1 = redo.do(cfg, "g1", now=datetime(2026, 11, 20, 5, 0))         # the first redo: both made again
    assert sorted(r1["fresh"]) == ["clerk", "kid"]
    _held_round(tmp_path, cfg, "clerk", POSE, ntries=3)                  # held again for its arms
    _held_round(tmp_path, cfg, "kid", PROP, ntries=3)                    # held again, but for something else
    r2 = redo.do(cfg, "g1", now=datetime(2026, 11, 21, 5, 0))
    assert r2["fresh"] == ["kid"] and [t["id"] for t in r2["tired"]] == ["clerk"]
    assert r2["tired"][0]["twice"] and r2["tired"][0]["reason"] == "picture gate: pose"
    assert world.read_state(cfg, "g1", "clerk")["state"] == "held"
    nb = (world.world_dir(cfg, "g1") / "NEEDS_BETTER_WORDS.md").read_text(encoding="utf-8")
    assert "| clerk |" in nb and "twice running" in nb and "picture gate: pose" in nb
    rep = (world.world_dir(cfg, "g1") / "REDO_2026-11-21.txt").read_text(encoding="utf-8")
    assert "clerk: picture gate: pose (twice running)" in rep


def test_the_reason_a_thing_is_held_is_one_short_key():
    assert redo.reason_of({"held_by": "picture gate", "why": ["Picture gate: pose: the arms are at 5°"]}) == "picture gate: pose"
    assert redo.reason_of({"held_by": "picture gate", "why": ["Picture gate: proportions: the head is 21%",
                                                              "Picture gate: limbs: one arm"]}) == "picture gate: limbs, proportions"
    assert redo.reason_of({"state": "held", "why": ["Loose pieces: 1 piece"]}) == "loose pieces"


# ================================================================================================ Part 1: a body's colours
def _body(tmp_path, name, tex: np.ndarray, picture_tex: np.ndarray, metal: np.ndarray | None = None):
    """A standing slab (a body's outline, near enough) with its colour picture `tex`; its picture is `picture_tex` seen front
    on. `metal` (0-255, h x w) is a metallicRoughness texture's blue channel."""
    P, F = box_mesh((0.5, 1.8, 0.25), sub=10)
    uv = np.c_[(P[:, 0] - P[:, 0].min()) / np.ptp(P[:, 0]), 1 - (P[:, 1] - P[:, 1].min()) / np.ptp(P[:, 1])]
    textures = {"baseColorTexture": Image.fromarray(tex.astype(np.uint8))}
    mat = {"pbrMetallicRoughness": {"metallicFactor": 0.0 if metal is None else 1.0, "roughnessFactor": 1.0}}
    if metal is not None:
        mr = np.zeros(tex.shape[:2] + (3,), np.uint8)
        mr[..., 1] = 200
        mr[..., 2] = metal
        textures["metallicRoughnessTexture"] = Image.fromarray(mr)
    path = save(tmp_path / f"{name}.glb", [(P, F)], mat, uv, textures)
    g = Glb.load(path)
    m = g.mesh()
    scr, _ = raster.project(m["P"], raster.view_matrix(0, 0), 384)
    mask, _, col, _ = raster.rasterize(scr, m["F"], 384, m["UV"], Image.fromarray(picture_tex.astype(np.uint8)), want_color=True)
    pic = np.full((384, 384, 3), 232, np.uint8)
    pic[mask] = col[mask].clip(0, 255).astype(np.uint8)
    pp = tmp_path / f"{name}.png"
    Image.fromarray(pic).save(pp)
    return path, pp


def _suit(dark_blue=True):
    """A body's true colours: a skin band (the head), a near-black suit with the faint blue cast the bake leaves (15, 14,
    21), and a mid-grey chest plate."""
    t = np.zeros((64, 64, 3), np.float64)
    t[:] = (15, 14, 21) if dark_blue else (16, 16, 16)
    t[0:9] = (196, 150, 124)
    t[20:30, 16:48] = (120, 120, 124)
    return t


def _arrays(path):
    g = Glb.load(path)
    return [a for _, _, a, _ in checks.colour_arrays(g, g.mesh())]


def test_a_body_is_put_right_by_one_gain_for_its_whole_colour_picture_and_no_hue_moves(tmp_path):
    true = _suit()
    true[9:20] = (60, 80, 120)
    glbp, pic = _body(tmp_path, "b", true * 0.6, true)                    # a body too dark all over by one number
    fr = checks.fix_colour(glbp, tmp_path / "b__one.glb", Image.open(pic), None, "crowd")
    assert fr["mode"] == "one_gain" and fr["ok"] and fr["inside"], fr["said"]
    assert 1.2 < fr["gain"] < 1.75 and fr["hue"]["ok"] and fr["hue"]["share"] == 0.0         # the least that brings it inside
    a, b = _arrays(glbp)[0], _arrays(tmp_path / "b__one.glb")[0]
    np.testing.assert_allclose(b[..., :3], np.clip(np.round(a[..., :3] * fr["gain"]), 0, 255))     # one number, every texel
    # every body kind takes the same road: a curve never reaches a body
    for kind in checks.BODY_KINDS:
        assert checks.fix_colour(glbp, tmp_path / f"b_{kind}.glb", Image.open(pic), None, kind, mode="luma")["mode"] == "one_gain"


def test_a_black_suit_stays_black_the_gain_is_the_least_the_check_allows_and_the_face_comes_first(tmp_path):
    true = _suit(dark_blue=False)
    true[9:64] = np.where(true[9:64] == 16, 32, true[9:64])                # the picture's suit: charcoal, lit
    made = _suit()                                                         # as made: black, a faint blue cast
    glbp, pic = _body(tmp_path, "sarahlike", made, true)
    before = checks.check_colour(Glb.load(glbp).mesh(), Glb.load(glbp), Image.open(pic), checks.settings(None), "named")
    fr = checks.fix_colour_body(glbp, tmp_path / "s__one.glb", Image.open(pic), None, "named")
    a, b = _arrays(glbp)[0], _arrays(tmp_path / "s__one.glb")[0]
    suit_a, suit_b = a[40, 5, :3], b[40, 5, :3]
    assert suit_b.max() < 40                                               # black: nowhere near navy
    assert abs(suit_b[2] / max(suit_b[0], 1) - suit_a[2] / max(suit_a[0], 1)) < 0.12        # its colour's proportions kept
    if before.get("head_ratio"):
        hlo, hhi = checks.DEFAULTS["colour_head_band"]
        assert fr["after"]["head_ratio"] <= hhi + 0.03                     # the face is never pushed past its band for the body
    assert "one gain ×" in fr["said"]


def test_the_hue_check_catches_a_curve_a_colour_and_passes_one_gain():
    rng = np.random.default_rng(84)
    a = np.clip(rng.normal(100, 25, (64, 64, 3)), 0, 255)
    assert checks.hue_moved([a], [checks.one_gain(a, 1.3)])["ok"]
    curved = 255.0 * (a / 255.0) ** np.array([0.7, 1.0, 1.4])              # a curve a colour: each channel its own
    hm = checks.hue_moved([a], [curved])
    assert not hm["ok"] and hm["share"] > 0.02


def _held_body(tmp_path, cfg, eid="walker", stale_offer=True):
    out = world.item_dir(cfg, "g1", eid)
    (out / "models").mkdir(parents=True, exist_ok=True)
    true = _suit()
    glbp, pic = _body(out / "models", f"{eid}__trellis2", true * 0.6, true)
    st = {"state": "held", "kind": "body", "tier": "crowd", "model_raw": _rel(tmp_path, glbp), "picture": _rel(tmp_path, pic),
          "why": ["Colours hold: 60% as bright as its picture"],
          "check_results": [{"check": "loose", "ok": True}, {"check": "colour", "ok": False, "mean_ratio": 0.6}]}
    if stale_offer:                                        # an offer matched by a curve before BUILD 84: never to be used
        luma = out / f"{eid}__colour.glb"
        checks.apply_lut(glbp, luma, np.stack([np.arange(256)[::-1]] * 3).astype(np.uint8), "rgb")
        st.update(colour_offer=_rel(tmp_path, luma), colour_offer_mode="luma")
    world.write_state(cfg, "g1", eid, st)
    return out, glbp


def test_match_and_release_takes_one_gain_from_the_body_as_made_never_an_old_curve_offer(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, [{"id": "walker", "kind": "body", "tier": "crowd", "words": "A man of fifty.", "real_size_m": {"height": 1.8}}])
    out, as_made = _held_body(tmp_path, cfg)
    seen = []
    real = checks.fix_colour_body
    monkeypatch.setattr(checks, "fix_colour_body", lambda src, *a, **k: seen.append(Path(src)) or real(src, *a, **k))
    r = world.match_and_release(cfg, "g1", ["walker"], "Claude Fable, for William")
    assert [d["id"] for d in r["released"]] == ["walker"] and "one gain" in r["released"][0]["how"]
    assert seen == [as_made]                                                # worked out from the body as made
    st = world.read_state(cfg, "g1", "walker")
    assert st["state"] == "wanted" and st["reuse_body"].endswith("walker__one_gain.glb") and st["colour_mode"] == "one_gain"
    assert st["colour_released"]["how"] == "one gain" and st["colour_released"]["gain"] == st["colour_gain"]
    assert _rel(tmp_path, as_made) == st["model_as_made"] and (out / "colour.png").exists()
    assert checks.hue_moved(_arrays(as_made), _arrays(tmp_path / st["reuse_body"]))["share"] == 0.0


def test_a_release_whose_hue_would_move_is_refused_and_the_body_stays_held(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, [{"id": "walker", "kind": "body", "tier": "crowd", "words": "A man of fifty.", "real_size_m": {"height": 1.8}}])
    _held_body(tmp_path, cfg, stale_offer=False)
    monkeypatch.setattr(checks, "one_gain", lambda a, g: a[..., [2, 0, 1, *range(3, a.shape[-1])]] * 1.0)   # a hue turned
    r = world.match_and_release(cfg, "g1", ["walker"], "Claude Fable, for William")
    assert not r["released"] and "hue moved" in r["refused"][0]["why"]
    assert world.read_state(cfg, "g1", "walker")["state"] == "held"


def test_the_queue_does_not_match_a_released_body_again(tmp_path):
    cfg = _cfg(tmp_path, [{"id": "walker", "kind": "body", "tier": "crowd", "words": "A man of fifty.", "real_size_m": {"height": 1.8}}])
    out, as_made = _held_body(tmp_path, cfg, stale_offer=False)
    e = world.load(cfg, "g1")[0][0]
    res = checks.run(as_made, out / "models" / "walker__trellis2.png", "body", "crowd", cfg)
    cur, res2, fixed = world._put_right(cfg, e, out, as_made, out / "models" / "walker__trellis2.png", res, colour=False)
    assert cur == as_made and not fixed.get("colour_offer") and not fixed.get("colour_lut")
    cur, res3, fixed = world._put_right(cfg, e, out, as_made, out / "models" / "walker__trellis2.png", res)
    assert fixed.get("colour_mode") == "one_gain" or fixed.get("colour_offer_mode") == "one_gain"


def test_metal_is_left_out_of_the_colour_check(tmp_path):
    true = np.full((64, 64, 3), 150.0)
    made = true.copy()
    made[18:] = 30                                                         # most of it dark: its metal part
    metal = np.zeros((64, 64), np.uint8)
    metal[18:] = 255
    glbp, pic = _body(tmp_path, "rail", made, true, metal=metal)
    g = Glb.load(glbp)
    r = checks.check_colour(g.mesh(), g, Image.open(pic), checks.settings(None), "prop")
    assert r["ok"] and 0.3 < r["metal_share"] < 0.85 and "marked as metal left out" in r["line"]
    plain, pic2 = _body(tmp_path, "rail2", made, true)                     # the same, nothing marked: held as before
    g2 = Glb.load(plain)
    assert not checks.check_colour(g2.mesh(), g2, Image.open(pic2), checks.settings(None), "prop")["ok"]
    allm, pic3 = _body(tmp_path, "horn", made, true, metal=np.full((64, 64), 250, np.uint8))
    g3 = Glb.load(allm)
    r3 = checks.check_colour(g3.mesh(), g3, Image.open(pic3), checks.settings(None), "prop")
    assert r3["ok"] and r3.get("skipped") and "marked as metal" in r3["line"]
    undecided, pic4 = _body(tmp_path, "suit", made, true, metal=np.full((64, 64), 128, np.uint8))   # 0.5: the step didn't know
    g4 = Glb.load(undecided)
    assert checks.check_colour(g4.mesh(), g4, Image.open(pic4), checks.settings(None), "prop")["metal_share"] == 0.0


def _game_default(tmp_path, gid="g1"):
    d = tmp_path / "games" / gid
    d.mkdir(parents=True, exist_ok=True)
    (d / "approvals.json").write_text(json.dumps({"assistant_may_approve": True, "assistants": ["Claude Fable"], "for": "William"}),
                                      encoding="utf-8")


@pytest.fixture
def suite_json(tmp_path, monkeypatch):
    from forge import config as cfgmod
    from forge.suite import settings
    monkeypatch.setattr(settings, "PATH", tmp_path / "local" / "suite.json")
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    monkeypatch.delenv("FORGE_IDENTITY", raising=False)


def test_a_made_body_released_with_a_curve_has_its_colour_picture_swapped_and_undo_puts_it_back(tmp_path, suite_json):
    from forge.suite import approve_all as ap
    cfg = _cfg(tmp_path, [{"id": "walker", "kind": "body", "tier": "crowd", "words": "A man of fifty.", "real_size_m": {"height": 1.8}}])
    _game_default(tmp_path)
    out, raw = _held_body(tmp_path, cfg, stale_offer=False)
    import shutil
    as_made = out / "models" / "walker__trellis2__as_made.glb"
    shutil.copyfile(raw, as_made)                                          # the queue kept the body as made beside it ...
    lut = np.stack([np.arange(256), np.arange(256) * 0.8, np.arange(256) * 0.6]).astype(np.uint8)   # a curve a colour
    checks.apply_lut(as_made, raw, lut, "rgb")                             # ... and rigged the curve-matched one
    (out / "moves").mkdir()
    moving = out / "moves" / "walker_moves.glb"
    shutil.copyfile(raw, moving)
    st = world.read_state(cfg, "g1", "walker")
    st.update(state="made", model=_rel(tmp_path, moving), reuse_body=_rel(tmp_path, raw), model_raw=_rel(tmp_path, raw),
              colour_released={"by": "Claude Fable, for William", "at": "2026-11-19T17:13:48"}, check_results=[], why=[])
    world.write_state(cfg, "g1", "walker", st)
    r = ap.world_one_gain(cfg, "g1", "Claude Fable", ["walker"], note="BUILD 84 part 1.5")
    assert r["by"] == "Claude Fable, for William" and [d["id"] for d in r["done"]] == ["walker"], r
    st = world.read_state(cfg, "g1", "walker")
    g = st["colour_gain"]
    np.testing.assert_allclose(_arrays(moving)[0][..., :3], np.clip(np.round(_arrays(as_made)[0][..., :3] * g), 0, 255))
    assert (out / "moves" / "walker_moves__before_one_gain.glb").exists() and st["colour_mode"] == "one_gain"
    rec = next(h for h in ap.history(cfg, "g1") if h["id"] == "walker")
    assert rec["what"] == "Put right at one gain" and rec["how"].startswith("one gain ×")
    u = ap.undo(cfg, "g1", rec["uid"], "Bill")
    assert u["ok"], u
    assert (moving.read_bytes() == (out / "moves" / "walker_moves__before_one_gain.glb").read_bytes())
    # a body released as made has no curve to put right
    st = world.read_state(cfg, "g1", "walker")
    st.update(as_made=True)
    world.write_state(cfg, "g1", "walker", st)
    assert "as made" in world.one_gain_now(cfg, "g1", "walker", "Claude Fable, for William")["why"]


def test_approve_everything_says_the_gain_each_body_went_at(tmp_path, suite_json):
    from forge.suite import approve_all as ap
    cfg = _cfg(tmp_path, [{"id": "walker", "kind": "body", "tier": "crowd", "words": "A man of fifty.", "real_size_m": {"height": 1.8}}])
    _game_default(tmp_path)
    _held_body(tmp_path, cfg)
    p = ap.world_plan(cfg, "g1")
    assert "one gain for the whole colour picture" in " ".join(p["lines"]) and "never a hue" in " ".join(p["lines"])
    r = ap.world_approve_all(cfg, "g1", "Claude Fable")
    assert r["done"][0]["how"].startswith("one gain ×")


# ================================================================================================ Part 3: animals
from test_world_build39 import FAKE_BLENDER, _rigenv, art  # noqa: E402,F401


def _no_person_steps(monkeypatch):
    from forge.threed import motions, rig
    called = []

    def refuse(name):
        def f(*a, **k):
            called.append(name)
            raise AssertionError(f"an animal reached the person's {name}")
        return f
    monkeypatch.setattr(rig, "rig_bodies", refuse("skeleton"))
    monkeypatch.setattr(motions, "fit", refuse("motions"))
    return called


def test_an_animal_is_made_with_no_skeleton_and_never_reaches_the_peoples_motions_or_checks(tmp_path, art, monkeypatch):
    si, url = art
    called = _no_person_steps(monkeypatch)
    cfg = {"_root": str(tmp_path), "comfy": {"url": url},
           "threed": {"out_root": str(tmp_path / "out3d"), "blender_python": FAKE_BLENDER}}
    d = tmp_path / "games" / "g1" / "wanted_3d"
    d.mkdir(parents=True)
    (d / "l.json").write_text(json.dumps({"entries": [
        {"id": "porch_dog", "kind": "body", "tier": "crowd", "rig_kind": "animal", "gate": True,
         "words": "Hyperrealistic. A single old hound asleep, lying on its side.", "real_size_m": {"height": 0.4}}]}), encoding="utf-8")
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False, env=_rigenv(tmp_path), blender_python=FAKE_BLENDER)
    st = world.read_state(cfg, "g1", "porch_dog")
    assert t["made"] == 1 and st["state"] == "made", st.get("why") or st.get("error")
    assert called == []                                                          # never the person's skeleton or motions
    assert st["moves"] == "none yet" and st["rig"] == "none" and not st.get("fbx") and st["model"].endswith("porch_dog.glb")
    assert not any(w in " ".join(st["checks"]).lower() for w in ("the face", "the hair", "smile"))
    out = tmp_path / "out3d" / "world" / "g1" / "porch_dog"
    assert not (out / "rig").exists() and not (out / "moves" / "porch_dog_moves.glb").exists()
    assert not (out / "pictures" / "porch_dog.gate.json").exists()               # the picture gate is for people
    tr = json.loads(next((tmp_path / "games" / "g1" / "threed" / "tries").glob("*/*.json")).read_text(encoding="utf-8"))
    assert tr["steps"]["motions"]["state"] == "skipped" and "none yet" in tr["steps"]["motions"]["note"]
    assert "always" not in json.dumps([n for n in si.seen if "A-pose" in json.dumps(n)])   # painted with the thing words


def test_the_line_never_fits_a_persons_skeleton_or_motions_to_an_animal(tmp_path, monkeypatch):
    from forge.threed import line
    called = _no_person_steps(monkeypatch)
    out = tmp_path / "line"
    (out / "models").mkdir(parents=True)
    P, F = box_mesh((0.8, 0.5, 0.3))
    save(out / "models" / "coyote__trellis2.glb", [(P, F)])
    rows = line.run({"_root": str(tmp_path)}, {"batch": "b", "objects": [{"id": "coyote", "kind": "animal"}]}, out,
                    skip=("pictures",), env=_rigenv(tmp_path), blender_python=FAKE_BLENDER)
    assert called == [] and rows[0]["body"] and not rows[0]["skeleton"]


def test_an_animal_made_with_a_persons_skeleton_is_made_again_as_an_animal(tmp_path):
    cfg = _cfg(tmp_path, [{"id": "black_bear", "kind": "body", "tier": "crowd", "rig_kind": "animal", "words": "A black bear.",
                           "real_size_m": {"height": 1.0}},
                          {"id": "walker", "kind": "body", "tier": "crowd", "words": "A man.", "real_size_m": {"height": 1.8}}])
    out = world.item_dir(cfg, "g1", "black_bear")
    for sub in ("models", "moves", "rig"):
        (out / sub).mkdir(parents=True)
    P, F = box_mesh((1.6, 1.0, 0.6))
    body = save(out / "models" / "black_bear__trellis2.glb", [(P, F)])
    (out / "moves" / "black_bear_moves.glb").write_bytes(b"x")
    (out / "rig" / "black_bear__unirig.fbx").write_bytes(b"x")
    e = world.load(cfg, "g1")[0][0]
    st = {"state": "made", "kind": "body", "tries": 1, "model": _rel(tmp_path, out / "moves" / "black_bear_moves.glb"),
          "model_raw": _rel(tmp_path, body), "rigger": "unirig"}
    st["try"] = world.to_review(cfg, "g1", e, st)
    world.write_state(cfg, "g1", "black_bear", st)
    r = world.animal_again(cfg, "g1", ["black_bear", "walker"], "the forge")
    assert r["again"] == ["black_bear"] and r["left"][0]["id"] == "walker"
    st = world.read_state(cfg, "g1", "black_bear")
    assert st["state"] == "wanted" and st["reuse_body"].endswith("black_bear__trellis2.glb")
    assert not (out / "moves").exists() and not (out / "rig").exists()
    assert list(out.glob("moves__person_skeleton_superseded_*")) and list(out.glob("rig__person_skeleton_superseded_*"))
    tfile = next((tmp_path / "games" / "g1" / "threed" / "tries" / "black_bear").glob("*.json"))
    assert json.loads(tfile.read_text())["review"]["state"] == "withdrawn"


def test_world_fix_unhold_takes_a_held_animal_off_hold(tmp_path):
    from forge import cli_approve
    cfg = _cfg(tmp_path, [{"id": "jn_longhorn_steer", "kind": "body", "tier": "crowd", "rig_kind": "animal", "hold": True,
                           "words": "A longhorn steer.", "real_size_m": {"height": 1.5}}])
    assert world.load(cfg, "g1")[0][0]["hold"]
    assert cli_approve.cmd_world_fix(cfg, ["unhold", "jn_longhorn_steer", "--game", "g1"]) == 0
    assert not world.load(cfg, "g1")[0][0]["hold"]


# ================================================================================================ putting changes in
def test_a_put_in_is_a_pause_for_art_around_the_clock_not_a_stop(tmp_path):
    from test_build82_around_the_clock import FakeMachine, T   # the launcher's own stand-in machine and clock
    from forge import around_the_clock as atc
    t = T()
    m = FakeMachine(tmp_path, t())
    c = atc.Clock(m, "g1", redo=False, now=t, sleep=lambda s: None, out=lambda s: None)
    c.started = t()
    m.up = True
    c.tick()
    t.go(600)
    m.put_in = (t(), True)
    m.put_in_marks = lambda: m.put_in                   # put_in_waiting_changes.bat: PUT_IN, then STOP
    m.marks = t() + 1
    m.procs[0].rc = 0                                   # the queue stops after the thing in hand
    assert c.tick() is None and "put in" in c.step      # the launcher waits; it does not stop itself
    t.go(300)
    assert c.tick() is None and len(m.procs) == 1       # nothing started while the changes go in
    m.put_in = (m.put_in[0], False)                     # PUT_IN.done: the pause is over
    t.go(60)
    c.tick()
    assert len(m.procs) == 2                            # it takes the queue up again
    t.go(600)
    m.marks = t()                                       # a real Stop later (3D -> Runs) still stops it
    m.procs[1].rc = 0
    assert c.tick() == "stop asked"


def test_the_put_in_writes_put_in_first_and_ends_it(tmp_path):
    cfg = _cfg(tmp_path, [])
    world.ask_stop(cfg, "g1", "put_in_waiting_changes.bat", pause_for="putting in")
    wd = world.world_dir(cfg, "g1")
    assert (wd / "PUT_IN").exists() and (wd / "STOP").exists()
    assert (wd / "PUT_IN").stat().st_mtime <= (wd / "STOP").stat().st_mtime
    world.put_in_done(cfg, "g1")
    assert not (wd / "PUT_IN").exists() and (wd / "PUT_IN.done").exists()
