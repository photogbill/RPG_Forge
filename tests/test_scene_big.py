"""G3: scene_big end to end against the fake ComfyUI — climbs ≤ 2×, tile + canny ControlNets, merged at target."""
import json

from PIL import Image

from forge.engines import graph_ops as go
from forge.night3 import big
from test_paint import FakeComfy, ctx_with, greybox


def test_climb_sizes_never_more_than_max_step():
    assert big.climb_sizes((1920, 1080), (3840, 2160)) == [(3840, 2160)]
    s = big.climb_sizes((1408, 704), (6144, 3072))
    assert len(s) == 3 and s[-1] == (6144, 3072)
    prev = (1408, 704)
    for w, h in s:
        assert w / prev[0] <= 2.0 + 1e-6 and w % 8 == 0
        prev = (w, h)
    assert len(big.climb_sizes((1408, 704), (6144, 3072), 1.5)) == 4


def test_scene_big_from_source(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    Image.new("RGB", (1920, 1080), (90, 60, 30)).save(src_dir / "scene.png")
    (src_dir / "prov.json").write_text(json.dumps({"licences": [{"role": "checkpoint", "file": "sd_xl_base_1.0.safetensors"}]}))
    fake = FakeComfy()
    ctx = ctx_with(tmp_path, fake)
    out = tmp_path / "out"
    out.mkdir()
    job = {"id": "b1", "type": "scene_big", "name": "bigtest", "prompt": "a street", "target": [3840, 2160],
           "source": str(src_dir / "scene.png"), "tile": [1536, 1152], "checkpoint": "sd_xl_base_1.0.safetensors", "seed": 5}
    res = big.scene_big(job, ctx, out)
    assert res["tiles"] == 6 and res["climbs"] == 1
    assert Image.open(out / "scene.png").size == (3840, 2160)
    for f in ("upscaled.png", "seams.json", "seam_sheet.jpg", "contact.png", "prov.json"):
        assert (out / f).exists(), f
    tile_graphs = [g for g in fake.graphs if go.nodes_of(g, "KSampler")]
    assert len(tile_graphs) == 6
    g = tile_graphs[0]
    types = [n["inputs"]["type"] for n in g.values() if n["class_type"] == "SetUnionControlNetType"]
    assert types == ["tile"]                                    # no greybox → tile only
    ks = [n for n in g.values() if n["class_type"] == "KSampler"]
    assert len(ks) == 1 and ks[0]["inputs"]["denoise"] == 0.3 and ks[0]["inputs"]["seed"] == 5
    assert all(n["inputs"]["seed"] == 5 for t in tile_graphs for n in t.values() if n["class_type"] == "KSampler")
    prov = json.loads((out / "prov.json").read_text(encoding="utf-8"))
    roles = {l["role"] for l in prov["licences"]}
    assert {"checkpoint", "upscaler", "controlnet", "source_checkpoint"} <= roles
    assert json.loads((out / "seams.json").read_text())["worst"] == 0      # the fake paints every tile one colour


def test_scene_big_from_greybox_paints_small_then_climbs_with_canny(tmp_path):
    init = tmp_path / "grey.png"
    greybox(1536, 768).save(init)
    fake = FakeComfy()
    ctx = ctx_with(tmp_path, fake)
    out = tmp_path / "out"
    out.mkdir()
    job = {"id": "b2", "type": "scene_big", "name": "street", "prompt": "a street", "target": [3072, 1536],
           "init": str(init), "size": [1024, 512], "checkpoint": "sd_xl_base_1.0.safetensors", "seed": 9}
    res = big.scene_big(job, ctx, out)
    assert res["climbs"] == 2 and (out / "small.png").exists() and Image.open(out / "small.png").size == (1024, 512)
    assert Image.open(out / "scene.png").size == (3072, 1536)
    tg = [g for g in fake.graphs[1:] if go.nodes_of(g, "KSampler")]
    types = [n["inputs"]["type"] for n in tg[-1].values() if n["class_type"] == "SetUnionControlNetType"]
    assert types[0] == "tile" and types[1].startswith("canny")
