"""BUILD 12 — art production in the suite: the Wanted board (where every wanted item stands; a selection planned with
hours and disk; queued only when nothing refuses), Review & approve → Deliver (held approvals, the dry-run list, the
copy with its ledger, nothing deleted), and Make a picture (a form by kind; the prompt expanded with every block
marked; refusals beside their field). A throwaway game ("tg", tests/test_night4_produce.world) — no real game."""
from __future__ import annotations
import json, threading, urllib.request
from pathlib import Path

import pytest
from PIL import Image

from forge import manifest
from forge.suite import games, journal, picture as make, production, settings
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
    from forge.night4 import produce as _pr
    _pr._measured_cache.clear()
    manifest.refresh_wanted(cfg, "tg")
    return cfg, root, assets, tmp_path


def _write_blocks(cfg):
    """Stand-in for the art direction filling the shelves (every TODO block gets words)."""
    g = Path(cfg["paths"]["games"]) / "tg" / "prompts"
    for f in g.glob("*.json"):
        if f.name == "never.json":
            continue
        d = json.loads(f.read_text())
        d["blocks"] = {k: (f"words for {k}" if str(v).startswith("TODO") else v) for k, v in (d.get("blocks") or {}).items()}
        f.write_text(json.dumps(d))


def _ok_licences(monkeypatch):
    from forge import manifest as mf
    monkeypatch.setattr(mf, "licence_chain", lambda ctx, parts: ([{"role": "checkpoint", "file": "x.safetensors",
                                                                   "license": "test", "commercial_ok": True}], True))


def _state(b, name):
    return next(r for r in b["items"] if r["name"] == name)["state"]


# ---------------------------------------------------------------- the Wanted board
def test_the_board_says_where_every_item_stands(tg):
    cfg, root, assets, tmp = tg
    b = production.board(cfg, "tg")
    names = {r["name"] for r in b["items"]}
    assert "scenes/bills_house" in names and not any(n.endswith("_depth") for n in names), "kit slots ride with the painting"
    bh = next(r for r in b["items"] if r["name"] == "scenes/bills_house")
    assert bh["state"] == "missing" and bh["town"] == "linden_mills" and bh["fate"] == "spared" and bh["first_hour"]
    assert _state(b, "placeholder/hero_sarah") == "stand-in"
    production.make_plan(cfg, "tg", "Bill")
    b = production.board(cfg, "tg")
    assert _state(b, "scenes/bills_house") == "drafted" and b["plan"]["jobs"] > 0
    (tmp / "jobs" / "pending" / "q1.json").write_text(json.dumps({"id": "q1", "type": "scene_kit", "_wanted": "scenes/hobby_shop"}))
    fake_done_job(tmp, "d1", "x.safetensors", outputs=("card_1.png",))
    j = json.loads((tmp / "jobs" / "done" / "d1.json").read_text())
    j["_wanted"] = "vignettes/gate_law/01_ribbon"
    (tmp / "jobs" / "done" / "d1.json").write_text(json.dumps(j))
    b = production.board(cfg, "tg")
    assert _state(b, "scenes/hobby_shop") == "queued" and _state(b, "vignettes/gate_law/01_ribbon") == "rendered"
    lines = journal.read(games.game_root(cfg, "tg"))
    assert lines[-1]["kind"] == "queue" and lines[-1]["obj"] == "produce plan" and lines[-1]["who"] == "Bill"


