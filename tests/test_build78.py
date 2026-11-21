"""BUILD 78 — approvals made easy, and what the night of 2026-11-17 taught.

Part 0: the queue failed every released body (00:24 onward: "Object of type ndarray is not JSON serializable" — BUILD
73's head_pairs left in the colour check's result), and an adopted body went round its checks as if nobody had released
it. Part 1: "Approve everything here", with an undo a thing. Part 2: the setting "Fable may approve for me", an
assistant's approval written as "Claude Fable, for William", never as him. No graphics card, nothing generated.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from forge.threed import checks, world

from test_threed_build40 import _coloured_body   # noqa: E402 — the BUILD 40 test body (a slab with a skin band)

REPO = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures" / "threed"
FAKE_BLENDER = [sys.executable, str(FIX / "fake_blender.py")]


@pytest.fixture(autouse=True)
def _pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))


def _cfg(tmp_path, entries, gid="g1"):
    d = tmp_path / "games" / gid / "wanted_3d"
    d.mkdir(parents=True, exist_ok=True)
    (d / "list.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return {"_root": str(tmp_path), "threed": {"out_root": str(tmp_path / "out3d"), "blender_python": FAKE_BLENDER},
            "paths": {"games": str(tmp_path / "games"), "out": str(tmp_path / "out"), "jobs": str(tmp_path / "jobs")},
            "allow_external_paths": True}


def _rel(tmp_path, p):
    return os.path.relpath(p, tmp_path).replace("\\", "/")


# ------------------------------------------------------------------------------------------------ part 0: the crash
def test_a_body_checked_by_the_queue_can_be_written_down(tmp_path):
    """The night's failure, as it happened: a body whose face is found carries head_pairs (pixels) in its colour result."""
    glbp, pic = _coloured_body(tmp_path, "b", 2.2)
    res = checks.run(glbp, pic, "body", "named")
    col = next(r for r in res["results"] if r["check"] == "colour")
    assert "head_pairs" not in col and "face_ratio" in col          # the numbers stay, the pixels do not
    json.dumps(res)                                                  # raised TypeError before BUILD 78
    world._write(tmp_path / "checks.json", res)
    assert json.loads((tmp_path / "checks.json").read_text())["results"]


def test_jsonable_keeps_numbers_and_drops_pixels():
    big = np.zeros((500, 3))
    v = checks.jsonable({"a": np.float32(0.5), "b": np.int64(3), "c": np.bool_(True), "d": np.array([1.0, 2.0]),
                         "e": (big, big), "f": big, "g": [np.float64(1.25), (1, 2)]})
    assert v == {"a": 0.5, "b": 3, "c": True, "d": [1.0, 2.0], "e": [], "g": [1.25, [1, 2]]}
    json.dumps(v)


def test_the_queue_writes_numpy_numbers_and_never_pixels(tmp_path):
    world._write(tmp_path / "x.json", {"n": np.float32(2.5), "small": np.arange(3), "big": np.zeros(1000)})
    d = json.loads((tmp_path / "x.json").read_text())
    assert d == {"n": 2.5, "small": [0, 1, 2], "big": None}
    assert not list(tmp_path.glob("*.part"))


def _adopted_body(tmp_path, released: bool):
    out_src = tmp_path / "runs" / "old"
    out_src.mkdir(parents=True)
    glbp, pic = _coloured_body(out_src, "walker", 2.2)
    moves = out_src / "walker_moves.glb"
    shutil.copyfile(glbp, moves)
    moves.with_suffix(".json").write_text(json.dumps({"motions": {"Idle_Loop": {}}}), encoding="utf-8")
    cfg = _cfg(tmp_path, [{"id": "walker", "kind": "body", "tier": "crowd", "words": "A man of fifty.",
                           "real_size_m": {"height": 1.8}, "adopt": _rel(tmp_path, glbp),
                           "adopt_picture": _rel(tmp_path, pic), "adopt_moves": _rel(tmp_path, moves)}])
    if released:
        world.write_state(cfg, "g1", "walker", {"state": "wanted", "tries": 2,
                                                "colour_released": {"by": "Claude Fable, for William", "at": "2026-11-17T23:50:00"},
                                                "reuse_body": "out/3d/world/g1/walker/walker__colour.glb"})
    e = {x["id"]: x for x in world.load(cfg, "g1")[0]}["walker"]
    return cfg, e


