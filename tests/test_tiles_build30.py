"""BUILD 30 — the tile builder: every blob case joins its neighbours, normals in the OpenGL convention, world-space
textures at full resolution, the materials bake-off planned (never queued by a session), scored and reported, a pick
is a person's, Filter Forge's install never touched, nothing written outside the forge's folders, no game named."""
from __future__ import annotations
import hashlib, json, random, re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge.tiles import autotile as A, materials as M, report as R, score as S
from test_suite_build01 import REPO, world  # noqa: F401


def _noise_tile(seed: int, base, px: int = 256) -> Image.Image:
    """A seamless test material: smooth noise built on a wrapped grid."""
    r = np.random.default_rng(seed)
    k = 8
    g = r.random((k, k))
    yy, xx = np.mgrid[0:px, 0:px] / px * k
    x0, y0 = np.floor(xx).astype(int), np.floor(yy).astype(int)
    fx, fy = xx - x0, yy - y0
    v = (g[y0 % k, x0 % k] * (1 - fx) * (1 - fy) + g[y0 % k, (x0 + 1) % k] * fx * (1 - fy)
         + g[(y0 + 1) % k, x0 % k] * (1 - fx) * fy + g[(y0 + 1) % k, (x0 + 1) % k] * fx * fy)
    a = np.clip(v[..., None] * np.array(base)[None, None] * 1.4, 0, 1)
    return Image.fromarray((a * 255).astype(np.uint8), "RGB")


def test_the_blob_set_has_47_and_every_neighbourhood_maps_to_one():
    assert len(A.BLOB47) == 47
    for m in range(256):
        assert A.reduce_mask(m) in A.BLOB47
    assert len(A.SET16) == 16


@pytest.mark.parametrize("style", list(A.STYLES))
def test_every_blob_case_joins_its_neighbours_on_a_map_with_every_case(style):
    T = 40
    masks = {m: A.blob_mask(m, T, style) for m in A.BLOB47}
    # a map that contains every one of the 47 cases (random maps until all are seen)
    seen, worst, inner = set(), 0.0, 0.0
    for trial in range(400):
        rnd = random.Random(trial)
        W, H = 14, 10
        cells = [[1 if rnd.random() < 0.6 else 0 for _ in range(W)] for _ in range(H)]

        def mk(x, y):
            t = A.tile_for(cells, x, y)
            if t is not None:
                seen.add(t)
            return masks[t] if t is not None else np.zeros((T, T))
        for y in range(H):
            for x in range(W - 1):
                a, b = mk(x, y), mk(x + 1, y)
                worst = max(worst, float(np.abs(a[:, -1] - b[:, 0]).max()))
                inner = max(inner, float(np.abs(a[:, -1] - a[:, -2]).max()))
        for y in range(H - 1):
            for x in range(W):
                worst = max(worst, float(np.abs(mk(x, y)[-1, :] - mk(x, y + 1)[0, :]).max()))
        if len(seen) == 47 and trial > 40:
            break
    assert len(seen) == 47
    assert worst < 0.05 and worst < inner, (worst, inner)    # across a border: smaller than a step inside a tile
    # a tile of A next to B is B at the shared edge; a tile with all eight neighbours is A everywhere
    assert masks[255].min() == 1.0
    assert masks[0][:, 0].max() < 0.01


def test_the_corner_set_joins_on_every_shared_edge():
    T = 32
    m = {cs: A.corner_mask(cs, T, "ragged") for cs in A.SET16}
    for (tl, tr, br, bl) in A.SET16:
        for (tl2, tr2, br2, bl2) in A.SET16:
            if tl2 == tr and bl2 == br:
                assert np.abs(m[(tl, tr, br, bl)][:, -1] - m[(tl2, tr2, br2, bl2)][:, 0]).max() < 0.08


