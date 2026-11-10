"""N1–N3: depth ops, normals from depth, layer cuts and hole filling, the depth graph, and scene_kit end to end
against a fake ComfyUI (no GPU)."""
import io, json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge import config as cfgmod, schema
from forge.engines import graph_ops as go
from forge.ops import depth as dp, layers as ly

from test_paint import FakeComfy, FAKE_INFO


def scene(w=240, h=135):
    """A painting and its depth: a far wall (top), a mid floor, a near box (bottom left), a bright poster on the wall."""
    yy, xx = np.mgrid[0:h, 0:w]
    d = (0.15 + 0.35 * yy / h).astype(np.float32)
    d[int(h * 0.6):, int(w * 0.1):int(w * 0.35)] = 0.92
    rgb = np.dstack([90 + 0 * xx, 110 + 60 * yy / h, 140 + 0 * xx]).astype(np.float32)
    rgb[10:40, 150:200] = 250                                   # the poster: bright but flat
    rgb[int(h * 0.6):, int(w * 0.1):int(w * 0.35)] = (160, 80, 40)
    return Image.fromarray(rgb.clip(0, 255).astype(np.uint8)), d


# ------------------------------------------------------------------ depth ops
def test_depth16_roundtrip_and_resample(tmp_path):
    _, d = scene()
    dp.depth_image16(d).save(tmp_path / "d.png")
    im = Image.open(tmp_path / "d.png")
    assert im.mode.startswith("I")
    assert np.abs(dp.load_depth(tmp_path / "d.png") - d).max() < 1e-4
    eight = Image.fromarray((d * 255).astype(np.uint8), "L")
    up = dp.load_depth(eight, (480, 270))
    assert up.shape == (270, 480) and 0.0 <= up.min() and up.max() <= 1.0


def test_depth_normals_ignore_a_bright_poster_that_luminance_normals_see():
    img, d = scene()
    nd = dp.decode_normals(dp.normal_map(img, source="depth", depth=d))
    nl = dp.decode_normals(dp.normal_map(img, source="luminance"))
    # poster edge, columns 148..152 at row 25: luminance sees a bump, depth sees a flat wall
    assert np.abs(nl[25, 148:152, 0]).max() > 0.3
    assert np.abs(nd[25, 148:152, 0]).max() < 0.05
    # the near box's top edge tilts the depth normal (light can rake across it)
    assert np.abs(nd[int(135 * 0.6) - 1:int(135 * 0.6) + 1, 40, 1]).max() > 0.2


def test_detail_blend_and_relight_shapes():
    img, d = scene()
    base = dp.normal_map(img, source="depth", depth=d)
    mixed = dp.normal_map(img, source="depth", depth=d, detail=0.5)
    assert mixed.size == img.size and np.asarray(mixed).tolist() != np.asarray(base).tolist()
    lit = dp.relight(img, base)
    assert lit.size == img.size and lit.mode == "RGB"
    with pytest.raises(ValueError):
        dp.normal_map(img, source="depth")
    with pytest.raises(ValueError):
        dp.normal_map(img, source="depth", depth=d[:10])


# ------------------------------------------------------------------ layers
def test_auto_cuts_find_the_valleys():
    d = np.concatenate([np.full(1000, 0.1), np.full(1000, 0.5), np.full(1000, 0.9)]).reshape(30, 100).astype(np.float32)
    c1, c2 = ly.auto_cuts(d)
    assert 0.1 < c1 <= 0.5 and 0.5 < c2 <= 0.9


def test_push_pull_fills_holes_with_neighbour_colours():
    rgb = np.zeros((64, 64, 3), np.float32)
    rgb[:, :32] = (200, 0, 0)
    rgb[:, 32:] = (0, 0, 200)
    known = np.ones((64, 64), bool)
    known[20:44, 20:44] = False
    rgb2 = rgb.copy()
    rgb2[~known] = 0
    f = ly.push_pull_fill(rgb2, known)
    assert np.array_equal(f[known], rgb2[known])
    assert f[32, 22, 0] > 100 and f[32, 42, 2] > 100          # left half filled reddish, right half bluish


