"""BUILD 91 — icons and portraits from the models: the jobs against a stand-in for Blender (what they ask it for, what
they keep, what they refuse), the commands (what is made, what waits, what has no model), the sheets and MISSING.md —
and, where a Python with Blender inside is at hand, the real script on a real little model."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge import config as cfgmod
from forge.jobs.common import Context
from forge.threed import modelpics as mp

STAND_IN = r'''
import json, sys
from PIL import Image, ImageDraw
spec = json.loads(open(sys.argv[-1], encoding="utf-8").read())      # (argv[1] is the forge's own script: this stands in for Blender)
if "broken" in spec["model"]:
    print("Blender quit unexpectedly"); sys.exit(1)
px = spec["pixels"]
im = Image.new("RGBA", (px, px), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
if "tiny" in spec["model"]:
    d.ellipse([px * 0.45, px * 0.45, px * 0.55, px * 0.55], fill=(255, 255, 255, 255))
else:
    d.ellipse([px * 0.1, px * 0.1, px * 0.9, px * 0.9], fill=(255, 255, 255, 255) if not spec.get("shape_key") else (255, 200, 60, 255))
im.save(spec["out"])
body = "body" in spec["model"]
print("PICTURE " + json.dumps({"ok": True, "kind": spec["kind"], "view": [spec.get("az"), spec.get("el")], "light": (spec.get("light") or {}).get("preset", "key"),
      "size_m": [1, 1, 1], "armature": body, "motion_used": "Idle_Loop" if body else None, "motions": ["Idle_Loop"] if body else [],
      "expressions": ["Smile", "Brow Up"] if "faces" in spec["model"] else [], "framed_by": "the head bone" if body else None,
      "seconds": 0.1, "blender": "stand-in", "asked": spec}))
'''


@pytest.fixture()
def world(tmp_path):
    """A forge in a folder: a stand-in Blender, a game with a world list, three made things and one that waits."""
    stand = tmp_path / "stand_in.py"
    stand.write_text(STAND_IN, encoding="utf-8")
    base = cfgmod.load()
    cfg = {**base, "paths": {**base["paths"], "jobs": str(tmp_path / "jobs"), "out": str(tmp_path / "out"), "logs": str(tmp_path / "logs"),
                             "games": str(tmp_path / "games")},
           "allow_external_paths": True, "threed": {**(base.get("threed") or {}), "blender_python": [sys.executable, str(stand)]}}
    g = tmp_path / "games" / "g"
    (g / "wanted_3d" / "_state").mkdir(parents=True)
    (g / "pictures").mkdir()
    entries = [{"id": i, "kind": k, "tier": "small_prop" if k == "prop" else "named", "words": "A single thing.", "real_size_m": {"height": 1}}
               for i, k in (("shotgun", "prop"), ("phone", "prop"), ("harmonica", "prop"), ("glasses", "prop"), ("hero_body", "body"), ("faces_body", "body"), ("later_body", "body"))]
    (g / "wanted_3d" / "list.json").write_text(json.dumps({"entries": entries}))
    models = tmp_path / "models"
    models.mkdir()
    for wid in ("shotgun", "phone", "glasses", "hero_body", "faces_body"):
        (models / f"{wid}.glb").write_bytes(b"glTF" + wid.encode())
        (g / "wanted_3d" / "_state" / f"{wid}.json").write_text(json.dumps({"state": "made", "model": str(models / f"{wid}.glb"), "engine": "trellis2", "try": f"t-{wid}"}))
    (g / "wanted_3d" / "_state" / "harmonica.json").write_text(json.dumps({"state": "held"}))
    items = {"pump_shotgun": {"name": "Pump shotgun"}, "burner": {"name": "Burner phone"}, "harp": {"name": "A spare harmonica"},
             "pack_1": {"name": "Pack I"}, "pack_2": {"name": "Pack II"}, "lighter": {"name": "Lucky lighter"}}
    (tmp_path / "items.json").write_text(json.dumps(items))
    (g / "pictures" / "items_to_models.json").write_text(json.dumps({"items_file": str(tmp_path / "items.json"), "size": 128, "items": {
        "pump_shotgun": {"world": "shotgun", "fit": "exact"}, "burner": {"world": "phone", "fit": "near", "note": "a smartphone"},
        "harp": {"world": "harmonica", "fit": "exact"}, "pack_1": {"world": None, "group": "a pack (one model, two tiers)"},
        "pack_2": {"world": None, "group": "a pack (one model, two tiers)"}, "lighter": {"world": None}}, "also": ["glasses"]}))
    (g / "pictures" / "portraits.json").write_text(json.dumps({"size": 96, "portraits": {
        "hero": {"world": "hero_body", "rim": [0.2, 0.9, 1.0]}, "singer": {"world": "faces_body"}, "later": {"world": "later_body"}, "nobody": {"world": None}}}))
    return cfg, tmp_path, models


def ctx_of(cfg, tmp):
    return Context(cfg=cfg, palettes_dir=cfgmod.ROOT / "palettes", root=tmp)


class Args:
    only = None
    again = False


# ------------------------------------------------------------------ the jobs
def test_an_icon_asks_for_one_view_and_one_light_and_comes_back_clean(world):
    cfg, tmp, models = world
    out = tmp / "o"
    out.mkdir()
    res = mp.icon_job({"id": "I", "type": "model_icon", "name": "icon_shotgun", "model": str(models / "shotgun.glb"), "world_id": "shotgun",
                       "game": "g", "slot_name": "pump_shotgun", "size": 128}, ctx_of(cfg, tmp), out)
    im = Image.open(out / "pump_shotgun.png")
    assert im.mode == "RGBA" and im.size == (128, 128) and (out / "contact.png").exists() and res["fills"] > 0.7
    asked = json.loads((out / "_pump_shotgun_spec.json").read_text())
    assert asked["kind"] == "icon" and asked["pixels"] == 256 and asked["az"] == 35.0 and asked["el"] == 22.0 and asked["auto_view"] is True
    a = np.asarray(im).astype(int)
    edge = a[(a[..., 3] > 30) & (a[..., 3] < 220)]
    assert len(edge) and edge[:, :3].min() > 235                        # the see-through edge is still white: no dark fringe
    assert a[64, 64, 3] == 255 and a[2, 2, 3] == 0 and not list(out.glob("*_raw.png"))
    prov = json.loads((out / "prov.json").read_text())
    assert prov["world_id"] == "shotgun" and prov["try"] == "t-shotgun" and "trellis2" in prov["licence_keys"]


def test_an_icon_that_fills_little_of_its_square_says_so(world):
    cfg, tmp, models = world
    (models / "tiny.glb").write_bytes(b"glTF")
    out = tmp / "o"
    out.mkdir()
    res = mp.icon_job({"id": "I", "type": "model_icon", "model": str(models / "tiny.glb"), "slot_name": "speck", "size": 128}, ctx_of(cfg, tmp), out)
    assert res["fills"] < 0.2 and "its own `az` / `el`" in res["notes"][0]


def test_a_portrait_is_lit_by_the_candle_and_takes_every_expression_the_body_has(world):
    cfg, tmp, models = world
    out = tmp / "o"
    out.mkdir()
    res = mp.portrait_job({"id": "P", "type": "model_portrait", "name": "portrait_singer", "model": str(models / "faces_body.glb"), "slot_name": "singer",
                           "size": 96, "rim": [0.78, 0.05, 0.08]}, ctx_of(cfg, tmp), out)
    assert res["outputs"] == ["singer.png", "singer_smile.png", "singer_brow_up.png", "contact.png"] and res["motion"] == "Idle_Loop"
    asked = json.loads((out / "_singer_spec.json").read_text())
    assert asked["kind"] == "portrait" and asked["light"] == {"preset": "candle", "rim": [0.78, 0.05, 0.08]} and asked["level_head"] and asked["smooth"]
    assert json.loads((out / "_singer_smile_spec.json").read_text())["shape_key"] == "Smile"
    assert np.asarray(Image.open(out / "singer_smile.png"))[48, 48, 2] < 100          # the expression's own picture
    out2 = tmp / "o2"
    out2.mkdir()
    res2 = mp.portrait_job({"id": "P2", "type": "model_portrait", "model": str(models / "faces_body.glb"), "slot_name": "singer", "size": 96,
                            "expressions": False}, ctx_of(cfg, tmp), out2)
    assert res2["outputs"] == ["singer.png", "contact.png"]
    out3 = tmp / "o3"
    out3.mkdir()
    res3 = mp.portrait_job({"id": "P3", "type": "model_portrait", "model": str(models / "shotgun.glb"), "slot_name": "thing", "size": 96}, ctx_of(cfg, tmp), out3)
    assert any("no skeleton" in n for n in res3["notes"]) and any("no expressions" in n for n in res3["notes"])


def test_failures_are_said_plainly(world):
    cfg, tmp, models = world
    out = tmp / "o"
    out.mkdir()
    with pytest.raises(FileNotFoundError, match="model not found"):
        mp.icon_job({"type": "model_icon", "model": str(models / "nothing.glb")}, ctx_of(cfg, tmp), out)
    (models / "broken.glb").write_bytes(b"x")
    with pytest.raises(mp.PictureError, match="without a picture of broken.glb"):
        mp.icon_job({"type": "model_icon", "model": str(models / "broken.glb")}, ctx_of(cfg, tmp), out)


# ------------------------------------------------------------------ what is made, what waits, what has no model
def test_a_made_model_is_found_through_the_world_queues_own_record(world):
    cfg, tmp, models = world
    assert mp.made_model(cfg, "g", "shotgun") == (models / "shotgun.glb", "made")
    assert mp.made_model(cfg, "g", "harmonica") == (None, "made, but held by a check")
    assert mp.made_model(cfg, "g", "later_body") == (None, "on the world list, not made yet")
    assert mp.made_model(cfg, "g", "never_listed") == (None, "not on the world list")


def test_the_commands_take_what_is_made_and_list_the_rest(world, monkeypatch):
    cfg, tmp, models = world
    monkeypatch.setattr(cfgmod, "ROOT", tmp)
    icons = mp.cmd_icons(cfg, "g", Args())
    ports = mp.cmd_portraits(cfg, "g", Args())
    files = {f.name for f in mp.write_sheets(cfg, "g", icons, ports)}
    assert files == {"icons_sheet.png", "icons_also_sheet.png", "MISSING.md", "icons.json", "portraits_sheet.png", "portraits.json"}
    dest = tmp / "out" / "pictures" / "g"
    assert sorted(p.name for p in (dest / "icons").glob("*.png")) == ["burner.png", "pump_shotgun.png"]
    assert [p.name for p in (dest / "also").glob("*.png")] == ["glasses.png"]
    assert sorted(p.name for p in (dest / "portraits").glob("*.png")) == ["hero.png", "singer.png", "singer_brow_up.png", "singer_smile.png"]
    assert Image.open(dest / "icons" / "pump_shotgun.png").size == (128, 128)
    missing = (dest / "MISSING.md").read_text()
    assert "**2** have an icon from a made model" in missing and "`harp` (A spare harmonica) -> `harmonica`: made, but held by a check" in missing
    assert "**a pack (one model, two tiers)** - 2 items" in missing and "`lighter` (Lucky lighter)" in missing and "**3** have no model at all" in missing
    assert icons["burner"]["fit"] == "near" and ports["later"]["state"] == "on the world list, not made yet" and ports["nobody"]["state"] == "no body named"
    # the jobs were the forge's own: finished, with their receipts, and nobody else's job was touched
    done = list((tmp / "jobs" / "done").glob("*.json"))
    assert len(done) == 5 and all(json.loads(d.read_text())["batch"].startswith("pictures/") for d in done)
    # a second run takes nothing; a model made again is pictured again; --again takes all
    assert not [j for j in _queued(cfg, tmp, lambda: mp.cmd_icons(cfg, "g", Args()))]
    t = time.time() + 5
    os.utime(models / "shotgun.glb", (t, t))
    assert _queued(cfg, tmp, lambda: mp.cmd_icons(cfg, "g", Args())) == ["icon_pump_shotgun"]
    again = Args()
    again.again = True
    assert sorted(_queued(cfg, tmp, lambda: mp.cmd_icons(cfg, "g", again))) == ["icon_burner", "icon_glasses", "icon_pump_shotgun"]
    only = Args()
    only.only, only.again = ["burner"], True
    assert _queued(cfg, tmp, lambda: mp.cmd_icons(cfg, "g", only)) == ["icon_burner"]


def test_a_portrait_whose_name_begins_like_another_is_not_called_its_expression(world, monkeypatch):
    """`hero` and `hero_boy` are two people. Only the files a portrait's own note names are its expressions."""
    cfg, tmp, models = world
    monkeypatch.setattr(cfgmod, "ROOT", tmp)
    table = tmp / "games" / "g" / "pictures" / "portraits.json"
    t = json.loads(table.read_text())
    t["portraits"] = {"hero": {"world": "hero_body"}, "hero_boy": {"world": "hero_body"}, "singer": {"world": "faces_body"}, "later": {"world": "later_body"}}
    table.write_text(json.dumps(t))
    rows = mp.portrait_rows(mp.cmd_portraits(cfg, "g", Args()))
    assert [(r["label"], r.get("of")) for r in rows] == [("hero", None), ("hero_boy", None), ("singer", None), ("singer_smile", "singer"),
                                                         ("singer_brow_up", "singer"), ("later", None)]     # in the order the body carries them
    assert rows[-1]["image"] is None and rows[-1]["why"] == "on the world list, not made yet"
    note = json.loads((tmp / "out" / "pictures" / "g" / "portraits" / "singer.json").read_text())
    assert sorted(note["files"]) == ["singer.png", "singer_brow_up.png", "singer_smile.png"]