def test_an_adopted_body_that_was_released_is_made_with_its_colours_matched(tmp_path):
    cfg, e = _adopted_body(tmp_path, released=True)
    out = world.item_dir(cfg, "g1", "walker")
    out.mkdir(parents=True, exist_ok=True)
    res = world._adopt(cfg, "g1", e, out)
    assert res["state"] == "made", res.get("why")
    assert res["model"].endswith("__colour.glb") and res.get("colour_lut")          # the moving copy took the same curve
    json.dumps(res)
    assert json.loads((out / "checks.json").read_text())["ok"] is True


def test_a_released_adopted_body_whose_colours_still_miss_is_not_held_for_them(tmp_path, monkeypatch):
    cfg, e = _adopted_body(tmp_path, released=True)
    out = world.item_dir(cfg, "g1", "walker")
    out.mkdir(parents=True, exist_ok=True)
    real = checks.run

    def colour_misses(*a, **k):                     # every look at it says the colours miss, as the night's bodies did
        r = real(*a, **k)
        for x in r["results"]:
            if x["check"] == "colour":
                x.update(ok=False, auto_fix=True, line="Colours hold: the face 55% as bright as the picture's — held back.")
        r["ok"] = all(x["ok"] for x in r["results"])
        r["lines"] = [x["line"] for x in r["results"]]
        return r

    monkeypatch.setattr(checks, "run", colour_misses)
    res = world._adopt(cfg, "g1", e, out)
    assert res["state"] == "made", res.get("why")
    assert any("released by Claude Fable, for William" in ln for ln in res["checks"])
    assert not res.get("face_redo")


def test_an_adopted_body_nobody_released_is_still_checked_as_before(tmp_path):
    cfg, e = _adopted_body(tmp_path, released=False)
    out = world.item_dir(cfg, "g1", "walker")
    out.mkdir(parents=True, exist_ok=True)
    res = world._adopt(cfg, "g1", e, out)
    assert not any("released by" in ln for ln in res.get("checks") or [])
    json.dumps(res)


def test_try_again_keeps_what_a_release_kept_and_leaves_the_rest(tmp_path):
    cfg = _cfg(tmp_path, [{"id": "a", "kind": "body", "words": "x"}, {"id": "b", "kind": "body", "words": "y"}])
    world.write_state(cfg, "g1", "a", {"state": "failed", "tries": 3, "error": "TypeError: Object of type ndarray …",
                                       "reuse_body": "out/x__colour.glb", "colour_released": {"by": "Claude Fable, for William"}})
    world.write_state(cfg, "g1", "b", {"state": "held", "tries": 1})
    r = world.try_again(cfg, "g1", ["a", "b"], "Claude Opus")
    assert r["again"] == ["a"] and r["left"][0]["id"] == "b"
    st = world.read_state(cfg, "g1", "a")
    assert st["state"] == "wanted" and st["reuse_body"] == "out/x__colour.glb" and st["colour_released"]["by"].startswith("Claude Fable")
    assert st["history"][-1]["state"] == "try again" and world.read_state(cfg, "g1", "b")["state"] == "held"
    items, _ = world.merged(cfg, "g1")
    assert world.next_item(items)["id"] == "a"


# ------------------------------------------------------------------------------------------------ part 2: the setting
@pytest.fixture
def suite_json(tmp_path, monkeypatch):
    from forge import config as cfgmod
    from forge.suite import settings
    p = tmp_path / "local" / "suite.json"
    monkeypatch.setattr(settings, "PATH", p)
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)          # the try's files are named from the forge's own folder
    monkeypatch.delenv("FORGE_IDENTITY", raising=False)
    return p


