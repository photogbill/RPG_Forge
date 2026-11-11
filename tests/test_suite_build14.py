"""BUILD 14 — art feedback and finishing in the suite: a circled complaint on a picture becomes an inpaint mask and a
redo draft (never queued) under Called out; the drafts are queued, dismissed or handed out from there; the prompt
library as shelves (words edited format-preserving, signed); the bake-off suites, the outside-tool hand-offs and the
model shelf with its safe-to-delete totals (it deletes nothing). A throwaway game ("tg") — no real game."""
from __future__ import annotations
import json, threading, urllib.request
from pathlib import Path

import pytest
from PIL import Image

from forge import manifest
from forge.suite import finishing, games, journal, production, settings
from test_manifest import fake_done_job
from test_night4_produce import world as produce_world


@pytest.fixture
def tg(tmp_path, monkeypatch):
    cfg, root, assets = produce_world(tmp_path)
    monkeypatch.setattr(settings, "PATH", tmp_path / "local" / "suite.json")
    monkeypatch.delenv("FORGE_IDENTITY", raising=False)
    monkeypatch.delenv("FORGE_GAME_ROOTS", raising=False)
    games._loaded.clear()
    production._done.clear()
    production._queued.clear()
    manifest.refresh_wanted(cfg, "tg")
    return cfg, root, assets, tmp_path


def _picture(tmp, cfg, jid="J5"):
    out = fake_done_job(tmp, jid, "x.safetensors", outputs=("card_1.png",))
    Image.new("RGB", (400, 300), (30, 120, 200)).save(out / "card_1.png")
    p = tmp / "jobs" / "done" / f"{jid}.json"
    j = json.loads(p.read_text())
    j.update({"_wanted": "vignettes/gate_law/01_ribbon", "prompt": "a ribbon across the gate", "seed": 77})
    p.write_text(json.dumps(j))
    return out


def test_a_circled_complaint_becomes_a_mask_and_a_reviewable_redo_draft(tg):
    from forge import ui
    cfg, root, assets, tmp = tg
    _picture(tmp, cfg)
    st = ui.State(cfg)
    shapes = [{"kind": "ellipse", "box": [100, 50, 200, 150]}]
    with pytest.raises(finishing.FinishRefused, match="who you are"):
        finishing.markup(cfg, "tg", "J5", "card_1.png", shapes, "the hand", "", None, st)
    with pytest.raises(finishing.FinishRefused, match="say what's wrong"):
        finishing.markup(cfg, "tg", "J5", "card_1.png", shapes, " ", "", "Bill", st)
    with pytest.raises(finishing.FinishRefused, match="circle"):
        finishing.markup(cfg, "tg", "J5", "card_1.png", [], "the hand", "", "Bill", st)
    with pytest.raises(finishing.FinishRefused, match="not in out"):
        finishing.markup(cfg, "tg", "J5", "nope.png", shapes, "the hand", "", "Bill", st)
    r = finishing.markup(cfg, "tg", "J5", "card_1.png", shapes, "the hand has six fingers", "", "Bill", st)
    assert r["ok"] and len(r["drafts"]) == 2 and 0.05 < r["share"] < 0.08
    drafts = {d["draft"]: d for d in finishing.called_out(cfg)}
    fix = next(d for n, d in drafts.items() if "-fix-" in n)
    redo = next(d for n, d in drafts.items() if "-redo-" in n)
    assert fix["note"] == "the hand has six fingers" and fix["type"] == "scene_state" and fix["ready"] is False
    assert fix["base"] == "out/J5/card_1.png" and fix["source"] == "mark-up in the suite" and fix["by"] == "Bill"
    m = Image.open(fix["mask"])
    assert m.size == (400, 300) and m.getpixel((150, 100)) == 255 and m.getpixel((20, 20)) == 0
    assert (tmp / fix["marked"].lstrip("/")).exists() or (tmp / "out" / fix["marked"][len("/out/"):]).exists()
    assert redo["redo_of"] == "J5" and redo["type"] == "scene_card"
    assert not list((tmp / "jobs" / "pending").glob("*.json")), "a mark-up never queues anything by itself"
    lines = [e for e in journal.read(games.game_root(cfg, "tg")) if e["kind"] == "draft"]
    assert lines and "six fingers" in lines[-1]["note"]


