"""BUILD 87 — materials: Filter Forge's every channel from working copies (proved by what the pictures are, against
stand-in renderers that behave three different ways), one geometry for a whole channel set, Material Maker's command
line and the check of a graph before it runs, named parameters, three seeds mixed, wear as decals, and the sheets."""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge import config as cfgmod
from forge.jobs.common import Context
from forge.materials import ffchannels as F
from forge.materials import look, mix, mm, mmgraph, sheets
from forge.night3b import ffdriver as ff
from forge.ops import lighting

FFXML = """<?xml version="1.0" encoding="utf-8"?>
<Filter>
 <Components>
  <Result id="result"><Source source="x"/><FilterType value="{ft}"/></Result>
  <PerlinNoise2 id="p1" note="map_type=&quot;7&quot; in a component is not a preset"/>
 </Components>
 <Presets>
  <DefaultPreset><Settings size_factor="1" variation="1" seamless="true" antialiasing="2" map_type="0" edges_only="true"/></DefaultPreset>
  <Preset><Settings size_factor="1" variation="5" seamless="true" antialiasing="2" map_type="0" edges_only="true"/><Controls><A v="1"/></Controls></Preset>
  <Preset><Settings size_factor="1.5" variation="9" seamless="false" antialiasing="2" edges_only="true"/></Preset>
 </Presets>
 <Information author="test" name-en="{name}" major_version="1" minor_version="0"/>
</Filter>
"""
LEGACY, PBR = F.MENU["legacy surface"], F.MENU["PBR surface"]


def a_filter(tmp, name="Library_777-1", ft=1):
    p = tmp / "library" / f"{name}.ffxml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(FFXML.format(ft=ft, name="Test Ground").encode("utf-8"))
    return p


def ctx_in(tmp):
    return Context(cfg=cfgmod.load(), palettes_dir=cfgmod.ROOT / "palettes", root=tmp)


def surface(size, seed):
    """A height that tiles, its colour, and its OpenGL normal map (what a filter would be underneath)."""
    h = mix.wrap_noise(size, 3.0, seed).astype(np.float64)
    h = 0.5 + 0.5 * np.sin(h * 6.283)                                   # hills with flanks, so slopes are plain
    hi = Image.fromarray((h * 255).astype(np.uint8)).convert("RGB")
    n = np.asarray(lighting.normal_map(hi, strength=2.0, smooth=1.0)).astype(np.float64) / 255.0
    col = np.stack([0.35 + 0.4 * h, 0.25 + 0.3 * h, 0.15 + 0.15 * h], axis=-1)
    return h, col, n


def stand_in(menu=LEGACY, shift=0, ignores=False, directx=False, seen=None):
    """Stands in for FFXCmdRenderer. It reads each task's filter FILE (the working copy) and renders what that file's
    preset asks for by its map_type — in the menu's order, optionally shifted, or ignoring it altogether."""
    def run(exe, task_file, out, timeout):
        tasks = ET.parse(task_file).getroot().findall("Task")
        for t in tasks:
            fpath = Path(t.find("Filter").get("value"))
            root = ET.parse(fpath).getroot()
            presets = root.findall("Presets/Preset")
            s = presets[int(t.find("Preset").get("value"))].find("Settings")
            k = 0 if ignores else int(s.get("map_type") or 0)
            size = int(t.find("Image").get("width"))
            h, col, n = surface(size, int(s.get("variation") or 1))
            if seen is not None:
                seen.append({"file": str(fpath), "map_type": k, "variation": s.get("variation")})
            name = menu[k - shift] if (k - shift) in range(1, len(menu)) and k >= shift else "final"
            if k == 0:
                name = "final"
            res = t.find("Result").get("path")
            if name == "final":
                shade = 0.55 + 0.45 * (n[..., 0] - 0.5) * 2
                img = np.clip(col * shade[..., None], 0, 1)
            elif name in ("diffuse", "albedo"):
                img = col
            elif name in ("bump", "height"):
                Image.fromarray((h * 65535).astype(np.uint16)).save(res)
                continue
            elif name == "normal":
                img = n.copy()
                if directx:
                    img[..., 1] = 1 - img[..., 1]
            elif name in ("ambient_occlusion", "occlusion"):
                img = np.repeat((0.55 + 0.45 * h)[..., None], 3, axis=2)
            elif name == "roughness":
                img = np.repeat((0.9 - 0.5 * h)[..., None], 3, axis=2)
            elif name in ("metallic", "emission"):
                img = np.zeros((size, size, 3))
            else:                                                       # the specular pair, reflective occlusion
                img = np.repeat((0.2 + 0.6 * h * (0.5 if "strength" in name else 1.0))[..., None], 3, axis=2)
            Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).save(res)
        return 0, f"Tasks completed {len(tasks)}. Tasks failed 0.\n"
    return run