def test_split_layers_no_holes_when_sliding():
    img, d = scene()
    L = ly.split_layers(img, d, cuts=[0.3, 0.8], feather=2, overscan=48)
    assert L["back"].size == (240 + 96, 135) and L["back"].mode == "RGB"
    assert L["over"].mode == "RGBA" and L["over"].size == img.size
    a = np.asarray(L["over"])[..., 3]
    assert a[120, 50] == 255 and a[10, 10] == 0                # the box is in the over plane, the wall is not
    for f in ly.slide_frames(img, L, 40):
        assert (np.asarray(f) == [255, 0, 255]).all(-1).sum() == 0
    info = L["info"]
    assert info["cuts"] == [0.3, 0.8] and info["parallax"]["over"] == 1.06 and info["overscan_px"] == 48


def test_tiny_over_plane_is_dropped_with_a_note():
    img, d = scene()
    L = ly.split_layers(img, d, cuts=[0.3, 0.99])
    assert L["over"] is None and any("over plane dropped" in n for n in L["info"]["notes"])
    with pytest.raises(ValueError):
        ly.split_layers(img, d, cuts=[0.0, 0.5])
    with pytest.raises(ValueError):
        ly.split_layers(img, d, cuts=[0.5])


# ------------------------------------------------------------------ depth graph (Small weights only)
DEPTH_INFO = {"DepthAnythingV2Preprocessor": {"input": {
    "required": {"image": ["IMAGE"]},
    "optional": {"ckpt_name": [["depth_anything_v2_vitg.pth", "depth_anything_v2_vitl.pth", "depth_anything_v2_vitb.pth",
                                "depth_anything_v2_vits.pth"], {"default": "depth_anything_v2_vitl.pth"}],
                 "resolution": ["INT", {"default": 512, "min": 64, "max": 16384, "step": 64}]}}}}


def test_depth_graph_always_names_small_weights():
    from forge.jobs import scene as sc
    g = sc.depth_graph(DEPTH_INFO, "forge/x.png", 1024)
    n = g["2"]
    assert n["class_type"] == "DepthAnythingV2Preprocessor"
    assert n["inputs"]["ckpt_name"] == "depth_anything_v2_vits.pth" and n["inputs"]["resolution"] == 1024
    assert g["3"]["inputs"]["images"] == ["2", 0]
    with pytest.raises(sc.SceneError, match="install_comfy_aux"):
        sc.depth_graph({}, "forge/x.png")
    no_small = json.loads(json.dumps(DEPTH_INFO))
    no_small["DepthAnythingV2Preprocessor"]["input"]["optional"]["ckpt_name"][0].remove("depth_anything_v2_vits.pth")
    with pytest.raises(go.GraphError):
        sc.depth_graph(no_small, "forge/x.png")


class SceneComfy(FakeComfy):
    """FakeComfy that answers the depth graph with a gradient (white at the bottom = near)."""
    def run_by_node(self, g):
        if any(n["class_type"] == "DepthAnythingV2Preprocessor" for n in g.values()):
            self.graphs.append(g)
            yy = np.linspace(0, 255, 96).astype(np.uint8)[:, None].repeat(128, 1)
            b = io.BytesIO()
            Image.fromarray(yy, "L").convert("RGB").save(b, "PNG")
            return {"3": [b.getvalue()]}
        return super().run_by_node(g)


def ctx_with(fake):
    from forge.jobs.common import Context
    return Context(cfg=cfgmod.load(), comfy=fake, palettes_dir=cfgmod.ROOT / "palettes", root=cfgmod.ROOT)


def test_depth_map_and_normal_map_handlers(tmp_path):
    from forge.jobs import scene as sc
    img, _ = scene()
    img.save(tmp_path / "room.png")
    fake = SceneComfy(info={**FAKE_INFO, **DEPTH_INFO})
    ctx = ctx_with(fake)
    out = tmp_path / "o1"; out.mkdir()
    res = sc.depth_map(schema.with_defaults({"id": "d1", "type": "depth_map", "inputs": [str(tmp_path / "room.png")]}), ctx, out)
    dfile = out / "room_depth.png"
    assert res["outputs"] == ["room_depth.png"] and Image.open(dfile).size == img.size and Image.open(dfile).mode.startswith("I")
    prov = json.loads((out / "prov.json").read_text(encoding="utf-8"))
    assert prov["depth_model"] == "depth_anything_v2_vits.pth" and prov["depth_commercial_ok"] is True
    out2 = tmp_path / "o2"; out2.mkdir()
    job = schema.with_defaults({"id": "n1", "type": "normal_map", "inputs": [str(tmp_path / "room.png")], "source": "depth",
                                "depth": [str(dfile)], "detail": 0.3})
    assert schema.validate(job) == []
    sc.normal_map(job, ctx, out2)
    assert (out2 / "room_n.png").exists() and (out2 / "room_lit.png").exists() and (out2 / "contact.png").exists()
    assert schema.validate({"type": "normal_map", "inputs": ["a.png"], "source": "depth"})       # depth missing → a problem