def test_a_town_is_planned_with_hours_and_disk_and_queued_only_when_nothing_refuses(tg):
    cfg, root, assets, tmp = tg
    r = production.plan_selection(cfg, "tg", ["scenes/bills_house"])
    assert r["ok"] is False and r["no_plan"]
    production.make_plan(cfg, "tg", "Bill")
    town = [x["name"] for x in production.board(cfg, "tg")["items"] if x["town"] == "linden_mills"]
    assert {"scenes/bills_house", "scenes/hobby_shop"} <= set(town)
    r = production.plan_selection(cfg, "tg", town)
    assert {j["name"] for j in r["jobs"]} == {"bills_house", "hobby_shop"}, "a selection plans only its own jobs"
    assert r["estimate"]["gpu_hours"] > 0 and r["estimate"]["disk_gb"] > 0 and r["estimate"]["free_gb"] is not None
    assert r["can_queue"] is False and any("culture.linden_mills" in b["problem"] for b in r["blockers"])
    q = production.queue_selection(cfg, "tg", town, "Bill")
    assert q["ok"] is False and "culture.linden_mills" in q["message"]
    assert not list((tmp / "jobs" / "pending").glob("*.json"))
    _write_blocks(cfg)
    r = production.plan_selection(cfg, "tg", town)
    assert r["can_queue"], r["blockers"]
    with pytest.raises(production.ProductionRefused, match="who you are"):
        production.queue_selection(cfg, "tg", town, None)
    q = production.queue_selection(cfg, "tg", town, "Bill")
    assert q["ok"], q
    pend = [json.loads(p.read_text()) for p in (tmp / "jobs" / "pending").glob("*.json")]
    assert len(pend) == 2 and {j["meta"]["town"] for j in pend} == {"linden_mills"} and all("{{" not in j["prompt"] for j in pend)
    assert not any(j["type"] == "icon_batch" for j in pend), "the icons were not selected, so they are not queued"
    b = production.board(cfg, "tg")
    assert _state(b, "scenes/bills_house") == "queued"
    left = production.plan_selection(cfg, "tg", ["placeholder/hero_sarah"])["left_out"]
    assert left and "Sprite intake" in left[0]["why"]


# ---------------------------------------------------------------- Review & approve → Deliver
def _done_card(tmp, assets, cfg):
    out = fake_done_job(tmp, "J9", "x.safetensors", outputs=("card_1.png",))
    w = manifest.load_wanted(cfg, "tg")["items"]["vignettes/gate_law/01_ribbon"]
    Image.new("RGB", tuple(w["target_size"]), (10, 200, 10)).save(out / "card_1.png")
    j = json.loads((tmp / "jobs" / "done" / "J9.json").read_text())
    j["_wanted"] = "vignettes/gate_law/01_ribbon"
    (tmp / "jobs" / "done" / "J9.json").write_text(json.dumps(j))
    return out


def test_review_approve_holds_then_deliver_copies_with_the_ledger(tg, monkeypatch):
    from forge import ui
    from forge.night4 import deliver as dl
    cfg, root, assets, tmp = tg
    _ok_licences(monkeypatch)
    _done_card(tmp, assets, cfg)
    st = ui.State(cfg)
    rv = production.review(cfg, "tg", st)
    assert [x["id"] for x in rv["waiting"]] == ["J9"] and rv["waiting"][0]["wanted"] == "vignettes/gate_law/01_ribbon"
    v = production.job_view(cfg, "tg", "J9", st)
    assert v["wanted"] == "vignettes/gate_law/01_ribbon" and v["files"][0]["file"] == "card_1.png" and v["licences"]
    dry = production.approve(cfg, "tg", "J9", "vignettes/gate_law/01_ribbon", "Bill", dry=True)
    assert dry["ok"] and dry["dry"] and dry["licences"][0]["commercial_ok"] is True
    before = (assets / "vignettes" / "gate_law" / "01_ribbon.png").read_bytes()
    with pytest.raises(production.ProductionRefused, match="assistant"):
        production.approve(cfg, "tg", "J9", "vignettes/gate_law/01_ribbon", "Claude Opus", dry=False)
    r = production.approve(cfg, "tg", "J9", "vignettes/gate_law/01_ribbon", "Bill", dry=False)
    assert r["ok"] and "held" in r["message"]
    assert (assets / "vignettes" / "gate_law" / "01_ribbon.png").read_bytes() == before, "approve holds; Deliver copies"
    assert _state(production.board(cfg, "tg"), "vignettes/gate_law/01_ribbon") == "approved"
    d = production.deliver(cfg, "tg", "Bill", dry=True)
    assert [x["wanted"] for x in d["ready"]] == ["vignettes/gate_law/01_ribbon"] and d["ready"][0]["why"] == "held approval"
    with pytest.raises(production.ProductionRefused, match="who you are"):
        production.deliver(cfg, "tg", None, dry=False)
    r = production.deliver(cfg, "tg", "Bill", dry=False)
    assert r["ok"] and r["moved"][0]["replaced"], r
    assert Image.open(assets / "vignettes" / "gate_law" / "01_ribbon.png").getpixel((3, 3)) == (10, 200, 10)
    assert Path(r["moved"][0]["replaced"]).read_bytes() == before, "the old file is kept, never deleted"
    assert dl.live(cfg, "tg")["vignettes/gate_law/01_ribbon"]["job_id"] == "J9"
    assert _state(production.board(cfg, "tg"), "vignettes/gate_law/01_ribbon") == "delivered"
    assert production.review(cfg, "tg", ui.State(cfg))["waiting"] == []
    kinds = [e["kind"] for e in journal.read(games.game_root(cfg, "tg"))]
    assert "approve" in kinds and "deliver" in kinds