# ------------------------------------------------------------------ the working copy
def test_a_working_copy_sets_every_preset_and_nothing_else(tmp_path):
    data = a_filter(tmp_path).read_bytes()
    new, n = F.working_copy(data, 3)
    assert n == 3                                                       # the default preset and both presets
    root = ET.fromstring(new)
    assert [s.get("map_type") for s in root.iter("Settings")] == ["3", "3", "3"]      # the one without it got it
    assert b'map_type=&quot;7&quot; in a component' in new                 # outside <Presets>: untouched
    i, j = data.index(b"<Presets>"), data.index(b"</Presets>")
    assert new.startswith(data[:i]) and new.endswith(data[j:])            # byte for byte outside the presets
    v, _ = F.working_copy(data, 0, variation=4242)
    assert [s.get("variation") for s in ET.fromstring(v).iter("Settings")] == ["4242"] * 3
    assert [p.find("Controls") is not None for p in ET.fromstring(v).findall("Presets/Preset")] == [True, False]
    with pytest.raises(ff.FilterForgeError):
        F.working_copy(b"<Filter><Components/></Filter>", 1)


def test_copies_go_in_the_jobs_folder_and_come_away_again(tmp_path):
    f = a_filter(tmp_path)
    out = tmp_path / "out" / "J"
    out.mkdir(parents=True)
    made = F.write_copies(f, out, [0, 3])
    assert all(p.is_file() and out in p.parents and p.name == f.name for p in made.values())
    assert f.read_bytes() == FFXML.format(ft=1, name="Test Ground").encode()            # the filter itself: as it was
    assert F.remove_copies(out) == 2 and not (out / F.WORK).exists()


# ------------------------------------------------------------------ the proof
def proof_job(tmp, f, runner, **kw):
    out = tmp / "out" / ("P" + str(len(list((tmp / "out").glob("P*"))) if (tmp / "out").exists() else "0"))
    out.mkdir(parents=True)
    return F.proof({"id": out.name, "type": "ff_channel_proof", "name": "proof", "filter": str(f), "preset": 0, "size": [96, 96], **kw},
                   ctx_in(tmp), out, runner=runner), out


def test_the_proof_names_the_numbers_by_what_the_pictures_are(tmp_path):
    f = a_filter(tmp_path)
    res, out = proof_job(tmp_path, f, stand_in())
    assert res["verdict"] == "yes" and res["filter_type"] == "legacy surface"
    assert res["numbers"]["normal"] == 3 and res["numbers"]["bump"] == 2 and res["numbers"]["ambient_occlusion"] == 7
    assert res["numbers"]["specular_strength"] == 4 and "reflective_occlusion" in res["numbers"]
    assert "slopes agree" in res["evidence"]
    assert (out / "proof.png").exists() and not list(out.rglob("*.ffxml"))             # copies gone after a clean proof
    assert F.learned("legacy surface", tmp_path)["numbers"]["normal"] == 3
    assert json.loads((out / "prov.json").read_text())["working_copies_removed"] == 12


def test_a_renderer_that_ignores_the_number_is_found_out(tmp_path):
    res, out = proof_job(tmp_path, a_filter(tmp_path), stand_in(ignores=True))
    assert res["verdict"] == "no" and "final picture again" in res["evidence"]
    assert F.learned("legacy surface", tmp_path) is None
    assert list(out.rglob("*.ffxml"))                                   # kept, to be looked at


def test_numbers_that_do_not_start_at_one_are_followed(tmp_path):
    res, _ = proof_job(tmp_path, a_filter(tmp_path), stand_in(shift=2))
    assert res["verdict"] == "yes" and res["numbers"]["normal"] == 5 and res["numbers"]["bump"] == 4


def test_a_pbr_filter_has_its_own_order(tmp_path):
    res, _ = proof_job(tmp_path, a_filter(tmp_path, "Library_888-1", ft=2), stand_in(menu=PBR))
    assert res["filter_type"] == "PBR surface" and res["verdict"] == "yes"
    assert res["numbers"]["roughness"] == 4 and res["numbers"]["occlusion"] == 7 and res["numbers"]["height"] == 2
    assert res["numbers"]["emission"] == 6 and res["numbers"]["metallic"] == 5        # flat black, but rendered: they have a number


def test_two_proofs_that_disagree_are_both_kept(tmp_path):
    f = a_filter(tmp_path)
    proof_job(tmp_path, f, stand_in())
    proof_job(tmp_path, f, stand_in(shift=2))
    rec = F.load_store(tmp_path)["types"]["legacy surface"]
    assert rec["conflict"]["normal"] == [3, 5] and len(rec["proofs"]) == 2


# ------------------------------------------------------------------ the channel set
def set_job(tmp, f, runner, name="S", **kw):
    out = tmp / "out" / name
    out.mkdir(parents=True)
    job = {"id": name, "type": "ff_channels", "name": "asphalt", "filter": str(f), "preset": 0, "size": [96, 96],
           "slot_name": "asphalt", "want": ["normal", "height", "roughness", "ambient_occlusion"], **kw}
    return F.render_set(job, ctx_in(tmp), out, runner=runner), out


