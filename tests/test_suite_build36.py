"""BUILD 36 — the 3D area in the suite: Bodies · Skeleton & motions · Props & buildings · Trees · Viewer · Runs, the 3D
models in Review & approve, Deliver into the game, and where a body stands. On a throwaway copy of the example game;
the queue's jobs are finished by hand here (the worker and the stand-in ComfyUI are tested in test_threed_build36.py)."""
from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from forge.suite import areas, server, settings, threed
from forge.threed import glb, standin
from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

BILL, OPUS = "Bill", "Claude Opus"


@pytest.fixture
def w(world):
    cfg, a, tmp = world
    threed._check_cache.clear()
    return cfg, a, tmp


def _finish(cfg, jid: str, result: dict, files: dict[str, bytes] | None = None, failed: str | None = None) -> None:
    """Play the worker: move a pending job to done (or failed) with a result, and write its files."""
    jobs = Path(cfg["paths"]["jobs"])
    j = json.loads((jobs / "pending" / f"{jid}.json").read_text())
    (jobs / "pending" / f"{jid}.json").unlink()
    out = Path(cfg["paths"]["out"]) / jid
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (files or {}).items():
        (out / name).write_bytes(data)
    if failed:
        j["error"] = failed
        (jobs / "failed" / f"{jid}.json").write_text(json.dumps(j))
    else:
        j["result"] = result
        (jobs / "done" / f"{jid}.json").write_text(json.dumps(j))


def _job(cfg, jid: str) -> dict:
    jobs = Path(cfg["paths"]["jobs"])
    for st in ("pending", "done", "failed"):
        p = jobs / st / f"{jid}.json"
        if p.exists():
            return json.loads(p.read_text())
    raise AssertionError(jid)


def _body_through(cfg, tmp, who="Wren Hale", look="A woman of thirty in a short canvas jacket, cropped hair, in a relaxed A-pose.",
                  never=None) -> str:
    r = threed.new_try(cfg, "_example", {"kind": "body", "who": who, "look": look, "height_m": 1.68}, BILL)
    tid = r["try"]
    _finish(cfg, r["job"], {"outputs": ["render.png", "render_2.png", "render_3.png", "render_4.png"]},
            {f: standin.png() for f in ("render.png", "render_2.png", "render_3.png", "render_4.png")})
    b = threed.make_body(cfg, "_example", tid, 2, BILL)
    bj = _job(cfg, b["job"])
    model = Path(cfg["paths"]["out"]) / b["job"] / f"{bj['name']}__trellis2.glb"
    _finish(cfg, b["job"], {"model": str(model), "picture": str(model.with_name("picture.png")), "engine": "trellis2", "info": {}},
            {"picture.png": standin.png()})
    glb.box(model, (0.6, 1.0, 0.4))
    if never is not None:
        threed.set_never(cfg, "_example", threed.slug(who), never, BILL)
    s = threed.add_skeleton(cfg, "_example", tid, None, BILL)
    fbx = Path(cfg["paths"]["out"]) / s["job"] / f"{bj['name']}__mia.fbx"
    _finish(cfg, s["job"], {"fbx": str(fbx), "rigger": "mia"}, {fbx.name: b"fbx"})
    m = threed.fit(cfg, "_example", tid, BILL)
    moves = Path(cfg["paths"]["out"]) / m["job"] / f"{bj['name']}_moves.glb"
    glb.box(moves, (0.5, 1.68, 0.3), motions=["Idle_Loop", "Walk_Loop"], joints=2)
    moves.with_suffix(".json").write_text(json.dumps({"height_m": 1.68, "motions": {"Walk_Loop": {"seconds": 1, "loop": True, "speed": 0.98}}}))
    _finish(cfg, m["job"], {"moves": str(moves), "sheet": str(moves.with_suffix(".json")), "motions": ["Idle_Loop", "Walk_Loop"],
                            "speeds": {"Walk_Loop": 0.98}})
    return tid


# ---------------------------------------------------------------- the area
def test_the_3d_area_has_its_tabs_each_with_a_screen_and_what_it_needs(w):
    cfg, a, _ = w
    a3 = next(x for x in areas.AREAS if x["id"] == "3d")
    assert [t["name"] for t in a3["tabs"]] == ["Bodies", "Skeleton & motions", "Props & buildings", "Trees", "World list",   # BUILD 39
                                               "Viewer", "Runs"]
    assert all(t["screen"] == "threed" and t["t3"] and t["holds"] for t in a3["tabs"])
    nd = areas.needs(cfg, "_example")
    assert "rigging ComfyUI" in nd["3d/skeleton"]["line"] or nd["3d/skeleton"]["met"] in (True, None)
    assert nd["3d/runs"]["met"] is True
    html = server.SHELL
    assert "threed:'v-threed'" in html and 'id="v-threed"' in html and '/suite/threed.js' in html and 'id="r-3d"' in html
    js = (REPO / "forge" / "suite" / "threed.js").read_text(encoding="utf-8")
    for fn in ("loadThreeD", "bodiesTab", "skeletonTab", "thingsTab", "treesTab", "viewerTab", "runsTab", "paintReview3d", "paintTools3d"):
        assert fn in js, fn