def _queued(cfg, tmp, run):
    before = {p.name for p in (tmp / "jobs" / "done").glob("*.json")}
    run()
    return [json.loads(p.read_text())["name"] for p in (tmp / "jobs" / "done").glob("*.json") if p.name not in before]


def test_the_sheet_marks_a_stand_in_and_an_empty_place():
    white = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    s = mp.sheet([{"image": white, "label": "Pump shotgun", "sub": "rescue_shotgun"}, {"image": white, "label": "1911", "sub": "near", "flag": "near"},
                  {"image": None, "label": "chloe", "sub": "chloe", "flag": "missing", "why": "not made yet"}], "A sheet", cell=64, cols=3, foot=["a foot line"])
    a = np.asarray(s)
    assert s.width == 8 + 3 * 72 and tuple(a[60, 30]) == (255, 255, 255) and tuple(a[60, 8 + 2 * 72 + 30]) != (255, 255, 255)
    assert mp.covered(white) == 1.0 and mp.covered(Image.new("RGBA", (64, 64), (0, 0, 0, 0))) == 0.0


def test_the_job_types_are_a_plug_in():
    from forge import schema
    from forge.jobs import get_handlers
    h = get_handlers(reload=True)
    assert "model_icon" in h and "model_portrait" in h
    assert schema.JOB_TYPES["model_icon"]["needs"] == "cpu" and schema.JOB_TYPES["model_portrait"]["needs"] == "cpu"      # never the card
    assert schema.validate({"type": "model_icon", "model": "a.glb"}) == [] and schema.validate({"type": "model_portrait"}) != []


