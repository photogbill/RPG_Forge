"""BUILD 39 — the world queue: the standing list, the one launcher's loop, size tiers, the checks after every model,
see-through things as cut-out panels, real sizes, people without baked smiles, heads on shared bodies, wrecked versions
and the glow layer. No graphics card: the line runs against the stand-in ComfyUI and a stand-in for Blender; the checks
run on meshes built here to fail each one the way the launch-site run's models did (a leaning building, a floating slab,
a white-mirror windscreen, a fence that lost its mesh). When a real Blender module is at hand (FORGE_TEST_BPY_PYTHON),
the head-joining script runs for real.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge.threed import cardlock, checks, damage, glb, heads, meshio, panels, raster, standin, world
from forge.threed.env import RigEnv
from forge.threed.meshio import Glb

REPO = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures" / "threed"
FAKE_BLENDER = [sys.executable, str(FIX / "fake_blender.py")]
BPY = os.environ.get("FORGE_TEST_BPY_PYTHON", "")


@pytest.fixture(autouse=True)
def _pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))


def _port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def art(tmp_path):
    srv, si, url = standin.serve(tmp_path / "art_comfy", "art", delay=0.02)
    yield si, url
    srv.shutdown()


def _cfg(tmp_path, url="http://127.0.0.1:9", **threed) -> dict:
    (tmp_path / "games" / "g1").mkdir(parents=True, exist_ok=True)
    return {"_root": str(tmp_path), "comfy": {"url": url}, "threed": {"out_root": str(tmp_path / "out3d"),
                                                                       "blender_python": FAKE_BLENDER, **threed}}


def _rigenv(tmp_path) -> RigEnv:
    port = _port()
    cmd = [sys.executable, "-m", "forge.threed.standin", "--kind", "rig", "--port", str(port), "--root", str(tmp_path / "rig"),
           "--delay", "0.02"]
    return RigEnv(root=tmp_path, rig=tmp_path / "rig", port=port, command=cmd, out=tmp_path / "out3d" / "_rig")


# ------------------------------------------------------------------------------------------------ meshes built to fail
def box_mesh(size=(1.0, 1.0, 1.0), at=(0.0, 0.0, 0.0), sub: int = 6):
    """A closed box standing on y = at[1], each face split into sub x sub squares (so checks have points to work with)."""
    w, h, d = size
    P, F = [], []

    def face(origin, u, v):
        base = len(P)
        for j in range(sub + 1):
            for i in range(sub + 1):
                P.append(np.asarray(origin) + u * i / sub + v * j / sub)
        for j in range(sub):
            for i in range(sub):
                a = base + j * (sub + 1) + i
                F.extend([[a, a + 1, a + sub + 2], [a, a + sub + 2, a + sub + 1]])
    x0, y0, z0 = at[0] - w / 2, at[1], at[2] - d / 2
    X, Y, Z = np.array([w, 0, 0.0]), np.array([0, h, 0.0]), np.array([0, 0, d])
    o = np.array([x0, y0, z0])
    face(o, X, Z)
    face(o + Y, Z, X)
    face(o, Y, X)
    face(o + Z, X, Y)
    face(o, Z, Y)
    face(o + X, Y, Z)
    return np.array(P, dtype=np.float64), np.array(F, dtype=np.int64)


def rot_x(P, deg):
    a = np.radians(deg)
    R = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    return P @ R.T


def save(path, parts, material=None, uv=None, textures=None):
    """parts: [(P, F)] -> one .glb (one primitive), optionally with a material whose textures are given as Pillow images."""
    P = np.concatenate([p for p, _ in parts])
    F, base = [], 0
    for p, f in parts:
        F.append(f + base)
        base += len(p)
    F = np.concatenate(F)
    g = Glb.new()
    mat = dict(material or {"pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.5, 0.5, 1], "metallicFactor": 0.0, "roughnessFactor": 1.0}})
    if textures:
        pbr = mat.setdefault("pbrMetallicRoughness", {})
        for slot, img in textures.items():
            pbr[slot] = {"index": g.add_image(img)}
    g.add_mesh_node(P, F, uv if uv is not None else np.zeros((len(P), 2)), mat, "m")
    return g.save(path)


def picture_of(P, F, path, az=30, el=20, extra=None, size=256):
    """A plain picture of a mesh's outline (dark on light grey), the way image-to-3D pictures look; `extra` draws more
    into the outline (the mesh of a fence that the model then loses)."""
    R = raster.view_matrix(az, el)
    scr, _ = raster.project(P, R, size)
    m = raster.rasterize(scr, F, size)[0]
    img = np.full((size, size, 3), 226, np.uint8)
    img[m] = (70, 72, 76)
    if extra is not None:
        extra(img, m)
    Image.fromarray(img).save(path)
    return path


# ------------------------------------------------------------------------------------------------ the checks
def test_sits_level_catches_a_lean_and_reads_a_fence_line_right(tmp_path):
    P, F = box_mesh((2.0, 2.5, 2.0))
    ok = checks.run(save(tmp_path / "level.glb", [(P, F)]), None, "building", only=("level",))
    assert ok["ok"] and ok["results"][0]["tilt_deg"] < 0.5 and ok["lines"][0].startswith("Sits level: 0")
    lean = checks.run(save(tmp_path / "lean.glb", [(rot_x(P, 7.0), F)]), None, "building", only=("level",))
    r = lean["results"][0]
    assert not lean["ok"] and 6.5 <= r["tilt_deg"] <= 7.5 and "held back" in lean["lines"][0] and "Straighten" in lean["lines"][0]
    assert r["leans_as_whole"] and r["between_deg"] < 2
    # upright by its own structure but resting on parts that hang lower (a wall-mounted box with a padlock): passes, noted
    box, fb = box_mesh((0.6, 0.6, 0.25))
    lock, fl = box_mesh((0.08, 0.14, 0.04), at=(0.26, -0.12, 0.14))
    hanging = checks.run(save(tmp_path / "safe.glb", [(box + [0, 0.2, 0], fb), (lock + [0, 0.2, 0], fl)]), None, "prop", only=("level",))
    assert hanging["ok"] and "upright by its own walls" in hanging["lines"][0]
    # a long thin fence: posts reach the ground, the bottom rail is a little higher — across its width nothing is known,
    # and it must not be read as a steep tilt (the launch-site fence once measured 20 degrees this way)
    parts = [box_mesh((0.06, 2.0, 0.06), at=(x, 0.0, 0.0)) for x in (-1.5, -0.5, 0.5, 1.5)]
    parts.append(box_mesh((3.0, 0.05, 0.04), at=(0.0, 0.08, 0.015)))
    parts.append(box_mesh((3.0, 0.05, 0.04), at=(0.0, 1.9, 0.015)))
    fence = checks.run(save(tmp_path / "fence.glb", parts), None, "prop", only=("level",))
    assert fence["ok"] and fence["results"][0]["tilt_deg"] < 1.0
    # a hand prop lies however it likes: no level check
    assert "level" not in checks.which("prop", "hand_prop") and "level" not in checks.which("body", "crowd")


def test_loose_pieces_floating_and_below_the_floor_but_a_standing_post_is_fine(tmp_path):
    house = box_mesh((3.0, 2.5, 3.0))
    floating = box_mesh((0.6, 0.3, 0.6), at=(0.0, 3.4, 0.0))
    r = checks.run(save(tmp_path / "a.glb", [house, floating]), None, "building", only=("loose",))
    assert not r["ok"] and r["results"][0]["loose"][0]["where"] == "in the air" and "not joined" in r["lines"][0]
    under = box_mesh((1.0, 0.2, 0.4), at=(0.0, -0.6, 0.0))
    r = checks.run(save(tmp_path / "b.glb", [house, under]), None, "building", only=("loose",))
    assert not r["ok"] and r["results"][0]["loose"][0]["where"] == "below the floor"
    post = box_mesh((0.1, 2.2, 0.1), at=(2.5, 0.0, 0.0))                    # stands on the ground by itself
    r = checks.run(save(tmp_path / "c.glb", [house, post]), None, "building", only=("loose",))
    assert r["ok"] and "every part is joined" in r["lines"][0]
    crumb = box_mesh((0.03, 0.03, 0.03), at=(0.0, 3.0, 0.0))                 # tidy takes crumbs off: not counted
    assert checks.run(save(tmp_path / "d.glb", [house, crumb]), None, "building", only=("loose",))["ok"]
    # a floating slab must not become the floor of a leaning thing (the launch-site closure)
    slab = rot_x(box_mesh((3.0, 0.6, 3.0))[0], 30.0), box_mesh((3.0, 0.6, 3.0))[1]
    piece = box_mesh((1.2, 0.2, 0.3), at=(0.0, -1.8, 0.0))
    r = checks.run(save(tmp_path / "e.glb", [slab, piece]), None, "building", only=("level", "loose"))
    by = {x["check"]: x for x in r["results"]}
    assert not by["loose"]["ok"] and not by["level"]["ok"] and by["level"]["tilt_deg"] > 20


def _textured_box(tmp_path, name, rough_glass: int):
    """A box whose texture has a white patch; the metal/rough map makes that patch a perfect mirror (or not)."""
    P, F = box_mesh((2.0, 1.2, 4.0), sub=8)
    uv = (P[:, [0, 2]] - P[:, [0, 2]].min(0)) / np.ptp(P[:, [0, 2]], axis=0)   # a top-down projection: good enough
    base = np.full((64, 64, 3), (150, 130, 90), np.uint8)
    base[8:30, 8:56] = (236, 234, 228)                                       # the windscreen: flat near-white
    mr = np.zeros((64, 64, 3), np.uint8)
    mr[..., 1], mr[..., 2] = 200, 0                                          # body paint: rough, not metal
    mr[8:30, 8:56, 1], mr[8:30, 8:56, 2] = rough_glass, 255                  # the glass: metal 1, roughness as given
    mat = {"pbrMetallicRoughness": {"metallicFactor": 1.0, "roughnessFactor": 1.0}}
    return save(tmp_path / name, [(P, F)], mat, uv, {"baseColorTexture": Image.fromarray(base),
                                                     "metallicRoughnessTexture": Image.fromarray(mr)})


def test_blank_glass_is_a_white_mirror_and_only_that(tmp_path):
    bad = checks.run(_textured_box(tmp_path, "truck.glb", 0), None, "prop", only=("glass",))
    assert not bad["ok"] and bad["results"][0]["share"] > 0.05 and "white mirror" in bad["lines"][0]
    fine = checks.run(_textured_box(tmp_path, "truck2.glb", 140), None, "prop", only=("glass",))
    assert fine["ok"] and fine["results"][0]["share"] == 0
    plain = checks.run(save(tmp_path / "plain.glb", [box_mesh()]), None, "prop", only=("glass",))
    assert plain["ok"]


def test_thin_parts_lost_against_the_picture(tmp_path):
    # a frame (posts and rails) whose picture shows chain-link mesh filling it: the model lost the mesh
    parts = [box_mesh((0.08, 2.0, 0.08), at=(x, 0.0, 0.0)) for x in (-1.5, 0.0, 1.5)]
    parts += [box_mesh((3.1, 0.08, 0.08), at=(0.0, y, 0.0)) for y in (0.05, 1.92)]
    P = np.concatenate([p for p, _ in parts])
    F = np.concatenate([f + sum(len(q) for q, _ in parts[:k]) for k, (_, f) in enumerate(parts)])
    model = save(tmp_path / "fence.glb", parts)

    def mesh(img, m):
        ys, xs = np.nonzero(m)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        yy, xx = np.mgrid[y0:y1, x0:x1]
        wire = ((xx + yy) % 6 == 0) | ((xx - yy) % 6 == 0)
        sub = img[y0:y1, x0:x1]
        sub[wire] = (80, 82, 86)
    pic = picture_of(P, F, tmp_path / "fence.png", az=25, el=15, extra=mesh)
    r = checks.run(model, pic, "prop", only=("thin",), out_picture=tmp_path / "fence_checks.png")
    assert not r["ok"] and r["results"][0]["lost"] > 0.25 and "cut-out panel" in r["lines"][0]
    assert (tmp_path / "fence_checks.png").exists()
    # a solid thing against its own outline loses nothing
    B = box_mesh((1.0, 1.4, 0.7))
    rb = checks.run(save(tmp_path / "box.glb", [B]), picture_of(*B, tmp_path / "box.png", az=40, el=20), "prop", only=("thin",))
    assert rb["ok"] and rb["results"][0]["lost"] < 0.1
    # no picture: not checked, and it says so
    assert "not checked" in checks.run(model, None, "prop", only=("thin",))["lines"][0]


def test_the_check_picture_shows_every_check(tmp_path):
    P, F = box_mesh((2.0, 2.0, 2.0))
    r = checks.run(save(tmp_path / "x.glb", [(rot_x(P, 5), F)]), None, "building", out_picture=tmp_path / "x.png")
    assert r["picture"] and Image.open(tmp_path / "x.png").size[0] >= 900
    assert [x["check"] for x in r["results"]] == ["level", "loose", "glass", "thin", "colour"]   # BUILD 40 added colours hold


def test_every_check_number_is_a_setting():
    cfg = {"threed": {"checks": {"level_max_deg": 12.0}}}
    assert checks.settings(cfg)["level_max_deg"] == 12.0 and checks.settings(None)["level_max_deg"] == 2.0
    assert set(checks.DEFAULTS) >= {"level_max_deg", "loose_min_size", "loose_gap", "glass_max_share", "thin_max_lost",
                                    "straighten_up_to_deg"}          # BUILD 40 added the colour and glass-fix settings


# ------------------------------------------------------------------------------------------------ real size, straightened
def test_place_gives_real_size_on_the_floor_and_straightens(tmp_path):
    P, F = box_mesh((0.5, 0.25, 1.0))
    src = save(tmp_path / "pistol.glb", [(P + [3, 2, 1], F)])
    rep = meshio.place(src, tmp_path / "pistol_m.glb", size={"width": 0.19})
    lo, hi = Glb.load(tmp_path / "pistol_m.glb").bounds()
    assert abs((hi - lo)[0] - 0.19) < 1e-4 and abs(lo[1]) < 1e-6 and abs((lo[0] + hi[0]) / 2) < 1e-6 and rep["by"] == "width"
    truck = meshio.place(save(tmp_path / "t.glb", [(P, F)]), tmp_path / "t_m.glb", size={"depth": 5.2})
    assert abs(truck["size_m"]["depth"] - 5.2) < 1e-3                              # a pistol and a truck at their true scale
    leaning = save(tmp_path / "lean.glb", [(rot_x(box_mesh((2.0, 2.5, 2.0))[0], 9.0), box_mesh()[1])])
    q = checks.run(leaning, None, "building", only=("level",))["results"][0]["straighten"]
    meshio.place(leaning, tmp_path / "level.glb", rotation=q, size={"height": 3.0})
    after = checks.run(tmp_path / "level.glb", None, "building", only=("level",))["results"][0]
    assert after["ok"] and after["tilt_deg"] < 0.3
    lo, hi = Glb.load(tmp_path / "level.glb").bounds()
    assert abs((hi - lo)[1] - 3.0) < 1e-3
    # the mesh itself is never rewritten: one node above it
    j = Glb.load(tmp_path / "level.glb").j
    assert j["nodes"][j["scenes"][0]["nodes"][0]]["name"] == "forge_root"


# ------------------------------------------------------------------------------------------------ the list
def _entries(tmp_path, gid="g1", name="list.json", data=None):
    d = tmp_path / "games" / gid / "wanted_3d"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data), encoding="utf-8")
    return d / name


def test_the_list_reads_files_of_every_shape_and_says_what_is_wrong(tmp_path):
    cfg = _cfg(tmp_path)
    _entries(tmp_path, name="a.json", data={"defaults": {"kind": "prop", "first": {"where": "the approach", "order": 2}},
                                            "entries": [{"id": "Jersey Barrier", "words": "a concrete barrier", "real_size_m": {"width": 3}},
                                                        {"id": "crate", "words": "a crate", "rank": -1}]})
    _entries(tmp_path, name="b.json", data=[{"id": "guard_booth", "kind": "building", "words": "a booth", "first": {"order": 1}},
                                            {"id": "crate", "words": "a second crate"},
                                            {"id": "ghost", "kind": "spaceship", "words": "x"}])
    _entries(tmp_path, name="c.json", data={"id": "mast", "kind": "prop", "words": "a lattice mast"})
    (tmp_path / "games" / "g1" / "wanted_3d" / "d.json").write_text("{half saved", encoding="utf-8")
    items, problems = world.merged(cfg, "g1")
    ids = [e["id"] for e in items]
    assert ids == ["guard_booth", "crate", "jersey_barrier", "mast"]      # by first appearance, then rank; no order = last
    by = {e["id"]: e for e in items}
    assert by["jersey_barrier"]["tier"] == "small_prop" and by["guard_booth"]["tier"] == "large_prop"
    assert by["crate"]["words"] == "a crate" and all(e["state"] == "wanted" for e in items)
    assert any("twice" in p for p in problems) and any("spaceship" in p for p in problems) and any("d.json" in p for p in problems)
    with pytest.raises(world.WorldError):
        world.normalise({"id": "x", "kind": "body", "tier": "large_prop", "words": "y"})
    assert world.normalise({"id": "y", "kind": "body", "words": "a man"})["real_size_m"] == {"height": 1.72}


def test_tiers_size_by_tier_and_a_game_overrides_them(tmp_path):
    cfg = _cfg(tmp_path)
    t = world.tiers(cfg, "g1")
    assert (t["principal"]["faces"], t["principal"]["texture"]) == (60000, 2048)
    assert (t["crowd"]["faces"], t["crowd"]["texture"]) == (20000, 1024) and t["crowd"]["measured"]
    assert t["hand_prop"]["faces"] < t["small_prop"]["faces"] < t["large_prop"]["faces"]
    _entries(tmp_path, name="_tiers.json", data={"hand_prop": {"faces": 8000}})
    assert world.tiers(cfg, "g1")["hand_prop"]["faces"] == 8000
    e = world.normalise({"id": "pistol", "kind": "prop", "tier": "hand_prop", "words": "a pistol"})
    assert world.tier_numbers(cfg, "g1", e) == (8000, 512)


def test_people_words_no_baked_smiles():
    w, gone = world.body_words("A young soldier, short hair, always with a smile, broad shoulders. Grinning at the camera.")
    assert w == "A young soldier, short hair, broad shoulders." and set(gone) == {"always with a smile", "Grinning at the camera"}
    assert world.body_words("A woman with a warm smile. Short hair.")[0] == "A woman. Short hair."
    assert world.body_words("a calm face, not smiling, no grin")[0] == "a calm face, not smiling, no grin"     # ruled out: kept
    always, _ = world.standing_words(None, None, "body")
    assert always.endswith(world.PEOPLE_WORDS) or "mouth closed" in always
    assert "smil" not in always.lower().replace("mouth closed", "")
    from forge.threed import rules
    assert any(c["word"] == "smile" for c in rules.look_chips("kind looking, always with a smile"))
    assert not any(c["word"] == "smile" for c in rules.look_chips("relaxed, not smiling"))
    d = json.loads((REPO / "forge" / "threed" / "defaults.json").read_text(encoding="utf-8"))
    assert "mouth closed" in d["blocks"]["pose.threed_body"]


# ------------------------------------------------------------------------------------------------ the loop
def _list(tmp_path, entries, name="needs.json"):
    return _entries(tmp_path, name=name, data={"entries": entries})


def test_the_queue_makes_checks_sizes_and_sends_to_review_with_no_terminal(tmp_path, art):
    si, url = art
    cfg = _cfg(tmp_path, url)
    _list(tmp_path, [{"id": "barrier", "kind": "prop", "tier": "large_prop", "words": "a concrete barrier",
                      "real_size_m": {"width": 3.0}, "first": {"order": 2}},
                     {"id": "booth", "kind": "building", "words": "a guard booth", "real_size_m": {"height": 2.6}, "first": {"order": 1}}])
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False)
    assert t == {"made": 2, "held": 0, "failed": 0, "stopped_by": "nothing left"}
    st = world.read_state(cfg, "g1", "barrier")
    assert st["state"] == "made" and st["checks"] and all("passes" in l or "none" in l or "not checked" in l for l in st["checks"])
    final = tmp_path / st["model"]
    lo, hi = Glb.load(final).bounds()
    assert abs((hi - lo)[0] - 3.0) < 1e-3 and abs(lo[1]) < 1e-6                     # real size, on the floor
    assert (tmp_path / "out3d" / "world" / "g1" / "barrier" / "checks.png").exists()
    # made in order of first appearance: the booth (order 1) first
    hist = [(e["id"], e["st"]["started"]) for e in world.merged(cfg, "g1")[0]]
    assert hist[0][0] == "booth" and hist[0][1] <= hist[1][1]
    # the picture of the booth was painted with the building words, the barrier with the thing words, and at the tier's size
    reqs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((tmp_path / "out3d" / "world" / "g1" / "barrier" / "prompts").glob("*.json"))]
    assert any(any(n.get("inputs", {}).get("target_face_num") == 40000 or n.get("inputs", {}).get("face_count") == 40000
                   or 40000 in n.get("inputs", {}).values() for n in r.values()) for r in reqs)
    # in Review & approve, with the checks and the licence lines of every tool behind it
    tries = list((tmp_path / "games" / "g1" / "threed" / "tries").glob("*/*.json"))
    assert len(tries) == 2
    tr = json.loads(next(p for p in tries if "barrier" in p.name).read_text(encoding="utf-8"))
    assert tr["review"]["state"] == "waiting" and tr["from"] == "world" and "trellis2" in tr["licence_keys"]
    assert tr["steps"]["body"]["model"] == st["model"] and tr["checks"] == st["checks"]
    rep = (tmp_path / "out3d" / "world" / "g1" / "REPORT.txt").read_text(encoding="utf-8")
    assert "2 made" in rep and "barrier" in rep
    beat = json.loads((tmp_path / "out3d" / "world" / "g1" / "_launcher.json").read_text(encoding="utf-8"))
    assert beat["step"] == "stopped" and not world.launcher_state(cfg, "g1")["running"]
    assert "world queue for g1 started" in (tmp_path / "out3d" / "world" / "g1" / "world.log").read_text(encoding="utf-8")


def test_the_list_is_read_again_before_every_item(tmp_path, art, monkeypatch):
    si, url = art
    cfg = _cfg(tmp_path, url)
    _list(tmp_path, [{"id": "first", "kind": "prop", "words": "a crate"}])
    real = world.make

    def make_and_add(*a, **k):
        st = real(*a, **k)
        if a[2]["id"] == "first":                          # someone adds to the list while the launcher runs
            world.add_entry(cfg, "g1", {"id": "added_meanwhile", "kind": "prop", "words": "a barrel"}, who="Bill")
        return st
    monkeypatch.setattr(world, "make", make_and_add)
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False)
    assert t["made"] == 2 and world.read_state(cfg, "g1", "added_meanwhile")["state"] == "made"
    assert json.loads((tmp_path / "games" / "g1" / "wanted_3d" / "added_meanwhile.json").read_text(encoding="utf-8"))["added"]["by"] == "Bill"


def test_stop_waits_for_the_machine_and_failures_wait_their_turn(tmp_path, art):
    si, url = art
    cfg = _cfg(tmp_path, url)
    _list(tmp_path, [{"id": "a_fails", "kind": "prop", "words": "a crate PLANT_FAIL"}, {"id": "b", "kind": "prop", "words": "a box"}])
    # someone else holds the card: the queue waits and says why
    lock = cardlock.CardLock(cfg, "another run", check_others=False)
    lock.acquire()
    try:
        t = world.run(cfg, "g1", once=True, poll=0.05)
        assert t["stopped_by"] == "busy"
        assert "another run" in json.loads((tmp_path / "out3d" / "world" / "g1" / "_launcher.json").read_text(encoding="utf-8"))["waiting"]
        assert world.machine_busy(cfg).startswith("another run has the graphics card")
    finally:
        lock.release()
    # Stop after this one, asked while the launcher runs (here: idle, waiting for the list to grow)
    (tmp_path / "games" / "g2").mkdir(parents=True)
    got = {}
    th = threading.Thread(target=lambda: got.update(world.run(cfg, "g2", poll=0.05, check_machine=False)), daemon=True)
    th.start()
    for _ in range(100):
        if world.launcher_state(cfg, "g2")["running"]:
            break
        time.sleep(0.05)
    assert world.launcher_state(cfg, "g2")["running"]
    world.ask_stop(cfg, "g2", "Bill")
    th.join(10)
    assert got.get("stopped_by") == "asked" and not (tmp_path / "out3d" / "world" / "g2" / "STOP").exists()
    # a stop asked while nothing runs doesn't stop tomorrow's launch
    world.ask_stop(cfg, "g2", "Bill")
    assert world.run(cfg, "g2", until_empty=True, poll=0.05, check_machine=False)["stopped_by"] == "nothing left"
    # a failure is written down and the next thing goes ahead; the failed one waits before its second try
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False)
    assert t["failed"] == 1 and t["made"] == 1
    st = world.read_state(cfg, "g1", "a_fails")
    assert st["state"] == "failed" and st["tries"] == 1 and st["error"] and st["retry_after"] > time.time()
    assert world.next_item(world.merged(cfg, "g1")[0]) is None
    r = world.make_again(cfg, "g1", "a_fails", "Bill")
    assert r["ok"] and world.read_state(cfg, "g1", "a_fails")["state"] == "wanted"
    # the thing that was made went through the tidy step (Blender, here a stand-in) on its way to its real size
    assert world.read_state(cfg, "g1", "b")["tidy"]


def test_the_thing_in_hand_is_taken_up_first(tmp_path):
    cfg = _cfg(tmp_path)
    _list(tmp_path, [{"id": "a", "kind": "prop", "words": "x", "first": {"order": 1}},
                     {"id": "b", "kind": "prop", "words": "y", "first": {"order": 2}}])
    world.write_state(cfg, "g1", "b", {"state": "making", "started": "2026-11-14T03:00:00", "tries": 1})
    assert world.next_item(world.merged(cfg, "g1")[0])["id"] == "b"
    world.set_fields(cfg, "g1", "b", {"hold": True})
    assert world.next_item(world.merged(cfg, "g1")[0])["id"] == "a"


def _held_building(tmp_path, cfg, deg=8.0):
    """A building the queue made and held back for leaning (the way the launch-site comms building came out)."""
    _list(tmp_path, [{"id": "comms", "kind": "building", "words": "a concrete hut", "real_size_m": {"height": 2.6}}])
    P, F = box_mesh((2.0, 2.4, 2.0))
    out = tmp_path / "out3d" / "world" / "g1" / "comms"
    raw = save(out / "models" / "comms__pixal3d.glb", [(rot_x(P, deg), F)])
    e = world.load(cfg, "g1")[0][0]
    world.write_state(cfg, "g1", "comms", {"state": "making", "started": "x", "tries": 1})
    res = world._check_and_place(cfg, "g1", e, out, raw, None, extra={"engine": "pixal3d"})
    st = world.read_state(cfg, "g1", "comms")
    st.update(res)
    world.write_state(cfg, "g1", "comms", st)
    return st


def test_a_building_that_leans_as_a_whole_is_straightened_by_the_queue(tmp_path):
    cfg = _cfg(tmp_path)
    st = _held_building(tmp_path, cfg, deg=8.0)
    assert st["state"] == "made" and 7.5 <= st["auto_straightened_deg"] <= 8.5 and "straightened by the queue" in st["checks"][0]
    after = checks.run(tmp_path / st["model"], None, "building", only=("level",))["results"][0]
    assert after["ok"] and after["tilt_deg"] < 0.5
    assert (tmp_path / "out3d" / "world" / "g1" / "comms" / "models" / "comms__pixal3d.glb").exists()     # the model as made is kept


def test_a_leaning_building_is_held_then_straightened_into_review(tmp_path):
    cfg = _cfg(tmp_path)
    cfg["threed"]["checks"] = {"straighten_up_to_deg": 0}          # every lean held: a person straightens it
    st = _held_building(tmp_path, cfg)
    assert st["state"] == "held" and any("off level" in w for w in st["why"])
    view = world.status(cfg, "g1")["items"][0]
    assert view["shown"] == "held" and view["straighten"]
    r = world.straighten(cfg, "g1", "comms", "Bill", env=RigEnv(root=tmp_path, rig=tmp_path / "rig"), blender_python=FAKE_BLENDER)
    assert r["ok"], r
    st = world.read_state(cfg, "g1", "comms")
    assert st["state"] == "made" and st["straightened"] and st["try"]
    after = checks.run(tmp_path / st["model"], None, "building", only=("level",))["results"][0]
    assert after["tilt_deg"] < 0.5
    with pytest.raises(world.WorldError):
        world.straighten(cfg, "g1", "comms", "Bill")


def test_a_person_can_let_a_held_thing_through(tmp_path):
    cfg = _cfg(tmp_path)
    _held_building(tmp_path, cfg, deg=30.0)
    r = world.let_through(cfg, "g1", "comms", "Bill")
    assert r["ok"]
    st = world.read_state(cfg, "g1", "comms")
    t = json.loads(next((tmp_path / "games" / "g1" / "threed" / "tries").glob("*/*.json")).read_text(encoding="utf-8"))
    assert st["state"] == "made" and "let through by a person" in t["review"]["note"]


def test_a_body_gets_its_skeleton_and_motions_and_no_smile(tmp_path, art):
    si, url = art
    env = _rigenv(tmp_path)
    cfg = _cfg(tmp_path, url)
    lib = glb.box(tmp_path / "lib.glb", (0.5, 1.8, 0.3), motions=["Walk_Loop"], joints=2)
    _list(tmp_path, [{"id": "sentry_one", "kind": "body", "tier": "principal", "real_size_m": {"height": 1.8},
                      "words": "A kind-looking soldier in great shape, always with a smile, short dark hair",
                      "motions": {"library": str(lib), "travel": str(lib)}}])
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False, env=env, blender_python=FAKE_BLENDER)
    assert t["made"] == 1, world.read_state(cfg, "g1", "sentry_one")
    st = world.read_state(cfg, "g1", "sentry_one")
    assert st["model"].endswith("sentry_one_moves.glb") and st["sheet"] and st["fbx"].endswith("__mia.fbx")
    assert "smile" not in st["words_used"] and any("smile" in n for n in st["notes"])
    painted = [p for p in si.seen if any(isinstance(n, dict) and "smile" in json.dumps(n).lower() for n in p.values())]
    sent = json.dumps(si.seen).lower()
    assert "always with a smile" not in sent and "mouth closed" in sent and not painted
    tr = json.loads(next((tmp_path / "games" / "g1" / "threed" / "tries").glob("*/*.json")).read_text(encoding="utf-8"))
    assert tr["kind"] == "body" and tr["steps"]["motions"]["moves"] == st["model"]
    assert {"mia", "quaternius_ual"} <= set(tr["licence_keys"])


def test_see_through_things_are_cut_out_panels(tmp_path):
    cfg = _cfg(tmp_path)
    parts = [box_mesh((0.06, 1.0, 0.06), at=(x, 0.0, 0.0)) for x in (-0.5, 0.0, 0.5)]
    parts += [box_mesh((1.0, 0.03, 0.03), at=(0.0, y, 0.0)) for y in (0.03, 0.95)]
    posts = save(tmp_path / "fence_model.glb", parts)
    _list(tmp_path, [{"id": "fence_chainlink", "kind": "panel", "real_size_m": {"height": 2.4},
                      "panel": {"texture": "standin:chainlink", "from_model": str(posts), "tile_m": 0.5}},
                     {"id": "netting", "kind": "panel", "real_size_m": {"width": 2.0, "height": 1.5}}])
    t = world.run(cfg, "g1", until_empty=True, poll=0.05)                       # no card needed: the machine isn't asked
    assert t["made"] == 2
    st = world.read_state(cfg, "g1", "fence_chainlink")
    g = Glb.load(tmp_path / st["model"])
    mats = g.j["materials"]
    panel = next(m for m in mats if m.get("alphaMode") == "MASK")
    assert panel["doubleSided"] and panel["alphaCutoff"] == 0.5
    tex = g.texture_image(panel, "baseColorTexture")
    a = np.asarray(tex.convert("RGBA"))[..., 3]
    assert 0.08 < (a > 127).mean() < 0.6                                        # wire where the wire is, see-through between
    lo, hi = g.bounds()
    assert abs((hi - lo)[1] - 2.4) < 0.05 and st["stand_in_texture"]
    assert any("image-to-3D checks don't apply" in c for c in st["checks"])
    # a picture with no transparency is keyed: its background colour goes see-through
    keyed = panels.cutout(Image.fromarray(np.dstack([np.full((32, 32), 230, np.uint8)] * 3)))
    assert np.asarray(keyed)[..., 3].max() == 0


def test_a_panel_says_what_made_its_texture_and_its_posts(tmp_path):
    """A real cut-out texture (a Filter Forge render keeps its own transparency) and posts kept from a model the list
    adopted: Review's licence lines name both, and a recorded texture maker lets the panel through."""
    from forge.threed import licences
    cfg = _cfg(tmp_path)
    parts = [box_mesh((0.06, 1.0, 0.06), at=(x, 0.0, 0.0)) for x in (-0.5, 0.0, 0.5)]
    parts += [box_mesh((1.0, 0.03, 0.03), at=(0.0, y, 0.0)) for y in (0.03, 0.95)]
    posts = save(tmp_path / "out" / "trellis" / "run" / "models" / "fence__trellis2.glb", parts)
    tex = tmp_path / "games" / "g1" / "wanted_3d" / "textures" / "chainlink.png"
    tex.parent.mkdir(parents=True, exist_ok=True)
    panels.chainlink_texture(px=128).save(tex)
    _list(tmp_path, [{"id": "fence", "kind": "prop", "adopt": str(posts.relative_to(tmp_path)), "real_size_m": {"height": 2.4},
                      "first": {"order": 1}},
                     {"id": "fence_chainlink", "kind": "panel", "real_size_m": {"height": 2.4}, "first": {"order": 2},
                      "panel": {"texture": "wanted_3d/textures/chainlink.png", "texture_licence": "filter_forge",
                                "from_model": "fence", "tile_m": 0.12}},
                     {"id": "loose_panel", "kind": "panel", "real_size_m": {"height": 2.4}, "first": {"order": 3},
                      "panel": {"texture": "wanted_3d/textures/chainlink.png", "texture_licence": "filter_forge",
                                "from_model": str(posts), "tile_m": 0.12}}])
    world.run(cfg, "g1", until_empty=True, poll=0.05)
    st = world.read_state(cfg, "g1", "fence_chainlink")
    assert not st["stand_in_texture"] and st["texture_licence"] == "filter_forge"
    keys = world.licence_keys(st)
    assert keys[-1] == "filter_forge" and "trellis2" in keys and "comfy_template" in keys
    assert licences.all_ok(keys) and not any("not recorded" in ln for ln in licences.lines(keys))
    # posts from a file nobody recorded keep the panel out of Deliver, and Review says why
    loose = world.licence_keys(world.read_state(cfg, "g1", "loose_panel"))
    assert not licences.all_ok(loose) and any("fence__trellis2.glb: not recorded" in ln for ln in licences.lines(loose))


