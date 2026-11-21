"""BUILD 98 / 97 Part 5: area checks 6 (Repeats) and 7 (Dressing), the board, the Blender profiles, tools and the shelf.

Small made-up places only; nothing real is read or written (tmp_path)."""
import json
from pathlib import Path

import pytest

from forge.threed import areacheck_dressing as ad
from forge import blenderrun, library, toolsreg


def _rules():
    return ad.load_rules()


def _street_place(things=None):
    # a 40 × 30 m plan: a road across the middle, one house north of it facing the road
    return {"id": "t_street", "size": [40, 30], "road": {"type": "street"},
            "ground": [{"mat": "asphalt", "rect": [0, 13, 40, 6]}],
            "things": [{"id": "house_a", "kind": "building", "label": "a house", "at": [20, 5], "box_m": [10, 8]}]
            + (things or [])}


def test_zones_cut_the_place():
    zz = ad.zones(_street_place(), _rules())
    Z = zz["Z"]
    names = {ad.ZONE_NAMES[int(k)] for k in set(Z.ravel().tolist())}
    assert {"road", "building", "kerb strip", "front yard", "back / side yard"} <= names


def test_an_empty_yard_is_flagged_and_a_dressed_one_is_not():
    empty = ad.check_dressing(_street_place(), [], _rules())
    assert empty["ok"] is False
    assert any(f["zone"] == "front yard" for f in empty["flags"])
    # dress the front yard (y 9..12.5 between the house face and the kerb) densely
    extra = [{"id": f"d{i}", "kind": "prop", "model": f"m{i}", "at": [12 + i * 1.6, 10.5], "box_m": [0.6, 0.6]}
             for i in range(10)]
    dressed = ad.check_dressing(_street_place(), extra, _rules())
    fy = [z for z in dressed["zones"] if z["zone"] == "front yard"][0]
    assert fy["things"] >= 8 and fy["per_100m2"] > 6


def test_excluded_lot_is_not_measured():
    r = _rules()
    r["places"] = {"t_street": {"exclude_lots": ["house_a"]}}
    res = ad.check_dressing(_street_place(), [], r)
    assert all(z["lot"] != "house_a" for z in res["zones"])


def test_repeats_in_one_view_and_side_by_side():
    things = [{"id": f"gnome{i}", "kind": "prop", "model": "garden_gnome", "at": [5 + i * 3, 25], "turn": i * 40,
               "box_m": [0.4, 0.4]} for i in range(3)]
    things += [{"id": "pot_a", "kind": "prop", "model": "pot", "at": [30, 25], "turn": 0, "box_m": [0.6, 0.6]},
               {"id": "pot_b", "kind": "prop", "model": "pot", "at": [30.6, 25], "turn": 3, "box_m": [0.6, 0.6]}]
    res = ad.check_repeats(_street_place(things), [], _rules(), view=(20, 21))
    whys = " ".join(f["why"] for f in res["flags"])
    assert "garden_gnome ×3" in whys and "side by side" in whys


def test_fences_may_repeat():
    things = [{"id": f"f{i}", "kind": "prop", "model": "picket_fence", "at": [2 + i * 2.4, 22], "box_m": [2.4, 0.2]}
              for i in range(6)]
    assert ad.check_repeats(_street_place(things), [], _rules(), view=(20, 21))["ok"]


def test_camera_view_from_the_stage(tmp_path):
    p = tmp_path / "stage.json"
    p.write_text(json.dumps({"camera": {"yaw": 10, "pitch": 35, "fov": 26, "dist": 24}}))
    w, d = ad.camera_view(p, _rules())
    assert 18 < w < 22 and 19 < d < 24


def test_board_writes_md(tmp_path):
    pd = tmp_path / "places"
    pd.mkdir()
    (pd / "t_street.place.json").write_text(json.dumps(_street_place()))
    res = ad.board(pd, _rules(), {}, (20, 21), tmp_path / "out", picture=False)
    assert res["rows"][0]["place"] == "t_street"
    assert "t_street" in (tmp_path / "out" / "board.md").read_text(encoding="utf-8")


def test_blender_command_enables_only_the_profile():
    cmd = blenderrun.command("grow.py", "trees", out=Path("run"), program="blender")
    assert "--factory-startup" in cmd
    mods = cmd[cmd.index("--modules") + 1].split(",")
    assert "bl_ext.blender_org.sapling_tree_gen" in mods and "bl_ext.blender_org.archimesh" not in mods
    plain = blenderrun.command("x.py", "", program="blender")
    assert plain[plain.index("--modules") + 1] == ""
    with pytest.raises(blenderrun.RunError):
        blenderrun.command("x.py", "no_such_profile", program="blender")


def test_every_profile_names_modules():
    p = blenderrun.load_profiles()
    assert {"trees", "buildings", "interiors", "ruins", "terrain", "retopo_bake", "godot_export", "animals",
            "cloth"} <= set(p["profiles"])
    assert all(v["modules"] for v in p["profiles"].values())


