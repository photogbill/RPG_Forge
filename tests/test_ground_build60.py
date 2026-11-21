"""BUILD 60 — the ground outdoors, the forge's half: a place plan's `terrain` block (rules or a height picture) becomes a
16-bit height picture and its numbers beside the stage; the land is levelled under the plan's solids, a building's whole
roof and its roads; the cells are square (the terrain add-on's own rule); compile_place makes the land, draws no flat
ground slabs and carries the game's `terrain` block in the plan copy; `3d terrain` and `3d pack-terrain` on the command
line; a surface packed as the terrain's two pictures (colour + height, normal + roughness). numpy only."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge.threed import ground, place
from forge.threed.env import RigEnv

REPO = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures" / "threed"
FAKE_BLENDER = [sys.executable, str(FIX / "fake_blender.py")]


@pytest.fixture(autouse=True)
def _pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))


def land_plan(**terrain) -> dict:
    t = {"pixels": 129, "rules": [{"kind": "roll", "height_m": 1.5, "across_m": 50, "seed": 4}],
         "surfaces": [{"word": "grass"}, {"word": "gravel"}]}
    t.update(terrain)
    return {"id": "field_place", "name": "A field", "size": [200, 80], "road": {"type": "gravel"},
            "ground": [{"mat": "gravel", "rect": [0, 50, 200, 6]}, {"mat": "dirt", "rect": [10, 5, 60, 30]}],
            "solids": [{"id": "barn_n", "mat": "wood", "rect": [120, 20, 16, 0.3], "h": 4},
                       {"id": "barn_roof", "mat": "shingle", "roof": {"rect": [120, 20, 16, 12], "ridge": "x", "pitch": 35, "eave": 4}},
                       {"id": "silo", "mat": "concrete", "cyl": [160, 30, 4], "h": 18}],
            "things": [], "anchors": {"start": [5, 53]}, "terrain": t}


def _X(size, shape):
    sx = size[0] / (shape[1] - 1)
    return np.meshgrid(np.arange(shape[1]) * sx, np.arange(shape[0]) * sx)


def test_cells_are_square_and_the_long_side_has_the_pixels():
    assert ground.dims([200, 80], 129) == (129, 52)
    assert ground.dims([80, 200], 129) == (52, 129)
    assert ground.dims([64, 64], 65) == (65, 65)


def test_the_same_rules_give_the_same_land_and_each_rule_does_what_it_says():
    size = [200, 80]
    a = ground.heights_by_rule(size, 129, [{"kind": "roll", "height_m": 2.0, "across_m": 40, "seed": 9}])
    b = ground.heights_by_rule(size, 129, [{"kind": "roll", "height_m": 2.0, "across_m": 40, "seed": 9}])
    c = ground.heights_by_rule(size, 129, [{"kind": "roll", "height_m": 2.0, "across_m": 40, "seed": 10}])
    assert a.shape == (52, 129) and np.array_equal(a, b) and not np.array_equal(a, c)
    assert np.abs(a).max() <= 2.0 + 1e-9 and a.std() > 0.1
    X, Y = _X(size, a.shape)
    d = ground.heights_by_rule(size, 129, [{"kind": "draw", "line": [[0, 40], [200, 40]], "width_m": 20, "depth_m": 3}])
    assert d[np.abs(Y - 40) < 1].min() < -2.8 and np.abs(d[np.abs(Y - 40) > 12]).max() < 1e-9
    r = ground.heights_by_rule(size, 129, [{"kind": "rise", "line": [[100, 0], [100, 80]], "width_m": 30, "height_m": 5}])
    assert r[np.abs(X - 100) < 1].max() > 4.8 and r.min() >= 0
    s = ground.heights_by_rule(size, 129, [{"kind": "slope", "from": [0, 0], "to": [200, 0], "drop_m": 4}])
    assert abs(s[0, 0]) < 1e-9 and abs(s[0, -1] + 4) < 1e-6
    bs = ground.heights_by_rule(size, 129, [{"kind": "basin", "poly": [[20, 20], [60, 20], [60, 60], [20, 60]], "depth_m": 2, "edge_m": 5}])
    assert abs(bs[(X > 30) & (X < 50) & (Y > 30) & (Y < 50)].mean() + 2) < 1e-6 and np.abs(bs[X > 80]).max() < 1e-9


def test_the_land_is_levelled_under_solids_roofs_and_roads_and_eases_back():
    pl = land_plan(rules=[{"kind": "slope", "from": [0, 0], "to": [200, 0], "drop_m": 6}])
    fp = ground.footprints(pl, ["solids", "gravel"])
    assert len(fp) == 4                       # the barn wall, the barn's whole roof, the silo, the road
    h = ground.heights_by_rule(pl["size"], 129, pl["terrain"]["rules"])
    f = ground.flatten(h, pl["size"], fp, 6.0)
    X, Y = _X(pl["size"], f.shape)
    inside_barn = (X > 122) & (X < 134) & (Y > 22) & (Y < 30)
    assert np.abs(f[inside_barn]).max() < 1e-6, "the whole barn floor, not just under its walls"
    assert np.abs(f[(Y > 51) & (Y < 55)]).max() < 1e-6, "the road"
    assert np.abs(f[(X - 160) ** 2 + (Y - 30) ** 2 < 9]).max() < 1e-6, "the silo"
    far = (Y < 10) & (X > 40) & (X < 100)
    assert np.allclose(f[far], h[far]), "beyond the margin the land is as the rules made it"


def test_r16_round_trip_and_a_grey_picture_as_heights(tmp_path):
    h = np.linspace(-3, 7, 129 * 52).reshape(52, 129)
    p = tmp_path / "x.r16"
    ground.write_r16(h, p, -3, 7)
    assert p.stat().st_size == 129 * 52 * 2
    back = ground.read_r16(p, (129, 52), -3, 7)
    assert np.abs(back - h).max() <= 10 / 65535 + 1e-9
    im = Image.fromarray(np.tile(np.linspace(0, 255, 64).astype(np.uint8), (32, 1)))
    im.save(tmp_path / "grey.png")
    g = ground.read_height_picture(tmp_path / "grey.png", (64, 32), 10, 20)
    assert g.shape == (32, 64) and abs(g[0, 0] - 10) < 0.05 and abs(g[0, -1] - 20) < 0.05


def test_a_terrain_block_is_checked_in_words():
    assert ground.check({"id": "p"}) == []
    assert ground.check(land_plan()) == []
    bad = land_plan(rules=[{"kind": "volcano"}, {"kind": "draw", "line": [[0, 0]]}], pixels=9,
                    surfaces=[{"word": "w%d" % i} for i in range(9)])
    probs = ground.check(bad)
    assert len(probs) == 4 and any("volcano" in p for p in probs) and any("two or more" in p for p in probs)
    assert ground.check(land_plan(rules=[]))[0].endswith("neither rules nor a picture")


def test_make_writes_the_picture_and_the_games_block(tmp_path):
    b = ground.make(land_plan(), tmp_path)
    assert b["height"] == "field_place.terrain.r16" and b["pixels"] == [129, 52] and b["origin_m"] == [0.0, 0.0]
    assert abs(b["size_m"][0] - 200) < 1e-6 and abs(b["size_m"][1] - 79.6875) < 1e-6 and b["range_m"][0] < b["range_m"][1]
    j = json.loads((tmp_path / "field_place.terrain.json").read_text(encoding="utf-8"))
    assert j["height"] == b["height"] and j["surfaces"][1]["word"] == "gravel"
    h = ground.read_r16(tmp_path / b["height"], tuple(b["pixels"]), *b["range_m"])
    X, Y = _X([200, 80], h.shape)
    assert np.abs(h[(Y > 51) & (Y < 55)]).max() < 1e-3


def test_compile_place_makes_the_land_and_draws_no_flat_ground(tmp_path):
    p = tmp_path / "field_place.place.json"
    p.write_text(json.dumps(land_plan()), encoding="utf-8")
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig", port=9, command=[], out=tmp_path / "out")
    rep = place.compile_place(None, "g1", p, tmp_path / "stage", env=env, python=FAKE_BLENDER, minutes=3)
    assert rep["ok"], rep
    assert (tmp_path / "stage" / "field_place.terrain.r16").exists() and any(ln.startswith("Land: ") for ln in rep["lines"])
    cp = json.loads((tmp_path / "stage" / "field_place.compile_plan.json").read_text(encoding="utf-8"))
    assert cp["ground"] == [] and cp["terrain"] is True
    copy = json.loads((tmp_path / "stage" / "field_place.place.json").read_text(encoding="utf-8"))
    assert copy["terrain"]["height"] == "field_place.terrain.r16" and copy["terrain"]["pixels"] == [129, 52]
    assert copy["ground"][0]["mat"] == "gravel", "the plan copy keeps its ground words (footsteps, the terrain's paint)"
    bad = land_plan(rules=[{"kind": "volcano"}])
    p.write_text(json.dumps(bad), encoding="utf-8")
    rep2 = place.compile_place(None, "g1", p, tmp_path / "stage2", env=env, python=FAKE_BLENDER, minutes=3)
    assert not rep2["ok"] and "volcano" in rep2["error"]


def test_the_command_line_makes_land_and_packs_a_surface(tmp_path, capsys):
    from forge import cli_threed
    p = tmp_path / "field_place.place.json"
    p.write_text(json.dumps(land_plan()), encoding="utf-8")
    assert cli_threed.cmd_3d({}, ["terrain", str(p), "--out", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "field_place.terrain.r16").exists() and "terrain:" in capsys.readouterr().out
    rng = np.random.default_rng(3)
    Image.fromarray(rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)).save(tmp_path / "gravel.png")
    assert cli_threed.cmd_3d({}, ["pack-terrain", str(tmp_path / "gravel.png"), "--size", "64", "--roughness", "0.6"]) == 0
    a = np.asarray(Image.open(tmp_path / "gravel_t3d_albedo.png"))
    n = np.asarray(Image.open(tmp_path / "gravel_t3d_normal.png"))
    assert a.shape == (64, 64, 4) and n.shape == (64, 64, 4)
    assert a[..., 3].std() > 1, "colour with height in alpha"
    assert abs(int(n[..., 3].mean()) - 153) <= 1, "normal with roughness (0.6) in alpha"
    assert "normal from height" in capsys.readouterr().out
