"""BUILD 34 in the suite: 3D -> Places (a game's places as stages: the plan, a picture of it from above, its world-list
entries made / held / waiting, Compile again, Open in the game here) and Floor plans -> Approve "as a stage". Also the
compiler's door-rule names and roofs (OUTSIDE_/INSIDE_ layers), and that compiling can hold every new world-list entry.
Runs on a throwaway copy of the example game; nothing real is touched, nothing is generated."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from forge.suite import areas, games, places3d, server
from forge.threed import place, world as wq

from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world
from test_place_build34 import FAKE_BLENDER, HAVE_BPY, court

BILL, OPUS = "Bill", "Claude Opus"


def _game(cfg, tmp: Path) -> Path:
    """The example game with an asset folder in tmp and one place plan."""
    gdir = Path(cfg["paths"]["games"]) / "_example"
    gj = gdir / "forge.game.json"
    g = json.loads(gj.read_text(encoding="utf-8"))
    g["asset_root"] = str(tmp / "game_assets")
    gj.write_text(json.dumps(g, indent=1), encoding="utf-8")
    games._loaded.clear()
    (gdir / "places").mkdir(exist_ok=True)
    (gdir / "places" / "test_court.place.json").write_text(json.dumps(court(), indent=1), encoding="utf-8")
    return gdir


def test_the_places_tab_is_there_and_wired(world):  # noqa: F811
    a3 = next(x for x in areas.AREAS if x["id"] == "3d")
    t = next(t for t in a3["tabs"] if t["id"] == "places")
    assert t["name"] == "Places" and t["t3"] == "places" and "Compile again" in t["holds"]
    js = (REPO / "forge" / "suite" / "threed.js").read_text(encoding="utf-8")
    for fn in ("placesTab", "threed_places_compile", "threed_places_play", "Open in the game here", "Compile again"):
        assert fn in js, fn
    srv = (REPO / "forge" / "suite" / "server.py").read_text(encoding="utf-8")
    assert "/api/suite/threed/places" in srv and "floorplan_approve_stage" in srv
    assert "fpApproveStage" in (REPO / "forge" / "suite" / "shell.html").read_text(encoding="utf-8")


def test_a_place_shows_its_plan_its_picture_and_its_world_list(world):  # noqa: F811
    cfg, a, tmp = world
    _game(cfg, tmp)
    v = places3d.view(cfg, "_example")
    assert [p["id"] for p in v["places"]] == ["test_court"]
    p = v["places"][0]
    assert p["size"] == [30, 20] and p["solids"] == 3 and p["things"] == 7 and not p["problems"]
    assert not p["compiled"]["at"] and p["compiled"]["folder"].endswith(os.path.join("stages", "test_court"))
    pic = Path(cfg["paths"]["out"]) / "places" / "_example" / "test_court.png"
    assert pic.exists() and p["picture"].endswith("out/places/_example/test_court.png") or "test_court.png" in (p["picture"] or "")
    assert v["stamp"].startswith("plan from above") and "not how the game looks" in v["stamp"]
    # no world-list entries until it is compiled; then each generated thing, in its state
    wq_dir = Path(cfg["paths"]["games"]) / "_example" / "wanted_3d"
    place.write_wanted(Path(cfg["paths"]["games"]), "_example", court(), hold=True)
    v = places3d.view(cfg, "_example")
    ents = v["places"][0]["entries"]
    assert ents and {e["state"] for e in ents} == {"held"} and v["places"][0]["counts"]["held"] == len(ents)
    raw = json.loads((wq_dir / "test_court.json").read_text(encoding="utf-8"))
    assert all(e.get("hold") for e in raw["entries"]), "compiled from the suite, every new thing waits to be released"


def test_compile_again_is_queued_into_the_games_stage_folder_with_new_things_held(world):  # noqa: F811
    cfg, a, tmp = world
    _game(cfg, tmp)
    r = server.act_threed(cfg, "threed_places_compile", {"game": "_example", "place": "test_court"}, None)
    assert not r["ok"] and "who you are" in r["message"]
    r = server.act_threed(cfg, "threed_places_compile", {"game": "_example", "place": "test_court"}, OPUS)
    assert r["ok"] and r["job"], r
    job = json.loads((Path(cfg["paths"]["jobs"]) / "pending" / f"{r['job']}.json").read_text(encoding="utf-8"))
    assert job["type"] == "compile_place" and job["hold"] is True and job["game"] == "_example"
    assert Path(job["out"]) == tmp / "game_assets" / "stages" / "test_court"
    # one at a time
    again = server.act_threed(cfg, "threed_places_compile", {"game": "_example", "place": "test_court"}, BILL)
    assert not again["ok"] and "already" in again["message"]
    assert places3d.view(cfg, "_example")["places"][0]["jobs"][0]["state"] == "pending"
    assert not server.act_threed(cfg, "threed_places_compile", {"game": "_example", "place": "nowhere"}, BILL)["ok"]


def test_compiled_it_shows_when_and_whether_the_plan_has_changed_since(world):  # noqa: F811
    cfg, a, tmp = world
    gdir = _game(cfg, tmp)
    from forge.threed.env import RigEnv
    env = RigEnv(root=tmp, rig=tmp / "rig", port=9, command=[], out=tmp / "out_fake")
    out = place.stage_dir(cfg, "_example", "test_court")
    rep = place.compile_place(cfg, "_example", gdir / "places" / "test_court.place.json", out, env=env, python=FAKE_BLENDER,
                              games_root=Path(cfg["paths"]["games"]), hold=True)
    assert rep["ok"], rep
    p = places3d.view(cfg, "_example")["places"][0]
    assert p["compiled"]["at"] and p["compiled"]["things"] == 7 and not p["compiled"]["stale"]
    src = gdir / "places" / "test_court.place.json"
    os.utime(src, (src.stat().st_mtime + 60, src.stat().st_mtime + 60))
    assert places3d.view(cfg, "_example")["places"][0]["compiled"]["stale"]


def test_open_in_the_game_asks_the_adapter_which_map_and_how(world, monkeypatch):  # noqa: F811
    cfg, a, tmp = world
    _game(cfg, tmp)
    r = server.act_threed(cfg, "threed_places_play", {"game": "_example", "place": "test_court", "time": "night"}, BILL)
    assert not r["ok"] and "no map in the game" in r["message"]
    calls = []
    ad = games.adapter(cfg, "_example")
    monkeypatch.setattr(type(ad), "stage_maps", lambda self: {"test_court": ["test_court_stage"]}, raising=False)
    monkeypatch.setattr(type(ad), "play_command", lambda self, m, era, time=None: ["play", m, era, time], raising=False)
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    r = server.act_threed(cfg, "threed_places_play", {"game": "_example", "place": "test_court", "time": "night"}, BILL)
    assert r["ok"] and calls == [["play", "test_court_stage", "peace", "night"]], (r, calls)
    assert places3d.view(cfg, "_example")["places"][0]["maps"] == ["test_court_stage"]


def test_approve_as_a_stage_is_the_persons_and_writes_the_plan_once(world, monkeypatch):  # noqa: F811
    cfg, a, tmp = world
    _game(cfg, tmp)

    class Top:
        entities = []

        @staticmethod
        def layout_record():
            return {"place": "smallville", "era": "war", "archetype": "crossroads", "seed": 3}

        class grid:
            c = [["road"] * 6, ["ground", "wall", "wall", "ground", "ground", "ground"],
                 ["ground", "wall", "wall", "ground", "fence", "fence"]]
    from forge.layout import store
    monkeypatch.setattr(store, "load_set", lambda fol: (Top, {"place": "smallville", "sheet": {"road": "dirt"}, "problems": []}))
    folder = tmp / "a_plan_set"
    folder.mkdir()
    with pytest.raises(Exception):
        places3d.approve_as_stage(cfg, "_example", folder, OPUS)            # a person's call
    r = places3d.approve_as_stage(cfg, "_example", folder, BILL)
    assert r["ok"] and r["place"]
    plan = Path(cfg["paths"]["games"]) / "_example" / "places" / f"{r['place']}.place.json"
    assert plan.exists() and json.loads(plan.read_text(encoding="utf-8"))["id"]
    assert any("adapter can't write a stage map" in l for l in r["lines"])   # the example game has no stage_install
    with pytest.raises(Exception):
        places3d.approve_as_stage(cfg, "_example", folder, BILL)            # never written over


def test_the_compiler_names_what_gives_way_at_a_door_and_builds_roofs(tmp_path):
    """OUTSIDE_<building>__ / INSIDE_<building>__ before the mesh's own name: the game's door rule reads them."""
    if not HAVE_BPY:
        pytest.skip("this machine's Python has no Blender inside (bpy)")
    plan = {"id": "door_rule", "size": [12, 10], "anchors": {"door": [4, 2]},
            "solids": [{"id": "stub", "mat": "plaster", "rect": [1, 1, 6, 0.3], "h": 0.4, "show": "inside", "building": "hut"},
                       {"id": "outer", "mat": "siding", "rect": [1, 1, 6, 0.3], "h": 3.0, "show": "outside", "building": "hut"},
                       {"id": "roof", "mat": "shingle", "show": "outside", "building": "hut",
                        "roof": {"rect": [1, 1, 6, 5], "ridge": "x", "pitch": 30, "eave": 3.0, "overhang": 0.3, "gable": "siding"}},
                       {"id": "post", "mat": "wood", "cyl": [9, 5, 0.15], "h": 2.0}],
            "things": [{"id": "hut", "kind": "building", "enter": "plan-built", "footprint": [1, 1, 6, 5]}]}
    assert place.check(plan) == []
    p = tmp_path / "door_rule.place.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    from forge.threed.env import RigEnv
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig", port=9, command=[], out=tmp_path / "out")
    rep = place.compile_place(None, "g1", p, tmp_path / "out", env=env, python=sys.executable, minutes=3)
    assert rep["ok"], rep
    from forge.threed.meshio import Glb
    g = Glb.load(rep["model"])
    names = " ".join(str(n.get("name", "")) for n in g.j.get("nodes", []) + g.j.get("meshes", []))
    assert "OUTSIDE_hut__M_shingle" in names and "OUTSIDE_hut__M_siding" in names and "INSIDE_hut__" in names, names
    assert "M_wood" in names


def test_a_shown_mesh_names_a_plan_built_building():
    plan = court()
    plan["solids"].append({"id": "odd", "mat": "plaster", "rect": [16, 6, 1, 1], "h": 2, "show": "outside", "building": "neighbour"})
    probs = place.check(plan)
    assert any("neighbour" in x and "plan-built" in x for x in probs), probs
    plan["solids"][-1]["building"] = "farmhouse"
    assert place.check(plan) == []
