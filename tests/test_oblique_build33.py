"""BUILD 33 — the map camera as a block-out (forge/layout/oblique.py): a scene plan becomes the guide a model paints
over, its depth and line work, the overlay mask, the walk rings and the anchors. Nothing here needs a GPU or a game."""
from __future__ import annotations
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge.layout import oblique as ob

REPO = Path(__file__).resolve().parents[1]


def plan():
    return {
        "id": "room", "tile": 32, "size": [12, 10], "background": "void",
        "ground": [{"mat": "plank", "rect": [1, 4, 10, 5]},
                   {"mat": "grass_dark", "rect": [0, 0, 12, 1], "walk": False}],
        "solids": [
            {"id": "north_wall", "mat": "plaster", "top": "cut", "rect": [1, 3.6, 10, 0.4], "h": 3.0,
             "face": [{"mat": "window_night", "x": 4, "w": 2, "z": 1, "h": 1.2}]},
            {"id": "table", "mat": "wood", "rect": [4, 6, 2, 1], "h": 0.8},
            {"id": "stub", "mat": "cut", "rect": [1, 9, 10, 0.3], "h": 0.35},
            {"id": "fence", "mat": "fence", "rect": [8, 8, 2, 0.2], "h": 1.5, "over": True},
            {"id": "post", "mat": "wood", "cyl": [9.5, 5.5, 0.3], "h": 2.5},
        ],
        "anchors": {"start": [2.5, 7.5], "by_table": [5, 7.6], "behind_fence": [9, 7.6], "on_table": [5, 6.5]},
    }


def px_at(img, x, y, t=32):
    return img.getpixel((int(x * t), int(y * t)))


def test_the_floor_is_plan_true_and_height_stands_straight_up():
    b = ob.render(plan())
    assert b.guide.size == (12 * 32, 10 * 32)
    assert px_at(b.guide, 2.5, 7.5) == ob.MATERIALS["plank"]                    # a floor point is the same pixel as in the plan
    # the table: top at y - h (6-0.8 … 7-0.8), front below it (7-0.8 … 7), in a darker shade of the same colour
    assert px_at(b.guide, 5, 5.5) == ob.MATERIALS["wood"]
    front = px_at(b.guide, 5, 6.6)
    assert front != ob.MATERIALS["wood"] and all(f < w for f, w in zip(front, ob.MATERIALS["wood"]))
    # the north wall's face stands above the floor's north edge (base at y=4): 3 tiles of plaster with a window in it
    assert px_at(b.guide, 2, 2.5)[0] < ob.MATERIALS["plaster"][0] and px_at(b.guide, 2, 2.5) != ob.MATERIALS["void"]
    assert px_at(b.guide, 5, 2.4) == ob.MATERIALS["window_night"]
    assert px_at(b.guide, 5, 0.8) == ob.MATERIALS["cut"]                           # the wall's top, at its base minus its height


def test_what_is_nearer_the_camera_covers_what_is_behind():
    p = plan()
    p["solids"].append({"id": "crate", "mat": "metal", "rect": [4.5, 7.2, 1, 0.6], "h": 1.5})    # south of the table, taller
    b = ob.render(p)
    assert px_at(b.guide, 5, 6.5)[2] > px_at(b.guide, 5, 6.5)[0]                    # the crate (bluish metal) covers the table's front


def test_depth_is_white_toward_the_camera_and_with_height():
    b = ob.render(plan())
    d = np.asarray(b.depth).astype(int)
    assert d[int(8.5 * 32), 64] > d[int(4.5 * 32), 64]                              # the floor: south is nearer
    assert d[int(5.5 * 32), 5 * 32] > d[int(5.5 * 32), 2 * 32]                      # the table top is nearer than the floor beside it
    wall = d[int(1.2 * 32):int(3.8 * 32), 64]
    assert wall[0] > wall[-1]                                                       # up a wall face = nearer
    assert d.min() == 0 and d.max() == 255


def test_lines_are_the_edges_and_over_is_only_what_is_marked():
    b = ob.render(plan())
    lines = np.asarray(b.lines) > 0
    assert lines[int(7 * 32) - 1:int(7 * 32) + 2, 5 * 32].any()                     # the table's front edge meets the floor
    assert not lines[int(8.2 * 32), int(2.5 * 32)]                                  # open floor has none
    over = np.asarray(b.over) > 0
    assert over[int(7.4 * 32), int(9 * 32)]                                         # the fence's face
    assert not over[int(5.5 * 32), 5 * 32] and 0.002 < over.mean() < 0.05           # not the table; a small part of the picture