def test_wrecked_versions_wait_for_the_intact_one_and_glow_is_added(tmp_path, art):
    si, url = art
    cfg = _cfg(tmp_path, url)
    _list(tmp_path, [{"id": "console_wrecked", "kind": "prop", "wreck_of": "console", "damage": {"seed": 3, "strength": 1.0},
                      "first": {"order": 1}},
                     {"id": "console", "kind": "prop", "words": "a launch console", "first": {"order": 2},
                      "glow": {"colours": ["amber"], "strength": 2.0}}])
    items = world.merged(cfg, "g1")[0]
    assert world.next_item(items)["id"] == "console"                 # the wreck waits: its intact version isn't made yet
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False)
    assert t["made"] == 2
    w = world.read_state(cfg, "g1", "console_wrecked")
    assert w["wreck_of"] == "console" and w["damage"]["hits"] >= 1 and "plus damage" in w["checks"][0]
    c = world.read_state(cfg, "g1", "console")
    assert "glow" in c and "Glow layer" in c["checks"][-1]


def test_adopting_a_model_made_before_the_queue(tmp_path):
    cfg = _cfg(tmp_path)
    P, F = box_mesh((1.0, 1.0, 1.0))
    good = save(tmp_path / "out" / "trellis" / "run" / "models" / "crate__trellis2.glb", [(P, F)])
    bad = save(tmp_path / "out" / "trellis" / "run" / "models" / "slab__pixal3d.glb", [(rot_x(P, 25), F)])
    _list(tmp_path, [{"id": "crate", "kind": "prop", "adopt": str(good.relative_to(tmp_path)), "real_size_m": {"width": 0.8}},
                     {"id": "slab", "kind": "building", "adopt": str(bad.relative_to(tmp_path)), "real_size_m": {"width": 4.0}}])
    t = world.run(cfg, "g1", until_empty=True, poll=0.05)                      # checking needs no card
    assert t == {"made": 1, "held": 1, "failed": 0, "stopped_by": "nothing left"}
    assert world.read_state(cfg, "g1", "slab")["engine"] == "pixal3d"
    assert good.read_bytes() == save(tmp_path / "again.glb", [(P, F)]).read_bytes()   # the earlier run's file is untouched