def test_the_standing_words_are_the_games_block_when_it_has_one(w):
    cfg, a, tmp = w
    wd = threed.words(cfg, "_example")
    assert wd["body"]["always"]["from"] == "forge" and "A-pose" in wd["body"]["always"]["text"]
    assert wd["building"]["model"] == "pixal3d" and wd["prop"]["model"] == "trellis2"
    p = Path(cfg["paths"]["games"]) / "_example" / "prompts" / "threed.json"
    p.write_text(json.dumps({"blocks": {"pose.threed_body": "Our own A-pose words.", "neg.threed_body": "TODO later"}}))
    wd = threed.words(cfg, "_example")
    assert wd["body"]["always"] == {"block": "pose.threed_body", "text": "Our own A-pose words.", "from": "game"}
    assert wd["body"]["negative"]["from"] == "forge"                     # a TODO placeholder is not used
    with pytest.raises(threed.ThreeDRefused, match="assistant"):
        threed.save_block(cfg, "_example", "pose.threed_body", "x", OPUS)
    with pytest.raises(threed.ThreeDRefused):
        threed.save_block(cfg, "_example", "style.house", "x", BILL)


# ---------------------------------------------------------------- a body, step by step
def test_a_try_queues_four_pictures_from_the_words_exactly_as_shown(w):
    cfg, a, _ = w
    with pytest.raises(threed.ThreeDRefused):
        threed.new_try(cfg, "_example", {"kind": "body", "who": "", "look": "x"}, BILL)
    with pytest.raises(threed.ThreeDRefused):
        threed.new_try(cfg, "_example", {"kind": "body", "who": "Wren", "look": " "}, BILL)
    with pytest.raises(threed.ThreeDRefused, match="who you are"):
        threed.new_try(cfg, "_example", {"kind": "body", "who": "Wren", "look": "x"}, None)
    r = threed.new_try(cfg, "_example", {"kind": "body", "who": "Wren Hale", "look": "A woman in a canvas jacket.", "seed": 7,
                                         "always": "In an A-pose.", "negative": "text", "height_m": 175}, BILL)
    j = _job(cfg, r["job"])
    assert j["type"] == "render" and j["graph"] == "flux2_klein" and j["count"] == 4 and j["seed"] == 7
    assert j["prompt"] == "A woman in a canvas jacket. In an A-pose." and j["style_prefix"] == "" and j["negative"] == "text"
    assert j["meta"]["threed_try"] == r["try"] and j["game"] == "_example"
    assert j["priority"] == 5                           # ahead of the bulk queues (a person is waiting at the screen)
    t = threed.load_try(cfg, "_example", r["try"])
    assert t["who"] == "wren_hale" and t["by"] == BILL and "centimetres" in t["height_warning"]
    view = threed.try_view(cfg, "_example", r["try"])
    assert view["steps"]["pictures"]["state"] == "pending" and view["stage"] == "words"


def test_the_whole_body_line_through_the_area_and_the_motions_never_done(w):
    cfg, a, tmp = w
    with pytest.raises(threed.ThreeDRefused):
        threed.add_skeleton(cfg, "_example", "nope", None, BILL)
    tid = _body_through(cfg, tmp, never=["Dance_Loop"])
    t = threed.try_view(cfg, "_example", tid)
    assert t["stage"] == "motions" and t["steps"]["picked"]["index"] == 2
    assert t["urls"]["motions.moves"].startswith("/suite/3dfile?p=")
    jobs = Path(cfg["paths"]["jobs"]) / "done"
    fits = [json.loads(p.read_text()) for p in jobs.glob("*.json") if json.loads(p.read_text())["type"] == "fit_motions"]
    assert fits[0]["skip"] == ["Dance_Loop"] and fits[0]["height"] == 1.68
    rigs = [json.loads(p.read_text()) for p in jobs.glob("*.json") if json.loads(p.read_text())["type"] == "rig_body"]
    assert rigs[0]["kind"] == "people"
    assert threed.stage_of(cfg, "_example", "wren_hale") == "motions"
    assert {p["id"]: p for p in threed.people(cfg, "_example")}["wren_hale"]["never"] == ["Dance_Loop"]