def test_the_floor_keeps_actors_out_of_what_a_thing_hides_but_not_behind_an_overlay_or_a_stub():
    p = plan()
    ok = ob.walk_grid(p)
    cell = lambda x, y: bool(ok[int(y / 0.25), int(x / 0.25)])
    assert cell(2.5, 7.5) and not cell(5, 6.5)                                      # floor; the table's footprint
    assert not cell(5, 5.5)                                                         # the strip the table hides (0.8 north of it)
    assert cell(5, 4.6)                                                             # beyond that strip
    assert cell(9, 7.6)                                                             # behind the fence: it is an overlay, drawn over the actor
    assert cell(5, 8.6)                                                             # right up to the cut wall stub
    assert not cell(2, 0.5)                                                         # ground marked walk: false
    assert ob.reaches(p, "start", "by_table") and ob.reaches(p, "start", "behind_fence")
    assert not ob.reaches(p, "start", "on_table")


def _inside(pt, rings):
    n = 0
    for ring in rings:
        c = False
        for k in range(len(ring)):
            (x1, y1), (x2, y2) = ring[k], ring[(k + 1) % len(ring)]
            if (y1 > pt[1]) != (y2 > pt[1]) and pt[0] < (x2 - x1) * (pt[1] - y1) / (y2 - y1) + x1:
                c = not c
        n += c
    return n % 2 == 1


def test_walk_rings_nest_or_stay_apart_and_hold_every_reachable_anchor():
    p = plan()
    rings = ob.walk_rings(p, start="start")
    assert len(rings) >= 2                                                           # the room, and the hole the table makes
    pts = [tuple(q) for r in rings for q in r]
    assert len(pts) == len(set(pts))                                                 # no two rings share a corner
    a = ob.anchors_px(p)
    assert a["start"] == [80, 240]
    assert _inside(a["start"], rings) and _inside(a["by_table"], rings) and not _inside(a["on_table"], rings)
    for r in rings:                                                                  # corners only: no point in the middle of a run
        for k in range(len(r)):
            (x0, y0), (x1, y1), (x2, y2) = r[k - 1], r[k], r[(k + 1) % len(r)]
            assert (x1 - x0) * (y2 - y1) != (y1 - y0) * (x2 - x1)


def test_floors_that_touch_only_at_a_corner_do_not_make_touching_rings():
    p = {"id": "x", "tile": 32, "size": [4, 4], "ground": [{"mat": "plank", "rect": [0, 0, 2, 2]}, {"mat": "plank", "rect": [2, 2, 2, 2]}],
         "solids": [], "anchors": {}}
    rings = ob.walk_rings(p)
    pts = [tuple(q) for r in rings for q in r]
    assert len(rings) == 2 and len(pts) == len(set(pts))


def test_the_same_plan_draws_the_same_bytes():
    def png(im):
        b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
    a, b = ob.render(plan()), ob.render(plan())
    assert all(png(getattr(a, n)) == png(getattr(b, n)) for n in ("guide", "depth", "lines", "over", "normal", "glow"))
    assert ob.walk_rings(plan()) == ob.walk_rings(plan())


def test_check_says_what_is_wrong_with_a_plan():
    p = plan()
    p["solids"].append({"id": "table", "mat": "wood", "rect": [20, 2, 1, 1], "h": 1})
    p["solids"].append({"id": "odd", "mat": "unobtainium", "rect": [2, 5, 1, 1], "h": 1})
    p["solids"][0]["face"].append({"mat": "door", "x": 10.5, "w": 2, "z": 0, "h": 2})
    p["anchors"]["lost"] = [40, 2]
    said = " | ".join(ob.check(p))
    for word in ("two solids are called 'table'", "outside the picture", "unobtainium", "hangs off its front", "anchor 'lost'"):
        assert word in said
    with pytest.raises(ob.PlanError):
        ob.render(p)
    assert ob.check(plan()) == []
    assert ob.check({"ground": []}) == ['the plan has no "size": [tiles wide, tiles deep]']


def test_a_canopy_may_hang_past_the_edge_and_a_plan_may_bring_its_own_colours():
    p = plan()
    p["materials"] = {"moss": [10, 200, 30]}
    p["solids"].append({"id": "canopy", "mat": "moss", "cyl": [11, 9, 2.5], "z": 2.5, "h": 1, "over": True, "block": False})
    assert ob.check(p) == []
    b = ob.render(p)
    assert (10, 200, 30) in {px_at(b.guide, 10.5, 6.2)}
    assert ob.reaches(p, "start", "behind_fence")                                    # block: false takes no floor