def test_a_licence_problem_refuses_in_plain_words(tg):
    from forge import ui
    cfg, root, assets, tmp = tg
    _done_card(tmp, assets, cfg)                     # its checkpoint is not in the licence register
    r = production.approve(cfg, "tg", "J9", "vignettes/gate_law/01_ribbon", "Bill", dry=True)
    assert r["ok"] is False and "commercial" in r["message"]


def test_redo_with_a_note_is_a_draft_never_queued_and_send_out_makes_a_folder(tg):
    from forge import ui
    from forge.night4 import feedback
    cfg, root, assets, tmp = tg
    _done_card(tmp, assets, cfg)
    st = ui.State(cfg)
    with pytest.raises(production.ProductionRefused, match="say what to change"):
        production.redo(cfg, "tg", "J9", "  ", "Bill", st)
    r = production.redo(cfg, "tg", "J9", "the ribbon should be red", "Bill", st)
    assert r["ok"] and r["drafts"]
    d = feedback.list_drafts(cfg)
    assert d and d[0]["note"] == "the ribbon should be red" and d[0]["redo_of"] == "J9"
    assert not list((tmp / "jobs" / "pending").glob("*.json"))
    o = production.send_out(cfg, "tg", "J9", "Bill")
    assert o["ok"], o
    folder = tmp / "out" / "handoff" / o["handout"]["name"]
    assert (folder / "in").is_dir() and (folder / "done").is_dir() and list((folder / "in").glob("*.png"))


# ---------------------------------------------------------------- Make a picture
def test_make_a_picture_form_by_kind_with_the_games_defaults(tg):
    cfg, root, assets, tmp = tg
    k = make.kinds(cfg, "tg")
    types = {x["type"]: x for x in k["kinds"]}
    assert {"scene_kit", "portrait", "character_set", "icon", "tile_texture", "photo_plate", "render"} <= set(types)
    sk = {f["name"]: f for f in types["scene_kit"]["fields"]}
    assert sk["prompt"]["required"] and sk["prompt"]["label"] == "What to paint" and "target" in sk
    assert any(t["town"] == "linden_mills" for t in k["towns"]) and any(w["name"] == "scenes/bills_house" for w in k["wanted"])


def test_make_preview_marks_blocks_and_names_refusals_beside_the_field(tg):
    cfg, root, assets, tmp = tg
    form = {"type": "scene_kit", "fields": {"prompt": "a quiet street, {{style.house}}"}, "town": "linden_mills",
            "for": "scenes/bills_house", "takes": 2}
    pv = make.preview(cfg, "tg", form)
    assert pv["can_queue"] is False
    states = {b["ref"]: b["state"] for b in pv["blocks"]["prompt"]}
    assert states["style.house"] == "placeholder" and states["culture.linden_mills"] == "missing"   # plan hasn't added it yet
    assert any(p["field"] == "prompt" for p in pv["problems"])
    j = pv["jobs"][0]
    assert j["target"] == manifest.load_wanted(cfg, "tg")["items"]["scenes/bills_house"]["target_size"]
    assert j["_wanted"] == "scenes/bills_house" and j["meta"]["town"] == "linden_mills" and len(pv["jobs"]) == 2
    assert pv["jobs"][1]["seed"] == pv["jobs"][0]["seed"] + 1, "takes are neighbouring seeds of the town's family seed"
    bad = make.preview(cfg, "tg", {"type": "scene_kit", "fields": {"prompt": "", "target": "big"}})
    fields = {p["field"] for p in bad["problems"]}
    assert {"prompt", "target"} <= fields
    assert make.queue(cfg, "tg", form, "Bill")["ok"] is False
    assert not list((tmp / "jobs" / "pending").glob("*.json"))


