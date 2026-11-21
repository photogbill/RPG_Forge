"""BUILD 63 — the look, the forge's half: the stage compiler takes the look proof's five changes, each behind a switch a
place plan can set (real window openings with glass and curtains; a crown and a wainscot; a bevel scale; pictures left to
the engine; a dressing list) and a plan that sets none compiles as before; compile_place passes the switches through and
copies a place's dressing list beside the stage; the relief step writes a normal map beside every library picture (a
Filter Forge Normal render or a Material Maker normal wins, and the choice is recorded). The compiler runs against the
stand-in Blender, and for real when this machine's Python has Blender inside (bpy).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge.threed import place, relief
from forge.threed.env import RigEnv

REPO = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures" / "threed"
FAKE_BLENDER = [sys.executable, str(FIX / "fake_blender.py")]

try:
    import bpy  # noqa: F401
    HAVE_BPY = True
except Exception:  # noqa: BLE001
    HAVE_BPY = False


@pytest.fixture(autouse=True)
def _pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))


def room(**switches) -> dict:
    """A room the camera sees into: a north wall with a window and three pictures, a cut stub, a table, a kitchen lamp."""
    pl = {
        "id": "look_room", "name": "Look room", "size": [12, 10], "road": {"type": "street"},
        "ground": [{"mat": "plank", "rect": [1, 2, 10, 6]}],
        "solids": [{"id": "wall_n", "mat": "wallpaper_warm", "top": "cut", "rect": [1, 2, 10, 0.4], "h": 3.0,
                    "face": [{"mat": "picture", "x": 2.0, "w": 0.6, "z": 1.9, "h": 0.5},
                             {"mat": "picture", "x": 3.0, "w": 0.5, "z": 2.0, "h": 0.4},
                             {"mat": "window_night", "x": 6.0, "w": 1.6, "z": 1.0, "h": 1.4}]},
                   {"id": "stub_s", "mat": "cut", "rect": [1, 8, 10, 0.3], "h": 0.35},
                   {"id": "kitchen_table", "mat": "wood", "rect": [4, 4, 1.6, 0.9], "h": 0.75},
                   {"id": "kitchen_lamp", "mat": "glow_warm", "cyl": [4.8, 4.45, 0.2], "z": 2.2, "h": 0.25}],
        "things": [],
        "anchors": {"start": [5, 6]},
        "lighting": {"lights": [{"id": "kitchen_pendant", "at": [4.8, 4.45], "z": 2.3, "kind": "spot", "energy": 16}],
                     "zones": [{"rect": [1, 2, 10, 6.3]}]},
    }
    pl.update(switches)
    return pl


DRESSING = {"items": [{"kind": "mug", "at": [4.5, 4.3], "z": 0.75}, {"kind": "candlestick", "at": [5.0, 4.4], "z": 0.75, "lit": True},
                      {"kind": "book_row", "at": [9.0, 2.6], "z": 1.0, "w": 0.6},
                      {"kind": "cable", "pts": [[6, 3, 0.02], [7, 4, 0.02], [8, 4.5, 0.02]]}]}


def _env(tmp_path):
    return RigEnv(root=tmp_path, rig=tmp_path / "rig", port=9, command=[], out=tmp_path / "out")


# ------------------------------------------------------------------------------------------------ compile_place
def test_the_switches_and_the_dressing_pass_through_compile_place(tmp_path):
    p = tmp_path / "look_room.place.json"
    p.write_text(json.dumps(room(windows="open", trim=True, bevel=1.6, pictures="engine", dressing="look_room.dressing.json")), encoding="utf-8")
    (tmp_path / "look_room.dressing.json").write_text(json.dumps(DRESSING), encoding="utf-8")
    out = tmp_path / "out"
    rep = place.compile_place(None, "g1", p, out, env=_env(tmp_path), python=FAKE_BLENDER)
    assert rep["ok"], rep
    cp = json.loads((out / "look_room.compile_plan.json").read_text(encoding="utf-8"))
    assert cp["windows"] == "open" and cp["trim"] is True and cp["bevel"] == 1.6 and cp["pictures"] == "engine"
    assert Path(cp["dressing"]).name == "look_room.dressing.json" and Path(cp["dressing"]).is_file()
    copied = json.loads((out / "look_room.dressing.json").read_text(encoding="utf-8"))
    assert len(copied["items"]) == 4                                                   # the game reads it beside the stage
    assert any("Dressing: 4 small things" in ln for ln in rep["lines"]) and any("switches" in ln for ln in rep["lines"])
    plan_copy = json.loads((out / "look_room.place.json").read_text(encoding="utf-8"))
    assert plan_copy["pictures"] == "engine"                                            # the game hangs them


def test_a_plan_without_switches_compiles_as_before(tmp_path):
    p = tmp_path / "look_room.place.json"
    p.write_text(json.dumps(room()), encoding="utf-8")
    out = tmp_path / "out"
    rep = place.compile_place(None, "g1", p, out, env=_env(tmp_path), python=FAKE_BLENDER)
    assert rep["ok"], rep
    cp = json.loads((out / "look_room.compile_plan.json").read_text(encoding="utf-8"))
    assert not any(k in cp for k in ("windows", "trim", "bevel", "pictures", "dressing"))
    assert not (out / "look_room.dressing.json").exists() and "dressing" not in rep


def test_a_dressing_list_is_checked_in_words():
    assert place.check_dressing(DRESSING) == []
    bad = {"items": [{"kind": "lava_lamp", "at": [1, 1]}, {"kind": "mug"}, {"kind": "cable", "pts": [[0, 0, 0]]},
                     {"kind": "box", "at": [1, 1], "w": 1}]}
    probs = place.check_dressing(bad)
    assert len(probs) == 4 and any("lava_lamp" in p for p in probs) and any("two or more" in p for p in probs)
    assert len(place.DRESSING_KINDS) == 20


@pytest.mark.skipif(not HAVE_BPY, reason="no Blender (bpy) in this Python")
def test_the_look_compiler_for_real_in_blender(tmp_path):
    from forge.threed.meshio import Glb
    names = {}
    for tag, sw in (("before", {}), ("look", {"windows": "open", "trim": True, "bevel": 1.6, "pictures": "engine",
                                              "dressing": "look_room.dressing.json"})):
        d = tmp_path / tag
        d.mkdir()
        p = d / "look_room.place.json"
        p.write_text(json.dumps(room(**sw)), encoding="utf-8")
        (d / "look_room.dressing.json").write_text(json.dumps(DRESSING), encoding="utf-8")
        rep = place.compile_place(None, "g1", p, d / "out", env=_env(tmp_path), python=sys.executable, minutes=3)
        assert rep["ok"], rep
        g = Glb.load(rep["model"])
        names[tag] = {m.get("name") for m in g.j.get("meshes", [])}
    before, look = names["before"], names["look"]
    assert "N_window_night" in before and "N_glass" not in before                        # as before: a lit card on the wall
    assert "N_glass" in look and "M_curtain" in look and "N_window_night" not in look    # LOOK 1: an opening, glass, curtains
    assert "M_wainscot" in look and "M_trim" in look                                     # LOOK 2: crown and boards
    assert "M_picture" in before and "M_picture" not in look                             # LOOK 4: left to the engine
    assert "M_ceramic" in look and "M_wax" in look and "N_glow_candle" in look           # LOOK 5: a mug, a lit candle
    assert "N_glow_pendant" in look                                                      # the kitchen lamp has its own word


# ------------------------------------------------------------------------------------------------ relief
def _stripes(path: Path, n: int = 64):
    a = np.full((n, n, 3), 140, np.uint8)
    a[:, ::8] = 30                                                                      # board gaps every 8 pixels
    Image.fromarray(a).save(path)


def test_relief_is_flat_for_a_flat_picture_and_follows_gaps(tmp_path):
    Image.fromarray(np.full((32, 32, 3), 128, np.uint8)).save(tmp_path / "flat.png")
    _stripes(tmp_path / "boards.png")
    r = relief.run([tmp_path])
    assert r["pictures"] == 2 and r["written"] == 2
    flat = np.asarray(Image.open(tmp_path / "flat_n.png")).astype(int)
    assert abs(flat[..., 0].mean() - 128) <= 1 and abs(flat[..., 1].mean() - 128) <= 1 and flat[..., 2].mean() > 250
    b = np.asarray(Image.open(tmp_path / "boards_n.png")).astype(int)
    assert b[..., 0].std() > 10 and b[..., 1].std() < 2                                   # vertical gaps tilt x, not y
    led = json.loads((tmp_path / "relief.json").read_text(encoding="utf-8"))
    assert set(led["pictures"]) == {"flat.png", "boards.png"}
    assert not (tmp_path / "flat_n_n.png").exists()                                       # relief is never read as a picture


def test_relief_slow_tone_changes_do_not_become_slopes(tmp_path):
    n = 256
    x = np.arange(n, dtype=np.float32)
    tone = 130 + 80 * np.sin(x * 2 * np.pi / n)                                            # one slow swell across a tiling picture
    pic = np.tile(tone[None, :, None], (n, 1, 3))
    Image.fromarray(pic.astype(np.uint8)).save(tmp_path / "stain.png")
    relief.run([tmp_path / "stain.png"])
    s = np.asarray(Image.open(tmp_path / "stain_n.png")).astype(int)
    assert np.abs(s[..., 0] - 128).mean() < 8                                              # the high-pass ignores it: no slope (8-bit steps only)
    _stripes(tmp_path / "boards.png", 256)
    relief.run([tmp_path / "boards.png"])
    b = np.asarray(Image.open(tmp_path / "boards_n.png")).astype(int)
    assert np.abs(b[..., 0] - 128).mean() > 3 * np.abs(s[..., 0] - 128).mean()            # while gaps do


def test_a_filter_forge_normal_wins_and_an_existing_relief_is_kept(tmp_path):
    _stripes(tmp_path / "planks.png")
    Image.fromarray(np.full((16, 16, 3), (200, 90, 240), np.uint8)).save(tmp_path / "planks_ffnormal.png")
    r = relief.run([tmp_path])
    row = next(x for x in r["rows"] if x["picture"] == "planks.png")
    assert row["source"] == "Filter Forge Normal channel" and row["written"]
    assert tuple(np.asarray(Image.open(tmp_path / "planks_n.png"))[0, 0]) == (200, 90, 240)
    _stripes(tmp_path / "gravel.png")
    Image.fromarray(np.full((8, 8, 3), 7, np.uint8)).save(tmp_path / "gravel_n.png")       # somebody's own relief
    r2 = relief.run([tmp_path / "gravel.png"])
    assert not r2["rows"][0]["written"] and tuple(np.asarray(Image.open(tmp_path / "gravel_n.png"))[0, 0]) == (7, 7, 7)
    r3 = relief.run([tmp_path / "gravel.png"], force=True)
    assert r3["rows"][0]["written"]
    led = json.loads((tmp_path / "relief.json").read_text(encoding="utf-8"))
    assert led["pictures"]["planks.png"]["from"] == "Filter Forge Normal channel"


def test_relief_from_the_command_line(tmp_path, capsys):
    from forge.cli_threed import cmd_3d
    _stripes(tmp_path / "boards.png")
    assert cmd_3d({}, ["relief", str(tmp_path)]) == 0
    assert (tmp_path / "boards_n.png").exists() and "1 written" in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------ 3D -> Places (the suite)
class _Adapter:
    """A stand-in game adapter: one stage map, three looks, and a still command that writes the picture it is asked for."""
    def __init__(self, root):
        self.root = root
        self.asked = []

    def stage_maps(self):
        return {"look_room": ["look_room_map"]}

    def looks(self):
        return ["peace_evening", "power_cut", "rain_night"]

    def play_command(self, place, era, time=None):
        self.asked.append(("play", place, era, time))
        return [sys.executable, "-c", "pass"]

    def still_command(self, map_id, era, look, out_png, at=None, quality="film"):
        self.asked.append(("still", map_id, look, quality))
        return [sys.executable, "-c", f"from PIL import Image; Image.new('RGB', (8, 8), (10, 20, 30)).save({out_png!r})"]


def test_places_offers_the_games_looks_and_takes_one_picture_a_look(tmp_path, monkeypatch):
    from forge.suite import places3d
    cfg = {"_root": str(tmp_path), "allow_external_paths": True,
           "paths": {"games": str(tmp_path / "games"), "out": str(tmp_path / "out"), "jobs": str(tmp_path / "jobs")}}
    (tmp_path / "games" / "g1" / "places").mkdir(parents=True)
    (tmp_path / "games" / "g1" / "places" / "look_room.place.json").write_text(json.dumps(room()), encoding="utf-8")
    adp = _Adapter(tmp_path)
    monkeypatch.setattr(places3d, "_adapter", lambda cfg, gid: adp)
    monkeypatch.setattr(places3d, "_sign", lambda *a, **k: None)
    monkeypatch.setattr(places3d.world, "status", lambda cfg, gid: {"items": []})
    v = places3d.view(cfg, "g1")
    assert v["looks"] == ["peace_evening", "power_cut", "rain_night"] and v["can_take"]
    assert v["places"][0]["look_pictures"] == []
    # open the game under a look (not only day or night)
    r = places3d.play(cfg, "g1", "look_room", "power_cut", "owner")
    assert r["ok"] and adp.asked[-1] == ("play", "look_room_map", "peace", "power_cut")
    # take the pictures: a person's call; one a look, at film, into the place's picture folder
    with pytest.raises(Exception):
        places3d.take_pictures(cfg, "g1", "look_room", None, wait=True)
    import subprocess
    r = places3d.take_pictures(cfg, "g1", "look_room", "owner", wait=True, run=subprocess.run)
    assert r["ok"], r
    stills = [a for a in adp.asked if a[0] == "still"]
    assert [s[2] for s in stills] == ["peace_evening", "power_cut", "rain_night"] and all(s[3] == "film" for s in stills)
    pics = places3d.look_pictures(cfg, "g1", "look_room")
    assert sorted(p["look"] for p in pics) == ["peace_evening", "power_cut", "rain_night"]
    v = places3d.view(cfg, "g1")
    assert len(v["places"][0]["look_pictures"]) == 3 and v["places"][0]["taking"]["left"] == 0
    js = (REPO / "forge" / "suite" / "threed.js").read_text(encoding="utf-8")
    assert "threed_places_pictures" in js and "Take the pictures" in js and "pl-look" in js


@pytest.mark.skipif(not HAVE_BPY, reason="no Blender (bpy) in this Python")
@pytest.mark.parametrize("switch,on,expect_on,expect_off", [
    ("windows", "open", {"N_glass", "M_curtain"}, {"N_window_night"}),
    ("trim", True, {"M_wainscot"}, set()),                 # a crown and boards under the warm paper (in wood: the paper is the warm one)
    ("pictures", "engine", set(), {"M_picture"}),
    ("dressing", "look_room.dressing.json", {"M_ceramic", "M_wax"}, set()),
])
def test_each_switch_on_and_off_for_real(tmp_path, switch, on, expect_on, expect_off):
    from forge.threed.meshio import Glb
    meshes = {}
    for tag, sw in (("off", {}), ("on", {switch: on})):
        d = tmp_path / tag
        d.mkdir()
        p = d / "look_room.place.json"
        p.write_text(json.dumps(room(**sw)), encoding="utf-8")
        if switch == "dressing" and tag == "on":
            (d / "look_room.dressing.json").write_text(json.dumps(DRESSING), encoding="utf-8")
        rep = place.compile_place(None, "g1", p, d / "out", env=_env(tmp_path), python=sys.executable, minutes=3)
        assert rep["ok"], rep
        meshes[tag] = {m.get("name") for m in Glb.load(rep["model"]).j.get("meshes", [])}
    assert expect_on <= meshes["on"] and not (expect_on & meshes["off"])
    assert expect_off <= meshes["off"] and not (expect_off & meshes["on"])


@pytest.mark.skipif(not HAVE_BPY, reason="no Blender (bpy) in this Python")
def test_the_bevel_switch_scales_every_bevel_for_real(tmp_path):
    from forge.threed.meshio import Glb
    faces = {}
    for tag, sw in (("off", {}), ("on", {"bevel": 1.6})):
        d = tmp_path / tag
        d.mkdir()
        p = d / "look_room.place.json"
        p.write_text(json.dumps(room(**sw)), encoding="utf-8")
        rep = place.compile_place(None, "g1", p, d / "out", env=_env(tmp_path), python=sys.executable, minutes=3)
        assert rep["ok"], rep
        faces[tag] = rep["faces"]
    assert faces["on"] > faces["off"]                      # wider bevels get a third segment: more faces where edges catch light
