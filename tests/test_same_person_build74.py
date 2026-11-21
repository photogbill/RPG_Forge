"""BUILD 74 — the same person, changed: the job's contract, the region's mask, the check that nothing else moved, the three
graphs, the bake-off end to end against a stand-in client (no ComfyUI, no card), and a body's bearing."""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from forge.threed import motions, same_person as sp


def person(size=(320, 480), bg=(232, 232, 232), shirt=(70, 90, 160)):
    """A front-on figure on a plain ground: a head, a trunk, two arms held out a little, two legs."""
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    W, H = size
    cx = W // 2
    d.ellipse([cx - 22, 30, cx + 22, 92], fill=(200, 160, 130))                    # head
    d.rectangle([cx - 40, 95, cx + 40, 270], fill=shirt)                          # trunk
    d.polygon([(cx - 40, 100), (cx - 52, 100), (cx - 100, 240), (cx - 88, 246)], fill=shirt)   # arms
    d.polygon([(cx + 40, 100), (cx + 52, 100), (cx + 100, 240), (cx + 88, 246)], fill=shirt)
    d.rectangle([cx - 35, 270, cx - 8, 450], fill=(40, 40, 50))                    # legs
    d.rectangle([cx + 8, 270, cx + 35, 450], fill=(40, 40, 50))
    return im


def test_the_contract_refuses_what_it_cannot_do():
    with pytest.raises(sp.SamePersonError, match="from"):
        sp.validate({"change": "pose", "to": "a_pose"})
    with pytest.raises(sp.SamePersonError, match="change"):
        sp.validate({"from": "a.png", "change": "haircut", "to": "x"})
    with pytest.raises(sp.SamePersonError, match="cannot keep"):
        sp.validate({"from": "a.png", "change": "expression", "to": "laugh", "keep": ["face", "expression"]})
    with pytest.raises(sp.SamePersonError, match="cannot keep"):
        sp.validate({"from": "a.png", "change": "age", "to": "at seventy", "keep": ["face"]})
    with pytest.raises(sp.SamePersonError, match="can't change"):
        sp.validate({"from": "a.png", "change": "age", "to": "at seventy", "keep": ["identity"], "method": "masked"})
    j = sp.validate({"from": "a.png", "change": "expression", "to": "slight_smile"})
    assert j["method"] == "masked" and j["region"] == "mouth_brows" and "smile" in j["words"]


def test_the_mask_grows_and_feathers_inside_the_picture():
    im = person()
    fig = sp.figure_mask(im)
    m = sp.region_mask(fig, "mouth")
    soft = sp.grow_feather(m, 8, 10)
    assert soft.shape == fig.shape and 0 <= soft.min() and soft.max() <= 1.0
    assert soft[m].min() == 1.0 and (soft > 0).sum() > m.sum() * 2            # grown and soft beyond the region itself
    ys, xs = np.nonzero(m)
    assert ys.min() > 30 and ys.max() < 100                                  # the mouth is in the head, not the shirt
    arms = sp.region_mask(fig, "arms")
    assert arms[:, :140].any() and arms[:, 180:].any() and not arms[:, 150:170].any()   # beside the trunk, both sides


def test_nothing_else_moved_passes_an_identical_picture_and_refuses_a_changed_background():
    a = person()
    region = sp.make_mask(a, "mouth_brows")
    ok = sp.moved(a, a.copy(), region, ["face", "background"], "masked")
    assert ok["ok"] and ok["outside_mean"] == 0
    b = a.copy()
    ImageDraw.Draw(b).rectangle([0, 400, 80, 470], fill=(20, 200, 40))         # something changed in the corner
    bad = sp.moved(a, b, region, ["face", "background"], "masked")
    assert not bad["ok"] and "outside the region" in bad["problems"][0]
    x0, y0, x1, y1 = bad["changed_box"]
    assert x0 <= 2 and y1 >= 460 and x1 <= 82
    inside = a.copy()
    ImageDraw.Draw(inside).rectangle([150, 70, 170, 82], fill=(150, 60, 60))   # a new mouth, inside the region
    assert sp.moved(a, inside, region, ["face", "background"], "masked")["ok"]