def test_with_a_line_saying_what_it_should_be_the_fix_can_be_queued_from_called_out(tg):
    from forge import ui
    cfg, root, assets, tmp = tg
    _picture(tmp, cfg)
    st = ui.State(cfg)
    r = finishing.markup(cfg, "tg", "J5", "card_1.png", [{"kind": "stroke", "points": [[50, 50], [120, 80], [200, 60]], "width": 30}],
                         "the window is crooked", "a straight sash window", "Bill", st)
    assert r["ok"]
    fix = next(d for d in finishing.called_out(cfg) if "-fix-" in d["draft"])
    assert fix["ready"] is True and fix["prompt"] == "a straight sash window"
    with pytest.raises(finishing.FinishRefused, match="who you are"):
        finishing.callout(cfg, "tg", "draft_submit", fix["draft"], None)
    q = finishing.callout(cfg, "tg", "draft_submit", fix["draft"], "Bill")
    assert q["ok"], q
    pend = [json.loads(p.read_text()) for p in (tmp / "jobs" / "pending").glob("*.json")]
    assert len(pend) == 1 and pend[0]["type"] == "scene_state" and Path(pend[0]["mask"]).exists()
    redo = next(d for d in finishing.called_out(cfg) if "-redo-" in d["draft"])
    d = finishing.callout(cfg, "tg", "draft_dismiss", redo["draft"], "Bill")
    assert d["ok"] and not any(x["draft"] == redo["draft"] for x in finishing.called_out(cfg))
    assert (tmp / "jobs" / "drafts" / "_dismissed" / redo["draft"]).exists(), "dismissed is kept, not deleted"


def test_a_kit_is_marked_up_on_its_folder(tg):
    from forge import ui
    from test_scene_set import fake_kit_job
    cfg, root, assets, tmp = tg
    out = fake_kit_job(tmp, "K3")
    Image.new("RGB", (480, 270), (90, 90, 90)).save(out / "scene.png")
    r = finishing.markup(cfg, "tg", "K3", "scene.png", [{"kind": "ellipse", "box": [10, 10, 60, 60]}], "a stray lamp", "",
                         "Bill", ui.State(cfg))
    fix = next(d for d in finishing.called_out(cfg) if "-fix-" in d["draft"])
    assert r["ok"] and fix["base"] == "out/K3"


def test_playtest_notes_come_in_as_drafts(tg):
    cfg, root, assets, tmp = tg
    r = finishing.take_in(cfg, "tg", "Bill")
    assert r["ok"] is False and "art_feedback.json" in r["message"]
    (root / "playtest").mkdir()
    (root / "playtest" / "art_feedback.json").write_text(json.dumps({"entries": [
        {"map": "bills_house", "files": ["res://assets/placeholder/hero_sarah.png"], "note": "too small", "time": "t1", "tester": "Bill"}]}))
    r = finishing.take_in(cfg, "tg", "Bill")
    assert r["ok"] and "stand-in" in r["message"]