def test_hours_left_at_todays_speed(tmp_path):
    cfg = _cfg(tmp_path)
    _list(tmp_path, [{"id": f"p{k}", "kind": "prop", "words": "x"} for k in range(4)] + [{"id": "b0", "kind": "body", "words": "a man"}])
    est = world.estimate(cfg, "g1")
    assert est["to_make"] == 5 and est["basis"] == "a first guess"
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    world.write_state(cfg, "g1", "p0", {"state": "made", "history": [{"at": now, "state": "made", "seconds": 120}]})
    est = world.estimate(cfg, "g1")
    assert est["to_make"] == 4 and est["speeds"]["prop"] == 120 and "today's speed" in est["basis"]
    assert est["seconds"] == 3 * 120 + world.FIRST_GUESS["body"]


# ------------------------------------------------------------------------------------------------ damage and heads
def test_wreck_dents_punches_and_scorches_the_intact_model(tmp_path):
    P, F = box_mesh((1.0, 1.0, 1.0), sub=12)
    uv = np.c_[(P[:, 0] + 0.5), (P[:, 1])] % 1.0
    src = save(tmp_path / "c.glb", [(P, F)], {"pbrMetallicRoughness": {}}, uv,
               {"baseColorTexture": Image.fromarray(np.full((64, 64, 3), 180, np.uint8))})
    r = damage.wreck(src, tmp_path / "w.glb", seed=2, hits=3, strength=1.0)
    a, b = Glb.load(src), Glb.load(tmp_path / "w.glb")
    ma, mb = a.mesh(), b.mesh()
    assert r["faces_removed"] > 0 and len(mb["F"]) == len(ma["F"]) - r["faces_removed"]
    assert np.abs(ma["P"] - mb["P"]).max() > 0.01 and r["moved_vertices"] > 0
    ta = np.asarray(a.texture_image(a.j["materials"][0], "baseColorTexture").convert("RGB"), float)
    tb = np.asarray(b.texture_image(b.j["materials"][0], "baseColorTexture").convert("RGB"), float)
    assert tb.mean() < ta.mean() - 10                                             # grime and scorch
    assert np.isclose(np.ptp(mb["P"], axis=0), np.ptp(ma["P"], axis=0), atol=0.05).all()   # the same object, the same size


