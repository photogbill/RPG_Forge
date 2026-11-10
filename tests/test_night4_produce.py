"""Night 4 F3 — wanted export with towns, produce plan/queue/status, deliver + ledger + undo, disk guard, housekeeping."""
import json
from pathlib import Path

import pytest
from PIL import Image

from forge import config as cfgmod, manifest
from test_manifest import make_world, fake_done_job


def world(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    data = root / "project" / "data"
    m = json.loads((data / "maps" / "bills_house.json").read_text())
    m.update({"town": "linden_mills", "era": "peace"})
    (data / "maps" / "bills_house.json").write_text(json.dumps(m))
    (data / "maps" / "hobby_shop.json").write_text(json.dumps({"id": "hobby_shop", "tile_size": 32, "town": "linden_mills",
                                                               "rows": ["#" * 12] * 8, "notes": "a hobby shop"}))
    (data / "towns.json").write_text(json.dumps({"linden_mills": {"name": "Linden Mills", "look": "brick, amber, dusk, steeple",
        "fate": "spared", "enclaves": [{"from": "texas", "name": "Little Texas", "map": "bills_house", "block": [0, 0, 300, 200]}]}}))
    g = Path(cfg["paths"]["games"]) / "tg"
    (g / "produce_order.json").write_text(json.dumps({"first_hour": ["bills_house"], "story": ["hobby_shop"]}))
    (g / "prompts").mkdir(exist_ok=True)
    (g / "prompts" / "lib.json").write_text(json.dumps({"blocks": {"style.house": "TODO house"}}))
    cfg.update({"incoming_dir": str(tmp_path / "_incoming"), "disk_guard_gb": 0})
    for s in ("paused",):
        (tmp_path / "jobs" / s).mkdir(parents=True, exist_ok=True)
    return cfg, root, assets


def test_export_carries_towns_and_icons(tmp_path):
    cfg, root, _ = world(tmp_path)
    d = manifest.refresh_wanted(cfg, "tg")
    b = d["items"]["scenes/bills_house"]
    assert b["town"] == "linden_mills" and b["fate"] == "spared" and b["look"].startswith("brick")
    assert b["enclaves"][0]["from"] == "texas" and b["era"] == "peace"
    assert d["items"]["icons/coolant"]["description"] == "Cools a core." and d["items"]["icons/coolant"]["sha1"] is None
    assert d["items"]["placeholder/hero_sarah"]["sha1"]                    # a stand-in carries its hash


def test_plan_orders_towns_and_adds_placeholders(tmp_path):
    from forge.night4 import produce
    cfg, root, _ = world(tmp_path)
    p = produce.plan(cfg, "tg")
    names = [j["name"] for j in p["jobs"]]
    assert names[0] == "bills_house" and names.index("bills_house") < names.index("hobby_shop")
    bh = p["jobs"][0]
    assert "{{culture.linden_mills}}" in bh["prompt"] and "{{fate.spared}}" in bh["prompt"]
    assert bh["seed"] == produce.town_seed("linden_mills") == p["jobs"][names.index("hobby_shop")]["seed"]
    assert bh["meta"]["town"] == "linden_mills" and bh["priority"] == produce.LANES["first"]
    assert {"culture.linden_mills", "fate.spared", "icon.repair", "era.peace", "place.hobby_shop"} <= set(p["_new_blocks"])
    assert "{{place.hobby_shop}}" in p["jobs"][names.index("hobby_shop")]["prompt"] and "TODO" not in str([j["prompt"] for j in p["jobs"]])
    assert any(w["name"].endswith("#texas") and "approved" in w["waits_on"] for w in p["_waiting"])
    icons = [j for j in p["jobs"] if j["type"] == "icon_batch"]
    assert icons and icons[0]["items"][0]["name"] == "Coolant"
    assert any(b["name"] == "placeholder/hero_sarah" for b in p["_by_hand"])          # William draws sprites
    lib = json.loads((Path(cfg["paths"]["games"]) / "tg" / "prompts" / "night4.json").read_text())
    assert lib["blocks"]["culture.linden_mills"].startswith("TODO") and "brick, amber" in lib["blocks"]["culture.linden_mills"]
    assert "a hobby shop" in lib["blocks"]["place.hobby_shop"]               # the game's own words, for Fable
    assert Path(p["_file"]).with_suffix(".md").exists()
    assert p["_estimate"]["gpu_hours"] > 0


def test_queue_refuses_placeholders_then_submits(tmp_path):
    from forge.night4 import produce
    cfg, root, _ = world(tmp_path)
    produce.plan(cfg, "tg")
    r = produce.queue(cfg, "tg", lanes=["first", "story"])
    assert r["queued"] == 0 and any("culture.linden_mills" in k and "TODO" in k for k in r["refused"])
    g = Path(cfg["paths"]["games"]) / "tg" / "prompts"
    for f in g.glob("*.json"):
        d = json.loads(f.read_text())
        d["blocks"] = {k: (f"words for {k}" if str(v).startswith("TODO") else v) for k, v in (d.get("blocks") or {}).items()}
        f.write_text(json.dumps(d))
    r = produce.queue(cfg, "tg", lanes=["first", "story"])
    assert r.get("rc") == 0, r
    assert r.get("rc") == 0 and r["queued"] == 2, r
    pend = [json.loads(p.read_text()) for p in (tmp_path / "jobs" / "pending").glob("*.json")]
    assert {j["batch"] for j in pend} <= {"produce/first", "produce/story"}
    assert all("{{" not in j["prompt"] for j in pend) and all(j["meta"]["town"] == "linden_mills" for j in pend)
    s = produce.status(cfg)
    assert s["counts"]["pending"] == 2


def test_deliver_hold_run_ledger_undo(tmp_path):
    from forge.night4 import deliver as dl
    cfg, root, assets = world(tmp_path)
    manifest.refresh_wanted(cfg, "tg")
    out = fake_done_job(tmp_path, "j1", "ArtUniverseSDXL_v8.safetensors", outputs=("card_1.png",))
    w = manifest.load_wanted(cfg, "tg")["items"]["vignettes/gate_law/01_ribbon"]
    Image.new("RGB", tuple(w["target_size"]), (10, 200, 10)).save(out / "card_1.png")
    from forge import manifest as mf
    lic = tmp_path / "lic"
    old = mf.licence_chain
    mf.licence_chain = lambda ctx, parts: ([{"role": "checkpoint", "file": "x", "commercial_ok": True}], True)
    try:
        dl.hold(cfg, "j1", "vignettes/gate_law/01_ribbon", "tg")
    finally:
        mf.licence_chain = old
    assert dl.todo(cfg, "tg")[0]["why"] == "held approval"
    assert dl.run(cfg, "tg", dry=True)["moved"]
    before = (assets / "vignettes" / "gate_law" / "01_ribbon.png").read_bytes()
    rep = dl.run(cfg, "tg")
    assert len(rep["moved"]) == 1 and rep["moved"][0]["replaced"]
    dest = assets / "vignettes" / "gate_law" / "01_ribbon.png"
    assert Image.open(dest).getpixel((5, 5)) == (10, 200, 10)
    assert "vignettes/gate_law/01_ribbon" in manifest.load_approved(cfg, "tg") and not dl.held(cfg, "tg")
    assert dl.live(cfg, "tg")["vignettes/gate_law/01_ribbon"]["job_id"] == "j1"
    assert (assets / "_provenance" / "vignettes__gate_law__01_ribbon.json").exists()
    u = dl.undo(cfg, "tg", "vignettes/gate_law/01_ribbon")
    assert dest.read_bytes() == before and "put back" in u["what"]
    assert "vignettes/gate_law/01_ribbon" not in dl.live(cfg, "tg")


def test_deliver_refuses_wrong_size_and_fits(tmp_path):
    from forge.night4 import deliver as dl
    cfg, root, assets = world(tmp_path)
    manifest.refresh_wanted(cfg, "tg")
    fake_done_job(tmp_path, "j2", "x.safetensors", outputs=("card_1.png",))        # 864×486 vs target
    h = dl.held(cfg, "tg"); h["placeholder/hero_sarah"] = {"job_id": "j2", "file": str(tmp_path / "out" / "j2" / "card_1.png"),
                                                           "held": "now", "licences": []}
    dl._write(Path(cfg["paths"]["games"]) / "tg" / "held.json", h)
    rep = dl.run(cfg, "tg")
    assert rep["refused"] and "--fit" in rep["refused"][0]["reason"]
    rep = dl.run(cfg, "tg", fit=True)
    assert rep["moved"] and Image.open(assets / "placeholder" / "hero_sarah.png").size == (1152, 216)


def test_deliver_writes_a_bat_when_the_game_is_not_reachable(tmp_path):
    from forge.night4 import deliver as dl
    cfg, root, assets = world(tmp_path)
    manifest.refresh_wanted(cfg, "tg")
    out = fake_done_job(tmp_path, "j3", "x.safetensors", outputs=("card_1.png",))
    Image.new("RGB", (864, 486)).save(out / "card_1.png")
    g = Path(cfg["paths"]["games"]) / "tg"
    gc = json.loads((g / "forge.game.json").read_text())
    dl._write(g / "held.json", {"vignettes/gate_law/01_ribbon": {"job_id": "j3", "file": str(out / "card_1.png"), "held": "now"}})
    gc["asset_root"] = str(tmp_path / "nowhere" / "assets")
    (g / "forge.game.json").write_text(json.dumps(gc))
    rep = dl.run(cfg, "tg")
    bat = Path(rep["listed"])
    assert bat.exists() and "copy /Y" in bat.read_text() and "deliver record" in bat.read_text()


def test_disk_guard_parks_and_brings_back(tmp_path):
    from forge.night4 import guard
    cfg, root, _ = world(tmp_path)
    cfg["disk_guard_gb"] = 40
    for i in range(3):
        (tmp_path / "jobs" / "pending" / f"p{i}.json").write_text(json.dumps({"id": f"p{i}"}))
    st = guard.check(cfg, free=10)
    assert len(st["paused_ids"]) == 3 and "DISK GUARD" in st["message"]
    assert not list((tmp_path / "jobs" / "pending").glob("*.json"))
    st = guard.check(cfg, free=42)                      # under limit + hysteresis: stays parked
    assert st["paused_ids"]
    st = guard.check(cfg, free=60)
    assert not st["paused_ids"] and len(list((tmp_path / "jobs" / "pending").glob("*.json"))) == 3


def test_housekeeping_reports_and_deletes_nothing(tmp_path):
    from forge.night4 import housekeeping
    import os, time
    cfg, root, _ = world(tmp_path)
    d = tmp_path / "out" / "20250101-000000-old-abcd"
    d.mkdir(parents=True); (d / "render.png").write_bytes(b"x" * 1000)
    (tmp_path / "jobs" / "done" / f"{d.name}.json").write_text(json.dumps({"id": d.name, "batch": "bakeoff/x"}))
    old = time.time() - 40 * 86400
    os.utime(d, (old, old))
    p, rep = housekeeping.report(cfg, 14, "tg")
    assert rep["bakeoff"] == 1 and d.exists() and "nothing was moved" in p.read_text()


def test_plan_never_makes_a_character_block(tmp_path):
    from forge.night4 import produce
    cfg, root, _ = world(tmp_path)
    g = Path(cfg["paths"]["games"]) / "tg"
    (g / "characters").mkdir()
    (g / "characters" / "sarah.json").write_text(json.dumps({"id": "sarah", "variants": {"v": {"prompt": "x", "seed": 1,
        "wanted": {"portrait": "placeholder/portrait_sarah"}}}}))
    w = json.loads((g / "wanted.json").read_text()) if (g / "wanted.json").exists() else None
    manifest.refresh_wanted(cfg, "tg")
    wd = json.loads((g / "wanted.json").read_text())
    wd["items"]["placeholder/portrait_sarah"] = {"name": "placeholder/portrait_sarah", "kind": "portrait", "exists": True,
                                                "path": "project/assets/placeholder/portrait_sarah.png", "target_size": [384, 384]}
    (g / "wanted.json").write_text(json.dumps(wd))
    p = produce.plan(cfg, "tg", refresh=False)
    assert any(j.get("character") == "sarah" for j in p["jobs"]) and "character" not in p["_new_blocks"]