def test_a_channel_set_is_true_in_register_and_opengl(tmp_path):
    f = a_filter(tmp_path)
    proof_job(tmp_path, f, stand_in())
    seen = []
    res, out = set_job(tmp_path, f, stand_in(directx=True, seen=seen))
    assert sorted(res["true_channels"]) == ["ambient_occlusion", "height", "normal"]
    assert res["channels"]["roughness"].startswith("worked out") and "legacy" in res["channels"]["roughness"]
    for name in ("asphalt.png", "asphalt_n.png", "asphalt_height.png", "asphalt_rough.png", "asphalt_ao.png", "channels.json",
                 "contact.png", "moving_light.png", "tasks.xml"):
        assert (out / name).exists(), name
    assert not (out / "asphalt_metal.png").exists()                     # a metal map of nothing is not written
    n, h = look.load(out / "asphalt_n.png"), look.load(out / "asphalt_height.png")
    assert Image.open(out / "asphalt_height.png").mode.startswith("I")  # 16 bits: no steps in a slope
    assert ff.normal_convention(n, h)["verdict"] == "opengl" and res["measured"]["normal_convention"]["verdict"] == "directx"
    assert not list(out.rglob("*.ffxml")) and len({s["file"] for s in seen}) == len(seen)       # a copy a channel, all gone
    assert sorted(s["map_type"] for s in seen) == [0, 2, 3, 4, 5, 6, 7]
    prov = json.loads((out / "prov.json").read_text())
    assert prov["channels"]["normal"].startswith("true") and "never committed" in prov["filter_licence_note"]


def test_a_set_with_no_proof_on_file_proves_its_own_filter_first(tmp_path):
    res, out = set_job(tmp_path, a_filter(tmp_path), stand_in())
    assert "normal" in res["true_channels"] and any("proving this filter first" in n for n in res["notes"])
    assert F.learned("legacy surface", tmp_path) is not None and (out / "proof.log").exists()


def test_a_renderer_that_ignores_the_number_gives_the_fallback_and_says_so(tmp_path):
    res, out = set_job(tmp_path, a_filter(tmp_path), stand_in(ignores=True))
    assert res["true_channels"] == [] and res["channels"]["normal"].startswith("FALLBACK: guessed from the picture's brightness")
    assert res["channels"]["height"].startswith("MISSING") and (out / "asphalt_n.png").exists()


def test_another_variation_is_another_seed_of_the_same_surface(tmp_path):
    f = a_filter(tmp_path)
    proof_job(tmp_path, f, stand_in())
    seen = []
    _, a = set_job(tmp_path, f, stand_in(), "A")
    _, b = set_job(tmp_path, f, stand_in(seen=seen), "B", variation=7920)
    assert {s["variation"] for s in seen} == {"7920"}
    assert np.abs(look.load(a / "asphalt.png") - look.load(b / "asphalt.png")).mean() > 0.02


def test_beside_only_when_it_is_that_picture_and_never_over_a_file(tmp_path):
    f = a_filter(tmp_path)
    proof_job(tmp_path, f, stand_in())
    lib = tmp_path / "lib"
    lib.mkdir()
    _, first = set_job(tmp_path, f, stand_in(), "first")
    Image.open(first / "asphalt.png").save(lib / "asphalt.png")
    res, _ = set_job(tmp_path, f, stand_in(), "second", beside=str(lib), beside_stem="asphalt", match=str(lib / "asphalt.png"))
    assert sorted(res["delivered"]["written"]) == ["asphalt_ao.png", "asphalt_channels.json", "asphalt_ffnormal.png", "asphalt_height.png", "asphalt_rough.png"]
    assert look.find_set(lib / "asphalt.png")["normal_from"] == "Filter Forge's Normal channel"
    before = (lib / "asphalt_ffnormal.png").read_bytes()
    res2, _ = set_job(tmp_path, f, stand_in(), "third", beside=str(lib), beside_stem="asphalt", match=str(lib / "asphalt.png"))
    assert res2["delivered"]["written"] == [] and len(res2["delivered"]["left"]) == 4 and (lib / "asphalt_ffnormal.png").read_bytes() == before
    Image.fromarray(np.full((96, 96, 3), 90, np.uint8)).save(lib / "gravel.png")
    res3, _ = set_job(tmp_path, f, stand_in(), "fourth", beside=str(lib), beside_stem="gravel", match=str(lib / "gravel.png"))
    assert "not the picture already there" in res3["delivered"]["refused"] and not (lib / "gravel_ffnormal.png").exists()