def test_normals_are_opengl_green_up():
    T = 32
    ramp = np.tile(np.linspace(1, 0, T)[:, None], (1, T))        # bright (near) at the top, falling away downward
    n = A.normals_from_height(ramp, 4.0)
    assert n[T // 2, T // 2, 1] < 0                              # surface tilts down-screen: -y in OpenGL
    ramp_x = np.tile(np.linspace(0, 1, T)[None, :], (T, 1))      # rising to the right
    assert A.normals_from_height(ramp_x, 4.0)[T // 2, T // 2, 0] < 0   # faces left: -x
    wall = A.wall_tiles(_noise_tile(1, (0.5, 0.5, 0.5)), T)
    front = next(t for t in wall if t["kind"] == "wall_front")
    assert front["normal"][..., 1].mean() < -0.2                 # the front faces the viewer (down the screen)


def test_a_whole_set_writes_atlases_masks_world_textures_and_a_manifest(tmp_path):
    floor, edge, wall = _noise_tile(1, (0.8, 0.7, 0.4), 512), _noise_tile(2, (0.3, 0.6, 0.25), 512), _noise_tile(3, (0.4, 0.4, 0.4))
    man = A.build_set("t", tmp_path, floor=floor, edge=edge, wall=wall, T=64, variants=4, decals=1, seed=3)
    kinds = [t["kind"] for t in man["tiles"]]
    assert kinds.count("blob") == 47 and kinds.count("fill") == 1 and kinds.count("variant") == 4
    assert {"wall_top", "wall_front", "wall_cap"} <= set(kinds)
    assert sorted(d["kind"] for d in man["decals"]) == ["decal_crack", "decal_debris", "decal_scorch", "decal_stain"]
    al, nm = Image.open(tmp_path / "t.png"), Image.open(tmp_path / "t_n.png")
    assert al.size == nm.size and al.width == 8 * 64
    # every blob tile names its Godot neighbour bits; the full one has all eight
    full = next(t for t in man["tiles"] if t.get("mask") == 255)
    assert sorted(full["peering"]) == sorted(A.GODOT.values())
    assert all(t["blocking"] for t in man["tiles"] if t["kind"].startswith("wall"))
    # the sharp way: the material at its own resolution, the masks at tile size
    w = man["world"]
    assert Image.open(tmp_path / w["a"]).size == (512, 512) and w["period_tiles_a"] == 8.0
    assert Image.open(tmp_path / w["masks"]).mode == "L" and len(w["mask_order"]) == 48
    dec = Image.open(tmp_path / "t_decals.png")
    assert dec.mode == "RGBA" and dec.getpixel((0, 0))[3] == 0  # decals are transparent at their border
    # same inputs, same bytes
    A.build_set("t2", tmp_path, floor=floor, edge=edge, wall=wall, T=64, variants=4, decals=1, seed=3)
    assert (tmp_path / "t.png").read_bytes() == (tmp_path / "t2.png").read_bytes()


def test_variants_keep_their_borders_so_they_join():
    vs = A.variant_tiles(_noise_tile(5, (0.6, 0.5, 0.4)), 64, 5, seed=2)
    base = vs[0]["albedo"]
    for v in vs[1:]:
        a = v["albedo"]
        assert np.abs(a[0] - base[0]).max() < 0.02 and np.abs(a[:, -1] - base[:, -1]).max() < 0.02
        assert np.abs(a - base).mean() > 0.01                    # but differ inside


def test_the_scores_tell_good_from_bad():
    good = _noise_tile(7, (0.6, 0.6, 0.6), 256)
    bad = Image.fromarray(np.concatenate([np.full((256, 128, 3), 40, np.uint8), np.full((256, 128, 3), 220, np.uint8)], 1))
    # a perfect wrap scores about 1.0 (the seam is as rough as the texture itself); a visible line is over 1.5
    assert S.score(good, A.encode_normals(A.normals_from_height(A.lum(np.asarray(good) / 255.0), 4, True)))["seam"] < 1.2
    assert S.score(bad, Image.new("RGB", (256, 256), (128, 128, 255)))["seam"] > 1.5
    assert S.repetition(bad) > S.repetition(good)
    flat = Image.new("RGB", (64, 64), (128, 128, 255))
    assert S.normal_quality(flat) == 0.0


def test_the_bake_off_is_planned_from_the_list_and_filter_forge_is_matched_by_name():
    suites = M.suites("g", M.DEFAULT)
    assert [s["suite"] for s in suites] == ["materials_sdxl_v1", "materials_klein_v1"]
    assert len(suites[0]["categories"]["materials"]["prompts"]) == len(M.DEFAULT) == 25
    assert suites[0]["checkpoints"] == ["ArtUniverseSDXL_v8.safetensors"]
    assert all("klein" in c and "4b" in c for c in suites[1]["checkpoints"])   # the Apache 4B only
    listing = {"lib": [{"file": "Rusty_Metal.ffxml", "path": "X:/f/Rusty_Metal.ffxml", "kind": "texture", "name": "Rusty Metal Plates", "seamless_presets": [2]},
                       {"file": "Sand_Dunes.ffxml", "path": "X:/f/Sand_Dunes.ffxml", "kind": "texture", "name": "Sand Dunes", "seamless_presets": []},
                       {"file": "Grunge.ffxml", "path": "X:/f/Grunge.ffxml", "kind": "effect", "name": "Rust and Grime", "seamless_presets": []}]}
    jobs, missing = M.ff_jobs("g", M.DEFAULT, listing)
    by = {j["meta"]["prompt_id"]: j for j in jobs}
    assert by["rusted_steel"]["preset"] == 2 and by["rusted_steel"]["tileable"] is True
    assert by["desert_sand"]["filter"].endswith("Sand_Dunes.ffxml")
    assert "brick" in missing                                    # nothing matched: listed, never guessed
    assert not any(j["filter"].endswith("Grunge.ffxml") for j in jobs)   # an effect filter is not a material
    # a pick by the filter's real name wins over the words
    j2, missing2 = M.ff_jobs("g", M.DEFAULT, listing, chosen={"brick": ["Sand_Dunes"]})
    assert any(j["meta"]["prompt_id"] == "brick" and j["filter"].endswith("Sand_Dunes.ffxml") for j in j2) and "brick" not in missing2
    j3, missing3 = M.ff_jobs("g", M.DEFAULT, listing, chosen={"desert_sand": []})
    assert "desert_sand" in missing3 and not any(j["meta"]["prompt_id"] == "desert_sand" for j in j3)
    w, notes = M.weathering_jobs("g", {"rusted_steel": {"image": "X:/t.png"}}, M.DEFAULT, listing)
    assert {j["meta"]["category"] for j in w} == {"war", "after"}
    assert any(j["type"] == "filter_forge" and j["input"] == "X:/t.png" for j in w)
    w2, _n = M.weathering_jobs("g", {"rusted_steel": {"image": "X:/t.png"}}, M.DEFAULT, listing, chosen={"after": ["Grunge"]})
    assert any(j["type"] == "filter_forge" and j["meta"]["category"] == "after" and j["filter"].endswith("Grunge.ffxml") for j in w2)


def test_the_report_scores_sheets_and_a_pick_is_a_persons(tmp_path, world):
    cfg, _a, tmp = world
    from forge.suite import settings
    d = tmp_path / "src"
    d.mkdir()
    _noise_tile(1, (0.8, 0.7, 0.4), 512).save(d / "a.png")
    Image.fromarray((np.random.default_rng(0).random((300, 300, 3)) * 255).astype(np.uint8)).save(d / "b.png")
    found = {"desert_sand": {"sdxl": {"image": str(d / "a.png"), "seconds": 9}, "klein": {"image": str(d / "b.png"), "seconds": 20}}}
    out = tmp_path / "materials"
    v = R.report(found, out, [Image.open(d / "a.png")], {"desert_sand": "desert sand"})
    rows = v["materials"]["desert_sand"]
    assert {r["source"] for r in rows} == {"sdxl", "klein"} and rows[0]["rank"] == 1
    assert (out / "desert_sand.png").exists() and (out / "MATERIALS_VERDICT.md").exists()
    assert Image.open(rows[0]["tile"]).size[0] in (512, 300)     # kept at its own resolution, never squeezed
    with pytest.raises(ValueError):
        R.pick(out, "desert_sand", "sdxl", "Claude Opus")
    p = R.pick(out, "desert_sand", "sdxl", "Bill")
    assert p["by"] == "Bill" and "✦" in (out / "MATERIALS_VERDICT.md").read_text(encoding="utf-8")


def test_a_session_never_queues_the_bake_off(world, monkeypatch, capsys):
    cfg, _a, tmp = world
    from forge.cli_tiles import cmd_tiles
    monkeypatch.setenv("FORGE_IDENTITY", "Claude Opus")
    assert cmd_tiles(cfg, ["plan", "--game", "_example", "--no-ff"]) == 0
    assert (tmp / "games" / "_example" / "bakeoff" / "materials_sdxl_v1.json").exists()
    assert cmd_tiles(cfg, ["submit", "--game", "_example"]) == 1
    assert not list((tmp / "jobs" / "pending").glob("*.json"))
    assert "person" in capsys.readouterr().out


def test_build_command_writes_into_the_out_folder_at_twice_the_game_tile(world, tmp_path, capsys):
    cfg, _a, tmp = world
    from forge.cli_tiles import cmd_tiles
    f = tmp_path / "f.png"
    _noise_tile(1, (0.5, 0.5, 0.5), 256).save(f)
    assert cmd_tiles(cfg, ["build", "demo", "--floor", str(f), "--edge", str(f), "--game", "_example", "--variants", "2"]) == 0
    man = json.loads((tmp / "out" / "tiles" / "_example" / "demo" / "demo.json").read_text(encoding="utf-8"))
    assert man["tile_size"] == 192                               # the example game's 96 px tile, at 2x


def test_filter_forge_install_untouched_and_nothing_on_c(tmp_path, monkeypatch):
    """The planner reads filter names only; it never opens, copies or writes a filter or the install folder."""
    inst = tmp_path / "Filter Forge 9"
    (inst / "Bin").mkdir(parents=True)
    (inst / "Bin" / "FFXCmdRenderer-x64.exe").write_bytes(b"MZ")
    lib = inst / "Resources" / "System" / "Library"
    lib.mkdir(parents=True)
    (lib / "Concrete.ffxml").write_text('<Filter><Information name="Concrete Floor"/><Result><FilterType value="0"/></Result>'
                                        '<Components/><Presets><Preset><Settings seamless="true"/></Preset></Presets></Filter>', encoding="utf-8")

    def digest():
        return hashlib.md5(b"".join(p.read_bytes() for p in sorted(inst.rglob("*")) if p.is_file())).hexdigest()
    before = digest()
    from forge.night3b import ffdriver
    cfg = {"tools": {"filter_forge": {"exe": str(inst / "Bin" / "FFXCmdRenderer-x64.exe")}}}
    monkeypatch.setattr(ffdriver, "tool_cfg", lambda c=None: cfg["tools"]["filter_forge"])
    jobs, _missing = M.ff_jobs("g", M.DEFAULT, ffdriver.list_filters(cfg))
    assert any(j["meta"]["prompt_id"] == "poured_concrete" for j in jobs)
    assert digest() == before
    src = (REPO / "forge" / "tiles").glob("*.py")
    for f in src:
        t = f.read_text(encoding="utf-8")
        assert not re.search(r"['\"]C:\\\\", t), f.name


def test_tiles_names_no_game():
    names = re.compile(r"\b(turing|sarah|valkyrie|minerva|odin|meha|augusta|linden|boneyard|cheyenne)\b", re.I)
    for f in list((REPO / "forge" / "tiles").glob("*.py")) + [REPO / "forge" / "cli_tiles.py"]:
        assert not names.findall(f.read_text(encoding="utf-8")), f.name