def test_glow_layer_from_the_glow_colours(tmp_path):
    P, F = box_mesh((1.0, 1.0, 1.0))
    uv = np.c_[(P[:, 0] + 0.5), (P[:, 1])] % 1.0
    img = np.full((64, 64, 3), 40, np.uint8)
    img[10:16, 20:30] = (255, 165, 30)                                             # an amber eye
    src = save(tmp_path / "s.glb", [(P, F)], {"pbrMetallicRoughness": {}}, uv, {"baseColorTexture": Image.fromarray(img)})
    r = damage.glow(src, tmp_path / "g.glb", colours=("amber",), strength=3.0)
    g = Glb.load(tmp_path / "g.glb")
    m = g.j["materials"][0]
    assert r["share"] > 0.01 and r["found"] == ["amber"] and "KHR_materials_emissive_strength" in g.j["extensionsUsed"]
    assert m["extensions"]["KHR_materials_emissive_strength"]["emissiveStrength"] == 3.0 and "emissiveTexture" in m
    none = damage.glow(src, tmp_path / "n.glb", colours=("blue",))
    assert none["share"] == 0 and "lost" in none["line"]


def test_heads_join_through_the_stand_in_blender(tmp_path):
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig")
    body = glb.box(tmp_path / "body.glb", (0.5, 1.8, 0.3))
    head = glb.box(tmp_path / "head.glb", (0.3, 0.4, 0.3))
    r = heads.join(env, body, head, tmp_path / "joined.glb", python=FAKE_BLENDER)
    assert r["ok"] and r["report"]["collar_share"] == 0.86 and (tmp_path / "joined.glb").exists()
    assert not heads.join(env, tmp_path / "nobody.glb", head, tmp_path / "x.glb", python=FAKE_BLENDER)["ok"]