def test_one_geometry_heals_the_whole_set(tmp_path):
    h, col, n = surface(128, 3)
    cut = lambda a: np.roll(a, 37, axis=1)[:, 9:, ...][:, :112]          # a crop of a tiling picture no longer tiles
    sets = {"final": cut(col)[:112], "normal": cut(n)[:112], "height": cut(h)[:112]}
    out, info = F.tile_together(sets, "final", band=0.2)
    assert out["final"].shape == sets["final"].shape and out["height"].ndim == 2
    assert max(info["after"].values()) < max(info["before"].values())
    assert ff.normal_convention(out["normal"], out["height"][..., None])["red_agreement"] > 0.8     # still on each other
    v = out["normal"] * 2 - 1
    assert abs(float(np.sqrt((v * v).sum(-1)).mean()) - 1.0) < 0.02      # still unit vectors


def test_plans_come_from_the_jobs_that_made_the_pictures(tmp_path):
    f = a_filter(tmp_path)
    lib = tmp_path / "games" / "g" / "ref" / "materials"
    lib.mkdir(parents=True)
    for name in ("asphalt", "dirt_ai", "tin"):
        Image.fromarray(np.full((64, 64, 3), 80, np.uint8)).save(lib / f"{name}.png")
    Image.fromarray(np.full((64, 64, 3), 128, np.uint8)).save(lib / "tin_ffnormal.png")
    for jid, typ in (("j_asphalt", "filter_forge"), ("j_dirt", "tile_texture"), ("j_pick", "filter_forge")):
        d = tmp_path / "out" / jid
        d.mkdir(parents=True)
        (d / "job.json").write_text(json.dumps({"id": jid, "type": typ, "filter": str(f), "preset": 1, "size": [1024, 1024], "seamless": True, "tileable": True}))
        Image.fromarray(np.full((64, 64, 3), 80, np.uint8)).save(d / "texture_final_tile.png")
    (lib / "_sources.json").write_text(json.dumps({"asphalt": {"from": "out/j_asphalt/texture_final.png"}, "dirt_ai": {"from": "out/j_dirt/render.png"},
                                                    "tin": {"from": "out/j_asphalt/texture_final.png"}}))
    plan = F.library_plan(tmp_path, lib)
    assert [j["slot_name"] for j in plan["jobs"]] == ["asphalt"] and plan["already"] == ["tin.png"]
    assert plan["no_filter"][0]["picture"] == "dirt_ai.png"
    j = plan["jobs"][0]
    assert j["preset"] == 1 and j["size"] == [64, 64] and j["tileable"] is False and j["match"].endswith("asphalt.png")
    cull = tmp_path / "cull.json"
    cull.write_text(json.dumps({"picks": [{"id": "9-1", "verdict": "keep", "kind": "tile", "render_dir": "out/j_pick", "use": "texture_final_tile.png", "name": "A"},
                                          {"id": "9-2", "verdict": "cut", "render_dir": "out/j_pick", "use": "texture_final_tile.png"},
                                          {"id": "9-3", "verdict": "keep", "render_dir": "out/j_pick", "use": "needs healing: no healed file exists"}]}))
    pp = F.picks_plan(tmp_path, cull)
    assert len(pp["jobs"]) == 1 and pp["jobs"][0]["tileable"] is True and pp["jobs"][0]["beside_stem"] == "texture_final_tile"
    assert pp["skipped"][0]["id"] == "9-3"


# ------------------------------------------------------------------ Material Maker
LIB = {"perlin": {"params": {"scale_x": {"type": "float", "min": 1, "max": 32}}, "inputs": 0, "outputs": 1, "variadic": False},
       "colorize": {"params": {"gradient": {"type": "gradient"}}, "inputs": 1, "outputs": 1, "variadic": False},
       "blend": {"params": {"amount": {"type": "float", "min": 0, "max": 1}, "blend_type": {"type": "enum", "values": [0] * 15}}, "inputs": 3, "outputs": 1, "variadic": False},
       "material": {"params": {"size": {"type": "size"}, "metallic": {"type": "float", "min": 0, "max": 1}}, "inputs": 9, "outputs": 14, "variadic": False}}


def small_graph():
    g = mmgraph.Graph("t", "T")
    p = g.node("perlin", "noise", scale_x=4)
    c = g.ramp(p, [(0.2, 0.0), (0.6, 1.0)], name="mask")
    b = g.blend(c, p, 0.5, name="layer")
    m = g.node("material", "Material", size=11, metallic=0)
    for port in (0, 2, 4, 5, 6):
        g.link(b, m, port)
    g.named("wear", "how worn", 0.25, {"node": "layer", "param": "amount", "to": [0.0, 0.8]},
            {"node": "mask", "param": "gradient", "point": 1, "key": "pos", "to": [0.9, 0.3]})
    g.side["settings"] = {"broken": {"wear": 1.0}, "mended": {"wear": 0.0}}
    return g


