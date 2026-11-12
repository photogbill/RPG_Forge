"""BUILD 29 — the floor-plan generator: a town sheet → districts → lots → interiors from kits, seeded.

Determinism · reachability on 200 seeds per archetype · the game's own map check (the example game's adapter) ·
paint guide and greybox pixel-aligned with the rows · an approved or hand-edited plan never written over · forge/layout
names no game · nothing written outside the out folder.
"""
from __future__ import annotations
import json, re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest
from PIL import Image

from forge.layout import archetypes, check, render, store, tiles as T, town, wfc
from forge.layout.grid import Grid, Rect
from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

SHEET = {"id": "testville", "name": "Testville",
         "required": [{"kind": "inn", "label": "INN"}, {"kind": "store"}, {"kind": "gas_station"}, {"kind": "diner"}],
         "tiers": {"weapon": 1, "armor": 1, "accessory": 0}}


def _sweep(aid: str) -> tuple[str, list]:
    """200 seeds of one archetype (alternating War and After): every plan passes every check."""
    bad = []
    for s in range(200):
        era = ("war", "after")[s % 2]
        p = town.generate(SHEET, aid, era, 5000 + s)
        if p.problems:
            bad.append((era, 5000 + s, p.problems[:2]))
    return aid, bad


def test_every_archetype_has_a_war_and_an_after_version_and_a_rule():
    assert len(archetypes.ARCHETYPES) == 15
    for aid, a in archetypes.ARCHETYPES.items():
        assert a["rule"] in town.RULES, aid
        for era in ("war", "after"):
            assert a["story"][era] and a["upgrade"][era] and a["accessory"][era], (aid, era)
    assert archetypes.ARCHETYPES["buried_town"]["mark"] == "✦"     # William's ruling, not a proposal


def test_same_sheet_and_seed_give_the_same_bytes(tmp_path):
    a = town.generate(SHEET, "purity_town", "after", 7)
    b = town.generate(SHEET, "purity_town", "after", 7)
    assert [p.grid.c for p in a.all_plans()] == [p.grid.c for p in b.all_plans()]
    assert [p.entities for p in a.all_plans()] == [p.entities for p in b.all_plans()]
    store.write(a, tmp_path / "a", sheet=SHEET)
    store.write(b, tmp_path / "b", sheet=SHEET)
    for f in sorted((tmp_path / "a").iterdir()):
        if f.name == "plan_set.json":
            continue                                       # carries the time it was written
        assert f.read_bytes() == (tmp_path / "b" / f.name).read_bytes(), f.name
    c = town.generate(SHEET, "purity_town", "after", 8)
    assert c.grid.c != a.grid.c                            # another seed, another plan


def test_reachability_on_200_seeds_per_archetype():
    ids = list(archetypes.ARCHETYPES)
    try:
        with ProcessPoolExecutor() as ex:
            results = list(ex.map(_sweep, ids))
    except Exception:  # noqa: BLE001 — a machine that can't fork still runs the sweep, just slower
        results = [_sweep(a) for a in ids]
    failed = {aid: bad for aid, bad in results if bad}
    assert not failed, failed


def test_a_plan_is_sound_where_the_checks_look():
    p = town.generate(SHEET, "toll_kingdom", "war", 3)
    assert not p.problems
    g = p.grid
    start = next(e for e in p.of("spawn") if e["name"] == "start")
    reach = g.flood((start["x"], start["y"]))
    for e in p.of("door"):
        assert (e["x"], e["y"]) in reach
    # every interior has one way back, onto a spawn the town has
    for kid in p.children:
        back = [d for d in kid.of("door") if d["to"] == f"plan:{p.id}"]
        assert len(back) == 1 and back[0]["spawn"] in p.spawn_names()
    # the upgrade places: weapon and armor in the smith, accessory in the trinket shop, with the sheet's tiers
    ups = [e for k in p.children for e in k.of("upgrade")]
    assert sorted(e["kind"] for e in ups) == ["accessory", "armor", "weapon"]
    assert {e["kind"]: e["tier"] for e in ups} == {"weapon": 1, "armor": 1, "accessory": 0}
    # the story element is visible from the spawn
    s = p.story
    cells = [(x, y) for y in range(s["y"], s["y"] + s["h"]) for x in range(s["x"], s["x"] + s["w"])]
    assert any(g.sees((start["x"], start["y"]), c, set(cells)) for c in cells)
    assert "toll" in p.notes[-1] or any("gauntlet" in n for n in p.notes)