def test_a_crowd_body_is_a_head_on_the_shared_body(tmp_path, art):
    si, url = art
    env = _rigenv(tmp_path)
    cfg = _cfg(tmp_path, url)
    lib = glb.box(tmp_path / "lib.glb", (0.5, 1.8, 0.3), motions=["Walk_Loop"], joints=2)
    mot = {"library": str(lib), "travel": str(lib)}
    _list(tmp_path, [{"id": "guard_08", "kind": "body", "tier": "crowd", "shared_body": "guard_body", "first": {"order": 1},
                      "head_words": "a man in his forties, a moustache, grinning", "motions": mot},
                     {"id": "guard_body", "kind": "body", "tier": "crowd", "words": "a guard in a grey uniform", "first": {"order": 2},
                      "motions": mot}])
    t = world.run(cfg, "g1", until_empty=True, poll=0.05, check_machine=False, env=env, blender_python=FAKE_BLENDER)
    assert t["made"] == 2, (world.read_state(cfg, "g1", "guard_08"), world.read_state(cfg, "g1", "guard_body"))
    st = world.read_state(cfg, "g1", "guard_08")
    assert st["shared_body"] == "guard_body" and st["join"]["collar_share"] == 0.86 and st["model"].endswith("guard_08_moves.glb")
    assert any("grinning" in n for n in st["notes"])
    heads_painted = [r for r in si.seen if "head-and-shoulders" in json.dumps(r)]
    assert heads_painted and "grinning" not in json.dumps(heads_painted)