def test_the_command_is_in_the_order_the_program_reads_it(tmp_path):
    cmd = mm.command(Path("D:/forge/engines/material_maker/material_maker.exe"), tmp_path / "a b.ptex", tmp_path, "wall_mm", 2048)
    assert cmd[1] == "--export-material"                                # its parser skips the first word: it must be this one
    assert cmd[cmd.index("-t") + 1] == "Godot/Godot 4 ORM" and cmd[cmd.index("--size") + 1] == "2048"
    assert cmd[cmd.index("--output-file") + 1] == "wall_mm" and cmd[-1].endswith("a b.ptex") and "\\" not in cmd[-1]
    env = mm.data_env(tmp_path)
    assert all(str(tmp_path / "local" / "material_maker_data") in env[k] for k in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"))


def test_a_graph_is_checked_before_material_maker_is_started():
    g = small_graph().to_json()
    assert mm.lint(g, LIB) == []
    bad = json.loads(json.dumps(g))
    bad["nodes"].append({"name": "x", "type": "no_such_node", "parameters": {}})
    bad["connections"].append({"from": "noise", "from_port": 3, "to": "layer", "to_port": 7})
    bad["connections"].append({"from": "layer", "from_port": 0, "to": "noise", "to_port": 0})
    bad["connections"] = [c for c in bad["connections"] if not (c["to"] == "Material" and c["to_port"] == 4)]
    probs = " | ".join(mm.lint(bad, LIB))
    for part in ("'no_such_node' is not in the installed node library", "has only 1 output", "has only 3 input", "make a loop", "normal input is not connected"):
        assert part in probs, part
    old = json.loads(json.dumps(g))
    old["nodes"][0]["parameters"].update(scale_x=40, epsilon=0)
    notes = mm.lint(old, LIB)
    assert len(notes) == 2 and all(n.startswith("note:") for n in notes)   # Material Maker lets these pass; so does the forge


def test_named_parameters_move_the_graph_and_the_seed_moves_it_all():
    gr = small_graph()
    g, side = gr.to_json(), gr.side
    assert mm.values_for(side, None, None) == {"wear": 0.25} and mm.values_for(side, "broken", None) == {"wear": 1.0}
    assert mm.values_for(side, "broken", {"wear": 0.5}) == {"wear": 0.5}
    for bad in ((side, "nope", None), (side, None, {"rust": 1}), (side, None, {"wear": 1.5})):
        with pytest.raises(ValueError):
            mm.values_for(*bad)
    p, sets = mm.patch(g, side, {"wear": 0.5}, seed=0.31, size=1024)
    nodes = {n["name"]: n for n in p["nodes"]}
    assert nodes["layer"]["parameters"]["amount"] == 0.4 and nodes["mask"]["parameters"]["gradient"]["points"][1]["pos"] == 0.6
    assert p["seed"] == 0.31 and nodes["Material"]["parameters"]["size"] == 10 and len(sets) == 2
    assert {n["name"]: n for n in g["nodes"]}["layer"]["parameters"]["amount"] == 0.5        # the graph itself: untouched


def fake_exporter(height_is_depth=False, nothing=False):
    def run(cmd, env, cwd, timeout):
        if nothing:
            return None, "Exporting...\n[stopped]"
        out, name = Path(cmd[cmd.index("-o") + 1]), cmd[cmd.index("--output-file") + 1]
        size = int(cmd[cmd.index("--size") + 1])
        h, col, n = surface(size, 5)
        u8 = lambda a: Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8))
        u8(col).save(out / f"{name}_albedo.png")
        u8(np.stack([0.5 + 0.5 * h, 0.9 - 0.4 * h, np.zeros_like(h)], -1)).save(out / f"{name}_orm.png")
        u8(n).save(out / f"{name}_normal.png")
        u8(1 - h if height_is_depth else h).save(out / f"{name}_heightmap.png")
        return 0, f"Exporting...\nExporting Material x.ptex to {out / name}...\nDone\n"
    return run


def test_material_maker_job_with_a_stand_in(tmp_path):
    gr = small_graph()
    ptex = tmp_path / "wall.ptex"
    ptex.write_text(json.dumps(gr.to_json()))
    ptex.with_suffix(".json").write_text(json.dumps({"label": "A wall", "needs": ["albedo", "roughness", "normal", "ao", "depth"], **gr.side}))
    out = tmp_path / "o"
    out.mkdir()
    job = {"id": "M1", "type": "mm_material", "name": "mm_wall_broken", "graph": str(ptex), "setting": "broken", "seed": 0.5, "size": 128}
    res = mm.render(job, ctx_in(tmp_path), out, runner=fake_exporter())
    for name in ("wall_broken.png", "wall_broken_n.png", "wall_broken_height.png", "wall_broken_rough.png", "wall_broken_ao.png",
                 "wall_broken.ptex", "command.txt", "channels.json", "contact.png", "moving_light.png"):
        assert (out / name).exists(), name
    assert not (out / "wall_broken_metal.png").exists() and res["values"] == {"wear": 1.0}
    sent = json.loads((out / "wall_broken.ptex").read_text())
    assert sent["seed"] == 0.5 and {n["name"]: n for n in sent["nodes"]}["layer"]["parameters"]["amount"] == 0.8
    assert res["measured"]["normal_convention"]["verdict"] == "opengl" and res["commercial_ok"] is True
    assert json.loads((out / "prov.json").read_text())["licences"][0]["license"].startswith("MIT")
    out2 = tmp_path / "o2"
    out2.mkdir()
    res2 = mm.render(job, ctx_in(tmp_path), out2, runner=fake_exporter(height_is_depth=True))
    assert any("white looks LOW" in n for n in res2["notes"])
    out3 = tmp_path / "o3"
    out3.mkdir()
    with pytest.raises(mm.MaterialMakerError, match="did not finish in time"):
        mm.render(job, ctx_in(tmp_path), out3, runner=fake_exporter(nothing=True))


