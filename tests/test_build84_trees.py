"""BUILD 84 part 5 — trees by species: a sheet a species, and each one grows.

Two court trees failed for want of a sheet called "linden", and the towns on the list want trees the one broadleaf sheet
could not be: a live oak, a pecan, a mesquite, an Ashe juniper, a bald cypress, a cottonwood — and three plants no
crown-filling rule can grow at all: a saguaro, an ocotillo, a yucca. Each has its sheet; the grower gained a leaf a species
and three forms. Where this Python has Blender inside (bpy), every one is grown for real and looked at as numbers; anywhere
else the world queue grows each against the stand-in Blender.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from forge.threed import trees, world
from forge.threed.env import RigEnv
from forge.threed.meshio import Glb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_world_build39 import FAKE_BLENDER, _cfg, _list  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "forge" / "threed" / "blender" / "grow_tree.py"
try:
    import bpy  # noqa: F401
    HAVE_BPY = True
except Exception:  # noqa: BLE001
    HAVE_BPY = False

BROADLEAVES = {"linden": "heart", "live_oak": "oval", "pecan": "lance", "mesquite": "feather", "ashe_juniper": "scale",
               "bald_cypress": "feather", "cottonwood": "delta"}
PLANTS = {"saguaro": "column", "ocotillo": "canes", "yucca": "rosette"}
WANTED = sorted([*BROADLEAVES, *PLANTS])


def _sheet(name: str) -> dict:
    return next(s for s in trees.sheets() if s["name"] == name)


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_every_species_the_towns_want_has_its_sheet():
    have = {s["name"]: s for s in trees.sheets()}
    assert set(WANTED) <= set(have) and {"broadleaf", "young_broadleaf"} <= set(have)
    for name in WANTED:
        s = have[name]
        assert s["where"] == "forge" and Path(s["file"]).stem == name and len(s["about"]) > 40
        n = s["numbers"]
        assert 1.0 <= n["height"] <= 40 and (n.get("trunk_radius") or n.get("cane_radius")) > 0
        for k, v in n.items():                              # every number a slider knows is inside the slider's range
            if k in trees.SLIDERS and isinstance(v, (int, float)):
                _, lo, hi, _ = trees.SLIDERS[k]
                assert lo <= v <= hi, (name, k, v)
    for name, leaf in BROADLEAVES.items():
        n = have[name]["numbers"]
        assert n.get("form", "broadleaf") == "broadleaf" and n["leaf"] == leaf
        assert n["crown_floor"] < n["crown_centre_z"] < n["height"] and n["fork_height"] < n["height"]
    for name, form in PLANTS.items():
        assert have[name]["numbers"]["form"] == form
    # a live oak is wider than it is tall, a bald cypress far taller than wide, a mesquite forks at the ground
    lo, bc, mq = (have[k]["numbers"] for k in ("live_oak", "bald_cypress", "mesquite"))
    assert 2 * lo["crown_radius"] > 1.5 * lo["height"] and bc["height"] > 5 * bc["crown_radius"] and mq["fork_height"] < 1.0
    assert bc["flare"] > 1.5                                 # the buttress


def test_the_grower_knows_every_leaf_and_form_a_sheet_asks_for_and_keeps_a_sprig_for_each():
    src = _script_text()
    for name in WANTED:
        n = _sheet(name)["numbers"]
        for k in n:
            assert f'"{k}":' in src, (name, k)             # a number the grower has no default for would be dropped silently
    for leaf in set(BROADLEAVES.values()) - {"heart"}:
        assert f'"{leaf}":' in src
        kept = SCRIPT.with_name(f"sprig_{leaf}.png")       # for a Blender whose Python cannot paint (no Pillow)
        assert kept.exists() and kept.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", leaf
    for form in PLANTS.values():
        assert f'form == "{form}"' in src
    low = src.lower()
    assert not [w for w in ("turing", "sarah", "valkyrie", "tucson", "el paso", "boneyard") if w in low]
    for name in WANTED:
        assert not [w for w in ("turing", "sarah", "valkyrie") if w in json.dumps(_sheet(name)).lower()]


def test_the_world_queue_grows_each_species_and_says_so_when_there_is_no_sheet(tmp_path):
    cfg = _cfg(tmp_path)
    _list(tmp_path, [{"id": f"tree_{name}", "kind": "tree", "species": name, "seed": 3 + i, "real_size_m": {"height": 6.0}}
                     for i, name in enumerate(WANTED)] + [{"id": "tree_baobab", "kind": "tree", "species": "baobab"}])
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig")
    for e in world.load(cfg, "g1")[0]:
        st = world.make(cfg, "g1", e, env=env, blender_python=FAKE_BLENDER)
        if e["id"] == "tree_baobab":
            assert st["state"] == "failed" and "no species sheet called 'baobab'" in st["error"]
            continue
        assert st["state"] == "made" and st["engine"] == "forge_tree", (e["id"], st.get("error"))
        lo, hi = Glb.load(tmp_path / st["model"]).bounds()
        assert abs((hi[1] - lo[1]) - 6.0) < 1e-3 and abs(lo[1]) < 1e-6


@pytest.mark.skipif(not HAVE_BPY, reason="no Blender (bpy) in this Python")
@pytest.mark.parametrize("name", WANTED)
def test_each_species_grows_for_real(tmp_path, name):
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig")
    sheet = _sheet(name)
    g = trees.grow(env, tmp_path / "t", sheet, 11, python=sys.executable, views=1, size=64, samples=1, minutes=5)
    assert g["ok"], g
    glb = Glb.load(g["glb"])
    m = glb.mesh()
    lo, hi = glb.bounds()
    tall, wide = float(hi[1] - lo[1]), float(max(hi[0] - lo[0], hi[2] - lo[2]))
    n = sheet["numbers"]
    assert len(m["F"]) > 1500 and abs(lo[1]) < 0.15 and np.isfinite(m["P"]).all()   # a wide leaning foot dips a hand's width
    prims = [p for me in glb.j["meshes"] for p in me["primitives"]]
    if name in PLANTS:
        assert len(prims) == 1 and "COLOR_0" in prims[0]["attributes"]        # its colours are on the mesh itself
        assert f"'form': '{PLANTS[name]}'" in g["stats"]
        if name == "saguaro":
            assert abs(tall - n["height"]) < 0.3 and wide < 0.6 * tall and "'arms': 3" in g["stats"]
        elif name == "ocotillo":
            assert 0.7 * n["height"] < tall < 1.25 * n["height"] and wide > 0.4 * tall and "'canes': 18" in g["stats"]
        else:
            assert tall > n["height"] and "'heads': 2" in g["stats"]            # the flower stalk stands above the heads
    else:
        assert len(prims) == 2                                                  # the wood, and the leaf cards with their sprig
        assert 0.8 * n["height"] < tall < 1.35 * n["height"]
        assert (tmp_path / "t" / f"{name}_sprig.png").exists()
    if name == "live_oak":
        assert wide > 1.3 * tall
    if name == "bald_cypress":
        assert tall > 1.7 * wide


@pytest.mark.skipif(not HAVE_BPY, reason="no Blender (bpy) in this Python")
def test_one_seed_is_one_tree_and_the_next_seed_is_its_sibling(tmp_path):
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig")
    kw = dict(python=sys.executable, views=1, size=64, samples=1, minutes=5)
    for name in ("saguaro", "mesquite"):
        a = trees.grow(env, tmp_path / "a", _sheet(name), 5, **kw)
        b = trees.grow(env, tmp_path / "b", _sheet(name), 5, **kw)
        c = trees.grow(env, tmp_path / "c", _sheet(name), 6, **kw)
        pa, pb, pc = (Glb.load(x["glb"]).mesh()["P"] for x in (a, b, c))
        assert pa.shape == pb.shape and np.array_equal(pa, pb)
        assert pa.shape != pc.shape or not np.allclose(pa, pc)
    dry = trees.grow(env, tmp_path / "dry", _sheet("ocotillo"), 5, bare=True, **kw)
    wet = trees.grow(env, tmp_path / "wet", _sheet("ocotillo"), 5, **kw)
    assert "'spikes': 0" in dry["stats"] and "'spikes': 18" in wet["stats"]     # bare: the dry months, no flowers