@pytest.mark.skipif(not BPY, reason="needs a Python with bpy (FORGE_TEST_BPY_PYTHON)")
def test_the_head_joining_script_for_real(tmp_path):
    def lathe(profile, n=24):
        P, F = [], []
        for z, r in profile:
            for k in range(n):
                a = 2 * np.pi * k / n
                P.append([r * np.cos(a), z, r * np.sin(a)])
        for i in range(len(profile) - 1):
            for k in range(n):
                a, b = i * n + k, i * n + (k + 1) % n
                F += [[a, b, (i + 1) * n + (k + 1) % n], [a, (i + 1) * n + (k + 1) % n, (i + 1) * n + k]]
        return np.array(P, float), np.array(F)
    body = save(tmp_path / "body.glb", [lathe([(0, 0.08), (0.8, 0.12), (0.9, 0.17), (1.3, 0.2), (1.45, 0.2), (1.5, 0.12),
                                               (1.55, 0.055), (1.6, 0.06), (1.66, 0.1), (1.72, 0.105), (1.8, 0.07), (1.82, 0.01)])])
    head = save(tmp_path / "head.glb", [lathe([(0, 0.25), (0.08, 0.22), (0.12, 0.1), (0.16, 0.07), (0.2, 0.075), (0.28, 0.12),
                                               (0.36, 0.125), (0.44, 0.09), (0.47, 0.01)])])
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig")
    r = heads.join(env, body, head, tmp_path / "joined.glb", python=BPY)
    assert r["ok"], r
    rep = r["report"]
    assert 0.82 < rep["collar_share"] < 0.88 and 0.6 < rep["head_scale"] < 1.1 and 1.6 < rep["height_after_m"] < 2.0
    assert rep["materials"] >= 1


# ------------------------------------------------------------------------------------------------ the suite and the files
def test_the_launcher_is_one_file_nobody_edits_and_the_code_names_no_game():
    bat = (REPO / "make_what_we_need.bat").read_bytes()
    assert b"\r\n" in bat and b"python -m forge 3d world run" in bat and b"comfy-up" in bat
    from forge.suite import runwords
    assert "make_what_we_need" in runwords.__dict__.get("RUNS", runwords.__dict__.get("WORDS", {})) or b"make_what_we_need" in (
        REPO / "forge" / "suite" / "runwords.py").read_bytes()
    banned = ["turing", "sarah", "valkyrie", "minerva", "silo", "boneyard", "mont ross", "sentinel"]
    for f in ("forge/threed/world.py", "forge/threed/checks.py", "forge/threed/panels.py", "forge/threed/damage.py",
              "forge/threed/heads.py", "forge/threed/meshio.py", "forge/threed/raster.py", "forge/threed/blender/join_head.py",
              "forge/suite/world3d.py"):
        low = (REPO / f).read_text(encoding="utf-8").lower()
        assert not [b for b in banned if b in low], (f, [b for b in banned if b in low])
