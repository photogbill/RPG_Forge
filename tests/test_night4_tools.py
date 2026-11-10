"""Night 4 F7 — make-tileable (CPU blend), and the filter_forge tileable flag's helper."""
import json

import numpy as np
import pytest
from PIL import Image

from forge import config as cfgmod, schema
from forge.jobs.common import Context
from forge.night4 import tileable as t


def _texture(seed=0, w=256, h=192):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    base = np.stack([xx / w * 200, yy / h * 180, (xx + yy) % 97 + 40], -1)          # gradients: never wrap
    return Image.fromarray(np.clip(base + rng.normal(0, 6, base.shape), 0, 255).astype(np.uint8))


def test_blend_makes_it_tile_and_reports_before_after(tmp_path):
    img = _texture()
    assert t.worst(t.score(img)) > 3
    for mode in ("cut", "fade"):
        r = t.blend(img, 0.2, mode)
        assert r.size == img.size and t.worst(t.score(r)) < 1.5, mode


def test_already_tiling_is_left_alone():
    a = np.asarray(_texture())
    per = np.concatenate([a[:, :128], a[:, :128][:, ::-1]], axis=1)                  # mirrored → wraps in x
    per = np.concatenate([per[:96], per[:96][::-1]], axis=0)
    res, info = t.make(Image.fromarray(per), "blend", 0.2)
    assert "already tiles" in info["skipped"] and res is not None


def test_handler_writes_outputs_and_refuses_inpaint_without_gpu(tmp_path):
    src = tmp_path / "tex.png"; _texture().save(src)
    ctx = Context(cfg=cfgmod.load(), root=tmp_path)
    out = tmp_path / "o"; out.mkdir()
    job = schema.with_defaults({"id": "t1", "type": "tileable", "input": str(src), "band": 0.2})
    r = t.run(job, ctx, out)
    assert r["heal"] == "blend" and (out / "tile.png").exists() and (out / "compare.png").exists()
    assert t.worst(r["after"]) < 1.5 < t.worst(r["before"])
    assert Image.open(out / "tiled_2x2.png").size == (512, 384)
    out2 = tmp_path / "o2"; out2.mkdir()
    with pytest.raises(t.TileableError, match="GPU"):
        t.run({**job, "id": "t2", "heal": "inpaint"}, ctx, out2)


def test_tile_channels_keeps_channels_in_register(tmp_path):
    a, n = tmp_path / "tex_final.png", tmp_path / "tex_normal.png"
    _texture(1).save(a); _texture(1).save(n)
    rep = t.tile_channels({"final": a, "normal": n}, 0.2)
    fa = np.asarray(Image.open(tmp_path / "tex_final_tile.png"))
    fn = np.asarray(Image.open(tmp_path / "tex_normal_tile.png"))
    assert np.array_equal(fa, fn) and rep["final"]["after"]                            # same geometry for every channel


# ------------------------------------------------------------------ F4 icon_batch, F6 photo_plate (fake ComfyUI)
def test_icon_batch_one_seed_per_category(tmp_path):
    from forge.night4 import icons
    from test_paint import FakeComfy
    fake = FakeComfy()
    ctx = Context(cfg=cfgmod.load(), comfy=fake, palettes_dir=cfgmod.ROOT / "palettes", root=cfgmod.ROOT)
    job = schema.with_defaults({"id": "ib", "type": "icon_batch", "prompt": "an icon, {name}: {description}",
        "items": [{"id": "coolant", "name": "Coolant", "description": "Cools a core.", "category": "repair"},
                  {"id": "wrench", "name": "Wrench", "description": "", "category": "repair"},
                  {"id": "pistol", "name": "Pistol", "description": "A sidearm.", "category": "weapons"}],
        "checkpoint": "ArtUniverseSDXL_v8.safetensors"})
    r = icons.run(job, ctx, tmp_path)
    assert r["icons"] == 3 and set(r["seeds"]) == {"repair", "weapons"}
    assert Image.open(tmp_path / "icons" / "coolant.png").size == (256, 256)
    assert Image.open(tmp_path / "icons@2x" / "coolant.png").size == (512, 512)
    assert (tmp_path / "contact_repair.png").exists() and (tmp_path / "contact_weapons.png").exists()
    seeds = [n["inputs"]["seed"] for g in fake.graphs for n in g.values() if n["class_type"] == "KSampler"]
    assert seeds[0] == seeds[1] == r["seeds"]["repair"] != seeds[2]
    texts = [n["inputs"]["text"] for g in fake.graphs for n in g.values() if n["class_type"] == "CLIPTextEncode"]
    assert any("Coolant: Cools a core" in t for t in texts) and any("Wrench" in t and "Wrench:" not in t.split("Wrench")[1][:1] for t in texts)
    with pytest.raises(ValueError, match="blocks"):
        icons.run({**job, "prompt": "{{icon.house}}, {name}"}, ctx, tmp_path / "x")


def test_photo_plate_people_guard_and_kit(tmp_path):
    from forge.night4 import photo
    from test_scene import SceneComfy, FAKE_INFO, DEPTH_INFO
    games = tmp_path / "games" / "tg"; games.mkdir(parents=True)
    cfg = {**cfgmod.load(), "allow_external_paths": True, "paths": {**cfgmod.load()["paths"], "games": str(tmp_path / "games")}}
    ok, who = tmp_path / "smoke.jpg", tmp_path / "soldier.jpg"
    Image.new("RGB", (400, 300), (120, 90, 60)).save(ok); Image.new("RGB", (400, 300), (60, 90, 120)).save(who)
    fake = SceneComfy(info={**FAKE_INFO, **DEPTH_INFO})
    ctx = Context(cfg=cfg, comfy=fake, palettes_dir=cfgmod.ROOT / "palettes", root=cfgmod.ROOT)
    job = schema.with_defaults({"id": "pp", "type": "photo_plate", "photo": str(ok), "prompt": "a tent camp",
                                "game": "tg", "target": [192, 108], "checkpoint": "ArtUniverseSDXL_v8.safetensors"})
    with pytest.raises(photo.PeopleGuard, match="refs.local.json"):
        photo.run(job, ctx, tmp_path / "o0")
    (games / "refs.local.json").write_text(json.dumps({"frames": {str(ok): {"people": "none", "note": "smoke front"},
                                                                  str(who): {"people": "a soldier"}}}))
    with pytest.raises(photo.PeopleGuard, match="only frames with no one"):
        photo.run({**job, "photo": str(who)}, ctx, tmp_path / "o1")
    out = tmp_path / "o2"; out.mkdir()
    r = photo.run(job, ctx, out)
    for f in ("scene.png", "scene_n.png", "scene_depth.png", "scene_back.png"):
        assert (out / f).exists(), f
    prov = json.loads((out / "prov.json").read_text())
    assert prov["source_photo"]["path"] == str(ok) and prov["source_photo"]["copied_into_repo"] is False
    assert prov["op"] == "photo_plate" and r["people"] == "none"
