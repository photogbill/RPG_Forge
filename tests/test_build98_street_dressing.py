"""BUILD 98 / 97: the dresser on the street — a held place inside another, shop fronts and backs, a fuel canopy's
forecourt, the sidewalk's furniture strip, and a plan's own building size.

Small made-up places only; everything is written under tmp_path."""
import json

from forge.threed import areacheck_dressing as ad
from forge.threed import dresser

KIT = {"town": "t", "era": "peace", "order": 9, "characters": {"kept": 1.0},
       "variants": [
           {"id": "pot", "family": "porch", "role": "porch", "box_m": [0.6, 0.6], "words": "x A pot."},
           {"id": "shrub", "family": "planting", "role": "foundation", "box_m": [1.0, 1.0], "words": "x A shrub."},
           {"id": "bed", "family": "planting", "role": "bed", "box_m": [1.2, 1.0], "words": "x A bed."},
           {"id": "barrow", "family": "yard_life", "role": "work", "box_m": [1.4, 0.6], "words": "x A barrow."},
           {"id": "hydrant", "family": "street", "role": "kerb", "box_m": [0.5, 0.5], "words": "x A hydrant."},
           {"id": "bench", "family": "shop_front", "role": "shop_front", "box_m": [1.6, 0.6], "words": "x A bench."},
           {"id": "planter", "family": "shop_front", "role": "shop_front", "box_m": [1.0, 1.0], "words": "x A planter."},
           {"id": "dumpster", "family": "shop_back", "role": "shop_back", "box_m": [2.0, 1.6], "words": "x A dumpster."},
           {"id": "pallets", "family": "shop_back", "role": "shop_back", "box_m": [1.2, 1.0], "words": "x Pallets."},
           {"id": "forsythia", "family": "planting", "role": "edge", "box_m": [1.5, 1.5], "words": "x A forsythia."}]}


def _rules(**place):
    r = ad.load_rules()
    r["places"] = {"t_big": place} if place else {}
    return r


def _road_place(pid, things, ground=None, size=(60, 30)):
    return {"id": pid, "size": list(size), "road": {"type": "street"},
            "ground": [{"mat": "asphalt", "rect": [0, 20, size[0], 6]}] + (ground or []), "things": things}


def test_a_shop_gets_its_front_and_back_and_a_home_gets_no_dumpster():
    place = _road_place("t_big", [
        {"id": "shop", "kind": "building", "label": "a shop", "at": [15, 10], "size_m": {"width": 16, "depth": 8}},
        {"id": "house", "kind": "building", "label": "a house", "at": [45, 10], "size_m": {"width": 10, "depth": 8}}])
    items = dresser.Dresser(place, KIT, _rules(buildings={"shop": "shop"}), {}, seed=2, view=(20, 21)).run()
    shop_back = [i for i in items if i["family"] == "shop_back"]
    assert shop_back and all(i["lot"] == "shop" for i in shop_back)
    assert any(i["family"] == "shop_front" and i["lot"] == "shop" for i in items)


def test_a_plans_own_depth_is_used():
    w, d = ad.box_of({"id": "mall", "kind": "building", "size_m": {"width": 46, "depth": 14}},
                     {"mall": {"width": 46}}, ad.load_rules())
    assert (w, d) == (46.0, 14.0)


def test_held_place_is_mirrored_and_nothing_new_goes_in_it(tmp_path):
    inner = {"id": "t_inner", "size": [20, 12], "things": []}
    (tmp_path / "t_inner.place.json").write_text(json.dumps(inner), encoding="utf-8")
    (tmp_path / "t_inner.dressing_out.json").write_text(json.dumps({"items": [
        {"id": "dz_001_pot", "kind": "prop", "model": "pot", "at": [5, 5], "turn": 0, "box_m": [0.6, 0.6],
         "family": "porch", "variant": "pot"}]}), encoding="utf-8")
    place = _road_place("t_big", [
        {"id": "house", "kind": "building", "label": "a house", "at": [45, 8], "size_m": {"width": 10, "depth": 8}}])
    rules = _rules(mirror_from={"place": "t_inner", "offset": [10, 2]}, held_rects=[[10, 2, 20, 12]])
    items = dresser.Dresser(place, KIT, rules, {}, seed=4, view=(20, 21), places_dir=tmp_path).run()
    mirrored = [i for i in items if i["zone"] == "mirrored"]
    assert [i["at"] for i in mirrored] == [[15.0, 7.0]]
    for i in items:
        if i["zone"] != "mirrored":
            x, y = i["at"]
            assert not (10 <= x < 30 and 2 <= y < 14), i
    # the check does not measure held ground
    res = ad.check_dressing(place, items, rules)
    assert all(z.get("lot") != "t_inner" for z in res["zones"])


def test_kerb_furniture_goes_on_a_sidewalks_kerb_edge_only():
    sidewalk = {"mat": "sidewalk", "rect": [0, 18, 60, 2]}
    place = _road_place("t_big", [
        {"id": "house", "kind": "building", "label": "a house", "at": [30, 8], "size_m": {"width": 10, "depth": 8}}],
        ground=[sidewalk])
    d = dresser.Dresser(place, KIT, _rules(), {}, seed=5, view=(20, 21))
    d.dress_kerb(__import__("random").Random(5))
    kerb = [i for i in d.items if i["variant"] == "hydrant"]
    assert kerb, "the kerb got nothing"
    for i in kerb:
        assert i["at"][1] >= 18.9, i            # within the last metre of the sidewalk, never its walking width


def test_a_fuel_canopy_is_a_forecourt_not_a_room():
    place = _road_place("t_big", [
        {"id": "canopy", "kind": "building", "label": "the fuel canopy", "footprint": [20, 4, 20, 12],
         "rooms": [[20, 4, 20, 12]]}])
    rules = _rules(buildings={"canopy": "shop"}, open_rooms=["canopy"])
    zz = ad.zones(place, rules)
    assert not (zz["Z"] == ad.Z_INTERIOR).any()
    res = ad.check_dressing(place, [], rules)
    assert any(z["rule"] == "forecourt" for z in res["zones"])