def test_scene_layers_handler(tmp_path):
    from forge.jobs import scene as sc
    img, d = scene()
    img.save(tmp_path / "street.png")
    dp.depth_image16(d).save(tmp_path / "street_depth.png")
    out = tmp_path / "o"; out.mkdir()
    job = schema.with_defaults({"id": "l1", "type": "scene_layers", "inputs": [str(tmp_path / "street.png")],
                                "depth": [str(tmp_path / "street_depth.png")]})
    res = sc.scene_layers(job, ctx_with(None), out)
    assert set(res["outputs"]) == {"street_back.png", "street_over.png"}
    assert (out / "street_slide.png").exists() and (out / "street_mid_alpha.png").exists()
    info = json.loads((out / "layers.json").read_text(encoding="utf-8"))
    assert info["cuts_mode"] == "auto" and len(info["cuts"]) == 2


def test_kit_steps_are_paint_then_depth_normals_glow_layers():
    from forge.jobs import scene as sc
    steps = sc.kit_steps({"prompt": "p", "checkpoint": "sd_xl_base_1.0.safetensors", "normals": {"detail": 0.5}})
    assert [s["type"] for s in steps] == ["scene_paint", "depth_map", "normal_map", "emissive_mask", "scene_layers"]
    assert steps[2]["source"] == "depth" and steps[2]["detail"] == 0.5 and steps[2]["depth"] == ["$steps[2].outputs[0]"]
    assert sc.kit_steps({"prompt": "p", "init": "g.png", "denoise": 0.5})[0]["type"] == "repaint"
    with pytest.raises(sc.SceneError):
        sc.kit_steps({"prompt": "p", "init": "g.png", "denoise": [0.4, 0.5]})


def test_scene_kit_end_to_end_six_files(tmp_path):
    from forge.jobs import scene as sc
    fake = SceneComfy(info={**FAKE_INFO, **DEPTH_INFO})
    ctx = ctx_with(fake)
    job = schema.with_defaults({"id": "k1", "type": "scene_kit", "name": "bills_house", "prompt": "a living room with a server rack",
                                "checkpoint": "sd_xl_base_1.0.safetensors", "target": [480, 270], "refine": False,
                                "layers": {"cuts": [0.3, 0.7]}})
    assert schema.validate(job) == []
    res = sc.scene_kit(job, ctx, tmp_path)
    names = ["scene.png", "scene_n.png", "scene_e.png", "scene_back.png", "scene_over.png", "scene_depth.png"]
    assert res["outputs"] == names and res["missing_slots"] == []
    for n in names:
        assert (tmp_path / n).exists(), n
    w, h = Image.open(tmp_path / "scene.png").size
    assert (w, h) == (480, 270)
    assert all(Image.open(tmp_path / n).size == (w, h) for n in names if n != "scene_back.png")
    assert Image.open(tmp_path / "scene_back.png").size == (w + 96, h)
    prov = json.loads((tmp_path / "prov.json").read_text(encoding="utf-8"))
    roles = {l["role"] for l in prov["licences"]}
    assert {"checkpoint", "upscaler", "depth_model"} <= roles and prov["set"] is True
    assert prov["commercial_ok"] is True and (tmp_path / "contact.png").exists() and (tmp_path / "layers.json").exists()


def test_flatten_stops_a_receding_floor_reading_as_a_slope():
    h, w = 270, 480
    yy = np.mgrid[0:h, 0:w][0] / h
    d = (0.1 + 0.8 * yy).astype(np.float32)
    d[150:220, 100:200] += 0.1
    raw = dp.decode_normals(dp.normals_from_depth(d, flatten=0.0))
    flat = dp.decode_normals(dp.normals_from_depth(d, flatten=0.85))
    assert flat[40:120, 300:450, 2].mean() > 0.99 > raw[40:120, 300:450, 2].mean()
    assert np.abs(flat[148:152, 120:180, 1]).max() > 0.5            # the box's top edge still catches the light