def test_the_prompt_library_as_shelves_and_its_words_saved_carefully(tg):
    cfg, root, assets, tmp = tg
    lib = finishing.library(cfg, "tg")
    style = next(s for s in lib["shelves"] if s["shelf"] == "style")
    assert style["blocks"][0]["name"] == "style.house" and style["blocks"][0]["state"] == "placeholder" and style["placeholders"] == 1
    p = Path(cfg["paths"]["games"]) / "tg" / "prompts" / "lib.json"
    raw = p.read_text()
    with pytest.raises(finishing.FinishRefused, match="who you are"):
        finishing.edit_block(cfg, "tg", "style.house", "oil on board", None)
    r = finishing.edit_block(cfg, "tg", "style.house", "oil on board, warm light", "Claude Fable")
    assert r["ok"] and r["changed"]
    assert json.loads(p.read_text())["blocks"]["style.house"] == "oil on board, warm light"
    assert p.read_text() == raw.replace("TODO house", "oil on board, warm light"), "only the block's own bytes change"
    assert list((p.parent / "_history").glob("lib.*.json"))
    assert finishing.edit_block(cfg, "tg", "style.house", "oil on board, warm light", "Claude Fable")["changed"] is False
    with pytest.raises(finishing.FinishRefused, match="shelf.name"):
        finishing.edit_block(cfg, "tg", "nodot", "x", "Bill")
    with pytest.raises(finishing.FinishRefused, match="expand"):
        finishing.edit_block(cfg, "tg", "light.dusk", "{{no.such.block}}", "Bill")
    nv = Path(cfg["paths"]["games"]) / "tg" / "prompts" / "never.json"
    nv.write_text(json.dumps({"words": ["Rutkowski"], "lora_triggers_forbidden": []}))
    with pytest.raises(finishing.FinishRefused, match="never-list"):
        finishing.edit_block(cfg, "tg", "light.dusk", "in the style of rutkowski", "Bill")
    r = finishing.edit_block(cfg, "tg", "light.dusk", "sodium dusk", "Bill")
    assert r["ok"] and json.loads((p.parent / "night4.json").read_text())["blocks"]["light.dusk"] == "sodium dusk"
    e = [x for x in journal.read(games.game_root(cfg, "tg")) if x["kind"] == "edit"][0]
    assert e["obj"] == "prompt block · style.house" and e["before"] == "TODO house" and e["who"] == "Claude Fable"


def test_the_model_shelf_says_what_can_go_and_deletes_nothing(tg):
    cfg, root, assets, tmp = tg
    mdir = Path(next(iter(cfg["model_dirs"].values()))[0])
    f = mdir / "Pixel_Xl_V1.safetensors"
    f.write_bytes(b"\0" * 2048)
    r = finishing.models(cfg, "tg", scan=False)
    row = next(x for x in r["rows"] if x["file"] == "Pixel_Xl_V1.safetensors")
    assert row["verdict"].startswith("dropped") and row["safe_to_delete"] is True
    assert r["totals"]["safe"] >= 1 and "safe_gb" in r["totals"] and r["report"].startswith("/out/reports/MODELS_SHELF_")
    assert f.exists(), "a report only — nothing deleted"


def test_bakeoffs_and_handoffs_are_listed(tg):
    cfg, root, assets, tmp = tg
    b = finishing.bakeoffs(cfg, "tg")
    assert b["suites"] == []
    h = finishing.handoffs(cfg)
    assert h["handoffs"] == [] and "tools" in h
    _picture(tmp, cfg)
    production.send_out(cfg, "tg", "J5", "Bill")
    h = finishing.handoffs(cfg)
    assert h["handoffs"][0]["entries"] == 1 and h["handoffs"][0]["back"] == 0 and h["handoffs"][0]["missing"]
    with pytest.raises(finishing.FinishRefused, match="hand-off folder"):
        finishing.open_folder(cfg, str(tmp))
    r = finishing.hand_in(cfg, "tg", "no_such_handoff", None, "Bill")
    assert r["ok"] is False and "no hand-off" in r["message"]