def test_try_again_keeps_the_parent_and_a_failed_step_says_why(w):
    cfg, a, tmp = w
    r1 = threed.new_try(cfg, "_example", {"kind": "body", "who": "Wren", "look": "first words"}, BILL)
    r2 = threed.new_try(cfg, "_example", {"kind": "body", "who": "Wren", "look": "second words", "parent": r1["try"]}, BILL)
    assert threed.load_try(cfg, "_example", r2["try"])["parent"] == r1["try"]
    _finish(cfg, r2["job"], {}, failed="ComfyUI is not reachable")
    t = threed.try_view(cfg, "_example", r2["try"])
    assert t["steps"]["pictures"]["state"] == "failed" and "not reachable" in t["steps"]["pictures"]["error"]
    assert [x["id"] for x in threed.tries(cfg, "_example", "wren")] == [r2["try"], r1["try"]]


# ---------------------------------------------------------------- things
def test_a_prop_gets_its_real_size_and_goes_to_review_without_a_skeleton(w):
    cfg, a, _ = w
    r = threed.new_try(cfg, "_example", {"kind": "prop", "who": "handcart", "look": "a wooden handcart",
                                         "real_size_m": {"width": 1.6}}, BILL)
    _finish(cfg, r["job"], {"outputs": ["render.png"]}, {"render.png": standin.png()})
    b = threed.make_body(cfg, "_example", r["try"], 0, BILL)
    j = _job(cfg, b["job"])
    assert j["type"] == "model_3d" and j["kind"] == "prop" and j["real_size_m"] == {"width": 1.6} and j["model"] == "trellis2"
    with pytest.raises(threed.ThreeDRefused, match="make the model first"):
        threed.send_review(cfg, "_example", r["try"], BILL)
    model = Path(cfg["paths"]["out"]) / b["job"] / "handcart__trellis2.glb"
    glb.box(model, (1.6, 0.9, 0.8))
    _finish(cfg, b["job"], {"model": str(model), "engine": "trellis2"})
    assert threed.send_review(cfg, "_example", r["try"], BILL)["ok"]
    rv = threed.review_list(cfg, "_example")
    assert rv["waiting"][0]["dest"] == "project/assets/models/props/handcart.glb" and rv["waiting"][0]["commercial_ok"]
    bld = threed.new_try(cfg, "_example", {"kind": "building", "who": "chapel", "look": "a chapel"}, BILL)
    assert threed.load_try(cfg, "_example", bld["try"])["model"] == "pixal3d"


# ---------------------------------------------------------------- review, approve, deliver
def test_approving_is_the_persons_and_deliver_copies_the_model_its_sheet_and_provenance(w):
    cfg, a, tmp = w
    tid = _body_through(cfg, tmp)
    with pytest.raises(threed.ThreeDRefused, match="motions"):
        t2 = threed.new_try(cfg, "_example", {"kind": "body", "who": "Other", "look": "x"}, BILL)
        threed.send_review(cfg, "_example", t2["try"], BILL)
    threed.send_review(cfg, "_example", tid, BILL, "the jacket reads well")
    with pytest.raises(threed.ThreeDRefused, match="assistant"):
        threed.decide(cfg, "_example", tid, "approve", OPUS)
    assert threed.decide(cfg, "_example", tid, "approve", BILL)["ok"]
    appr = threed.review_list(cfg, "_example")["approved"]
    assert "body/wren_hale" in appr and appr["body/wren_hale"]["by"] == BILL
    plan = threed.deliver(cfg, "_example", BILL, dry=True)
    assert plan["plan"][0]["dest"] == "project/assets/models/characters/wren_hale.glb"
    with pytest.raises(threed.ThreeDRefused, match="assistant"):
        threed.deliver(cfg, "_example", OPUS, dry=False)
    r = threed.deliver(cfg, "_example", BILL, dry=False)
    assert r["moved"][0]["what"] == "body/wren_hale"
    root = a.root
    dest = root / "project" / "assets" / "models" / "characters" / "wren_hale.glb"
    assert dest.exists() and dest.with_suffix(".json").exists()
    prov = json.loads((root / "project" / "assets" / "_provenance" / "models__characters__wren_hale.json").read_text())
    assert prov["approved_by"] == BILL and any("CC0" in l for l in prov["licences"])
    led = json.loads((Path(cfg["paths"]["games"]) / "_example" / "delivered.json").read_text())["entries"]
    assert led[-1]["action"] == "delivered" and led[-1]["wanted"] == "models/body/wren_hale" and led[-1]["kind"] == "3d"
    assert threed.stage_of(cfg, "_example", "wren_hale") == "approved"
    assert threed.deliver(cfg, "_example", BILL, dry=False)["moved"] == []          # once is enough