def _game_default(tmp_path, on=True, gid="g1"):
    d = tmp_path / "games" / gid
    d.mkdir(parents=True, exist_ok=True)
    (d / "approvals.json").write_text(json.dumps({"assistant_may_approve": on, "assistants": ["Claude Fable"], "for": "William"}),
                                      encoding="utf-8")


def test_fable_may_approve_for_william_and_is_written_so(tmp_path, suite_json):
    from forge.suite import approve_all as ap
    cfg = _cfg(tmp_path, [])
    _game_default(tmp_path)
    s = ap.setting(cfg, "g1")
    assert s["on"] and s["where"] == "the game's default" and "never as William" in s["said"]
    assert ap.signer(cfg, "g1", "Claude Fable", "approving") == "Claude Fable, for William"
    assert ap.signer(cfg, "g1", "Claude Fable, for William") == "Claude Fable, for William"     # not "…, for William, for William"
    assert ap.signer(cfg, "g1", "Bill") == "Bill"                                               # a person signs as himself
    with pytest.raises(ap.ApproveRefused, match="may approve for me"):
        ap.signer(cfg, "g1", "Claude Opus")                                                     # only the assistants it names
    with pytest.raises(ap.ApproveRefused):
        ap.signer(cfg, "g1", "")


def test_only_the_person_turns_it_off_and_then_an_assistant_cannot_approve(tmp_path, suite_json):
    from forge.suite import approve_all as ap
    cfg = _cfg(tmp_path, [])
    _game_default(tmp_path)
    with pytest.raises(ap.ApproveRefused, match="person's to decide"):
        ap.set_setting(cfg, "g1", False, "Claude Fable")
    s = ap.set_setting(cfg, "g1", False, "Bill")
    assert s["on"] is False and s["where"] == "this computer" and s["set_by"] == "Bill"
    with pytest.raises(ap.ApproveRefused):
        ap.signer(cfg, "g1", "Claude Fable")
    assert json.loads(suite_json.read_text())["approvals"]["g1"]["on"] is False


def test_a_game_without_a_default_keeps_approving_the_persons(tmp_path, suite_json):
    from forge.suite import approve_all as ap
    cfg = _cfg(tmp_path, [])
    assert ap.setting(cfg, "g1")["on"] is False
    with pytest.raises(ap.ApproveRefused):
        ap.signer(cfg, "g1", "Claude Fable")


def test_the_turing_accords_default_is_on_for_fable_as_william_ruled():
    d = json.loads((REPO / "games" / "turing_accords" / "approvals.json").read_text(encoding="utf-8"))
    assert d["assistant_may_approve"] is True and d["assistants"] == ["Claude Fable"] and d["for"] == "William"


# ------------------------------------------------------------------------------------------------ part 1: Approve everything here
def _held(tmp_path, cfg, eid, kind, why="Colours hold: 39% as bright as its picture"):
    out = world.item_dir(cfg, "g1", eid)
    out.mkdir(parents=True, exist_ok=True)
    glbp, pic = _coloured_body(out, eid, 2.2)
    world.write_state(cfg, "g1", eid, {"state": "held", "kind": kind, "tier": "small_prop" if kind != "body" else "crowd",
                                       "model_raw": _rel(tmp_path, glbp), "picture": _rel(tmp_path, pic), "why": [why],
                                       "engine": "trellis2",
                                       "check_results": [{"check": "loose", "ok": True},
                                                         {"check": "colour", "ok": False, "mean_ratio": 0.39}]})