def test_the_forges_own_graphs_hold_together():
    names = sorted(p.stem for p in mm.GRAPHS.glob("*.ptex"))
    assert names == ["ash_crust", "caliche", "canvas", "chalked_wall", "fused_glass", "whitewash_brick"]
    lib = mm.node_library(mm.exe_path(cfgmod.load()).parent)             # the real library, where Material Maker is installed
    for name in names:
        p = mm.GRAPHS / f"{name}.ptex"
        g, side = json.loads(p.read_text(encoding="utf-8")), mm.side_file(p)
        assert {"broken", "mended"} <= set(side["settings"]), name
        nodes = {n["name"]: n for n in g["nodes"]}
        fed = {c["to_port"] for c in g["connections"] if c["to"] == "Material"}
        assert {0, 2, 4, 5, 6} <= fed, name                              # colour, roughness, normal, occlusion, depth
        for st in side["settings"]:
            pg, sets = mm.patch(g, side, mm.values_for(side, st, None), 0.2, 2048)
            assert sets and all(s["node"] in nodes for s in sets)
            if lib:
                assert mm.lint(pg, lib) == [], (name, st)
        a, b = (mm.patch(g, side, mm.values_for(side, s, None))[0] for s in ("broken", "mended"))
        assert a != b and [n["name"] for n in a["nodes"]] == [n["name"] for n in b["nodes"]]      # one graph, two states
    if not lib:
        pytest.skip("Material Maker is not installed here: the graphs were not checked against its node library")


# ------------------------------------------------------------------ no repeats, and wear as a layer
def a_set(size, seed):
    h, col, n = surface(size, seed)
    return {"colour": col, "normal": n, "height": h, "roughness": 0.9 - 0.4 * h, "ambient_occlusion": 0.6 + 0.4 * h,
            "metallic": np.zeros_like(h), "how": {}}


def test_three_seeds_mixed_do_not_repeat_and_still_tile():
    sets = [a_set(64, s) for s in (1, 2, 3)]
    mixed, mask = mix.mix_sets(sets, repeat=2, seed=4)
    assert mixed["colour"].shape == (128, 128, 3) and mask.shape == (128, 128, 3)
    assert np.allclose(mask.sum(axis=2), 1.0, atol=1e-4) and mask.reshape(-1, 3).mean(axis=0).min() > 0.15      # each seed shows
    tiled = np.tile(sets[0]["colour"], (2, 2, 1))
    assert mix.repeat_score(tiled, 64) > 0.99 and mix.repeat_score(mixed["colour"], 64) < 0.6
    assert max(ff.seam_score(mixed["colour"]).values()) < 1.6            # the mix tiles at its own, wider, period
    v = mixed["normal"] * 2 - 1
    assert abs(float(np.sqrt((v * v).sum(-1)).mean()) - 1.0) < 0.01
    with pytest.raises(ValueError):
        mix.mix_sets(sets[:1])


def test_the_mix_job_writes_the_set_and_the_mask(tmp_path):
    paths = []
    for i in (1, 2, 3):
        s = a_set(64, i)
        p = tmp_path / f"gravel_{i}.png"
        look.save(s["colour"], p)
        look.save(s["normal"], p.with_name(p.stem + "_n.png"))
        look.save(s["height"], p.with_name(p.stem + "_height.png"), 16)
        paths.append(str(p))
    out = tmp_path / "o"
    out.mkdir()
    res = mix.mix_job({"id": "X", "type": "material_mix", "inputs": paths, "slot_name": "gravel_mix", "repeat": 2}, ctx_in(tmp_path), out)
    for name in ("gravel_mix.png", "gravel_mix_n.png", "gravel_mix_height.png", "gravel_mix_rough.png", "gravel_mix_mixmask.png", "contact.png"):
        assert (out / name).exists(), name
    assert res["measured"]["repeat_of_the_mix"] < res["measured"]["repeat_of_one_seed"] and Image.open(out / "gravel_mix.png").size == (128, 128)


