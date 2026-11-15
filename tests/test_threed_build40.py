"""BUILD 40 — what the second run taught: colours that hold (the check, the tone-curve fix, blank glass painted dark),
a look at the picture before the body is made (the picture gate), and the standing words for children, missing limbs
and lettering. No graphics card: meshes and pictures are made here, the line runs against the stand-in ComfyUI, and the
stand-in paints an A-pose figure with an adult's proportions (a good picture) unless asked otherwise.
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge.threed import bodies, checks, gate, raster, rules, standin, world
from forge.threed.meshio import Glb

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_world_build39 import FAKE_BLENDER, _cfg, _list, _rigenv, _textured_box, art, box_mesh, save  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))


def fig(**kw) -> Image.Image:
    im = Image.open(io.BytesIO(standin.png(**kw)))
    im.load()
    return im


# ------------------------------------------------------------------------------------------------ the picture gate
def test_the_gate_passes_a_good_a_pose_and_says_why():
    j = gate.judge(fig(), {"prompt": "A soldier of thirty, short dark hair"})
    assert j["ok"], j["lines"]
    assert any("2 arms, as asked" in ln for ln in j["lines"]) and any("A-pose" in ln for ln in j["lines"])
    assert any("right for an adult" in ln for ln in j["lines"])


def test_the_gate_catches_an_a_pose_drawn_for_a_t_pose_and_passes_a_t_pose():
    miss = gate.judge(fig(arm_deg=45), {"prompt": "A soldier of thirty", "always": "standing in a T-pose, arms level"})
    assert not miss["ok"] and any("T-pose" in ln and "Made again" in ln for ln in miss["lines"])
    for deg in (80, 90):
        assert gate.judge(fig(arm_deg=deg), {"prompt": "A soldier of thirty in a T-pose"})["ok"]


def test_the_gate_counts_arms_one_asked_two_drawn_is_a_miss_a_stump_is_not():
    words = {"prompt": "A man of forty with one arm, an amputee"}
    two = gate.judge(fig(), words)
    assert not two["ok"] and any("two arms stand out" in ln for ln in two["lines"])
    assert gate.judge(fig(arms="right"), words)["ok"]
    stump = gate.judge(fig(forearm=False), {"prompt": "A man of forty, his left arm is missing from just below the elbow"})
    assert stump["ok"] and any("stump" in ln for ln in stump["lines"]), stump["lines"]
    # and an entry can say it outright
    assert not gate.judge(fig(), {"prompt": "A man of forty", "expects": {"arms": 1}})["ok"]


def test_the_gate_catches_cartoon_proportions_for_the_age_given():
    cartoon = gate.judge(fig(head=0.11), {"prompt": "A boy of nine with untidy brown hair"})
    assert not cartoon["ok"] and any("cartoon proportions" in ln for ln in cartoon["lines"])
    assert gate.judge(fig(head=0.085), {"prompt": "A real nine-year-old boy"})["ok"]
    assert not gate.judge(fig(head=0.095), {"prompt": "A Vietnamese-American girl of sixteen"})["ok"]
    assert gate.judge(fig(), {"prompt": "A Vietnamese-American girl of sixteen"})["ok"]


def test_arms_held_against_the_body_are_a_miss_but_a_seated_or_crutch_figure_skips_the_pose():
    j = gate.judge(fig(arm_deg=6), {"prompt": "A man of thirty"})
    assert not j["ok"] and any("held against the sides" in ln for ln in j["lines"])
    seated = gate.judge(fig(arm_deg=85), {"prompt": "A man of thirty-six sitting upright in a manual wheelchair"})
    assert seated["ok"] and any("seated" in ln for ln in seated["lines"])
    leaning = gate.judge(fig(arm_deg=20), {"prompt": "A man of thirty-five who leans on a forearm crutch"})
    assert any("crutch" in ln for ln in leaning["lines"])


def test_what_the_entry_asks_for_is_read_from_its_words_and_its_fields():
    e = gate.expectations({"prompt": "Hyperrealistic. A real nine-year-old boy"})
    assert e["age"] == 9 and e["band"] == "child" and e["arms"] == 2 and e["pose"] == "a"
    assert gate.expectations({"prompt": "A Black man of thirty-four"})["age"] == 34
    assert gate.expectations({"prompt": "a sixteen-year-old girl"})["band"] == "teen"
    assert gate.expectations({"prompt": "his left arm is missing from just below the elbow"})["arms"] == 1
    assert gate.expectations({"prompt": "x", "always": "T-pose"})["pose"] == "t"
    f = gate.expectations({"prompt": "a woman", "age": 70, "seated": True, "carried_object": "cane", "expects": {"arms": 1}})
    assert f["age"] == 70 and f["band"] == "adult" and f["seated"] and f["carried_object"] == "cane" and f["arms"] == 1
    assert gate.age_of("a crew of ten") is None                      # a number after "of" is not always an age


def test_every_gate_number_is_a_setting():
    s = gate.settings({"threed": {"gate": {"tries": 5, "head_ratio": {"child": [0.1, 0.3]}}}})
    assert s["tries"] == 5 and s["head_ratio"]["child"] == [0.1, 0.3] and s["head_ratio"]["adult"] == gate.DEFAULTS["head_ratio"]["adult"]
    assert gate.judge(fig(head=0.11), {"prompt": "A boy of nine"}, {"threed": {"gate": {"head_ratio": {"child": [0.1, 0.3]}}}})["ok"]


def test_a_missed_picture_is_painted_again_with_a_new_seed_and_kept(tmp_path):
    (tmp_path / "pictures").mkdir()
    target = tmp_path / "pictures" / "kim.png"
    fig().save(target)                                                # try 1: two arms
    seeds = []

    def paint(url, pic, obj, tgt, batch, cfg):
        seeds.append(obj["seed"])
        fig(arms="right").save(tgt)                                   # try 2: one arm
        return {"seed": obj["seed"], "prompt": obj["prompt"]}
    rec = bodies.gate_picture("u", {"seed": 5}, {"id": "kim", "prompt": "A man of forty with one arm", "seed": 5}, target, "b", None,
                              tmp_path, {}, paint_fn=paint)
    assert rec["ok"] and not rec["held"] and len(rec["tries"]) == 2 and seeds == [5 + 7919]
    assert (tmp_path / "pictures" / "kim__try1.png").exists() and (tmp_path / "pictures" / "kim__try2.png").exists()
    assert json.loads((tmp_path / "pictures" / "kim.gate.json").read_text())["ok"]


def test_three_misses_hold_the_thing_with_the_tries_side_by_side(tmp_path):
    (tmp_path / "pictures").mkdir()
    target = tmp_path / "pictures" / "boy.png"
    fig(head=0.11).save(target)
    seeds = []

    def paint(url, pic, obj, tgt, batch, cfg):
        seeds.append(obj["seed"])
        fig(head=0.11).save(tgt)
        return {"seed": obj["seed"]}
    rec = bodies.gate_picture("u", {}, {"id": "boy", "prompt": "A boy of nine", "seed": 3}, target, "b", None, tmp_path, {},
                              paint_fn=paint)
    assert rec["held"] and len(rec["tries"]) == 3 and len(set(seeds)) == 2
    assert any("cartoon proportions" in w for w in rec["why"])
    sbs = tmp_path / "pictures" / "boy__gate.png"
    assert sbs.exists() and Image.open(sbs).size[0] == 3 * 320
    # asked again (the queue's next go), it carries on from try 4 with new seeds
    rec2 = bodies.gate_picture("u", {}, {"id": "boy", "prompt": "A boy of nine", "seed": 3}, target, "b", None, tmp_path, {},
                               paint_fn=paint)
    assert [t["try"] for t in rec2["tries"]] == [1, 2, 3, 4, 5, 6] and len(set(seeds)) == 5


def test_a_picture_from_a_file_is_measured_never_repainted(tmp_path):
    (tmp_path / "pictures").mkdir()
    target = tmp_path / "pictures" / "x.png"
    fig().save(target)
    called = []
    rec = bodies.gate_picture("u", {}, {"id": "x", "prompt": "A man of forty with one arm", "image": "given.png"}, target, "b",
                              None, tmp_path, {}, paint_fn=lambda *a: called.append(a))
    assert rec["held"] and not called and len(rec["tries"]) == 1


# ------------------------------------------------------------------------------------------------ the world queue
def test_the_queue_holds_a_body_whose_picture_misses_and_a_person_can_overrule_it(tmp_path, art):
    si, url = art
    env = _rigenv(tmp_path)
    cfg = _cfg(tmp_path, url)
    from forge.threed import glb
    lib = glb.box(tmp_path / "lib.glb", (0.5, 1.8, 0.3), motions=["Walk_Loop"], joints=2)
    _list(tmp_path, [{"id": "kim_later", "kind": "body", "tier": "principal", "real_size_m": {"height": 1.75},
                      "words": "A Korean-American man of forty with one arm, an amputee; a worn green field jacket",
                      "motions": {"library": str(lib), "travel": str(lib)}}])
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False, env=env, blender_python=FAKE_BLENDER)
    assert t["held"] == 1 and t["made"] == 0
    st = world.read_state(cfg, "g1", "kim_later")
    assert st["held_by"] == "picture gate" and len(st["gate"]["tries"]) == 3 and st["gate"]["side_by_side"]
    assert any("two arms" in w for w in st["why"])
    assert not (tmp_path / "out3d" / "world" / "g1" / "kim_later" / "models" / "kim_later__trellis2.glb").exists()
    sent = json.dumps(si.seen)
    assert "Only one arm" in sent and "No lettering" in sent                    # the standing words went in
    seeds = {n["inputs"].get("noise_seed") or n["inputs"].get("seed") for p in si.seen for n in p.values()
             if isinstance(n, dict) and isinstance(n.get("inputs"), dict) and ("noise_seed" in n["inputs"] or "seed" in n["inputs"])}
    assert len(seeds) >= 3                                                       # each try a new seed
    v = [i for i in world.status(cfg, "g1")["items"] if i["id"] == "kim_later"][0]
    assert v["held_by"] == "picture gate" and v["gate"]["tries"]
    with pytest.raises(world.WorldError):
        world.gate_anyway(cfg, "g1", "kim_later", "")
    r = world.gate_anyway(cfg, "g1", "kim_later", "William", pick=2)
    assert r["ok"] and world.read_state(cfg, "g1", "kim_later")["state"] == "wanted"
    t2 = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False, env=env, blender_python=FAKE_BLENDER)
    assert t2["made"] == 1, world.read_state(cfg, "g1", "kim_later")
    st2 = world.read_state(cfg, "g1", "kim_later")
    assert any("let through by William (picture 2)" in ln for ln in st2["checks"])


def test_an_entry_can_switch_the_gate_off(tmp_path, art):
    si, url = art
    env = _rigenv(tmp_path)
    cfg = _cfg(tmp_path, url)
    from forge.threed import glb
    lib = glb.box(tmp_path / "lib.glb", (0.5, 1.8, 0.3), motions=["Walk_Loop"], joints=2)
    _list(tmp_path, [{"id": "kim_off", "kind": "body", "tier": "principal", "real_size_m": {"height": 1.75}, "gate": False,
                      "words": "A man of forty with one arm", "motions": {"library": str(lib), "travel": str(lib)}}])
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False, env=env, blender_python=FAKE_BLENDER)
    assert t["made"] == 1
    assert not (tmp_path / "out3d" / "world" / "g1" / "kim_off" / "pictures" / "kim_off.gate.json").exists()


# ------------------------------------------------------------------------------------------------ standing words
def test_children_and_teenagers_start_hyperrealistic_and_name_real_proportions():
    w, al, notes = rules.body_word_rules("Fantastic realism. A boy of nine with untidy brown hair.", "A-pose.")
    assert w.startswith("Hyperrealistic. A boy of nine") and "natural proportions of a real 9-year-old" in w
    assert "Fantastic realism" not in w and len(notes) == 2
    w2, _, n2 = rules.body_word_rules("Fantastic realism. A white woman of fifty, an apron.", "A-pose.")
    assert w2.startswith("Fantastic realism") and not n2                       # adults keep William's two starts
    assert rules.standing_check("Fantastic realism. A girl of sixteen")[0].startswith("a teenager of 16")


def test_a_missing_limb_gets_its_own_pose_words_and_clothes_no_lettering():
    w, al, notes = rules.body_word_rules("A man of forty; his left arm is missing from just below the elbow.", "Both arms out.")
    assert "Only one arm" in w and "below the elbow" in w and any("cutting the finished body" in n for n in notes)
    assert al.endswith(rules.NO_LETTERING)
    assert any("lettering" in x for x in rules.standing_check("a school sports jacket with a logo"))
    assert not any("lettering" in x for x in rules.standing_check("a plain jacket with no lettering"))


# ------------------------------------------------------------------------------------------------ colours that hold
def _coloured_body(tmp_path, name, gamma: float):
    """A standing slab (a body's outline, near enough) whose texture is a gradient with a darker band; the picture is
    the gradient as painted, the model's texture is the same darkened by `gamma` (the ComfyUI bake's fault)."""
    P, F = box_mesh((0.5, 1.8, 0.25), sub=10)
    uv = np.c_[(P[:, 0] - P[:, 0].min()) / np.ptp(P[:, 0]), 1 - (P[:, 1] - P[:, 1].min()) / np.ptp(P[:, 1])]
    yy, xx = np.mgrid[0:64, 0:64]
    true = np.stack([60 + 2.6 * yy, 70 + 2.2 * yy, 90 + 1.5 * xx], -1).clip(0, 255).astype(np.uint8)
    true[20:28] = (190, 150, 120)
    dark = (255 * (true / 255.0) ** gamma).astype(np.uint8)
    path = save(tmp_path / f"{name}.glb", [(P, F)], {"pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0}},
                uv, {"baseColorTexture": Image.fromarray(dark)})
    # the picture: the true colours, front on, on light grey
    g = Glb.load(path)
    m = g.mesh()
    R = raster.view_matrix(0, 0)
    scr, _ = raster.project(m["P"], R, 384)
    mask, _, col, _ = raster.rasterize(scr, m["F"], 384, m["UV"], Image.fromarray(true), want_color=True)
    pic = np.full((384, 384, 3), 232, np.uint8)
    pic[mask] = col[mask].clip(0, 255).astype(np.uint8)
    pp = tmp_path / f"{name}.png"
    Image.fromarray(pic).save(pp)
    return path, pp


def test_the_colour_check_catches_a_dark_bake_and_the_fix_matches_the_picture(tmp_path):
    glbp, pic = _coloured_body(tmp_path, "body", 2.2)
    res = checks.run(glbp, pic, "body", only=("colour",))
    r = res["results"][0]
    assert not r["ok"] and r["mean_ratio"] < 0.8 and "held back" in r["line"]
    fixed = checks.fix_colour(glbp, tmp_path / "body__colour.glb", Image.open(pic), None, "body")
    assert fixed["ok"] and 0.9 < fixed["after"]["mean_ratio"] < 1.1, fixed["after"]["line"]
    assert Glb.load(glbp).texture_image(Glb.load(glbp).mesh()["materials"][0], "baseColorTexture") is not None   # as made, kept
    same, pic2 = _coloured_body(tmp_path, "fine", 1.0)
    assert checks.run(same, pic2, "body", only=("colour",))["ok"]


def test_tone_curves_never_fall_and_never_climb_too_steep():
    rng = np.random.default_rng(1)
    model = (255 * rng.random((5000, 3)) ** 2.2)
    pic = 255 * rng.random((5000, 3))
    lut = checks.tone_curves(model, pic, max_slope=3.0)
    assert lut.shape == (3, 256) and (np.diff(lut.astype(int), axis=1) >= 0).all()
    assert (np.diff(lut.astype(int), axis=1) <= 4).all()


def test_a_white_mirror_windscreen_is_painted_dark_glass(tmp_path):
    bad = _textured_box(tmp_path, "truck.glb", 0)
    assert not checks.run(bad, None, "prop", only=("glass",))["ok"]
    rep = checks.fix_glass(bad, tmp_path / "truck__glass.glb")
    assert rep["ok"] and rep["texels"] > 0
    assert checks.run(tmp_path / "truck__glass.glb", None, "prop", only=("glass",))["ok"]


def test_the_colour_check_is_on_every_kind_and_its_numbers_are_settings():
    for kind, names in checks.CHECKS_FOR.items():
        assert "colour" in names, kind
    for k in ("colour_mean_band", "colour_spread_min", "colour_head_band", "colour_prop_band", "colour_fix", "glass_fix"):
        assert k in checks.DEFAULTS


# ------------------------------------------------------------------------------------------------ seated, flames, backs
def test_a_seated_body_gets_a_skeleton_but_no_motions_and_says_so(tmp_path, art):
    si, url = art
    env = _rigenv(tmp_path)
    cfg = _cfg(tmp_path, url)
    from forge.threed import glb
    lib = glb.box(tmp_path / "lib.glb", (0.5, 1.8, 0.3), motions=["Walk_Loop"], joints=2)
    _list(tmp_path, [{"id": "reeves_chair", "kind": "body", "tier": "principal", "real_size_m": {"height": 1.3}, "seated": True,
                      "words": "A white man of thirty-six sitting upright in a manual wheelchair",
                      "motions": {"library": str(lib), "travel": str(lib)}}])
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False, env=env, blender_python=FAKE_BLENDER)
    assert t["made"] == 1, world.read_state(cfg, "g1", "reeves_chair")
    st = world.read_state(cfg, "g1", "reeves_chair")
    assert "no motions were fitted" in st["motion_note"] and any("no motions" in c for c in st["checks"])
    assert not st["model"].endswith("_moves.glb") and st["fbx"]
    assert not (tmp_path / "out3d" / "world" / "g1" / "reeves_chair" / "moves" / "reeves_chair_moves.glb").exists()
    tr = json.loads(next((tmp_path / "games" / "g1" / "threed" / "tries").glob("*/*.json")).read_text())
    assert tr["steps"]["motions"]["state"] == "skipped"


def _burning(tmp_path, name, spots):
    """A slab whose texture has bright flame-coloured spots (a fire, candles) at the given texture places."""
    P, F = box_mesh((1.0, 0.4, 1.0), sub=16)
    uv = np.c_[(P[:, 0] - P[:, 0].min()) / np.ptp(P[:, 0]), (P[:, 2] - P[:, 2].min()) / np.ptp(P[:, 2])]
    uv[P[:, 1] < P[:, 1].max() - 1e-6] = 0.01                  # only the top carries the picture; the rest is plain
    tex = np.full((128, 128, 3), (90, 80, 70), np.uint8)
    for (u, v, r) in spots:
        yy, xx = np.mgrid[0:128, 0:128]
        tex[(xx - u * 128) ** 2 + (yy - v * 128) ** 2 < (r * 128) ** 2] = (255, 170, 40)
    return save(tmp_path / f"{name}.glb", [(P, F)], {"pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0}},
                uv, {"baseColorTexture": Image.fromarray(tex)})


def test_flames_stand_where_the_colours_burn_one_card_pair_per_site(tmp_path):
    from forge.threed import damage
    src = _burning(tmp_path, "candles", [(0.2, 0.2, 0.04), (0.5, 0.5, 0.04), (0.8, 0.8, 0.04)])
    sites = damage.flame_sites(Glb.load(src))
    assert len(sites) == 3
    r = damage.flame(src, tmp_path / "lit.glb", source="a test flame")
    assert r["sites"] == 3 and "3 flame cards" in r["line"]
    g = Glb.load(tmp_path / "lit.glb")
    mat = [m for m in g.j["materials"] if m.get("name") == "forge_flame"][0]
    assert mat["alphaMode"] == "BLEND" and "KHR_materials_unlit" in mat["extensions"] and mat["emissiveTexture"]
    assert len(g.j["meshes"]) == 2
    plain = save(tmp_path / "plain.glb", [box_mesh()])
    assert damage.flame(plain, tmp_path / "plain2.glb")["sites"] == 0


def test_the_queue_adds_the_flame_and_the_viewer_opens_at_night(tmp_path):
    cfg = _cfg(tmp_path, blender_python="")                     # sized without Blender: the stand-in keeps no textures
    src = _burning(tmp_path, "fire", [(0.5, 0.5, 0.12)])
    _list(tmp_path, [{"id": "campfire", "kind": "prop", "tier": "small_prop", "real_size_m": {"width": 1.2}, "adopt": str(src),
                      "flame": {"width_share": 0.45}, "words": "a campfire"}])
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False)
    st = world.read_state(cfg, "g1", "campfire")
    assert t["made"] == 1 and st["flame"]["sites"] == 1 and any("flame card" in c for c in st["checks"])
    v = [i for i in world.status(cfg, "g1")["items"] if i["id"] == "campfire"][0]
    assert v["flame"]
    js = (REPO / "forge" / "suite" / "threed.js").read_text(encoding="utf-8")
    assert "light: i.flame || i.glow ? 'night'" in js
    assert "forge_flame" in (REPO / "forge" / "suite" / "viewer.html").read_text(encoding="utf-8")


def test_a_back_picture_goes_to_pixal3d_through_the_multi_view_node_and_never_to_trellis2(tmp_path, art):
    from forge.threed import template
    info = json.loads((REPO / "forge" / "threed" / "standin_info_art.json").read_text())
    api = template.build_prompt(template.load(), info, "front.png", "pixal3d", 1024, 40000, 2048, "p")
    two = template.add_back_view(api, "back.png")
    mv = [n for n in two.values() if n["class_type"] == "Pixal3DMultiViewConditioning"]
    assert len(mv) == 1 and not [n for n in two.values() if n["class_type"] == "Pixal3DConditioning"]
    back_crop = two[mv[0]["inputs"]["back"][0]]
    assert back_crop["class_type"] == "ImageCropToMask" and two[back_crop["inputs"]["images"][0]]["inputs"]["image"] == "back.png"
    with pytest.raises(RuntimeError):
        template.add_back_view(template.build_prompt(template.load(), info, "f.png", "trellis2", 1024, 40000, 2048, "p"), "b.png")
    # through the line: Pixal3D uses it, TRELLIS.2 is told it takes one picture
    si, url = art
    out = tmp_path / "run"
    back = tmp_path / "back.png"
    Image.open(io.BytesIO(standin.png())).save(back)
    spec = {"batch": "b", "models": ["pixal3d", "trellis2"], "resolutions": [1024],
            "objects": [{"id": "farmhouse", "prompt": "a farmhouse", "back_image": str(back)}]}
    rows = bodies.run(_cfg(tmp_path, url), spec, out, url=url, use_lock=False)
    assert {r["model"]: r.get("back_view") for r in rows} == {"pixal3d": True, "trellis2": False}
    sent = json.dumps(si.seen)
    assert sent.count("Pixal3DMultiViewConditioning") == 1


def test_the_review_card_asks_seen_from_behind():
    js = (REPO / "forge" / "suite" / "threed.js").read_text(encoding="utf-8")
    assert "Seen from behind?" in js


def test_vehicles_go_to_trellis2_and_the_route_is_written_down():
    d = json.loads((REPO / "forge" / "threed" / "defaults.json").read_text(encoding="utf-8"))
    assert d["kinds"]["prop"]["model"] == "trellis2" and d["kinds"]["building"]["model"] == "pixal3d"
    assert "vehicles" in d["_routes"].lower() and "TRELLIS.2" in d["_routes"]
    assert world.model_for("prop") == "trellis2" and "vehicles" in world.TIERS["large_prop"]["for"]


def test_a_thing_made_before_build_40_keeps_its_hash():
    e = {"id": "x", "kind": "prop", "tier": "small_prop", "words": "a crate", "real_size_m": {"width": 1.0}}
    old = __import__("hashlib").sha1(json.dumps({k: e.get(k) for k in world.MAKING_FIELDS}, sort_keys=True,
                                                default=str).encode("utf-8")).hexdigest()[:12]
    assert world.making_hash(e) == old
    assert world.making_hash(dict(e, flame={"width_share": 0.4})) != old
