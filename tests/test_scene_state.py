"""G4: inpaint graph, state mask (share, refusal), the bit-identical guarantee, inpaint/scene_state end to end."""
import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from forge import schema
from forge.engines import graph_ops as go
from forge.night3 import inpaint as ip
from forge.ops import state_mask as smk
from test_paint import FakeComfy, FAKE_INFO, ctx_with as paint_ctx
from test_scene import SceneComfy, DEPTH_INFO, ctx_with


def grey(w=480, h=270, rack=0):
    im = Image.new("RGB", (w, h), (120, 110, 100))
    d = ImageDraw.Draw(im)
    d.rectangle([0, h * 2 // 3, w, h], fill=(80, 70, 60))
    d.rectangle([40, 60, 120, 180], fill=(60, 60, 70))                 # a door
    if rack:
        d.rectangle([300, 80, 300 + rack, 190], fill=(30, 40, 50))      # the server rack grows
    return im


def test_inpaint_graph_noise_mask_and_encode_for_inpaint():
    ctx = paint_ctx(None, FakeComfy())
    job = {"prompt": "a server rack", "checkpoint": "sd_xl_base_1.0.safetensors"}
    g, _ = ip.inpaint_graph(ctx, job, "forge/c.png", "forge/m.png", 1024, 576, 7, denoise=0.85)
    kinds = go.required_nodes(g)
    assert {"LoadImageMask", "SetLatentNoiseMask", "VAEEncode"} <= kinds and not go.nodes_of(g, *go.EMPTY_LATENTS)
    ks = g[go.main_sampler(g)]["inputs"]
    assert ks["denoise"] == 0.85 and g[ks["latent_image"][0]]["class_type"] == "SetLatentNoiseMask"
    assert g[go.nodes_of(g, "LoadImageMask")[0]]["inputs"]["channel"] == "red"
    g2, _ = ip.inpaint_graph(ctx, job, "a", "b", 512, 512, 1, method="encode_for_inpaint", grow=6)
    assert go.nodes_of(g2, "VAEEncodeForInpaint") and g2[go.main_sampler(g2)]["inputs"]["denoise"] == 1.0
    g3, _ = ip.inpaint_graph(ctx, job, "a", "b", 512, 512, 1, edge_name="e", controlnet="cn.safetensors")
    assert go.nodes_of(g3, "ControlNetApplyAdvanced")


def test_state_mask_share_grow_and_refusal():
    mask, binary, share, rep = smk.state_mask(grey(), grey(rack=60), grow=10, feather=4)
    assert 0.03 < rep["changed_share"] < 0.08 and share > rep["changed_share"]
    a = np.asarray(mask)
    assert a[135, 330] == 255 and a[5, 5] == 0 and a[120, 80] == 0          # rack in, far corner and door out
    with pytest.raises(smk.StateTooBig, match="new painting"):
        smk.state_mask(grey(), Image.new("RGB", (480, 270), (0, 0, 0)))
    with pytest.raises(ValueError, match="identical"):
        smk.state_mask(grey(), grey())
    with pytest.raises(ValueError, match="different sizes"):
        smk.changed(grey(), grey(200, 100))


def test_composite_is_bit_identical_outside_the_mask():
    rng = np.random.default_rng(3)
    base = Image.fromarray(rng.integers(0, 255, (100, 160, 3), dtype=np.uint8))
    painted = Image.new("RGB", (160, 100), (255, 0, 0))
    m = Image.new("L", (160, 100), 0)
    ImageDraw.Draw(m).rectangle([40, 20, 100, 70], fill=255)
    m = smk.grow_feather(m, 6, 4)
    out = np.asarray(smk.composite(base, painted, m))
    outside = np.asarray(m) == 0
    assert np.array_equal(out[outside], np.asarray(base)[outside])
    assert (out[45, 70] == [255, 0, 0]).all()


def test_inpaint_and_scene_state_end_to_end_with_kit(tmp_path):
    from forge.jobs import scene as sc
    fake = SceneComfy(info={**FAKE_INFO, **DEPTH_INFO})
    ctx = ctx_with(fake)
    kit = tmp_path / "kit"; kit.mkdir()
    sc.scene_kit(schema.with_defaults({"id": "k1", "type": "scene_kit", "name": "bills_house", "prompt": "a room",
                                       "checkpoint": "sd_xl_base_1.0.safetensors", "target": [480, 270], "refine": False,
                                       "layers": {"cuts": [0.3, 0.7]}}), ctx, kit)
    rng = np.random.default_rng(1)      # the fake paints one flat colour; give the base texture so a change shows
    Image.fromarray(rng.integers(0, 255, (270, 480, 3), dtype=np.uint8)).save(kit / "scene.png")
    grey().save(tmp_path / "gb.png")
    grey(rack=60).save(tmp_path / "gs.png")
    out = tmp_path / "state"; out.mkdir()
    job = dict(ip.STATE_SPEC["optional"], **{"id": "s1", "type": "scene_state", "name": "peace_b", "base": str(kit),
                                "greybox_base": str(tmp_path / "gb.png"), "greybox_state": str(tmp_path / "gs.png"),
                                "prompt": "a taller server rack", "checkpoint": "sd_xl_base_1.0.safetensors", "seed": 3})
    res = ip.scene_state(job, ctx, out)
    assert res["outside_mask_max_diff"] == 0
    base = np.asarray(Image.open(kit / "scene.png").convert("RGB"))
    st = np.asarray(Image.open(out / "scene.png").convert("RGB"))
    m = np.asarray(Image.open(out / "mask.png")) == 0
    assert np.array_equal(st[m], base[m]) and not np.array_equal(st, base)
    for f in ("scene_n.png", "scene_e.png", "scene_depth.png", "scene_back.png", "scene_over.png"):
        assert (out / f).exists(), f
    n_old, n_new = np.asarray(Image.open(kit / "scene_n.png")), np.asarray(Image.open(out / "scene_n.png"))
    assert np.array_equal(n_new[m], n_old[m])                       # companions untouched outside the mask
    g = [x for x in fake.graphs if go.nodes_of(x, "SetLatentNoiseMask")][0]
    assert go.nodes_of(g, "ControlNetApplyAdvanced")                # canny from the state greybox
    prov = json.loads((out / "prov.json").read_text(encoding="utf-8"))
    assert prov["mask_report"]["changed_share"] > 0 and "depth_model" in {l["role"] for l in prov["licences"]}
    # plain inpaint with a hand-made rectangle
    Image.open(kit / "scene.png").save(tmp_path / "pic.png")
    mk = Image.new("L", (480, 270), 0)
    ImageDraw.Draw(mk).rectangle([200, 50, 320, 200], fill=255)
    mk.save(tmp_path / "rect.png")
    out2 = tmp_path / "inp"; out2.mkdir()
    r2 = ip.inpaint(dict(ip.INPAINT_SPEC["optional"], **{"id": "i1", "type": "inpaint", "init": str(tmp_path / "pic.png"),
                                          "mask": str(tmp_path / "rect.png"), "prompt": "a lamp",
                                          "checkpoint": "sd_xl_base_1.0.safetensors", "seed": 1}), ctx, out2)
    assert r2["outside_mask_max_diff"] == 0 and (out2 / "contact.png").exists()