def test_a_decal_fades_out_carries_its_own_relief_and_leaves_the_ground_alone():
    pic = np.ones((96, 96, 3))
    pic[20:76, 44:52] = 0.1                                             # a dark crack on white, running off toward the edges
    pic[:, 46:50] = 0.1
    d = mix.make_decal(pic, "dark", tint=(0.03, 0.03, 0.03), relief="cut")
    a = d["colour"][..., 3]
    assert a[48, 48] > 0.9 and a[0].max() < 0.01 and a[:, 0].max() < 0.01 and a[2, 48] < 0.1       # solid in the middle, gone at the border
    assert d["colour"][48, 48, :3].max() < 0.05 and "cut" in d["how"]["normal"]
    n = d["normal"][..., :3]
    assert abs(n[48, 43, 0] - 0.5) > 0.03 and np.allclose(n[5, 5], (0.5, 0.5, 1.0), atol=0.01)       # tilted at the crack's lip only
    ground = mix.flat_ground(192, (0.3, 0.3, 0.3))
    keep = ground["colour"].copy()
    worn = mix.lay(ground, [{"decal": d, "at": (0.5, 0.5), "size": 0.5, "turn": 30}])
    assert np.array_equal(ground["colour"], keep) and worn["colour"][96, 96].max() < 0.1 and np.allclose(worn["colour"][5, 5], 0.3)
    assert mix.alpha_of(np.dstack([pic, np.zeros((96, 96))]), "alpha").max() == 0
    smoke = np.zeros((96, 96, 3))
    smoke[30:60, 30:60] = 0.8
    assert mix.alpha_of(smoke, "light")[45, 45] > 0.9 and mix.alpha_of(smoke, "light")[5, 5] == 0
    runs = mix.streaks(96, seed=2)
    assert runs.max() > 0.5 and runs[:2].max() < 0.2 and runs[30:].mean() > runs[:3].mean()          # they start below the top and run down


def test_the_decal_job_and_a_place_with_its_wear_on_and_off(tmp_path):
    pic = np.ones((96, 96, 3))
    pic[:, 44:52] = 0.2
    look.save(pic, tmp_path / "crack.png")
    out = tmp_path / "o"
    out.mkdir()
    res = mix.decal_job({"id": "D", "type": "material_decal", "name": "decal_crack", "input": str(tmp_path / "crack.png"), "slot_name": "crack",
                         "tint": [0.02, 0.02, 0.02]}, ctx_in(tmp_path), out)
    assert res["covers"] > 0.02 and all((out / f"crack_decal{e}.png").exists() for e in ("", "_n", "_rough"))
    assert Image.open(out / "crack_decal.png").mode == "RGBA" and mix.load_decal(out / "crack_decal.png")["normal"].shape[2] == 4
    # a place: a road on grass; the same ground twice, only the list of decals different
    road, grass = a_set(64, 1), a_set(64, 2)
    for name, s in (("road", road), ("grass", grass)):
        look.save(s["colour"], tmp_path / f"{name}.png")
    plan = {"name": "A street", "background": "grass", "ground": [{"mat": "road", "rect": [0, 4, 20, 6]}, {"mat": "kerb", "rect": [0, 3.8, 20, 0.2]}]}
    (tmp_path / "street.place.json").write_text(json.dumps(plan))
    game = {"licences": ["a licence line"], "places": {"street": {
        "plan": "street.place.json", "window": [0, 0, 20, 14], "stand": [10, 13], "eye_m": 1.7, "looks_at": [10, 6],
        "materials": {"road": {"picture": "road.png", "tile_m": 4}, "grass": {"picture": "grass.png", "tile_m": 2}},
        "decals": {"crack": {"picture": "crack.png", "alpha_from": "dark", "tint": [0.02, 0.02, 0.02]}},
        "layers": {"War": [{"decal": "crack", "at": [10, 7], "size_m": 4, "turn": 15}], "After": []}}}}
    views, top, notes = sheets.place_pictures(tmp_path, game, "street", {}, px_per_m=16, size=(320, 180))
    assert set(views) == {"War", "After"} and views["War"].size == views["After"].size == (320, 200)
    w, a = np.asarray(views["War"]).astype(int), np.asarray(views["After"]).astype(int)
    changed = np.abs(w - a).sum(axis=2)[:180] > 12
    assert 0.002 < changed.mean() < 0.4                                 # something changed, and only somewhere
    assert any("kerb" in n for n in notes) and any("guessed" in n for n in notes)


def test_the_lamp_shows_relief_and_roughness():
    s = a_set(96, 4)
    flat = dict(s, normal=np.broadcast_to(np.array([0.5, 0.5, 1.0]), s["normal"].shape).copy())
    assert np.abs(look.lit_plane(s, (0.3, 0.3), size=96) - look.lit_plane(flat, (0.3, 0.3), size=96)).mean() > 0.01
    assert np.abs(look.lit_plane(s, (0.2, 0.2), size=96) - look.lit_plane(s, (0.8, 0.8), size=96)).mean() > 0.02
    glossy = dict(flat, roughness=np.full((96, 96), 0.08))
    assert look.lit_plane(glossy, (0.5, 0.5), size=96).max() > look.lit_plane(flat, (0.5, 0.5), size=96).max()
    ball = look.lit_ball(s, 96)
    assert ball.shape == (96, 96, 3) and ball[48, 48].mean() > ball[2, 2].mean()
    strip = look.moving_light(flat, s, "a floor", cell=64)
    assert strip.width > 4 * 64 and strip.height > 2 * 64