def test_tools_registry_reads_and_lists():
    rows = toolsreg.listing()
    ids = {r["id"] for r in rows}
    assert {"blender", "comfyui", "material_maker", "realityscan", "effekseer", "photoshop"} <= ids
    assert all(r["licence"] for r in rows)


def test_library_refuses_non_commercial_and_keeps_licence(tmp_path):
    cfg = {"paths": {"library": str(tmp_path / "lib")}}
    src = tmp_path / "bark.png"
    src.write_bytes(b"\x89PNG fake")
    with pytest.raises(library.LibraryError):
        library.import_folder(str(src), "scan", "CC BY-NC 4.0", cfg=cfg)
    e = library.import_folder(str(src), "scan", "William's own (his R5 photograph)", name="oak bark", cfg=cfg)
    assert e["licence"].startswith("William's own")
    assert (tmp_path / "lib" / "scan" / "oak_bark" / "LICENCE.txt").exists()
    assert library.search("oak", cfg=cfg)[0]["id"] == "oak_bark"


def test_dresser_dresses_a_street_and_keeps_paths_clear(tmp_path):
    from forge.threed import dresser
    kit = {"town": "t", "era": "peace", "order": 9, "characters": {"kept": 1.0},
           "variants": [
               {"id": "pot", "family": "porch", "role": "porch", "box_m": [0.6, 0.6], "words": "x A single pot."},
               {"id": "chair", "family": "porch", "role": "porch_step", "box_m": [0.8, 0.8], "words": "x A single chair."},
               {"id": "shrub", "family": "planting", "role": "foundation", "box_m": [1.0, 1.0], "words": "x A single shrub."},
               {"id": "bed", "family": "planting", "role": "bed", "box_m": [1.2, 1.0], "words": "x A single bed."},
               {"id": "grill", "family": "yard_life", "role": "patio", "box_m": [0.8, 0.8], "words": "x A single grill."},
               {"id": "bike", "family": "yard_life", "role": "yard", "box_m": [1.2, 0.5], "words": "x A single bike."},
               {"id": "barrow", "family": "yard_life", "role": "work", "box_m": [1.4, 0.6], "words": "x A single barrow."},
               {"id": "hydrant", "family": "street", "role": "kerb", "box_m": [0.5, 0.5], "words": "x A single hydrant."},
               {"id": "fence", "family": "boundary", "role": "lot_line_back", "box_m": [2.4, 0.15], "words": "x A fence."}]}
    place = _street_place()
    place["ground"].append({"mat": "path", "rect": [19.5, 9, 1, 4]})
    d = dresser.Dresser(place, kit, _rules(), {}, seed=3, view=(20, 21))
    items = d.run()
    assert len(items) > 8
    for it in items:                                    # nothing on the path, nothing in the house
        x, y = it["at"]
        assert not (19.5 <= x <= 20.5 and 9 <= y <= 13)
        assert not (15 <= x <= 25 and 1 <= y <= 9)
    again = dresser.Dresser(place, kit, _rules(), {}, seed=3, view=(20, 21)).run()
    assert [i["at"] for i in again] == [i["at"] for i in items]          # the same seed, the same yard
    wl = dresser.kit_world_list(kit, {"bike"})
    assert {e["id"] for e in wl["entries"]} == {"pot", "chair", "shrub", "bed", "grill", "barrow", "hydrant", "fence"}


def test_compiler_places_the_dressers_things(tmp_path):
    from forge.threed import place as placemod
    p = tmp_path / "t_street.place.json"
    p.write_text(json.dumps(_street_place()))
    (tmp_path / "t_street.dressing_out.json").write_text(json.dumps({"items": [
        {"id": "dz_001_pot", "kind": "prop", "model": "lm_pot", "at": [12, 11], "turn": 15, "box_m": [0.6, 0.6]}]}))
    merged = placemod.with_dressing_out(_street_place(), p)
    tl = placemod.things_list(merged)
    row = [t for t in tl["things"] if t["id"] == "dz_001_pot"][0]
    assert row["model"] == "lm_pot" and row["at"] == [12.0, 11.0]
    assert all(e["id"] != "lm_pot" for e in placemod.wanted_entries(merged))     # its model is on the kit's own list


def test_compile_never_lists_a_model_another_list_already_has(tmp_path):
    from forge.threed import place as placemod
    games = tmp_path / "games"
    w = games / "g" / "wanted_3d"
    w.mkdir(parents=True)
    (w / "t_street_hand_pass.json").write_text(json.dumps({"entries": [{"id": "lm_bed", "kind": "prop", "words": "x"}]}))
    pl = _street_place([{"id": "bed", "kind": "prop", "model": "lm_bed", "at": [5, 25], "words": "x A bed."},
                        {"id": "pot", "kind": "prop", "model": "lm_pot2", "at": [8, 25], "words": "x A pot."}])
    out = placemod.write_wanted(games, "g", pl, hold=True)
    ids = {e["id"] for e in json.loads(out.read_text())["entries"]}
    assert "lm_bed" not in ids and "lm_pot2" in ids