def test_the_check_picture_is_three_across(tmp_path):
    a = person()
    p = sp.check_picture(a, a, sp.make_mask(a, "mouth"), tmp_path / "c.png")
    assert Image.open(p).size == (a.size[0] * 3, a.size[1] + 24)


def test_the_three_graphs_use_only_nodes_on_the_disk():
    core = {"CheckpointLoaderSimple", "LoadImage", "ImageToMask", "CLIPTextEncode", "DifferentialDiffusion", "InpaintModelConditioning",
            "KSampler", "VAEDecode", "ImageCompositeMasked", "SaveImage", "ControlNetLoader", "SetUnionControlNetType",
            "ControlNetApplyAdvanced", "VAEEncode", "UNETLoader", "CLIPLoader", "VAELoader", "ConditioningZeroOut",
            "EmptyFlux2LatentImage", "RandomNoise", "KSamplerSelect", "Flux2Scheduler", "CFGGuider", "SamplerCustomAdvanced",
            "ImageScaleToTotalPixels", "ReferenceLatent"}
    for g in (sp.graph_masked("s.png", "m.png", "w", "n", 1), sp.graph_guided("s.png", "p.png", "w", "n", 1),
              sp.graph_instructed("s.png", "w", 1, 768, 1024)):
        assert {n["class_type"] for n in g.values()} <= core
    gi = sp.graph_instructed("s.png", "w", 1, 768, 1024)
    assert gi["10"]["inputs"]["positive"] == ["43", 0] and gi["43"]["class_type"] == "ReferenceLatent"
    assert "flux-2-klein-4b" in gi["1"]["inputs"]["unet_name"]                # the Apache-2.0 4B, never the 9B


def test_the_bakeoff_runs_end_to_end_against_a_stand_in(tmp_path):
    src = tmp_path / "p.png"
    person().save(src)

    class Stand:
        def __init__(self):
            self.n = 0

        def upload_image(self, path, subfolder="forge", name=None):
            return name or Path(path).name

        def run(self, g):
            self.n += 1
            b = io.BytesIO()
            person().save(b, "PNG")                         # it hands back the person unchanged
            return [b.getvalue()]
    st = Stand()
    cases = [{"id": "e", "change": "expression", "to": "slight_smile", "from": str(src)},
             {"id": "p", "change": "pose", "to": "a_pose", "from": str(src), "methods": ["masked", "guided"]},
             {"id": "missing", "change": "age", "to": "older", "from": str(tmp_path / "nope.png")}]
    r = sp.bakeoff({}, cases, tmp_path / "out", tmp_path, client=st, use_lock=False, seeds=(1,))
    rep = json.loads((tmp_path / "out" / "report.json").read_text())
    assert st.n == 4 and r["rows"] == 5 and any("no picture" in x.get("error", "") for x in rep)
    assert (tmp_path / "out" / "report.md").read_text().count("|") > 10
    assert all(x.get("ok") for x in rep if x.get("method") == "masked")


def test_a_bearing_never_moves_a_joint_past_its_limit_and_leaves_the_feet_alone(tmp_path):
    for name in motions.BEARINGS:
        off = motions.bearing_offsets(name, {"head": 2.0})
        assert all(abs(v) <= motions.JOINT_LIMIT_DEG.get(j, 6.0) + 1e-9 for j, vs in off.items() for v in vs)
        assert all(abs(v) <= 2.0 for v in off["head"])
        assert not any(n in j.lower() for j in off for n in motions.NEVER)
    assert motions.bearing_from_words("A sentry of thirty, kind and steady") == "warm"
    assert motions.bearing_from_words("a man", "proud") == "proud"
    assert motions.bearing_from_words("a crate of apples") is None
    with pytest.raises(ValueError):
        motions.bearing_from_words("x", "sulky")
    sheet = tmp_path / "m.json"
    sheet.write_text(json.dumps({"motions": {"Idle_Loop": {}, "Walk_Loop": {}}}))
    b = motions.add_bearing(sheet, "warm")
    s = json.loads(sheet.read_text())
    assert s["bearing"]["over"] == ["Idle_Loop"] and b["name"] == "warm" and "Walk_Loop" in s["motions"]