def test_agreement_is_high_for_a_picture_that_holds_the_plan_and_low_for_one_that_does_not(tmp_path):
    b = ob.render(plan())
    assert ob.agreement(b.guide, b) > 0.7                                            # the guide holds its own plan
    assert ob.agreement(Image.new("RGB", b.guide.size, (90, 90, 90)), b) < 0.05      # a blank picture holds nothing
    rng = np.random.default_rng(7)                                                   # a busy picture does not score for being busy
    noise = Image.fromarray(rng.integers(0, 255, (b.guide.size[1] // 8, b.guide.size[0] // 8, 3), dtype=np.uint8).astype(np.uint8))
    assert ob.agreement(noise.resize(b.guide.size, Image.NEAREST), b) < 0.25
    shifted = Image.new("RGB", b.guide.size)
    shifted.paste(b.guide, (40, 28))
    assert ob.agreement(shifted, b) < ob.agreement(b.guide, b) - 0.3                 # the same room in the wrong place
    hold, clean = ob.agreement(b.guide, b, detail=True)
    assert hold > 0.7 and clean > 0.8
    paths = b.save(tmp_path)
    assert sorted(p.name for p in paths.values()) == ["room_depth.png", "room_glow.png", "room_guide.png", "room_lines.png", "room_normal.png", "room_over.png"]


def test_normals_say_which_way_a_surface_faces_and_glow_is_only_what_gives_light():
    p = plan()
    p["solids"].append({"id": "lamp", "mat": "glow_warm", "cyl": [3, 7, 0.3], "z": 1.2, "h": 0.3, "block": False})
    p["solids"][0]["face"].append({"mat": "screen", "x": 8, "w": 1.5, "z": 1, "h": 1})
    b = ob.render(p)
    assert px_at(b.normal, 2.5, 7.5) == (127, 127, 255)                             # the floor faces the viewer
    r, g, bl = px_at(b.normal, 5, 6.6)                                              # the table's front: tilted down the picture (y up → green low)
    assert r in (127, 128) and g < 60 and 200 < bl < 230
    assert px_at(b.normal, 5, 5.5) == (127, 127, 255)                               # its top is flat again
    left, right = px_at(b.normal, 9.5 - 0.25, 4.5), px_at(b.normal, 9.5 + 0.25, 4.5)  # the post's round side turns left and right
    assert left[0] < 100 and right[0] > 155
    glow = np.asarray(b.glow)
    assert glow[int(2.2 * 32), int(8.7 * 32)].tolist() == list(ob.MATERIALS["screen"])  # the screen on the wall
    assert glow[int((7 - 1.35) * 32), 3 * 32].any()                                 # the lamp
    assert not glow[int(7.5 * 32), int(2.5 * 32)].any() and not glow[int(6.6 * 32), 5 * 32].any()   # floor and table give none


def test_a_floor_pattern_is_in_the_guide_and_in_the_line_work_and_changes_no_floor():
    p = plan()
    before = ob.walk_rings(p, start="start")
    p["ground"][0]["pattern"] = {"kind": "boards", "run": "x", "every": 0.5}
    b = ob.render(p)
    a, c = px_at(b.guide, 2.5, 7.25), px_at(b.guide, 2.5, 7.75)                      # two neighbouring boards
    assert a != c and {a, c} == {ob.MATERIALS["plank"], tuple(int(v * 0.9) for v in ob.MATERIALS["plank"])}
    lines = np.asarray(b.lines) > 0
    assert lines[int(7.5 * 32) - 1:int(7.5 * 32) + 2, int(2.5 * 32)].any()           # the joint between them is a line
    assert ob.walk_rings(p, start="start") == before                                 # a pattern is paint, not floor
    p["ground"][0]["pattern"] = {"kind": "checker", "every": 1.0, "alt": "tile"}
    b = ob.render(p)
    assert px_at(b.guide, 2.5, 7.5) != px_at(b.guide, 3.5, 7.5) and px_at(b.guide, 2.5, 7.5) == px_at(b.guide, 3.5, 6.5)
    p["ground"][0]["pattern"] = {"kind": "herringbone"}
    with pytest.raises(ob.PlanError):
        ob.render(p)


def test_a_lit_guide_is_the_guide_with_the_plans_light_on_it():
    p = plan()
    b = ob.render(p)
    assert ob.lit(b).tobytes() == b.guide.tobytes()                                  # no light plan: the guide as it is
    lamp = {"at": [2.5, 7.5], "z": 1.6, "colour": "ffc27a", "power": 1.0, "radius": 3.0}
    light = {"ambient": [0.3, 0.3, 0.3], "lights": [lamp], "contact": 0.0, "bloom": 0.0, "grain": 0.0}
    out = ob.lit(b, light)
    assert out.size == b.guide.size
    lum = lambda im, x, y: sum(px_at(im, x, y))
    near, far = (2.5, 7.5), (10.5, 8.0)                                              # the same boards, under the lamp and out of its reach
    assert px_at(b.guide, *near) == px_at(b.guide, *far)
    assert lum(out, *near) > lum(out, *far) * 2                                      # the lamp makes a pool
    r, g, bl = px_at(out, *near)
    assert r - bl > px_at(b.guide, *near)[0] - px_at(b.guide, *near)[2]              # and a warm one
    assert lum(out, *far) < lum(b.guide, *far)                                       # ambient only: darker than the flat guide
    # "within" is a wall: the lamp lights nothing outside its area
    lamp2 = dict(lamp, within=[2.0, 7.0, 1.0, 1.0])
    walled = ob.lit(b, dict(light, lights=[lamp2]))
    assert px_at(walled, 2.5, 7.5) == px_at(out, 2.5, 7.5)
    assert lum(walled, 3.6, 7.5) < lum(out, 3.6, 7.5)
    # the plan may carry its own light; grain is the same for the same seed and never moves the floor
    p["lighting"] = dict(light, grain=0.02)
    b2 = ob.render(p)
    assert ob.lit(b2, seed=3).tobytes() == ob.lit(b2, seed=3).tobytes() != ob.lit(b2, seed=4).tobytes()
    assert ob.walk_rings(p, start="start") == ob.walk_rings(plan(), start="start")


def test_the_floor_is_shaded_at_the_foot_of_a_thing_and_glow_spills():
    p = plan()
    p["solids"].append({"id": "lamp", "mat": "glow_warm", "cyl": [3, 7, 0.3], "z": 1.2, "h": 0.3, "block": False})
    b = ob.render(p)
    flat = {"ambient": [1.0, 1.0, 1.0], "contact": 0.0, "bloom": 0.0, "grain": 0.0}
    plain = ob.lit(b, flat)
    shaded = ob.lit(b, dict(flat, contact=0.5))
    diff = np.asarray(plain, np.int32).sum(axis=2) - np.asarray(shaded, np.int32).sum(axis=2)
    assert diff.min() >= 0 and diff.max() > 30                                       # shade only ever darkens, and it is there
    floor = (b.height < 0.03)
    assert diff[~floor].max() == 0                                                   # only the floor takes it
    glowing = np.asarray(b.glow).any(axis=2)
    spilled = ob.lit(b, dict(flat, ambient=[0.2, 0.2, 0.2], bloom=0.8))
    dark = ob.lit(b, dict(flat, ambient=[0.2, 0.2, 0.2]))
    more = np.asarray(spilled, np.int32).sum(axis=2) - np.asarray(dark, np.int32).sum(axis=2)
    assert more.min() >= 0 and more[~glowing].max() > 10                             # light reaches past the lamp itself


def test_textures_fill_surfaces_at_a_true_scale_and_change_nothing_else(tmp_path):
    p = plan()
    flat = ob.render(p)
    stripes = np.zeros((64, 64, 3), np.uint8)
    stripes[:32] = (200, 40, 40)                                                     # a red band over a blue band
    stripes[32:] = (40, 40, 200)
    Image.fromarray(stripes, "RGB").save(tmp_path / "stripes.png")
    tex = {"plank": {"image": "stripes.png", "tiles": 2.0}}                          # one repeat = two tiles
    b = ob.render(p, textures=tex, root=tmp_path)
    assert px_at(b.guide, 2.5, 6.5) == (200, 40, 40) and px_at(b.guide, 2.5, 7.5) == (40, 40, 200)   # a band a tile
    assert px_at(b.guide, 2.5, 8.5) == (200, 40, 40) and px_at(b.guide, 8.5, 8.5) == (200, 40, 40)   # and it repeats
    assert px_at(b.guide, 5, 6.5) == px_at(flat.guide, 5, 6.5)                       # the table has no texture: as before
    for name in ("depth", "lines", "over", "normal", "glow"):
        assert getattr(b, name).tobytes() == getattr(flat, name).tobytes(), name     # only the colour changed
    turned = ob.render(p, textures={"plank": {"image": "stripes.png", "tiles": 2.0, "turn": 90}}, root=tmp_path)
    assert px_at(turned.guide, 2.5, 6.5) == px_at(turned.guide, 2.5, 7.5) != px_at(turned.guide, 3.5, 6.5)   # bands run the other way
    tinted = ob.render(p, textures={"plank": {"image": "stripes.png", "tiles": 2.0, "tint": [0.5, 1, 1]}}, root=tmp_path)
    assert px_at(tinted.guide, 2.5, 6.5) == (100, 40, 40)
    p["textures"] = tex                                                              # a plan may carry its own
    assert ob.render(p, root=tmp_path).guide.tobytes() == b.guide.tobytes()
    assert ob.walk_rings(p, start="start") == ob.walk_rings(plan(), start="start")
    with pytest.raises(ob.PlanError):
        ob.render(plan(), textures={"plank": "nowhere.png"}, root=tmp_path)


def test_the_module_names_no_game():
    text = (REPO / "forge" / "layout" / "oblique.py").read_text(encoding="utf-8").lower()
    assert "turing" not in text and "bill" not in text and "sarah" not in text