def test_a_town_sheet_shows_what_is_there_and_names_what_is_not(tmp_path):
    d = tmp_path / "out" / "pick1"
    d.mkdir(parents=True)
    s = a_set(64, 1)
    look.save(s["colour"], d / "texture_final_tile.png")
    cull = tmp_path / "cull.json"
    cull.write_text(json.dumps({"picks": [{"id": "1-1", "verdict": "keep", "render_dir": "out/pick1", "use": "texture_final_tile.png", "name": "Asphalt"},
                                          {"id": "2-1", "verdict": "keep", "render_dir": "out/pick1", "use": "needs healing"}]}))
    index = sheets.pick_index(tmp_path, cull)
    game = {"licences": ["renders cleared", "MIT"], "states": {"War": "broken", "After": "mended"},
            "towns": {"t": {"label": "A town", "materials": [{"word": "asphalt", "picks": ["1-1"]}, {"word": "tin", "picks": ["2-1", "3-1"]},
                                                             {"word": "canvas", "graph": "canvas"}, {"word": "brass"}]}}}
    img, missing = sheets.town_sheet(tmp_path, game, "t", index, 64)
    assert img is not None and img.height > 200 and len(missing) == 5
    assert {m["word"] for m in missing} == {"tin", "canvas", "brass"} and any("not been exported" in m["why"] for m in missing)
    look.save(s["normal"], d / "texture_final_tile_ffnormal.png")
    rows, _ = sheets.town_rows(tmp_path, game, "t", index, 64)
    assert len(rows) == 1


# ------------------------------------------------------------------ the plug-in and the commands
def test_the_job_types_are_a_plug_in_and_validate():
    from forge import schema
    from forge.jobs import get_handlers
    h = get_handlers(reload=True)
    for t in ("ff_channel_proof", "ff_channels", "mm_material", "material_mix", "material_decal"):
        assert t in h and schema.JOB_TYPES[t]["needs"] in ("cpu", "gpu"), t
    assert schema.validate({"type": "ff_channels", "filter": "x.ffxml"}) == []
    assert schema.validate({"type": "mm_material"}) != []
    assert schema.JOB_TYPES["mm_material"]["needs"] == "gpu" and schema.JOB_TYPES["ff_channels"]["needs"] == "cpu"


def test_a_command_runs_its_own_batch_and_leaves_the_rest_waiting(tmp_path, monkeypatch):
    from forge.materials import __main__ as M
    from forge.queue import Queue
    cfg = cfgmod.load()
    cfg = {**cfg, "paths": {**cfg["paths"], "jobs": str(tmp_path / "jobs"), "out": str(tmp_path / "out"), "logs": str(tmp_path / "logs")},
           "allow_external_paths": True}
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    other = q.submit({"type": "contact_sheet", "name": "someone_elses", "inputs": ["a.png"], "batch": "places"})
    pic = np.ones((64, 64, 3))
    pic[:, 28:36] = 0.1
    look.save(pic, tmp_path / "crack.png")
    jobs = [{"type": "material_decal", "name": "decal_crack", "input": str(tmp_path / "crack.png"), "slot_name": "crack"},
            {"type": "material_decal", "name": "decal_gone", "input": str(tmp_path / "nothing.png")}]
    rows = M.submit_and_run(cfg, jobs, "materials/decals")
    assert [r["ok"] for r in rows] == [True, False] and "not found" in rows[1]["error"]
    assert (tmp_path / "jobs" / "pending" / f"{other}.json").exists()   # not ours: exactly where it was
    assert len(list((tmp_path / "jobs" / "done").glob("*.json"))) == 1 and len(list((tmp_path / "jobs" / "failed").glob("*.json"))) == 1
    order = M.towns_first([{"name": "channels_pick_1-1"}, {"name": "channels_pick_2-1"}, {"name": "channels_pick_3-1"}, {"name": "channels_pick_4-1"}],
                          {"towns": {"t": {"materials": [{"word": "a", "picks": ["3-1"]}]}}, "places": {"p": {"materials": {"road": {"pick": "4-1"}}}}})
    assert [j["name"][-3:] for j in order] == ["3-1", "4-1", "1-1", "2-1"]      # what a sheet waits for first; the rest in their order
    again = M.submit_and_run(cfg, jobs, "materials/decals")
    assert [r["name"] for r in again] == ["decal_gone"]                 # the finished one is not made twice


def test_the_materials_code_names_no_game():
    words = re.compile(r"turing|linden|augusta|fayetteville|sarah|valkyrie", re.I)
    base = Path(mm.__file__).resolve().parent
    for p in list(base.rglob("*.py")) + list(base.rglob("*.json")) + list(base.rglob("*.ptex")) + [cfgmod.ROOT / "docs" / "MATERIALS.md"]:
        if p.is_file():
            assert not words.search(p.read_text(encoding="utf-8")), p.name
