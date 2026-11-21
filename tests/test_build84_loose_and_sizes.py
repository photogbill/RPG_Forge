"""BUILD 84, 2f and part 6 — loose pieces the queue puts right by itself, and proportions against what was asked.

2f was written from three held models that each said "1 piece not joined to the rest (below the floor)". Looked at, they
were three different things, and each has its test here: a sheet of ground floating under a closure (taken off), an
office chair stood behind a building with its feet through the floor (stood on the floor), and a chandelier's own
centre crystal (a thing that hangs has no floor). A piece in the air where it can be seen is held, as before.

Part 6: an entry may say "length" (the longer side on the ground, whichever way the model turned out), and a thing
whose second measure comes out more than a third from what was asked is held with its numbers.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge import cli_approve
from forge.threed import checks, meshio, world
from forge.threed.meshio import Glb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_world_build39 import _cfg, _list, box_mesh, rot_x, save  # noqa: E402


def _md5(p) -> str:
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def _loose(path, **kw) -> dict:
    return checks.run(path, None, "building", only=("loose",), **kw)["results"][0]


HOUSE = box_mesh((3.0, 2.5, 3.0))


# ------------------------------------------------------------------------------------------------ 2f: under the floor
def test_a_sheet_of_ground_wholly_under_the_floor_is_taken_off(tmp_path):
    sheet = box_mesh((1.6, 0.1, 1.2), at=(0.2, -0.7, 0.3))                     # floats 0.6 under the floor: 6% of the surface
    src = save(tmp_path / "a.glb", [HOUSE, sheet])
    before = _md5(src)
    r = _loose(src)
    assert not r["ok"] and r["loose"][0]["where"] == "below the floor" and r["loose"][0]["fix"] == "off"
    assert r["can_fix"] and 0.03 < r["fix_share"] < 0.10
    fr = checks.fix_loose(src, tmp_path / "a__loose_off.glb")
    assert fr["changed"] and fr["ok"] and fr["left"] == 0 and len(fr["removed"]) == 1 and not fr["lifted"]
    assert _md5(src) == before                                                # the model as made is never changed
    g = Glb.load(tmp_path / "a__loose_off.glb")
    lo, hi = g.bounds()
    assert abs(lo[1]) < 1e-6 and abs(hi[1] - 2.5) < 1e-6                      # it stands on its own floor now
    assert len(g.mesh()["F"]) == len(HOUSE[1])
    assert _loose(tmp_path / "a__loose_off.glb")["ok"]
    words = checks.loose_words(fr)
    assert len(words) == 1 and "taken off by the queue" in words[0] and "wholly under the floor" in words[0]


def test_a_piece_in_the_air_is_still_held_and_nothing_is_written(tmp_path):
    floating = box_mesh((0.6, 0.3, 0.6), at=(0.0, 3.4, 0.0))
    src = save(tmp_path / "b.glb", [HOUSE, floating])
    r = _loose(src)
    assert not r["ok"] and r["loose"][0]["where"] == "in the air" and "fix" not in r["loose"][0] and "can_fix" not in r
    fr = checks.fix_loose(src, tmp_path / "b__loose_off.glb")
    assert not fr["changed"] and not fr["ok"] and fr["left"] == 1 and not (tmp_path / "b__loose_off.glb").exists()
    # one piece under the floor and one in the air: the sheet goes, the piece in the air still holds the thing
    sheet = box_mesh((1.2, 0.1, 1.0), at=(0.0, -0.7, 0.0))
    src = save(tmp_path / "c.glb", [HOUSE, floating, sheet])
    fr = checks.fix_loose(src, tmp_path / "c__loose_off.glb")
    assert fr["changed"] and not fr["ok"] and fr["left"] == 1
    assert _loose(tmp_path / "c__loose_off.glb")["loose"][0]["where"] == "in the air"


def test_too_much_under_the_floor_is_left_for_a_person(tmp_path):
    big = box_mesh((3.0, 0.4, 3.0), at=(0.0, -1.2, 0.0))                       # as wide as the house: far over a tenth of it
    src = save(tmp_path / "d.glb", [HOUSE, big])
    r = _loose(src)
    assert not r["ok"] and r["loose"][0]["fix"] == "off" and r["can_fix"] is False and "too much to take off unasked" in r["line"]
    assert not checks.fix_loose(src, tmp_path / "d__loose_off.glb")["changed"]
    cfg = {"threed": {"checks": {"loose_fix": False}}}                        # and the whole thing is a setting
    sheet = box_mesh((1.6, 0.1, 1.2), at=(0.2, -0.7, 0.3))
    src = save(tmp_path / "e.glb", [HOUSE, sheet])
    assert not checks.fix_loose(src, tmp_path / "e__loose_off.glb", cfg)["changed"]


# ------------------------------------------------------------------------------------------------ 2f: a little through the floor
def test_a_piece_standing_a_little_through_the_floor_is_stood_on_it(tmp_path):
    chair = box_mesh((0.5, 0.6, 0.5), at=(2.4, -0.1, 0.0))                     # stands by itself; its feet 4% of the height under
    src = save(tmp_path / "a.glb", [HOUSE, chair])
    r = _loose(src)
    row = r["loose"][0]
    assert not r["ok"] and row["where"] == "below the floor" and row["fix"] == "lift" and abs(row["lift"] - 0.1) < 1e-3
    assert r["can_fix"] and r["fix_share"] == 0.0
    fr = checks.fix_loose(src, tmp_path / "a__loose_off.glb")
    assert fr["changed"] and fr["ok"] and len(fr["lifted"]) == 1 and not fr["removed"]
    g = Glb.load(tmp_path / "a__loose_off.glb")
    m = g.mesh()
    assert len(m["F"]) == len(HOUSE[1]) + len(chair[1])                       # nothing was taken off
    assert abs(g.bounds()[0][1]) < 1e-6                                       # the thing stands on its own floor
    P = m["P"][len(HOUSE[0]):]
    assert abs(P[:, 1].min()) < 1e-6 and abs(P[:, 1].max() - 0.6) < 1e-6      # and the chair on it, whole
    said = checks.loose_words(fr)[0]
    assert "stood on the floor by the queue" in said and "Look at it in Review" in said      # 6% of the house: no scrap
    small = {"lifted": [{**fr["lifted"][0], "of_main": 0.012}]}
    assert "tidying takes it off altogether" in checks.loose_words(small)[0]
    # deep through the floor is not "a little": held, as before
    deep = box_mesh((0.5, 1.0, 0.5), at=(2.4, -0.5, 0.0))
    r = _loose(save(tmp_path / "b.glb", [HOUSE, deep]))
    assert not r["ok"] and "fix" not in r["loose"][0]


def test_moving_a_piece_respects_the_node_above_it_and_refuses_a_shared_vertex(tmp_path):
    chair = box_mesh((0.5, 0.6, 0.5), at=(2.4, -0.1, 0.0))
    src = save(tmp_path / "a.glb", [HOUSE, chair])
    g = Glb.load(src)
    g.wrap(scale=2.0, rotation=meshio.quat_between([0, 1, 0], [1, 0, 0]))     # the model under a turned, scaled node
    before = g.mesh()["P"].copy()
    sel = np.r_[np.zeros(len(HOUSE[1]), bool), np.ones(len(chair[1]), bool)]
    g.move_faces(sel, (0.0, 0.25, 0.0))
    after = g.mesh()["P"]
    n = len(HOUSE[0])
    assert np.allclose(after[:n], before[:n]) and np.allclose(after[n:] - before[n:], [0.0, 0.25, 0.0], atol=1e-5)
    g2 = Glb.load(src)
    half = np.zeros(len(HOUSE[1]) + len(chair[1]), bool)
    half[:5] = True                                                           # a few triangles of the house: not a piece
    with pytest.raises(ValueError):
        g2.move_faces(half, (0, 1, 0))
    with pytest.raises(ValueError):
        g2.move_faces(np.zeros(3, bool), (0, 1, 0))


# ------------------------------------------------------------------------------------------------ taking triangles out
def test_drop_faces_takes_the_triangles_and_their_vertices_and_keeps_the_rest_as_it_was(tmp_path):
    P, F = box_mesh((2.0, 1.0, 2.0), sub=4)
    uv = (P[:, [0, 2]] - P[:, [0, 2]].min(0)) / np.ptp(P[:, [0, 2]], axis=0)
    tex = Image.fromarray(np.full((16, 16, 3), (150, 130, 90), np.uint8))
    g = Glb.new()
    mat = {"pbrMetallicRoughness": {"baseColorTexture": {"index": g.add_image(tex)}}}
    g.add_mesh_node(P, F, uv, mat, "body")
    slab = box_mesh((1.0, 0.1, 1.0), at=(0.0, -0.8, 0.0), sub=2)
    g.add_mesh_node(slab[0], slab[1], np.zeros((len(slab[0]), 2)), {"pbrMetallicRoughness": {}}, "slab")
    g.save(tmp_path / "two.glb")
    g = Glb.load(tmp_path / "two.glb")
    m = g.mesh()
    drop = np.zeros(len(m["F"]), bool)
    drop[len(F):] = True                                                      # the whole second mesh
    drop[:8] = True                                                           # and a few triangles of the first
    rep = g.drop_faces(drop)
    assert rep == {"faces": len(slab[1]) + 8, "primitives_out": 1}
    g.save(tmp_path / "out.glb")
    g2 = Glb.load(tmp_path / "out.glb")
    m2 = g2.mesh()
    assert len(g2.j["meshes"]) == 1 and all("mesh" not in n or n["mesh"] == 0 for n in g2.j["nodes"])
    assert len(m2["F"]) == len(F) - 8 and m2["P"][:, 1].min() >= -1e-6        # the slab's vertices are gone from the box
    assert m2["F"].max() == len(m2["P"]) - 1 and len(np.unique(m2["F"])) == len(m2["P"])    # no vertex left unused
    # every triangle that stayed has the corners and the texture coordinates it had
    kept = F[8:]
    assert np.allclose(m2["P"][m2["F"]], P[kept], atol=1e-6) and np.allclose(m2["UV"][m2["F"]], uv[kept], atol=1e-6)
    assert g2.texture_image(m2["materials"][0], "baseColorTexture").size == (16, 16)
    with pytest.raises(ValueError):
        Glb.load(tmp_path / "two.glb").drop_faces(np.zeros(5, bool))          # a mask for another file


# ------------------------------------------------------------------------------------------------ 2f: a thing that hangs
def _chandelier(drop_gap=0.06, far=None):
    frame = box_mesh((1.0, 0.25, 1.0), at=(0.0, 1.0, 0.0))                     # the frame, hung high
    drops = [box_mesh((0.08, 0.3, 0.08), at=(x, 1.0 - drop_gap - 0.3, z)) for x, z in ((-0.3, -0.3), (0.3, -0.3), (0.3, 0.3))]
    centre = box_mesh((0.1, 0.45, 0.1), at=(0.0, 1.0 - drop_gap - 0.45, 0.0))  # the longest: it hangs lowest
    parts = [frame] + drops + [centre]
    if far is not None:
        parts.append(box_mesh((0.2, 0.2, 0.2), at=far))
    return parts


def test_a_thing_that_hangs_has_no_floor_its_drops_hang_by_it(tmp_path):
    src = save(tmp_path / "ch.glb", _chandelier())
    as_standing = _loose(src)
    assert not as_standing["ok"]                                              # judged against a floor it is "below the floor"
    r = _loose(src, hangs=True)
    assert r["ok"] and r["hangs"] and len(r["hung"]) == 4 and "it hangs" in r["line"] and max(r["hung"]) < 0.04
    far = _loose(save(tmp_path / "far.glb", _chandelier(far=(0.0, -1.2, 0.0))), hangs=True)
    assert not far["ok"] and far["loose"][0]["where"] == "in the air" and "fix" not in far["loose"][0]
    assert not checks.fix_loose(tmp_path / "far.glb", tmp_path / "far__off.glb", hangs=True)["changed"]


def test_a_thing_that_hangs_keeps_its_drops_when_it_is_tidied(tmp_path, monkeypatch):
    """Tidying takes off every loose piece with fewer than 2% of the largest piece's points — which was nine of a
    chandelier's crystal drops. A thing that hangs is tidied of dust only; an entry's own "scraps" still wins."""
    from forge.threed import tidy
    from forge.threed.env import RigEnv
    cfg = _cfg(tmp_path)
    asked = []
    monkeypatch.setattr(tidy, "tidy", lambda env, src, dst, scraps=0.02, **kw: (asked.append(scraps), {"ok": False, "error": "not run"})[1])
    raw = save(tmp_path / "ch.glb", _chandelier())
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig")
    for e in ({"id": "lamp", "kind": "prop", "words": "a small crystal chandelier", "real_size_m": {"width": 0.6}},
              {"id": "crate", "kind": "prop", "words": "a crate", "real_size_m": {"width": 0.6}},
              {"id": "lamp2", "kind": "prop", "words": "a small crystal chandelier", "real_size_m": {"width": 0.6}, "scraps": 0.05}):
        world.place_final(cfg, e, raw, tmp_path / "out" / e["id"], env=env)
    assert asked == [checks.HANG_SCRAPS, checks.TIDY_SCRAPS, 0.05] and checks.HANG_SCRAPS < 0.005


def test_the_list_says_what_hangs_by_its_words_or_by_its_own_field():
    e = {"kind": "prop", "words": "Hyperrealistic. A single small crystal chandelier: a gilded frame, rows of hanging crystal drops."}
    assert world.is_hanging(e)
    assert not world.is_hanging({**e, "hangs": False})                        # the entry's own word wins
    assert world.is_hanging({"kind": "prop", "words": "a brass lamp", "hangs": True})
    assert not world.is_hanging({"kind": "prop", "words": "a coat rack with a coat hanging from a hook"})
    assert not world.is_hanging({"kind": "body", "words": "a man carrying a chandelier"})


# ------------------------------------------------------------------------------------------------ 2f: in the queue
def _made(tmp_path, cfg, eid, parts, entry=None, engine="pixal3d"):
    """What the queue does with a model just made: check, put right, size, send on. Returns its state."""
    out = tmp_path / "out3d" / "world" / "g1" / eid
    raw = save(out / "models" / f"{eid}__{engine}.glb", parts)
    e = next(x for x in world.load(cfg, "g1")[0] if x["id"] == eid)
    world.write_state(cfg, "g1", eid, {"state": "making", "started": "x", "tries": 1})
    res = world._check_and_place(cfg, "g1", e, out, raw, None, extra={"engine": engine})
    st = world.read_state(cfg, "g1", eid)
    st.update(res)
    world.write_state(cfg, "g1", eid, st)
    return st


def test_the_queue_takes_the_sheet_off_stands_the_chair_up_and_sends_the_thing_on(tmp_path):
    cfg = _cfg(tmp_path)
    _list(tmp_path, [{"id": "closure", "kind": "building", "words": "a concrete closure", "real_size_m": {"height": 5.0}},
                     {"id": "hut", "kind": "building", "words": "a hut", "real_size_m": {"height": 5.0}},
                     {"id": "mast", "kind": "building", "words": "a hut with an aerial", "real_size_m": {"height": 5.0}}])
    sheet = box_mesh((1.6, 0.1, 1.2), at=(0.2, -0.7, 0.3))
    st = _made(tmp_path, cfg, "closure", [HOUSE, sheet])
    assert st["state"] == "made" and "taken off by the queue" in st["checks"][0]
    assert st["loose_fixed"]["removed"][0]["fix"] == "off" and (tmp_path / st["model_as_made"]).exists()
    lo, hi = Glb.load(tmp_path / st["model"]).bounds()
    assert abs(lo[1]) < 1e-4 and abs(hi[1] - 5.0) < 1e-3                      # 5 m is the building's height, not building + gap + sheet
    chair = box_mesh((0.5, 0.6, 0.5), at=(2.4, -0.1, 0.0))
    st = _made(tmp_path, cfg, "hut", [HOUSE, chair])
    assert st["state"] == "made" and "stood on the floor by the queue" in st["checks"][0] and st["loose_fixed"]["lifted"]
    assert abs(Glb.load(tmp_path / st["model"]).bounds()[1][1] - 5.0) < 1e-3
    st = _made(tmp_path, cfg, "mast", [HOUSE, box_mesh((0.6, 0.3, 0.6), at=(0.0, 3.4, 0.0))])
    assert st["state"] == "held" and any("in the air" in w for w in st["why"]) and "loose_fixed" not in st


def test_a_body_is_never_rewritten_for_a_loose_piece(tmp_path):
    cfg = _cfg(tmp_path)
    sheet = box_mesh((1.6, 0.1, 1.2), at=(0.2, -0.7, 0.3))
    raw = save(tmp_path / "body.glb", [HOUSE, sheet])
    res = checks.run(raw, None, "body", "named", cfg, only=("loose",))
    e = {"id": "someone", "kind": "body", "tier": "named"}
    cur, res2, extra = world._put_right(cfg, e, tmp_path, raw, None, res)
    assert cur == raw and "loose_fixed" not in extra and not res2["ok"]       # held as before: its file as made feeds its colours


def test_check_again_releases_what_the_queue_can_now_put_right_without_remaking_it(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    _list(tmp_path, [{"id": "closure", "kind": "building", "words": "a concrete closure", "real_size_m": {"height": 5.0}},
                     {"id": "lamp", "kind": "prop", "words": "a single small crystal chandelier", "real_size_m": {"width": 0.9}},
                     {"id": "mast", "kind": "building", "words": "a hut with an aerial", "real_size_m": {"height": 5.0}},
                     {"id": "someone", "kind": "body", "words": "a man"}])
    out = tmp_path / "out3d" / "world" / "g1"
    held = {"state": "held", "tries": 3, "why": ["Loose pieces: 1 piece not joined to the rest"], "engine": "pixal3d", "adopted": True,
            "check_results": [{"check": "loose", "ok": False}]}
    # a closure that leans 6 degrees as a whole AND has a sheet under it: both are the queue's to put right
    leaning = [(rot_x(np.vstack([HOUSE[0], box_mesh((1.6, 0.1, 1.2), at=(0.2, -0.7, 0.3))[0]]), 6.0),
                np.vstack([HOUSE[1], box_mesh((1.6, 0.1, 1.2), at=(0.2, -0.7, 0.3))[1] + len(HOUSE[0])]))]
    for eid, parts in (("closure", leaning), ("lamp", _chandelier()),
                       ("mast", [HOUSE, box_mesh((0.6, 0.3, 0.6), at=(0.0, 3.4, 0.0))])):
        raw = save(out / eid / f"{eid}__level.glb", parts)
        world.write_state(cfg, "g1", eid, {**held, "model_raw": str(raw.relative_to(tmp_path)).replace("\\", "/")})
    world.write_state(cfg, "g1", "someone", {"state": "held", "why": ["Colours hold: 60%"], "model_raw": "x.glb"})
    before = {eid: _md5(out / eid / f"{eid}__level.glb") for eid in ("lamp", "mast")}
    r = world.check_again(cfg, "g1", ["closure", "lamp", "mast", "someone", "nobody"], "Claude Fable (Lane 2)")
    assert [d["id"] for d in r["made"]] == ["closure", "lamp"] and [d["id"] for d in r["still"]] == ["mast"]
    assert {d["id"] for d in r["left"]} == {"someone", "nobody"} and not r["ok"]
    st = world.read_state(cfg, "g1", "closure")
    assert st["state"] == "made" and st["try"] and st["tries"] == 3 and st["adopted"] and not st["why"]
    assert any("taken off by the queue" in c for c in st["checks"]) and any("straightened by the queue" in c for c in st["checks"])
    assert st["history"][-1]["state"] == "checked again: made" and st["history"][-1]["by"] == "Claude Fable (Lane 2)"
    lamp = world.read_state(cfg, "g1", "lamp")
    assert lamp["state"] == "made" and any("it hangs" in c for c in lamp["checks"]) and "loose_fixed" not in lamp
    assert world.read_state(cfg, "g1", "mast")["state"] == "held"
    assert all(_md5(out / eid / f"{eid}__level.glb") == h for eid, h in before.items())   # what was there is as it was
    tries = list((tmp_path / "games" / "g1" / "threed" / "tries").glob("*/*.json"))
    assert sorted(p.parent.name for p in tries) == ["closure", "lamp"]
    # and from the command line, the way a waiting package's step calls it
    world.write_state(cfg, "g1", "mast", {**held, "model_raw": world.read_state(cfg, "g1", "mast")["model_raw"]})
    code = cli_approve.cmd_world_fix(cfg, ["check-again", "mast", "--game", "g1", "--who", "Claude Fable (Lane 2)"])
    said = capsys.readouterr().out
    assert code == 1 and "still held" in said and "in the air" in said


def test_the_check_picture_shows_the_loose_piece_in_orange(tmp_path):
    src = save(tmp_path / "b.glb", [HOUSE, box_mesh((0.6, 0.3, 0.6), at=(0.0, 3.4, 0.0))])
    r = checks.run(src, None, "building", out_picture=tmp_path / "checks.png", only=("loose",))
    a = np.asarray(Image.open(r["picture"]).convert("RGB")).astype(int)
    orange = (abs(a[..., 0] - 255) < 6) & (abs(a[..., 1] - 120) < 6) & (a[..., 2] < 8)
    assert orange.sum() > 50
    assert "faces" not in r["results"][0] or not isinstance(r["results"][0]["faces"], np.ndarray)    # pixels are never written


def test_every_new_number_is_a_setting():
    assert set(checks.DEFAULTS) >= {"loose_fix", "loose_fix_max_share", "loose_sink_max", "loose_sink_own", "loose_hang_gap",
                                    "size_check", "size_max_off"}
    assert checks.settings({"threed": {"checks": {"size_max_off": 0.5}}})["size_max_off"] == 0.5


# ------------------------------------------------------------------------------------------------ part 6: sizes
def test_length_is_the_longer_side_on_the_ground_whichever_way_the_model_turned_out(tmp_path):
    car_along_z = save(tmp_path / "z.glb", [box_mesh((0.2, 0.25, 1.0))])       # the model lies along z
    car_along_x = save(tmp_path / "x.glb", [box_mesh((1.0, 0.25, 0.2))])       # the same car, turned a quarter
    for src in (car_along_z, car_along_x):
        rep = meshio.place(src, tmp_path / "placed.glb", size={"length": 14.0})
        assert rep["by"] == "length" and abs(max(rep["size_m"]["width"], rep["size_m"]["depth"]) - 14.0) < 1e-3
        assert abs(rep["size_m"]["height"] - 3.5) < 1e-3
    # the fault this is for: a named side on a model that came out the other way round makes it five times too big
    rep = meshio.place(car_along_x, tmp_path / "wrong.glb", size={"depth": 14.0})
    assert rep["size_m"]["width"] > 60
    # height still comes first when an entry gives both
    assert meshio.place(car_along_x, tmp_path / "h.glb", size={"height": 3.5, "length": 99.0})["by"] == "height"
    e = world.normalise({"id": "streetcar", "kind": "prop", "words": "a streetcar", "real_size_m": {"length": 14.0, "volume": 3}})
    assert e["real_size_m"] == {"length": 14.0}


def test_proportions_more_than_a_third_from_what_was_asked_are_held_with_their_numbers():
    s = checks.settings(None)
    lo = np.zeros(3)
    assert checks.size_check(lo, [2, 3, 2], {"height": 3.0}, s) is None                       # one measure: nothing to compare
    ok = checks.size_check(lo, [4.0, 3.0, 9.0], {"height": 3.0, "width": 4.5}, s)             # 4.0 against 4.5: fine
    assert ok["ok"] and ok["by"] == "height" and ok["measures"][0]["made_m"] == 4.0 and "passes" in ok["line"]
    turned = checks.size_check(lo, [9.0, 3.0, 4.0], {"height": 3.0, "width": 4.5}, s)         # the same shed, turned a quarter
    assert turned["ok"] and turned["measures"][0]["made_m"] == 4.0
    bad = checks.size_check(lo, [9.0, 3.0, 8.0], {"height": 3.0, "width": 4.5}, s)            # no side is near 4.5 m
    assert not bad["ok"] and bad["measures"][0]["ratio"] > 1.7 and "more than a third" in bad["line"] and "8.0 m" in bad["line"]
    # length is always the longer ground side: a streetcar that came out as tall as it is long is caught
    car = checks.size_check(lo, [3.0, 3.4, 3.2], {"height": 3.4, "length": 14.0}, s)
    assert not car["ok"] and car["measures"][0]["measure"] == "length" and car["measures"][0]["made_m"] == 3.2
    # width and depth both named: longer with longer, shorter with shorter
    house = checks.size_check(lo, [12.3, 8.1, 12.1], {"height": 8.1, "width": 10.5, "depth": 8.0}, s)
    by = {r["measure"]: r for r in house["measures"]}
    assert by["width"]["ok"] and not by["depth"]["ok"] and by["depth"]["made_m"] == 12.1 and not house["ok"]
    assert checks.size_check(lo, [9.0, 3.0, 8.0], {"height": 3.0, "width": 4.5}, {**s, "size_check": False}) is None


def test_the_queue_holds_a_thing_whose_proportions_are_off_and_a_person_can_let_it_through(tmp_path):
    cfg = _cfg(tmp_path)
    _list(tmp_path, [{"id": "shed", "kind": "building", "words": "a shed", "real_size_m": {"height": 2.5, "width": 3.0}},
                     {"id": "barn", "kind": "building", "words": "a barn", "real_size_m": {"height": 2.5, "width": 9.0}}])
    st = _made(tmp_path, cfg, "shed", [HOUSE])                                # 3 x 2.5 x 3: as asked
    assert st["state"] == "made" and any(c.startswith("Proportions:") and "passes" in c for c in st["checks"])
    st = _made(tmp_path, cfg, "barn", [HOUSE])                                # asked 9 m wide at 2.5 tall; it is 3
    assert st["state"] == "held" and len(st["why"]) == 1 and st["why"][0].startswith("Proportions:") and "9 m wide" in st["why"][0]
    size = next(r for r in st["check_results"] if r["check"] == "size")
    assert size["measures"][0]["asked_m"] == 9.0 and size["measures"][0]["made_m"] == 3.0
    assert world.let_through(cfg, "g1", "barn", "Bill")["ok"] and world.read_state(cfg, "g1", "barn")["state"] == "made"
