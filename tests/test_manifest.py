"""F4 manifest + approve, F8 review, F10 brief, F9 doctor — against a throwaway game and queue in tmp_path."""
import json
from pathlib import Path

import pytest
from PIL import Image

from forge import config as cfgmod, manifest, review, brief, doctor


def make_world(tmp_path):
    game_root = tmp_path / "Game"
    assets = game_root / "project" / "assets"
    (assets / "placeholder").mkdir(parents=True)
    (assets / "vignettes" / "gate_law").mkdir(parents=True)
    Image.new("RGB", (288, 162), (90, 90, 90)).save(assets / "vignettes" / "gate_law" / "01_ribbon.png")
    Image.new("RGBA", (384, 72)).save(assets / "placeholder" / "hero_sarah.png")
    maps = game_root / "project" / "data" / "maps"
    maps.mkdir(parents=True)
    (maps / "bills_house.json").write_text(json.dumps({"id": "bills_house", "name": "Bill's house", "tile_size": 32,
        "notes": "05.7 / 15.2 — suburban home: the living room with the server rack", "lighting": {"time": "interior"},
        "rows": ["#" * 24] * 16}), encoding="utf-8")
    data = game_root / "project" / "data"
    (data / "records.json").write_text(json.dumps({"notes": "x", "song_a": {"title": "Song A", "singer": "Sarah", "album": "Two",
        "album_no": "2", "sleeve": "res://assets/sleeves/song_a.png"}}), encoding="utf-8")
    (data / "items.json").write_text(json.dumps({"coolant": {"name": "Coolant", "kind": "repair", "desc": "Cools a core."}}), encoding="utf-8")
    games = tmp_path / "games"
    (games / "tg" / "batches").mkdir(parents=True)
    src = cfgmod.ROOT / "games" / "turing_accords" / "export_wanted.py"
    (games / "tg" / "export_wanted.py").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (games / "tg" / "forge.game.json").write_text(json.dumps({"game_root": str(game_root), "asset_root": str(assets),
        "provenance_dir": str(assets / "_provenance")}), encoding="utf-8")
    (games / "tg" / "batches" / "cards.json").write_text(json.dumps({"batch": "cards", "approved": [], "jobs": []}), encoding="utf-8")
    cfg = cfgmod.load()
    cfg = dict(cfg)
    cfg["paths"] = dict(cfg["paths"], jobs=str(tmp_path / "jobs"), out=str(tmp_path / "out"), games=str(games))
    cfg["allow_external_paths"] = True
    for s in ("pending", "running", "done", "failed"):
        (tmp_path / "jobs" / s).mkdir(parents=True, exist_ok=True)
    return cfg, game_root, assets


def fake_done_job(tmp_path, jid, checkpoint, outputs=("card_1.png", "card_2.png"), batch="cards", extra_prov=None):
    out = tmp_path / "out" / jid
    out.mkdir(parents=True)
    for i, o in enumerate(outputs):
        Image.new("RGB", (864, 486), (200, 100 + i * 40, 50)).save(out / o)
    prov = {"job_id": jid, "type": "scene_card", "checkpoint": checkpoint, "seed": 1}
    prov.update(extra_prov or {})
    (out / "prov.json").write_text(json.dumps(prov), encoding="utf-8")
    job = {"id": jid, "type": "scene_card", "name": "01_ribbon", "batch": batch, "game": "tg",
           "result": {"outputs": list(outputs)}}
    (tmp_path / "jobs" / "done" / f"{jid}.json").write_text(json.dumps(job), encoding="utf-8")
    return out