def test_make_queues_through_submit_once_the_words_exist(tg):
    from forge.night4 import produce
    cfg, root, assets, tmp = tg
    produce.plan(cfg, "tg")                           # adds the culture/fate placeholders
    _write_blocks(cfg)
    form = {"type": "scene_kit", "fields": {"prompt": "a quiet street, {{style.house}}"}, "town": "linden_mills",
            "for": "scenes/bills_house", "takes": 2, "name": "bh test"}
    pv = make.preview(cfg, "tg", form)
    assert pv["can_queue"], pv["problems"]
    assert "words for style.house" in pv["expanded"]["prompt"] and "words for culture.linden_mills" in pv["expanded"]["prompt"]
    with pytest.raises(make.MakeRefused, match="who you are"):
        make.queue(cfg, "tg", form, None)
    r = make.queue(cfg, "tg", form, "Bill")
    assert r["ok"], r["printed"]
    pend = sorted((json.loads(p.read_text()) for p in (tmp / "jobs" / "pending").glob("*.json")), key=lambda j: j["name"])
    assert [j["name"] for j in pend] == ["bh_test_01", "bh_test_02"] and all("{{" not in j["prompt"] for j in pend)
    assert all(j["_wanted"] == "scenes/bills_house" and j["batch"] == "make/scene_kit" for j in pend)
    assert _state(production.board(cfg, "tg"), "scenes/bills_house") == "queued"
    assert any(e["obj"].startswith("make · scene_kit") for e in journal.read(games.game_root(cfg, "tg")))


def test_make_with_a_character_uses_the_registry(tg):
    cfg, root, assets, tmp = tg
    chdir = Path(cfg["paths"]["games"]) / "tg" / "characters"
    chdir.mkdir(exist_ok=True)
    (chdir / "mira.json").write_text(json.dumps({"id": "mira", "name": "Mira", "variants": {"day": {
        "prompt": "{{char.mira}}", "checkpoint": "ArtUniverseSDXL_v8.safetensors", "seed": 555, "size": [832, 1216]}}}))
    lib = Path(cfg["paths"]["games"]) / "tg" / "prompts" / "lib.json"
    lib.write_text(json.dumps({"blocks": {"style.house": "a house style", "char.mira": "a tall woman in a green coat"}}))
    pv = make.preview(cfg, "tg", {"type": "render", "fields": {"prompt": "{{character}}, laughing"}, "character": "mira",
                                  "variant": "day"})
    assert pv["can_queue"], pv["problems"]
    assert pv["expanded"]["prompt"] == "a tall woman in a green coat, laughing" and pv["shown"]["seed"] == 555
    nope = make.preview(cfg, "tg", {"type": "character_set", "fields": {}, "character": ""})
    assert any(p["field"] == "character" for p in nope["problems"])
    with pytest.raises(make.MakeRefused, match="kind"):
        make.preview(cfg, "tg", {"type": "nonsense"})