def test_the_finishing_screens_over_http(tg):
    from forge.suite import server
    cfg, root, assets, tmp = tg
    settings.update(last_game="tg")
    _picture(tmp, cfg)
    srv = server.make_server(cfg, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(a, body):
        req = urllib.request.Request(base + "/api/suite/act/" + a, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Forge": "1"})
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    try:
        page = urllib.request.urlopen(base + "/", timeout=20).read()
        for word in (b"Prompt library", b"Bake-offs", b"Models", b"Outside tools", b"Called out", b"Mark up"):
            assert word in page, word
        lib = json.loads(urllib.request.urlopen(base + "/api/suite/library?id=tg", timeout=20).read())
        assert lib["shelves"]
        post("identity", {"name": "Bill"})
        r = post("fin_markup", {"game": "tg", "jid": "J5", "file": "card_1.png", "note": "too dark",
                                "shapes": [{"kind": "ellipse", "box": [0, 0, 100, 100]}]})
        assert r["ok"], r
        co = json.loads(urllib.request.urlopen(base + "/api/suite/calledout", timeout=20).read())
        assert len(co["drafts"]) == 2
        assert json.loads(urllib.request.urlopen(base + "/api/suite/handoffs", timeout=20).read())["handoffs"] == []
    finally:
        srv.shutdown()


def test_a_delivered_picture_stays_on_the_review_screen_for_a_mark_up(tg, monkeypatch):
    """Done-when: a circled complaint on a DELIVERED picture becomes a reviewable redo draft."""
    from forge import ui, manifest as mf
    cfg, root, assets, tmp = tg
    monkeypatch.setattr(mf, "licence_chain", lambda ctx, parts: ([{"role": "checkpoint", "file": "x", "commercial_ok": True}], True))
    out = _picture(tmp, cfg)
    w = manifest.load_wanted(cfg, "tg")["items"]["vignettes/gate_law/01_ribbon"]
    Image.new("RGB", tuple(w["target_size"]), (200, 30, 30)).save(out / "card_1.png")
    assert production.approve(cfg, "tg", "J5", "vignettes/gate_law/01_ribbon", "Bill", dry=False)["ok"]
    assert production.deliver(cfg, "tg", "Bill", dry=False)["moved"]
    rv = production.review(cfg, "tg", ui.State(cfg))
    assert rv["waiting"] == [] and rv["decided"][0]["id"] == "J5" and rv["decided"][0]["verdict"] == "delivered"
    r = finishing.markup(cfg, "tg", "J5", "card_1.png", [{"kind": "ellipse", "box": [10, 10, 120, 90]}],
                         "it reads too red in the game", "", "Bill", ui.State(cfg))
    assert r["ok"] and any(d["redo_of"] == "J5" and d["note"] == "it reads too red in the game" for d in finishing.called_out(cfg))


def test_photographs_as_plates_show_the_people_guard_beside_the_field(tg):
    from forge.suite import picture
    cfg, root, assets, tmp = tg
    photo = tmp / "porch.jpg"
    Image.new("RGB", (64, 48)).save(photo)
    pv = picture.preview(cfg, "tg", {"type": "photo_plate", "fields": {"photo": str(photo), "prompt": "a porch at dusk"}})
    assert any(p["field"] == "photo" and "refs.local.json" in p["message"] for p in pv["problems"])
    refs = Path(cfg["paths"]["games"]) / "tg" / "refs.local.json"
    refs.write_text(json.dumps({"frames": {str(photo): {"people": "neighbours"}}}))
    pv = picture.preview(cfg, "tg", {"type": "photo_plate", "fields": {"photo": str(photo), "prompt": "a porch at dusk"}})
    assert any(p["field"] == "photo" and "only William" in p["message"] for p in pv["problems"])
    refs.write_text(json.dumps({"frames": {str(photo): {"people": "none"}}}))
    pv = picture.preview(cfg, "tg", {"type": "photo_plate", "fields": {"photo": str(photo), "prompt": "a porch at dusk"}})
    assert not any(p["field"] == "photo" for p in pv["problems"])
    tl = picture.preview(cfg, "tg", {"type": "tileable", "fields": {"input": "out/x/tile.png", "heal": "blend"}})
    assert tl["jobs"][0]["type"] == "tileable" and not any(p["field"] == "input" for p in tl["problems"])