def test_the_picture_code_names_no_game():
    words = re.compile(r"turing|linden|sarah|valkyrie|chloe|minerva|\bbill(_|\b)", re.I)
    root = Path(mp.__file__).resolve().parent
    for p in (root / "modelpics.py", root / "modelpics_specs.py", root / "blender" / "picture_model.py", cfgmod.ROOT / "docs" / "MODEL_PICTURES.md"):
        if p.is_file():
            assert not words.search(p.read_text(encoding="utf-8")), p.name


# ------------------------------------------------------------------ the real script, where Blender is a Python module
def test_the_real_script_pictures_a_real_little_model(tmp_path):
    pytest.importorskip("bpy")
    make = tmp_path / "make.py"
    make.write_text('''
import bpy, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
if sys.argv[-2] == "bar":
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    bpy.context.active_object.scale = (2.0, 0.3, 0.2)             # a long flat bar lying on the ground, like a rifle
else:                                                             # a post with a ball on top: as tall as a person, a "head" up high
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.75))
    bpy.context.active_object.scale = (0.12, 0.12, 1.5)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(0, 0, 1.65))
m = bpy.data.materials.new("red"); m.use_nodes = True
m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.1, 0.1, 1)
m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
for ob in bpy.data.objects:
    ob.data.materials.append(m)
bpy.ops.export_scene.gltf(filepath=sys.argv[-1])
sys.stdout.flush()
import os; os._exit(0)                                            # (Blender 4.2's Python can fall over while shutting down)
''')
    script = Path(mp.__file__).resolve().parent / "blender" / mp.SCRIPT
    for kind, shape in (("icon", "bar"), ("portrait", "post")):
        glb = tmp_path / f"{shape}.glb"
        assert subprocess.run([sys.executable, str(make), shape, str(glb)], capture_output=True, text=True, timeout=300).returncode == 0 and glb.is_file()
        spec = tmp_path / f"{kind}.json"
        out = tmp_path / f"{kind}.png"
        spec.write_text(json.dumps({"model": str(glb), "out": str(out), "kind": kind, "pixels": 96, "samples": 4}))
        r = subprocess.run([sys.executable, str(script), str(spec)], capture_output=True, text=True, timeout=600)
        said = next((ln for ln in r.stdout.splitlines() if ln.startswith("PICTURE ")), None)
        assert said, r.stdout[-500:] + r.stderr[-500:]
        info = json.loads(said[8:])
        a = np.asarray(Image.open(out))
        assert info["ok"] and a.shape == (96, 96, 4) and a[0, 0, 3] == 0 and a[..., 3].max() == 255       # a clear background, a solid thing
        if kind == "icon":
            assert info["flat"] > 0.5 and info["view"][1] > 40 and info.get("rolled") is True               # seen from above, along the diagonal
            ys, xs = np.nonzero(a[..., 3] > 128)
            assert (xs.max() - xs.min()) > 60 and (ys.max() - ys.min()) > 40                               # it fills its square
            red = a[a[..., 3] > 250]
            assert red[:, 0].mean() > red[:, 1].mean() * 1.6 and red[:, 0].mean() > 90                     # its own colour, lit
        else:
            assert info["framed_by"].startswith("the top of its height") and info["armature"] is False
            ys, xs = np.nonzero(a[..., 3] > 128)
            assert ys.min() > 4 and ys.max() == 95 and 20 < (xs.max() - xs.min()) < 80                     # the top of it, whole, with air over it; the rest runs off below
            lit = a[a[..., 3] > 250][:, :3].astype(float)
            assert lit.max() > 70 and np.percentile(lit.sum(axis=1), 10) < np.percentile(lit.sum(axis=1), 90) * 0.5   # one warm key: a lit side and a dark side


