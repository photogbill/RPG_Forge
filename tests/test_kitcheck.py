"""G5: kit check — a good kit passes, each broken thing fails (or warns) for the right reason; map points drawn."""
import json, shutil

import numpy as np
from PIL import Image

from forge import config as cfgmod, kitcheck as kc
from forge.ops import depth as dp


def good_kit(d, W=480, H=270):
    d.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    paint = Image.fromarray(rng.integers(40, 200, (H, W, 3), dtype=np.uint8))
    paint.save(d / "scene.png")
    y = np.linspace(0, 1, H)[:, None].repeat(W, 1)
    depth = 0.15 + 0.8 * y + 0.03 * np.sin(np.arange(W) / 17.0)[None, :]
    dp.depth_image16(np.clip(depth, 0, 1)).save(d / "scene_depth.png")
    dp.normal_map(paint, source="depth", depth=np.clip(depth, 0, 1), detail=0.3).save(d / "scene_n.png")
    e = np.zeros((H, W, 3), np.uint8); e[10:30, 10:60] = (255, 200, 80)
    Image.fromarray(e).save(d / "scene_e.png")
    Image.new("RGBA", (W + 96, H), (90, 90, 90, 255)).save(d / "scene_back.png")
    o = np.zeros((H, W, 4), np.uint8); o[200:, :100] = (50, 50, 50, 255)
    Image.fromarray(o, "RGBA").save(d / "scene_over.png")
    return d


def status(rep, name):
    return next(l["status"] for l in rep["lines"] if l["check"] == name)


def test_good_kit_passes(tmp_path):
    rep = kc.check(cfgmod.load(), good_kit(tmp_path / "k"))
    assert rep["verdict"] == "pass", [l for l in rep["lines"] if l["status"] != "pass"]
    assert (tmp_path / "k" / "check.png").exists() and json.loads((tmp_path / "k" / "check.json").read_text())["verdict"] == "pass"


def test_broken_kit_fails_for_the_right_reasons(tmp_path):
    k = good_kit(tmp_path / "k")
    (k / "scene_e.png").unlink()                                                   # a slot missing
    Image.open(k / "scene_n.png").resize((240, 135)).save(k / "scene_n.png")      # companion at the wrong size
    d = np.asarray(Image.open(k / "scene_depth.png")).astype(np.uint16)
    Image.fromarray((65535 - d).astype(np.uint16)).save(k / "scene_depth.png")    # floor read as sky: inverted
    b = np.asarray(Image.open(k / "scene_back.png")).copy(); b[:50, :50, 3] = 0
    Image.fromarray(b, "RGBA").save(k / "scene_back.png")                         # holes in the back plane
    rep = kc.check(cfgmod.load(), k)
    assert rep["verdict"] == "fail"
    assert status(rep, "slots.present") == "fail" and status(rep, "slots.size._n") == "fail"
    assert status(rep, "depth.ground") == "fail" and status(rep, "layers.back_holes") == "fail"


def test_individual_checks():
    flat = Image.new("RGB", (64, 64), (128, 128, 255))
    r = {l["check"]: l["status"] for l in kc.check_normals(flat)}
    assert r["normals.facing"] == "pass" and r["normals.flat"] == "warn"
    terr = np.zeros((64, 256, 3), np.uint8)
    terr[..., 0] = (np.arange(256) // 16 * 16)[None, :]                            # terraces every 16 levels
    terr[..., 1] = terr[..., 0]; terr[..., 2] = 220
    assert {l["check"]: l["status"] for l in kc.check_normals(Image.fromarray(terr))}["normals.banding"] == "fail"
    glow = Image.new("RGB", (100, 100), (255, 255, 255))
    assert kc.check_emissive(glow)[0]["status"] == "warn"
    flatd = np.full((50, 80), 0.5)
    assert {l["check"]: l["status"] for l in kc.check_depth(flatd)[0]}["depth.range"] == "fail"
    over = Image.new("RGBA", (10, 10), (0, 0, 0, 255))
    assert kc.check_layers(None, over)[0]["status"] == "warn"


def test_map_points_and_footing(tmp_path):
    k = good_kit(tmp_path / "k")
    m = {"tile_size": 32, "rows": ["#####", "#...#", "#.S.#", "#..D#", "#####"],
         "walk": [[[32, 32], [128, 32], [128, 128], [32, 128]]], "spawns": [{"x": 2, "y": 0, "unit": "tile"}]}
    pts = kc.map_points(m, kc.map_scale(m, (480, 270)))
    assert len(pts["rings"]) == 1 and len(pts["doors"]) == 1 and len(pts["spawns"]) == 2
    rep = kc.check(cfgmod.load(), k, "testmap", map_data=m)
    checks = {l["check"]: l for l in rep["lines"]}
    assert "map.read" in checks and checks["map.read"]["status"] == "pass"
    assert any(c.startswith("map.door") for c in checks) and any(c.startswith("map.spawn") for c in checks)