def _world(tmp_path):
    cfg = _cfg(tmp_path, [{"id": "crank_radio", "kind": "prop", "words": "A crank radio.", "real_size_m": {"width": 0.3}},
                          {"id": "walker", "kind": "body", "words": "A man of fifty.", "real_size_m": {"height": 1.8}},
                          {"id": "colonel", "kind": "body", "words": "A colonel.", "real_size_m": {"height": 1.8}, "release": "as made"},
                          {"id": "cello", "kind": "prop", "words": "A cello.", "real_size_m": {"height": 1.2}},
                          {"id": "lamp", "kind": "prop", "words": "A lamp.", "real_size_m": {"height": 1.0}},
                          {"id": "chandelier", "kind": "prop", "words": "A chandelier.", "real_size_m": {"height": 1.0}},
                          {"id": "painter", "kind": "body", "words": "A painter.", "real_size_m": {"height": 1.7}}])
    _game_default(tmp_path)
    for eid, kind in (("crank_radio", "prop"), ("walker", "body"), ("colonel", "body")):
        _held(tmp_path, cfg, eid, kind)
    world.write_state(cfg, "g1", "cello", {"state": "held", "kind": "prop", "check_results": [
        {"check": "level", "ok": False, "straighten": [0, 0, 0, 1], "line": "Sits level: which way is up isn't clear"}]})
    world.write_state(cfg, "g1", "lamp", {"state": "failed", "tries": 2, "error": "boom"})
    world.write_state(cfg, "g1", "chandelier", {"state": "held", "kind": "prop", "check_results": [
        {"check": "loose", "ok": False, "line": "Loose pieces: 1 piece not joined to the rest"}]})
    world.write_state(cfg, "g1", "painter", {"state": "held", "kind": "body", "held_by": "picture gate",
                                             "gate": {"tries": [{"try": 1, "picture": "x.png"}]}})
    return cfg


def test_the_world_card_says_in_plain_words_what_will_happen(tmp_path, suite_json):
    from forge.suite import approve_all as ap
    cfg = _world(tmp_path)
    p = ap.world_plan(cfg, "g1")
    assert p["groups"]["match_bodies"] == ["walker"] and p["groups"]["as_made_bodies"] == ["colonel"]
    assert p["groups"]["match_things"] == ["crank_radio"] and p["groups"]["unclear"] == ["cello"] and p["groups"]["failed"] == ["lamp"]
    assert p["count"] == 3
    text = " ".join(p["lines"])
    assert "1 body goes back for its skeleton and motions with one gain for the whole colour picture" in text   # BUILD 84
    assert "nothing is remade" in text
    assert "colours as made (the match was worse)" in text and "Review & approve" in text
    assert any("which way is up" in x for x in p["left"]) and any("failed" in x for x in p["left"])
    assert p["groups"]["repair"] == ["chandelier"] and p["groups"]["gate"] == ["painter"]      # a real fault is not an approval
    assert any("real fault" in x for x in p["left"]) and any("picture gate" in x for x in p["left"])


