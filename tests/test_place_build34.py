"""BUILD 34 — towns as 3D stages, the forge's half: a place plan compiles into the stage model (the plan-built solids,
modelled in Blender, no graphics card), the world-list entries for every generated thing the place needs, and the
placed-things list the game reads; a town's floor-plan layout is written out as a place plan. The compiler runs against
the stand-in Blender, and for real when this machine's Python has Blender inside (bpy).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from forge.layout import town
from forge.threed import place, world
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


def court() -> dict:
    """A small court: a house the story enters (plan-built: its walls and a table are solids), a neighbour's house as a
    shell, a closed shed, a car at the kerb, a tree."""
    return {
        "id": "test_court", "name": "Test Court", "size": [30, 20], "road": {"type": "dirt"},
        "ground": [{"mat": "dirt_road", "rect": [0, 0, 30, 3]}, {"mat": "grass", "rect": [0, 3, 30, 17]}],
        "solids": [{"id": "wall_n", "mat": "plaster", "rect": [2, 6, 10, 0.3], "h": 3.0},
                   {"id": "wall_s", "mat": "plaster", "rect": [2, 12, 10, 0.3], "h": 3.0},
                   {"id": "kitchen_table", "mat": "wood", "rect": [5, 8, 1.6, 0.9], "h": 0.75}],
        "things": [
            {"id": "farmhouse", "kind": "building", "enter": "plan-built", "footprint": [2, 6, 10, 6.3], "door": [2, 9],
             "front": [1, 9], "size_m": {"height": 7.5}},
            {"id": "neighbour", "kind": "building", "enter": "shell", "footprint": [16, 6, 8, 6], "door": [20, 6],
             "front": [20, 5], "words": "A single two-storey clapboard house, white paint, a porch", "model": "court_house_a"},
            {"id": "neighbour_2", "kind": "building", "enter": "shell", "footprint": [25, 6, 4, 6], "model": "court_house_a",
             "words": "A single two-storey clapboard house, white paint, a porch"},
            {"id": "shed", "kind": "building", "footprint": [14, 14, 3, 3], "door": [15, 14], "front": [15, 13],
             "closed_line": "The shed's padlocked. Bill keeps the key."},
            {"id": "buick", "kind": "vehicle", "at": [10, 2], "turn": 90, "size_m": {"width": 5.4},
             "words": "A single 1980s Buick sedan, dark red, dusty"},
            {"id": "linden", "kind": "tree", "at": [24, 16], "species": "linden", "seed": 11, "size_m": {"height": 14}},
            {"id": "mailbox", "kind": "prop", "at": [13, 3.4], "size_m": {"height": 1.2}},
        ],
        "anchors": {"street": [1, 1.5], "front_door": [2, 9]},
        "lighting": {"lights": [{"id": "porch", "at": [1.5, 9], "z": 2.4, "colour": "ffc27a", "power": 1, "radius": 6}]},
    }


def test_a_place_plan_is_checked_in_words():
    assert place.check(court()) == []
    bad = court()
    bad["road"] = {"type": "cobbles"}
    bad["things"][3].pop("closed_line")
    bad["things"].append({"id": "buick", "kind": "car"})
    probs = place.check(bad)
    assert any("road type" in p for p in probs) and any("closed_line" in p for p in probs)
    assert any("twice" in p for p in probs) and any("kind must be" in p for p in probs)


def test_the_world_list_gets_every_generated_thing_once_and_guesses_no_look():
    es = {e["id"]: e for e in place.wanted_entries(court())}
    assert "test_court_farmhouse" not in es                                   # plan-built: the compiler models it
    assert es["court_house_a"]["kind"] == "building" and len([e for e in es if e == "court_house_a"]) == 1
    assert es["test_court_buick"]["kind"] == "prop" and es["test_court_buick"]["tier"] == "large_prop"
    assert es["test_court_linden"]["kind"] == "tree" and es["test_court_linden"]["species"] == "linden"
    mb = es["test_court_mailbox"]
    assert mb["hold"] and mb["needs_words"] and mb["words"] == ""
    shed = es["test_court_shed"]
    assert shed["needs_words"] and shed["real_size_m"]["height"] == place.BOX_HEIGHT["building"]
    orders = [e["first"]["order"] for e in place.wanted_entries(court())]
    assert orders == sorted(orders) and all(e["first"]["where"].startswith("Test Court") for e in es.values())


def test_the_placed_things_list_has_grey_boxes_of_real_size_facing_their_streets():
    tl = place.things_list(court())
    t = {x["id"]: x for x in tl["things"]}
    assert tl["dust"] is True and tl["road"] == "dirt"
    assert t["farmhouse"]["plan_built"] and t["farmhouse"]["model"] is None
    assert t["neighbour"]["box_m"] == [8.0, 6.0, place.BOX_HEIGHT["building"]] and t["neighbour"]["model"] == "court_house_a"
    assert t["neighbour"]["turn"] == 180.0                                    # its door faces north, to the street
    assert t["shed"]["enter"] == "closed" and t["shed"]["closed_line"].startswith("The shed")
    assert t["buick"]["turn"] == 90 and t["buick"]["box_m"][2] == place.BOX_HEIGHT["vehicle"]
    assert tl["lights"][0]["id"] == "porch"
    street = dict(court(), road={"type": "street"})
    assert place.things_list(street)["dust"] is False


def test_compiling_writes_the_stage_model_the_things_and_the_world_list(tmp_path):
    games = tmp_path / "games"
    (games / "g1").mkdir(parents=True)
    p = tmp_path / "test_court.place.json"
    p.write_text(json.dumps(court()), encoding="utf-8")
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig", port=9, command=[], out=tmp_path / "out")
    rep = place.compile_place(None, "g1", p, tmp_path / "out" / "places", env=env, python=FAKE_BLENDER, games_root=games)
    assert rep["ok"], rep
    assert Path(rep["model"]).exists() and Path(rep["things"]).exists()
    w = json.loads(Path(rep["wanted"]).read_text(encoding="utf-8"))
    assert len(w["entries"]) == 5 and any("held" in ln for ln in rep["lines"])
    # the world queue reads them: the described ones wait to be made, the undescribed ones are held, none is refused
    cfg = {"_root": str(tmp_path), "threed": {"out_root": str(tmp_path / "out3d")}}
    entries, problems = world.load(cfg, "g1")
    assert not problems, problems
    held = {e["id"] for e in entries if e["hold"]}
    assert held == {"test_court_shed", "test_court_mailbox"}


def test_compiling_again_keeps_what_a_person_wrote_and_never_drops_a_thing(tmp_path):
    games = tmp_path / "games"
    pl = court()
    w = place.write_wanted(games, "g1", pl)
    d = json.loads(w.read_text(encoding="utf-8"))
    for e in d["entries"]:
        if e["id"] == "test_court_mailbox":
            e.update(words="A single rural steel mailbox on a cedar post", hold=False, rank=2)
    w.write_text(json.dumps(d), encoding="utf-8")
    pl["things"] = [t for t in pl["things"] if t["id"] != "linden"]
    place.write_wanted(games, "g1", pl)
    d2 = {e["id"]: e for e in json.loads(w.read_text(encoding="utf-8"))["entries"]}
    mb = d2["test_court_mailbox"]
    assert mb["words"].startswith("A single rural") and mb["rank"] == 2 and "needs_words" not in mb
    assert d2["test_court_linden"]["hold"] and "no longer in" in d2["test_court_linden"]["gone_from_place"]


def test_a_place_that_fails_its_check_compiles_nothing(tmp_path):
    bad = court()
    bad["size"] = [0, 5]
    p = tmp_path / "bad.place.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig", port=9, command=[], out=tmp_path / "out")
    rep = place.compile_place(None, "g1", p, tmp_path / "out", env=env, python=FAKE_BLENDER)
    assert not rep["ok"] and "size" in rep["error"] and not list((tmp_path / "out").glob("*.glb"))


@pytest.mark.skipif(not HAVE_BPY, reason="no Blender (bpy) in this Python")
def test_the_compiler_for_real_in_blender(tmp_path):
    p = tmp_path / "test_court.place.json"
    p.write_text(json.dumps(court()), encoding="utf-8")
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig", port=9, command=[], out=tmp_path / "out")
    rep = place.compile_place(None, "g1", p, tmp_path / "out", env=env, python=sys.executable, minutes=3)
    assert rep["ok"], rep
    from forge.threed.meshio import Glb
    g = Glb.load(rep["model"])
    lo, hi = g.bounds()
    assert rep["faces"] > 100 and hi[1] - lo[1] == pytest.approx(3.0, abs=0.05)         # the walls stand 3 m
    names = {m.get("name") for m in g.j.get("materials", [])}
    assert {"plaster", "wood"} <= names                                                   # dressed by material word


SHEET = {"id": "testville", "name": "Testville",
         "required": [{"kind": "inn", "label": "INN"}, {"kind": "store"}, {"kind": "gas_station"}, {"kind": "diner"}],
         "tiers": {"weapon": 1, "armor": 1, "accessory": 0}}


def test_a_towns_layout_becomes_a_place_plan(tmp_path):
    p = town.generate(SHEET, "purity_town", "after", 7)
    pl = place.from_town(p.layout_record(), p.grid.c, {"road": "gravel", "looks": {"inn": "A single two-storey brick inn"}},
                         entities=p.entities)
    assert place.check(pl) == [], place.check(pl)
    assert pl["road"]["type"] == "gravel" and pl["size"] == [float(p.w), float(p.h)]
    assert any(g["mat"] == "gravel" for g in pl["ground"])
    ids = {t["id"] for t in pl["things"]}
    assert ids == {b["id"] for b in p.buildings}
    inn = next(t for t in pl["things"] if t["label"] == "INN" or t["id"].startswith("inn"))
    assert inn["words"].startswith("A single two-storey brick inn")
    assert all(t["footprint"][2] > 0 for t in pl["things"])
    assert pl["anchors"]                                                     # spawns and doors
    silent = place.from_town(p.layout_record(), p.grid.c, {}, entities=p.entities)
    assert silent["road"]["type"] == "street" and len(silent["unknowns"]) == 2
    es = place.wanted_entries(silent)
    assert es and all(e.get("needs_words") for e in es if e["kind"] == "building")


def test_compile_place_is_a_job_type_a_running_worker_takes(tmp_path):
    from types import SimpleNamespace
    from forge.plugins import places
    assert "compile_place" in places.JOB_TYPES and places.JOB_TYPES["compile_place"]["needs"] == "cpu"
    (tmp_path / "games" / "g1").mkdir(parents=True)
    (tmp_path / "games" / "g1" / "court.place.json").write_text(json.dumps(court()), encoding="utf-8")
    ctx = SimpleNamespace(cfg={"_root": str(tmp_path), "threed": {"blender_python": FAKE_BLENDER}}, root=str(tmp_path))
    out = tmp_path / "out" / "job1"
    out.mkdir(parents=True)
    r = places.compile_place({"place": "court.place.json", "game": "g1"}, ctx, out)
    assert Path(r["model"]).exists() and (out / "prov.json").exists()
    assert (tmp_path / "games" / "g1" / "wanted_3d" / "test_court.json").exists()