def test_wanted_export_and_status(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    d = manifest.refresh_wanted(cfg, "tg")
    items = d["items"]
    assert set(items) == {"placeholder/hero_sarah", "vignettes/gate_law/01_ribbon", "scenes/bills_house", "sleeves/song_a"}
    assert items["scenes/bills_house"]["target_size"] == [2304, 1536] and items["scenes/bills_house"]["exists"] is False
    assert items["placeholder/hero_sarah"]["kind"] == "sprite_sheet" and items["placeholder/hero_sarah"]["target_size"] == [1152, 216]
    assert items["sleeves/song_a"]["path"] == "project/assets/sleeves/song_a.png"
    rows = manifest.status(cfg, "tg")
    assert {r["state"] for r in rows} == {"missing"}


def test_approve_copies_with_provenance_and_records(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    manifest.refresh_wanted(cfg, "tg")
    fake_done_job(tmp_path, "J1", "sd_xl_base_1.0.safetensors")
    with pytest.raises(manifest.ApproveError, match="--pick"):
        manifest.approve(cfg, "J1", "vignettes/gate_law/01_ribbon")
    plan = manifest.approve(cfg, "J1", "vignettes/gate_law/01_ribbon", pick=2, dry_run=True)
    assert plan["dry_run"] and Image.open(assets / "vignettes/gate_law/01_ribbon.png").size == (288, 162)   # untouched
    r = manifest.approve(cfg, "J1", "vignettes/gate_law/01_ribbon", pick=2)
    dest = assets / "vignettes" / "gate_law" / "01_ribbon.png"
    assert Image.open(dest).size == (864, 486)
    prov = json.loads((assets / "_provenance" / "vignettes__gate_law__01_ribbon.json").read_text(encoding="utf-8"))
    assert prov["job_id"] == "J1" and prov["licences"][0]["commercial_ok"] is True
    backups = list((tmp_path / "out" / "_approved_backup").rglob("*.png"))
    assert len(backups) == 1 and Image.open(backups[0]).size == (288, 162)                                  # the placeholder kept
    batch = json.loads((tmp_path / "games" / "tg" / "batches" / "cards.json").read_text(encoding="utf-8"))
    assert batch["approved"][0]["wanted"] == "vignettes/gate_law/01_ribbon"
    states = {x["name"]: x["state"] for x in manifest.status(cfg, "tg")}
    assert states["vignettes/gate_law/01_ribbon"] == "approved"
    Image.new("RGB", (10, 10)).save(dest)                       # e.g. make_placeholders.py ran again
    assert {x["name"]: x["state"] for x in manifest.status(cfg, "tg")}["vignettes/gate_law/01_ribbon"] == "stale"
    assert "sd_xl_base_1.0" in manifest.licence_report(cfg, "tg")


def test_approve_refuses_unknown_and_noncommercial_and_follows_inputs(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    manifest.refresh_wanted(cfg, "tg")
    fake_done_job(tmp_path, "J2", "SomeCivitaiModel_v3.safetensors", outputs=("card.png",))
    with pytest.raises(manifest.ApproveError, match="SomeCivitaiModel_v3.safetensors"):
        manifest.approve(cfg, "J2", "vignettes/gate_law/01_ribbon")
    fake_done_job(tmp_path, "J3", "flux1-dev-fp8.safetensors", outputs=("card.png",))
    with pytest.raises(manifest.ApproveError, match="commercial"):
        manifest.approve(cfg, "J3", "vignettes/gate_law/01_ribbon")
    # a CPU job made from J3's output inherits J3's models — no laundering through a palette snap
    fake_done_job(tmp_path, "J4", None, outputs=("card.png",),
                  extra_prov={"op": "palette_snap", "checkpoint": None, "inputs": [str(tmp_path / "out" / "J3" / "card.png")]})
    with pytest.raises(manifest.ApproveError, match="flux1-dev"):
        manifest.approve(cfg, "J4", "vignettes/gate_law/01_ribbon")
    with pytest.raises(manifest.ApproveError, match="not in"):
        manifest.approve(cfg, "J3", "vignettes/gate_law/99_nope")


def test_recorded_licence_unlocks_approval(tmp_path, monkeypatch):
    cfg, root, assets = make_world(tmp_path)
    manifest.refresh_wanted(cfg, "tg")
    fake_done_job(tmp_path, "J5", "MyCheckedModel.safetensors", outputs=("card.png",))
    fake_root = tmp_path / "repo"
    (fake_root / "models").mkdir(parents=True)
    (fake_root / "models" / "models.json").write_text((cfgmod.ROOT / "models" / "models.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(cfgmod, "ROOT", fake_root)
    manifest.record_licence(cfg, "MyCheckedModel.safetensors", "CreativeML Open RAIL++-M", True, "civitai page, 2026-11-09")
    r = manifest.approve(cfg, "J5", "vignettes/gate_law/01_ribbon")
    assert r["licences"][0]["license"] == "CreativeML Open RAIL++-M"


def test_review_and_rating_import(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    fake_done_job(tmp_path, "R1", "sd_xl_base_1.0.safetensors", outputs=("card.png",), batch="cards")
    fake_done_job(tmp_path, "R2", "flux1-dev-fp8.safetensors", outputs=("card.png",), batch="cards",
                  extra_prov={"commercial_ok": False})
    out = review.build(cfg, "cards", by="model", thumb=64)
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "R1" in html and 'class="card nc' in html and "Export ratings.json" in html
    assert list(out.glob("sheet_*.png")) and (out / "thumbs" / "R1.jpg").exists()
    exported = tmp_path / "ratings_cards.json"
    exported.write_text(json.dumps({"target": "cards", "ratings": {"R1": {"score": 4, "note": "good light"}, "R2": {"score": 0}}}), encoding="utf-8")
    rf, n = review.import_ratings(cfg, "cards", exported)
    assert n == 1 and json.loads(rf.read_text(encoding="utf-8"))["R1"]["score"] == 4
    html2 = (review.build(cfg, "cards") / "index.html").read_text(encoding="utf-8")
    assert 'value="4" checked' in html2


def test_brief_drafts(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    m = brief.maps(cfg, "tg")
    j = m["jobs"][0]
    assert m["_draft"] and j["type"] == "scene_paint" and j["target"] == [2304, 1536]
    assert j["prompt"].startswith("Bill's house, suburban home") and "05.7" not in j["prompt"]
    (assets / "scenes").mkdir()
    Image.new("RGB", (2304, 1536)).save(assets / "scenes" / "bills_house_greybox.png")
    j2 = brief.maps(cfg, "tg")["jobs"][0]
    assert j2["type"] == "repaint" and j2["control"]["type"] == "canny"
    s = brief.sleeves(cfg, "tg")
    assert s["jobs"][0]["title"] == "Song A" and s["defaults"]["type"] == "sleeve"
    assert brief.icons(cfg, "tg")["jobs"][0]["prompt"] == "Coolant, Cools a core"
    from forge import cli
    p, n = brief.write(cfg, "tg", "maps")
    assert n == 1
    assert cli.cmd_submit(cfg, [str(p)]) == 2        # drafts are refused


def test_doctor_shapes_and_queue(tmp_path):
    shapes = doctor.graph_shapes()
    assert "UnetLoaderGGUF" in shapes["flux1 gguf"] and "Flux2Scheduler" in shapes["flux2_klein"]
    assert shapes["upscale"] == {"UpscaleModelLoader", "ImageUpscaleWithModel", "ImageScale"}
    info = {n: {} for n in shapes["sdxl"] | shapes["flux1"] | shapes["flux2_klein"] | shapes["upscale"] | shapes["refine"]}
    line = doctor.node_report(info)[0]
    assert "flux2_klein: OK" in line and "flux1 gguf: UnetLoaderGGUF missing → install_comfy_gguf.bat" in line
    assert "FaceDetailer" in line and "install_comfy_faces.bat" in line
    cfg, root, assets = make_world(tmp_path)
    (tmp_path / "jobs" / "pending" / "x.json").write_text(json.dumps({"id": "x", "type": "scene_paint", "prompt": "p",
        "checkpoint": "nope_missing.safetensors", "face_fix": True, "control": {"type": "canny"}}), encoding="utf-8")
    lines = doctor.queue_report(cfg)
    text = "\n".join(lines)
    assert "checkpoint nope_missing.safetensors" in text and "controlnet" in text and "face_detector face_yolov8m.pt" in text


def test_queue_priority_and_pause(tmp_path):
    from forge.queue import Queue
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    a = q.submit({"type": "canny", "name": "a", "inputs": ["x"], "batch": "bakeoff/style_v1"})
    b = q.submit({"type": "canny", "name": "b", "inputs": ["x"], "priority": 10})
    c = q.submit({"type": "canny", "name": "c", "inputs": ["x"], "batch": "bakeoff/style_v1"})
    assert q.claim()[0] == b                                    # priority first
    assert q.pause("bakeoff/") == 2 and q.status()["paused"] == 2 and q.claim() is None
    assert q.resume() == 2 and q.claim()[0] == a                # then oldest