def test_a_test_dance_can_never_be_approved(w):
    cfg, a, tmp = w
    tid = _body_through(cfg, tmp)
    t = threed.try_view(cfg, "_example", tid)
    moves = Path(t["steps"]["motions"]["moves"])
    glb.box(moves, (0.5, 1.7, 0.3), motions=["Walk_Loop", "Capoeira"], joints=2)
    threed.send_review(cfg, "_example", tid, BILL)
    with pytest.raises(threed.ThreeDRefused, match="test dances"):
        threed.decide(cfg, "_example", tid, "approve", BILL)


# ---------------------------------------------------------------- trees, runs, lists, files
def test_trees_species_runs_and_lists(w):
    cfg, a, tmp = w
    g = threed.grow(cfg, "_example", {"species": "broadleaf", "seed": 3, "count": 4}, BILL)
    j = _job(cfg, g["job"])
    assert j["type"] == "grow_tree" and j["count"] == 4 and j["species"]["name"] == "broadleaf" and j["species"]["numbers"]["height"] == 14.0
    with pytest.raises(threed.ThreeDRefused):
        threed.save_species(cfg, "_example", {"name": "broadleaf", "where": "forge", "numbers": {}}, BILL)
    s = threed.save_species(cfg, "_example", {"name": "Old Oak", "numbers": {"height": 20}}, BILL)
    assert s["ok"] and any(x["name"] == "old_oak" and x["where"] == "game" for x in threed.view(cfg, "_example")["species"])
    lists = Path(cfg["paths"]["games"]) / "_example" / "threed" / "lists"
    lists.mkdir(parents=True)
    (lists / "crowd.json").write_text(json.dumps({"batch": "crowd", "objects": [{"id": "a", "prompt": "x"}, {"id": "b", "prompt": "y"}]}))
    ru = threed.runs(cfg, "_example")
    assert ru["card"]["held"] is False and ru["lists"][0]["bodies"] == 2 and ru["lists"][0]["estimate"]["total_seconds"] > 0
    assert any(x["type"] == "grow_tree" for x in ru["active"])
    with pytest.raises(threed.ThreeDRefused, match="assistant"):
        threed.run_list(cfg, "_example", ru["lists"][0]["file"], OPUS)
    lr = threed.run_list(cfg, "_example", str(lists / "crowd.json"), BILL)
    assert _job(cfg, lr["job"])["type"] == "line_3d" and _job(cfg, lr["job"])["priority"] == 2


def test_only_the_workshops_own_files_are_served(w):
    cfg, a, tmp = w
    ok = Path(cfg["paths"]["out"]) / "x" / "m.glb"
    glb.box(ok)
    assert threed.safe_file(cfg, str(ok)) == ok.resolve()
    for bad in (str(REPO / "forge.json"), str(Path(cfg["paths"]["out"]) / "x" / "m.py"), "../../etc/passwd"):
        with pytest.raises(FileNotFoundError):
            threed.safe_file(cfg, bad)
    (Path(cfg["paths"]["out"]) / "x" / "m.py").write_text("x")
    with pytest.raises(FileNotFoundError):
        threed.safe_file(cfg, str(Path(cfg["paths"]["out"]) / "x" / "m.py"))


def test_the_pages_answer_through_the_server(w):
    cfg, a, tmp = w
    settings.set_identity(BILL)
    s = server.make_server(cfg, 0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    port = s.server_address[1]
    try:
        get = lambda p: urllib.request.urlopen(f"http://127.0.0.1:{port}{p}").read()
        d = json.loads(get("/api/suite/threed?id=_example"))
        assert d["words"]["body"]["always"]["text"] and d["rules"]["apose"] and d["species"] and "sliders" in d
        assert json.loads(get("/api/suite/threed/chips?kind=body&text=" + urllib.request.quote("a long trench coat, arms at his sides")))["chips"]
        assert b"<canvas" in get("/suite/viewer?u=/x.glb")
        assert b"loadThreeD" in get("/suite/threed.js")
        assert b"three.js" in get("/suite/vendor/three/three.module.min.js")[:2000] or len(get("/suite/vendor/three/three.module.min.js")) > 100000
        with pytest.raises(urllib.error.HTTPError):
            get("/suite/vendor/three/../../server.py")
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/suite/act/threed_pictures", method="POST",
                                     data=json.dumps({"game": "_example", "kind": "body", "who": "Wren", "look": "words"}).encode(),
                                     headers={"X-Forge": "1", "Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req).read())
        assert r["ok"] and r["try"]
        tv = json.loads(get(f"/api/suite/threed/try?id=_example&t={r['try']}"))
        assert tv["who"] == "wren" and tv["steps"]["pictures"]["state"] == "pending"
        assert json.loads(get("/api/suite/threed/runs?id=_example"))["active"]
    finally:
        s.shutdown()


import urllib.error  # noqa: E402  (used above)