def test_the_resting_motion_is_never_a_crouch(tmp_path):
    """Blender 4.2 names an imported motion "<motion>_<figure>". Asked for Idle_Loop, the script must take
    Idle_Loop_character and not the first name that holds the words (Crouch_Idle_Loop_character) — found by
    running the script under Blender 4.2, 2026-11-19: she crouched."""
    pytest.importorskip("bpy")
    script = Path(mp.__file__).resolve().parent / "blender" / mp.SCRIPT
    probe = tmp_path / "probe.py"
    probe.write_text(f'''
import importlib.util, json, sys
import bpy
spec = importlib.util.spec_from_file_location("picture_model", r"{script}")
pm = importlib.util.module_from_spec(spec); spec.loader.exec_module(pm)
said = {{}}
for names in (["Crouch_Idle_Loop_character", "Idle_Loop_character", "Idle_Talking_Loop_character"], ["Crouch_Idle_Loop", "Idle_Loop", "A_TPose"],
              ["Walk_Loop", "Idle_Torch_Loop"], ["Walk_Loop"]):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = bpy.data.objects.new("rig", bpy.data.armatures.new("rig"))
    bpy.context.scene.collection.objects.link(arm)
    for n in names:
        bpy.data.actions.new(n)
    said[",".join(names)] = pm.pose(arm, "", 0)[0]
print("SAID " + json.dumps(said), flush=True)
import os; os._exit(0)
''')
    r = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True, timeout=300)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("SAID ")), None)
    assert line, r.stdout[-400:] + r.stderr[-800:]
    assert list(json.loads(line[5:]).values()) == ["Idle_Loop_character", "Idle_Loop", "Idle_Torch_Loop", None]