def test_approve_everything_on_the_world_list_as_fable_for_william_and_undo_one(tmp_path, suite_json):
    from forge.suite import approve_all as ap
    cfg = _world(tmp_path)
    jobs_before = list((tmp_path / "jobs").rglob("*.json")) if (tmp_path / "jobs").exists() else []
    r = ap.world_approve_all(cfg, "g1", "Claude Fable", env=None, blender_python=FAKE_BLENDER)
    assert r["by"] == "Claude Fable, for William" and {d["id"] for d in r["done"]} == {"walker", "colonel", "crank_radio"}, r
    w, c, radio = (world.read_state(cfg, "g1", i) for i in ("walker", "colonel", "crank_radio"))
    assert w["state"] == "wanted" and w["reuse_body"].endswith("__one_gain.glb") and w["colour_released"]["by"] == "Claude Fable, for William"
    assert c["state"] == "wanted" and c["as_made"] is True and c["reuse_body"] == c["model_raw"]       # not matched
    assert radio["state"] == "made" and radio["try"]
    assert world.read_state(cfg, "g1", "cello")["state"] == "held" and world.read_state(cfg, "g1", "lamp")["state"] == "failed"
    assert world.read_state(cfg, "g1", "chandelier")["state"] == "held" and world.read_state(cfg, "g1", "painter")["state"] == "held"
    assert (list((tmp_path / "jobs").rglob("*.json")) if (tmp_path / "jobs").exists() else []) == jobs_before   # no job started
    hist = ap.history(cfg, "g1")
    assert len(hist) == 3 and all(h["by"] == "Claude Fable, for William" for h in hist)
    # undo the prop: its state comes back as it was and its try leaves Review & approve (kept, marked withdrawn)
    uid = next(h["uid"] for h in hist if h["id"] == "crank_radio")
    u = ap.undo(cfg, "g1", uid, "Bill")
    assert u["ok"], u
    assert world.read_state(cfg, "g1", "crank_radio")["state"] == "held"
    tfile = next((tmp_path / "games" / "g1" / "threed" / "tries" / "crank_radio").glob("*.json"))
    assert json.loads(tfile.read_text())["review"]["state"] == "withdrawn"
    assert not ap.undo(cfg, "g1", uid, "Bill")["ok"]                                  # once
    assert next(h for h in ap.history(cfg, "g1") if h["id"] == "crank_radio")["undone"]
    # a body the queue has taken up since cannot be undone from here — it says what to do instead
    st = world.read_state(cfg, "g1", "walker")
    st["state"] = "made"
    world.write_state(cfg, "g1", "walker", st)
    uid_w = next(h["uid"] for h in hist if h["id"] == "walker")
    u2 = ap.undo(cfg, "g1", uid_w, "Bill")
    assert not u2["ok"] and "Review & approve" in u2["message"]


def test_an_assistant_not_allowed_changes_nothing(tmp_path, suite_json):
    from forge.suite import approve_all as ap
    cfg = _world(tmp_path)
    ap.set_setting(cfg, "g1", False, "Bill")
    with pytest.raises(ap.ApproveRefused):
        ap.world_approve_all(cfg, "g1", "Claude Fable", blender_python=FAKE_BLENDER)
    assert world.read_state(cfg, "g1", "walker")["state"] == "held" and not ap.history(cfg, "g1")


def test_review_and_approve_everything_holds_each_model_for_deliver_signed_so(tmp_path, suite_json):
    from forge.suite import approve_all as ap, threed
    cfg = _world(tmp_path)
    ap.world_approve_all(cfg, "g1", "Bill", ids=["crank_radio"], blender_python=FAKE_BLENDER)
    tcfg = cfg
    rp = ap.review_plan(tcfg, "g1")
    assert rp["count"] == 1 and rp["models"] and "held for Deliver" in rp["lines"][0], rp
    r = ap.review_approve_all(tcfg, "g1", "Claude Fable")
    assert r["done"] and r["by"] == "Claude Fable, for William", r
    appr = json.loads((tmp_path / "games" / "g1" / "threed" / "approved.json").read_text())
    assert next(iter(appr.values()))["by"] == "Claude Fable, for William"
    uid = ap.history(cfg, "g1")[0]["uid"]
    assert ap.undo(tcfg, "g1", uid, "Bill")["ok"]
    assert json.loads((tmp_path / "games" / "g1" / "threed" / "approved.json").read_text()) == {}
    assert threed.review_list(tcfg, "g1")["waiting"]


def test_one_model_approved_by_fable_through_the_page_is_signed_for_william(tmp_path, suite_json):
    from forge.suite import approve_all as ap, threed
    cfg = _world(tmp_path)
    ap.world_approve_all(cfg, "g1", "Bill", ids=["crank_radio"], blender_python=FAKE_BLENDER)
    tcfg = cfg
    tid = threed.review_list(tcfg, "g1")["waiting"][0]["id"]
    ap.set_setting(tcfg, "g1", False, "Bill")
    with pytest.raises(threed.ThreeDRefused):
        threed.decide(tcfg, "g1", tid, "approve", "Claude Fable")
    ap.set_setting(tcfg, "g1", True, "Bill")
    threed.decide(tcfg, "g1", tid, "approve", "Claude Fable")
    assert json.loads(threed._try_path(tcfg, "g1", tid).read_text())["review"]["decided_by"] == "Claude Fable, for William"


