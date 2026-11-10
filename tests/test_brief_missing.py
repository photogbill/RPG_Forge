"""G10/G11: brief missing picks the job type by the facts (four cases) and drafts room families that differ only in
their skin/era references."""
import json

from PIL import Image

from forge import brief_missing as bm, review_compact as rc
from test_night_report import world


def setup(tmp_path):
    cfg, jobs, out = world(tmp_path)
    root = tmp_path / "Game"
    maps = root / "project" / "data" / "maps"
    scenes = root / "project" / "assets" / "scenes"
    maps.mkdir(parents=True); scenes.mkdir(parents=True)
    games = tmp_path / "games" / "tg"
    games.mkdir(parents=True)
    (games / "forge.game.json").write_text(json.dumps({"game_root": str(root), "scene_size": [1920, 1080]}))
    cfg["paths"]["games"] = str(tmp_path / "games")
    items = {}

    def add(mid, size, greybox=None, **fields):
        (maps / f"{mid}.json").write_text(json.dumps({"id": mid, "name": mid.title(), "notes": f"notes for {mid}", **fields}))
        gb = None
        if greybox is not None:
            greybox.save(scenes / f"{mid}_greybox.png")
            gb = f"project/assets/scenes/{mid}_greybox.png"
        items[f"scenes/{mid}"] = {"name": f"scenes/{mid}", "kind": "scene", "target_size": list(size), "notes": "",
                                  "greybox": gb, "name_in_game": mid}
    g1 = Image.new("RGB", (64, 36), (100, 100, 100))
    g2 = g1.copy(); g2.paste((20, 20, 20), (40, 5, 50, 30))
    add("gas_station", (1920, 1080), g1)                                # one frame → scene_kit
    add("street", (6144, 3072))                                         # larger → scene_big
    add("bills_house", (2304, 1536), g1)                                # base, approved below
    add("bills_house_peace_b", (2304, 1536), g2, state_of="bills_house")  # state, base approved → scene_state
    add("lab", (1920, 1080), g1)
    add("lab_after", (1920, 1080), g2, state_of="lab")                  # state, base not approved → held back
    for town, era in (("linden", "war"), ("dry_fork", "war"), ("tucson", "peace")):
        add(f"inn_{town}", (1920, 1080), template="inn_small", skin=town, era=era)
    (games / "wanted.json").write_text(json.dumps({"game": "tg", "exported": "x", "items": items}))
    (games / "approved.json").write_text(json.dumps({"scenes/bills_house": {"job_id": "KIT1", "file": "scene.png", "sha256": "x"}}))
    return cfg


def test_four_cases_and_families(tmp_path):
    cfg = setup(tmp_path)
    r = bm.draft(cfg, "tg", refresh=False)
    by = {t["map"]: t for t in r["table"]}
    jobs = {j["name"]: j for j in r["draft"]["jobs"]}
    assert "bills_house" not in by                                         # approved: nothing to paint
    assert by["gas_station"]["type"] == "scene_kit" and jobs["gas_station"]["control"]["type"] == "canny"
    assert by["street"]["type"] == "scene_big" and jobs["street"]["target"] == [6144, 3072] and "init" not in jobs["street"]
    assert by["bills_house_peace_b"]["type"] == "scene_state"
    st = jobs["bills_house_peace_b"]
    assert st["base"] == "out/KIT1" and st["greybox_base"].endswith("bills_house_greybox.png") and st["greybox_state"].endswith("peace_b_greybox.png")
    assert by["lab_after"]["type"] == "-" and "lab to be approved" in by["lab_after"]["waits_on"] and "lab_after" not in jobs
    assert r["draft"]["_draft"] is True
    fam = [jobs[f"inn_{t}"] for t in ("linden", "dry_fork", "tucson")]
    assert all(j["meta"]["family"] == "inn_small" and j["seed"] == 1001 for j in fam)
    assert fam[0]["prompt"] == "{{style.house}}, {{layout.inn_small}}, {{skin.linden}}, {{era.war}}"
    assert fam[2]["prompt"] == "{{style.house}}, {{layout.inn_small}}, {{skin.tucson}}, {{era.peace}}"
    strip = lambda j: {k: v for k, v in j.items() if k not in ("name", "prompt", "meta", "_notes", "_wanted", "_name_in_game")}
    assert strip(fam[0]) == strip(fam[1]) == strip(fam[2])                 # differ only in their references
    p, rep, _ = bm.write(cfg, "tg", refresh=False)
    assert p.exists() and "| street | 6144x3072 | scene_big |" in rep.read_text(encoding="utf-8")


def test_family_sheet_from_rendered_members(tmp_path):
    cfg, jobs, out = world(tmp_path)
    for i, town in enumerate(("linden", "dry_fork", "tucson")):
        jid = f"F{i}"
        (jobs / "done" / f"{jid}.json").write_text(json.dumps({"id": jid, "type": "scene_kit", "name": f"inn_{town}",
            "meta": {"family": "inn_small", "member": f"inn_{town}", "skin": town, "era": "war"}, "result": {"outputs": ["scene.png"]}}))
        (out / jid).mkdir(parents=True)
        Image.new("RGB", (192, 108), (60 * i, 90, 120)).save(out / jid / "scene.png")
    folder, idx = rc.build_family(cfg, "inn_small")
    assert len(idx["cells"]) == 3 and (folder / "family.jpg").exists()
    assert idx["cells"][0]["label"].startswith("inn_linden")
