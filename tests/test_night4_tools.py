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


def _set(tmp_path, w=256, h=192):
    """A set that does not tile: a colour picture (the lead), a 16-bit height of other content, a true normal map, and a
    picture whose every pixel says where it is (red = its column, green = its row) - so a healed copy says where each
    of its pixels came from."""
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:h, 0:w]
    paths = {k: tmp_path / f"tex_{k}.png" for k in ("final", "height", "normal", "where")}
    _texture(1, w, h).save(paths["final"])
    hgt = np.clip((np.hypot(xx - 40, yy - 150) * 180 + rng.normal(0, 300, (h, w))), 0, 65535).astype(np.uint16)
    Image.fromarray(hgt).save(paths["height"])
    nx, ny = np.sin(xx / 9.0) * 0.5, np.cos(yy / 7.0) * 0.5 + xx / w * 0.3
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0.05, 1))
    v = np.stack([nx, ny, nz], -1)
    v /= np.sqrt((v * v).sum(-1, keepdims=True))
    Image.fromarray(np.clip((v + 1) * 127.5 + 0.5, 0, 255).astype(np.uint8)).save(paths["normal"])
    Image.fromarray(np.stack([xx, yy, np.zeros_like(xx)], -1).astype(np.uint8)).save(paths["where"])
    return paths, hgt


def test_tile_channels_heals_a_whole_set_with_one_geometry(tmp_path):
    """Found 2026-11-19, fixed 2026-11-20: each channel used to be healed by itself (its own quietest column, its own
    cut, its own yes or no), so a set came back out of register. The old test gave both channels the same picture."""
    paths, hgt = _set(tmp_path)
    rep = t.tile_channels(paths, 0.2)
    assert all(r["lead"] == "final" and r["shift"] == rep["final"]["shift"] and r["file"].endswith("_tile.png") for r in rep.values())
    dx, dy = rep["final"]["shift"]
    assert t.worst(rep["final"]["after"]) < 1.5 < t.worst(rep["final"]["before"])
    F = np.asarray(Image.open(tmp_path / "tex_final_tile.png")).astype(int)
    Wh = np.asarray(Image.open(tmp_path / "tex_where_tile.png")).astype(int)
    Hh = Image.open(tmp_path / "tex_height_tile.png")
    assert Hh.mode.startswith("I") and np.asarray(Hh).max() > 255                    # the height is still 16-bit, not crushed to 8
    H = np.asarray(Hh).astype(int)
    f0 = np.asarray(Image.open(paths["final"])).astype(int)
    h, w = f0.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    sx, sy = Wh[..., 0], Wh[..., 1]                                                  # where this pixel says it came from
    whole = np.zeros((h, w), bool)                                                   # ... a whole source pixel, not a mix of two
    for ddx in (0, dx):
        for ddy in (0, dy):
            whole |= (sx == (xx - ddx) % w) & (sy == (yy - ddy) % h)
    assert whole.mean() > 0.75 and len({(int(a), int(b)) for a, b in zip((xx - sx)[whole] % w, (yy - sy)[whole] % h)}) >= 3
    # every channel took that same pixel from its own source: the set is in register
    assert np.abs(F[whole] - f0[sy[whole], sx[whole]]).max() <= 1
    assert np.abs(H[whole] - hgt.astype(int)[sy[whole], sx[whole]]).max() <= 2
    # a normal map is unit length again after the blend, in the mixed band too
    n = np.asarray(Image.open(tmp_path / "tex_normal_tile.png")).astype(float) / 127.5 - 1.0
    assert np.abs(np.sqrt((n * n).sum(-1)) - 1.0).max() < 0.03


def test_a_set_is_one_decision_and_a_channel_of_another_size_is_left(tmp_path):
    # the lead already tiles: nothing is healed, every channel is copied as it is (a channel is never healed alone)
    w, h = 128, 96
    yy, xx = np.mgrid[0:h, 0:w]
    lead = np.stack([np.sin(xx / w * 2 * np.pi) * 100 + 128, np.cos(yy / h * 2 * np.pi) * 100 + 128, np.full_like(xx, 90.0)], -1)
    a, b = tmp_path / "a_final.png", tmp_path / "a_height.png"
    Image.fromarray(lead.astype(np.uint8)).save(a)
    _texture(3, w, h).convert("L").save(b)                                           # this one does not tile by itself
    rep = t.tile_channels({"final": a, "height": b}, 0.2)
    assert "already tiles" in rep["final"]["skipped"] and "already tiles" in rep["height"]["skipped"]
    assert (tmp_path / "a_height_tile.png").read_bytes() == b.read_bytes() and (tmp_path / "a_final_tile.png").read_bytes() == a.read_bytes()
    # a channel of another size cannot share the geometry: it says so and is left; the rest are healed
    paths, _ = _set(tmp_path)
    small = tmp_path / "tex_ao.png"
    _texture(5, 64, 64).save(small)
    rep = t.tile_channels({**paths, "ao": small}, 0.2)
    assert "is not the lead's" in rep["ao"]["refused"] and not (tmp_path / "tex_ao_tile.png").exists() and rep["height"]["file"]
    assert t.tile_channels({}) == {}


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