def test_release_as_made_keeps_the_colours_and_the_queue_does_not_match_them(tmp_path, monkeypatch):
    cfg = _world(tmp_path)
    r = world.release_as_made(cfg, "g1", ["colonel", "crank_radio"], "Claude Fable, for William", blender_python=FAKE_BLENDER)
    assert {d["id"] for d in r["released"]} == {"colonel", "crank_radio"}, r
    radio = world.read_state(cfg, "g1", "crank_radio")
    assert radio["state"] == "made" and radio["as_made"] and "released as made" in radio["history"][-1]["state"]
    st = world.read_state(cfg, "g1", "colonel")
    assert st["state"] == "wanted" and st["as_made"] and st["reuse_body"] == st["model_raw"]
    assert not world.release_as_made(cfg, "g1", ["cello"], "Bill")["released"]               # not held for colour alone


def test_place_again_withdraws_the_untidied_try_and_sends_a_tidied_one(tmp_path):
    cfg = _world(tmp_path)
    world.match_and_release(cfg, "g1", ["crank_radio"], "Claude Fable, for William", blender_python=["no-such-blender"])
    st = world.read_state(cfg, "g1", "crank_radio")
    assert st["state"] == "made" and not st.get("tidy")            # as on the night: sized without Blender
    old = st["try"]
    from forge.threed.env import RigEnv
    r = world.place_again(cfg, "g1", ["crank_radio", "walker"], "Claude Opus", env=RigEnv(tmp_path), blender_python=FAKE_BLENDER)
    assert r["placed"] == ["crank_radio"] and r["left"][0]["id"] == "walker", r
    st2 = world.read_state(cfg, "g1", "crank_radio")
    assert st2["tidy"] and st2["try"] != old
    tdir = tmp_path / "games" / "g1" / "threed" / "tries" / "crank_radio"
    states = {p.stem: json.loads(p.read_text())["review"]["state"] for p in tdir.glob("*.json")}
    assert states[old] == "withdrawn" and states[st2["try"]] == "waiting"


def test_a_blender_that_started_the_forge_passes_nothing_of_its_own_on(monkeypatch, tmp_path):
    from forge.threed.env import RigEnv
    monkeypatch.setenv("OCIO", "C:/Program Files/Blender Foundation/Blender 5.3/5.3/datafiles/colormanagement/config.ocio")
    monkeypatch.setenv("BLENDER_SYSTEM_SCRIPTS", "C:/elsewhere")
    e = RigEnv(tmp_path).rig_env()
    assert "OCIO" not in e and "BLENDER_SYSTEM_SCRIPTS" not in e and "PATH" in e


def test_a_lean_whose_colours_are_the_rest_of_it_is_straightened_then_matched(tmp_path, suite_json):
    from forge.suite import approve_all as ap
    cfg = _cfg(tmp_path, [{"id": "house", "kind": "building", "words": "A house.", "real_size_m": {"height": 1.8}}])
    _game_default(tmp_path)
    _held(tmp_path, cfg, "house", "building")
    st = world.read_state(cfg, "g1", "house")
    st["check_results"] = [{"check": "level", "ok": False, "straighten": [0.0349, 0.0, 0.0, 0.9994], "tilt_deg": 4.0,
                            "line": "Sits level: 4.0° off level, and its own walls lean the same way — held back."},
                           {"check": "colour", "ok": False, "mean_ratio": 0.39, "line": "Colours hold: 39% — held back."}]
    st["colour_offer"] = "out3d/stale_offer_from_the_leaning_model.glb"
    world.write_state(cfg, "g1", "house", st)
    assert ap.world_plan(cfg, "g1")["groups"]["straighten"] == ["house"]
    r = ap.world_approve_all(cfg, "g1", "Claude Fable", blender_python=FAKE_BLENDER)
    assert [d["id"] for d in r["done"]] == ["house"], r
    after = world.read_state(cfg, "g1", "house")
    assert after["state"] == "made" and after["model_raw"].endswith("__colour.glb") and "__level" not in after["model_raw"]
    assert any(h["state"] == "straightened" for h in after["history"]) and after["colour_released"]["by"] == "Claude Fable, for William"


