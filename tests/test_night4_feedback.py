"""Night 4 F5 — the game's F9 notes → redo drafts, bumps, the dashboard's Called out actions."""
import json
from pathlib import Path

from PIL import Image

from forge import config as cfgmod
from test_night4_produce import world
from test_manifest import fake_done_job


def test_feedback_files_drafts_and_bumps(tmp_path):
    from forge.night4 import feedback, deliver as dl
    cfg, root, assets = world(tmp_path)
    out = fake_done_job(tmp_path, "j9", "x.safetensors", outputs=("scene.png",))
    job = json.loads((tmp_path / "jobs" / "done" / "j9.json").read_text())
    job.update({"type": "scene_kit", "name": "bills_house", "prompt": "a house", "seed": 5})
    (tmp_path / "jobs" / "done" / "j9.json").write_text(json.dumps(job))
    dl.ledger_add(cfg, "tg", {"action": "delivered", "wanted": "scenes/bills_house", "job_id": "j9", "file": "scene.png",
                              "dest": "project/assets/scenes/bills_house.png"})
    pt = root / "playtest"; pt.mkdir()
    Image.new("RGB", (320, 180), (9, 9, 9)).save(pt / "shot1.png")
    (pt / "art_feedback.json").write_text(json.dumps({"entries": [
        {"map": "bills_house", "files": ["res://assets/scenes/bills_house.png"], "note": "the window is too bright",
         "shot": "shot1.png", "time": "2026-11-11T10:00", "tester": "William"},
        {"map": "hobby_shop", "files": ["res://assets/scenes/hobby_shop.png"], "note": "needs art", "tester": "William"}]}))
    r = feedback.take_in(cfg, None, "tg")
    assert len(r["filed"]) == 1 and len(r["bumped"]) == 1
    drafts = sorted((tmp_path / "jobs" / "drafts").glob("*.json"))
    assert len(drafts) == 2                                     # the redo + the scene_state fix
    redo = json.loads(next(d for d in drafts if "-redo-" in d.name).read_text())
    assert redo["redo_of"] == "j9" and redo["seed"] != 5 and redo["comment"] == "the window is too bright" and redo["_draft"]
    fix = json.loads(next(d for d in drafts if "-fix-" in d.name).read_text())
    assert fix["type"] == "scene_state" and fix["mask"] == "" and fix["base"] == "out/j9"
    md = Path(r["md"]).read_text()
    assert "too bright" in md and "a house" in md and "priority bumped" in md
    bumps = json.loads((Path(cfg["paths"]["games"]) / "tg" / "priority_bumps.json").read_text())
    assert bumps["scenes/hobby_shop"]["bump"] == 1
    assert feedback.take_in(cfg, None, "tg")["skipped"] == 2    # twice files nothing twice
    # the dashboard
    lst = feedback.list_drafts(cfg)
    assert {d["type"] for d in lst} == {"scene_kit", "scene_state"} and not next(d for d in lst if d["type"] == "scene_state")["ready"]
    r2 = feedback.draft_action(cfg, "draft_submit", next(d["draft"] for d in lst if d["type"] == "scene_state"))
    assert not r2["ok"] and "mask" in r2["message"]
    r3 = feedback.draft_action(cfg, "draft_dismiss", next(d["draft"] for d in lst if d["type"] == "scene_state"))
    assert r3["ok"] and len(feedback.list_drafts(cfg)) == 1
    # bumped item goes first in the next plan
    from forge.night4 import produce
    p = produce.plan(cfg, "tg")
    assert p["jobs"][0]["name"] == "hobby_shop" and "called out" in p["jobs"][0]["_why"]