def test_the_checks_catch_what_they_promise():
    p = town.generate(SHEET, "pretend_town", "war", 2)
    assert not p.problems
    # wall the spawn in: everything becomes unreachable
    st = next(e for e in p.of("spawn") if e["name"] == "start")
    for n in p.grid.n4(st["x"], st["y"]):
        p.grid.set(*n, T.WALL)
    probs = check.problems(p)
    assert any("can't be reached" in q for q in probs)
    # a door into an interior that wasn't built
    q = town.generate(SHEET, "pretend_town", "war", 2)
    q.children.pop(0)
    assert any("wasn't built" in x or "has a door but no interior" in x for x in check.problems(q))
    # a road that stops on open ground
    g = Grid(20, 12)
    g.border_wall()
    for x in range(3, 9):
        g.set(x, 6, T.ROAD)
    from forge.layout.plan import Plan
    assert check.dead_ends(Plan(id="x", kind="town", grid=g))


def test_paint_guide_and_greybox_are_pixel_aligned_with_the_rows(tmp_path):
    p = town.generate(SHEET, "glass_field", "after", 4)
    px = 16
    guide, grey = render.paint_guide(p, px), render.greybox(p, px)
    assert guide.size == grey.size == (p.w * px, p.h * px)
    story = {(x, y) for y in range(p.story["y"], p.story["y"] + p.story["h"]) for x in range(p.story["x"], p.story["x"] + p.story["w"])}
    for y in range(p.h):
        for x in range(p.w):
            want = T.STORY_COLOUR if (x, y) in story else T.PAINT[p.grid.c[y][x]]
            assert guide.getpixel((x * px + px // 2, y * px + px // 2)) == want, (x, y)
            assert guide.getpixel((x * px, y * px)) == want
            assert grey.getpixel((x * px + 2, y * px + 2)) == T.GREY[p.grid.c[y][x]]
    assert sum(1 for y in range(p.h) for x in range(p.w)
               if guide.getpixel((x * px + 1, y * px + 1)) == T.STORY_COLOUR) == len(story) > 0


def test_buried_town_has_a_level_below_reached_by_the_hatch():
    p = town.generate(SHEET, "buried_town", "after", 11)
    assert not p.problems
    below = [c for c in p.children if c.kind == "level"]
    assert len(below) == 1
    down = [d for d in p.of("door") if d["id"] == "down"]
    assert down and down[0]["to"] == f"plan:{below[0].id}"
    up = [d for d in below[0].of("door") if d["id"] == "up"]
    assert up and up[0]["to"] == f"plan:{p.id}" and up[0]["spawn"] == "from_below"
    assert below[0].story["what"] == "the blast door"
    # the town lives below: its shops are there, underground, and the surface is a decoy
    assert {b["kind"] for b in below[0].buildings} >= {"inn", "store", "smith", "trinkets"}
    assert any("underground" in k for c in below[0].children for k in c.kit)
    assert {b["kind"] for b in p.buildings} == {"ruin"}


def test_ghost_town_comes_in_day_and_night():
    p = town.generate(SHEET, "ghost_town", "after", 1)
    assert p.states.get("night", {}).get("entities")


def test_wfc_fills_only_the_cells_it_is_given_and_is_seeded():
    from forge.layout.grid import rng_for
    cells = [(x, y) for y in range(4) for x in range(10)]
    a = wfc.collapse(cells, "crops", rng_for("t", 1))
    b = wfc.collapse(cells, "crops", rng_for("t", 1))
    assert a == b and set(a) == set(cells)
    for (x, y), t in a.items():                         # crop rows are stripes: one tile per row
        assert all(a[(xx, y)] == t for xx in range(10))


def test_never_written_over_once_approved_or_edited(tmp_path, world):
    cfg, _a, tmp = world
    from forge.suite import games
    adp = games.adapter(cfg, "_example")
    sheets = {s["id"]: s for s in adp.town_sheets()}
    assert sheets["ember_crossing"]["archetypes"]["after"]["ids"][0] == "toll_kingdom"   # "a bridge town … the toll"
    sh = adp.sheet_for(sheets["ember_crossing"], "after")
    p = town.generate(sh, "toll_kingdom", "after", 1)
    fol = store.folder(cfg, "_example", "ember_crossing", "after", "toll_kingdom", 1)
    assert str(fol).startswith(str(tmp / "out"))           # the out folder, never C: or a profile folder
    s = store.write(p, fol, adp, sh)
    assert s["game_problems"] == [] and s["problems"] == []
    assert store.protected(fol) is None
    store.write(p, fol, adp, sh)                          # untouched: a regenerate is fine
    # a hand edit to a map's rows protects the folder
    mid = s["top"]
    m = json.loads((fol / f"{mid}.json").read_text(encoding="utf-8"))
    m["rows"][1] = "#" * len(m["rows"][1])
    (fol / f"{mid}.json").write_text(json.dumps(m), encoding="utf-8")
    assert "edited by hand" in store.protected(fol)
    with pytest.raises(store.LayoutError):
        store.write(p, fol, adp, sh)
    # approval: a person only; then the folder is protected and the maps are in the game, never over another map
    fol2 = store.folder(cfg, "_example", "ember_crossing", "after", "toll_kingdom", 2)
    store.write(town.generate(sh, "toll_kingdom", "after", 2), fol2, adp, sh)
    with pytest.raises(store.LayoutError):
        store.approve(fol2, adp, "Claude Opus")
    done = store.approve(fol2, adp, "Bill")
    assert done["approved_by"] == "Bill" and done["installed"]
    assert all((adp.root / f).exists() for f in done["installed"])
    assert "approved by Bill" in store.protected(fol2)
    with pytest.raises(store.LayoutError):
        store.write(town.generate(sh, "toll_kingdom", "after", 2), fol2, adp, sh)
    # a different plan with the same map ids is refused by the game's install
    fol3 = tmp / "elsewhere"
    store.write(town.generate(sh, "toll_kingdom", "after", 3), fol3, adp, sh)
    with pytest.raises((store.LayoutError, ValueError)):
        store.approve(fol3, adp, "Bill")


def test_layout_names_no_game():
    names = re.compile(r"\b(turing|sarah|valkyrie|minerva|odin|meha|linden|fayetteville|augusta|mont ross|boneyard)\b", re.I)
    for f in (REPO / "forge" / "layout").glob("*.py"):
        hits = names.findall(f.read_text(encoding="utf-8"))
        assert not hits, (f.name, hits)
    assert not names.findall((REPO / "forge" / "cli_layout.py").read_text(encoding="utf-8"))


def test_the_command_writes_candidates_into_the_out_folder(world, capsys):
    cfg, _a, tmp = world
    from forge.cli_layout import cmd_layout
    assert cmd_layout(cfg, ["sheets", "--game", "_example"]) == 0
    assert "ember_crossing" in capsys.readouterr().out
    assert cmd_layout(cfg, ["generate", "ember_crossing", "--era", "after", "--count", "2", "--game", "_example"]) == 0
    out = capsys.readouterr().out
    assert out.count("clean") == 2
    fol = store.folder(cfg, "_example", "ember_crossing", "after", "toll_kingdom", 1)
    assert (fol / "plan_set.json").exists()
    assert cmd_layout(cfg, ["show", str(fol)]) == 0
    shown = capsys.readouterr().out
    assert "S" in shown and "@" in shown
    assert cmd_layout(cfg, ["check", str(fol), "--game", "_example"]) == 0