# ---------------------------------------------------------------- the app
def test_the_production_screens_over_http(tg, monkeypatch):
    from forge.suite import server
    cfg, root, assets, tmp = tg
    settings.update(last_game="tg")
    srv = server.make_server(cfg, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/", timeout=20).read()
        assert b"Wanted" in page and b"Make a picture" in page and b"Review" in page
        b = json.loads(urllib.request.urlopen(base + "/api/suite/wanted?id=tg", timeout=20).read())
        assert any(r["name"] == "scenes/bills_house" for r in b["items"])
        k = json.loads(urllib.request.urlopen(base + "/api/suite/make?id=tg", timeout=20).read())
        assert k["kinds"]

        def post(a, body):
            req = urllib.request.Request(base + "/api/suite/act/" + a, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "X-Forge": "1"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        assert post("wanted_plan", {"game": "tg"})["ok"] is False             # nobody signed in
        post("identity", {"name": "Bill"})
        assert post("wanted_plan", {"game": "tg"})["ok"]
        sel = post("wanted_select", {"game": "tg", "names": ["scenes/bills_house"]})
        assert sel["ok"] and sel["jobs"][0]["name"] == "bills_house" and sel["can_queue"] is False
        pv = post("make_preview", {"game": "tg", "form": {"type": "icon", "fields": {"prompt": "a wrench"}}})
        assert pv["ok"] and pv["can_queue"], pv
        rv = json.loads(urllib.request.urlopen(base + "/api/suite/review?id=tg", timeout=20).read())
        assert "waiting" in rv and "deliver" in rv
    finally:
        srv.shutdown()


def test_town_sheet_and_atlas_from_the_board(tg):
    cfg, root, assets, tmp = tg
    r = production.town_sheet(cfg, "tg", "linden_mills", "Bill")
    assert r["ok"] is False and "Nothing to put on it yet" in r["message"]
    for i, name in enumerate(("bills_house", "hobby_shop")):
        jid = f"K{i}"
        out = tmp / "out" / jid
        out.mkdir(parents=True)
        Image.new("RGB", (480, 270), (60 + 80 * i, 90, 120)).save(out / "scene.png")
        (tmp / "jobs" / "done" / f"{jid}.json").write_text(json.dumps({"id": jid, "type": "scene_kit", "name": name,
            "game": "tg", "meta": {"town": "linden_mills", "era": "peace"}, "result": {"outputs": ["scene.png"]}}))
    r = production.town_sheet(cfg, "tg", "linden_mills", "Bill")
    assert r["ok"], r
    assert r["sheets"][0].startswith("/out/review/town_linden_mills/") and (tmp / "out" / r["sheets"][0][len("/out/"):]).exists()
    a = production.town_sheet(cfg, "tg", None, "Bill")
    assert a["ok"] and "/atlas/" in a["sheets"][0]


def test_an_approved_kit_goes_into_the_game_as_a_set(tg, monkeypatch):
    """A scene kit is approved as one set (the kit check first; all six files or none) — then the board says delivered."""
    from forge import kitcheck
    from test_scene_set import fake_kit_job, SFX
    cfg, root, assets, tmp = tg
    _ok_licences(monkeypatch)
    fake_kit_job(tmp, "K7")
    monkeypatch.setattr(kitcheck, "check", lambda cfg, d, name: {"verdict": "fail", "lines": [
        {"check": "depth.range", "status": "fail", "message": "flat depth"}]})
    r = production.approve(cfg, "tg", "K7", "scenes/bills_house", "Bill", as_set=True, dry=True)
    assert r["ok"] is False and "flat depth" in r["message"]
    monkeypatch.setattr(kitcheck, "check", lambda cfg, d, name: {"verdict": "pass", "lines": []})
    r = production.approve(cfg, "tg", "K7", "scenes/bills_house", "Bill", as_set=True, dry=True)
    assert r["ok"] and r["dry"] and len(r["rows"]) == 6 and not (assets / "scenes").exists()
    r = production.approve(cfg, "tg", "K7", "scenes/bills_house", "Bill", as_set=True, dry=False)
    assert r["ok"], r
    for s in SFX:
        assert (assets / "scenes" / f"bills_house{s}.png").exists()
    assert _state(production.board(cfg, "tg"), "scenes/bills_house") == "delivered"
    assert any(e["kind"] == "approve" and e["obj"] == "scenes/bills_house" for e in journal.read(games.game_root(cfg, "tg")))