# ------------------------------------------------------------------------------------------------ put_in_waiting_changes.bat
def _package(tmp_path, files: dict, base: dict):
    """files: {path: new text}; base: {path: text the session started from, or None for a new file}."""
    from forge import sync_when_idle as sw
    pkg = tmp_path / "_xfer" / "waiting" / "tonight"
    man = {"title": "tonight", "files": []}
    for rel, text in files.items():
        f = pkg / "files" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        b = base.get(rel)
        man["files"].append({"path": rel, "new_md5": sw.md5(f),
                             "base_md5": None if b is None else __import__("hashlib").md5(b.encode()).hexdigest()})
    (pkg / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    return pkg


def test_waiting_changes_go_in_only_onto_what_the_session_read(tmp_path):
    from forge import sync_when_idle as sw
    root = tmp_path / "forge_root"
    (root / "a").mkdir(parents=True)
    (root / "a" / "one.py").write_text("old one", encoding="utf-8")
    (root / "a" / "two.py").write_text("old two", encoding="utf-8")
    pkg = _package(tmp_path, {"a/one.py": "new one", "a/two.py": "new two", "a/three.py": "brand new"},
                   {"a/one.py": "old one", "a/two.py": "old two", "a/three.py": None})
    assert sw.packages(tmp_path / "_xfer" / "waiting") == [pkg]
    (root / "a" / "two.py").write_text("someone else's two", encoding="utf-8")        # changed since the session read it
    r = sw.apply(pkg, root)
    assert not r["ok"] and r["conflicts"][0]["path"] == "a/two.py" and r["applied"] == []
    assert (root / "a" / "one.py").read_text() == "old one" and not (root / "a" / "three.py").exists()   # nothing half-done
    (root / "a" / "two.py").write_text("old two", encoding="utf-8")
    r = sw.apply(pkg, root)
    assert r["ok"] and sorted(r["applied"]) == ["a/one.py", "a/three.py", "a/two.py"]
    assert (root / "a" / "one.py").read_text() == "new one" and (pkg / "before" / "a" / "one.py").read_text() == "old one"
    assert sw.check(pkg, root)["already"] and sw.check(pkg, root)["ok"]               # a second run changes nothing
    sw.put_back(pkg, r["applied"], root)
    assert (root / "a" / "one.py").read_text() == "old one" and not (root / "a" / "three.py").exists()
    assert (pkg / "before" / "_new" / "a" / "three.py").read_text() == "brand new"   # moved aside, never deleted


def test_with_the_queue_running_nothing_changes_unless_the_person_says_s(tmp_path, monkeypatch):
    from forge import sync_when_idle as sw
    pkg = _package(tmp_path, {"x.py": "new"}, {"x.py": None})
    monkeypatch.setattr(sw, "WAITING", tmp_path / "_xfer" / "waiting")
    monkeypatch.setattr(sw, "packages", lambda base=None: [pkg])
    monkeypatch.setattr(sw, "_queue", lambda cfg, gid: {"running": True})
    said = []
    code = sw.run([], ask=lambda q: "", say=said.append)
    assert code == 1 and any("Nothing was changed" in s for s in said) and not (pkg / "APPLIED.txt").exists()


def test_the_put_in_bat_is_one_file_with_a_mac_answer():
    from forge.suite import runwords
    bat = (REPO / "put_in_waiting_changes.bat").read_text(encoding="utf-8")
    assert "python -m forge.sync_when_idle" in bat and "put_in_waiting_changes" in runwords.TABLE
