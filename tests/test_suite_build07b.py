"""BUILD 07, second part — People, Quests (the remembered branches side by side), Voice sheets beside the lines, Find &
replace with a preview, Play from here. On a throwaway copy of the example game; no real game is touched."""
from __future__ import annotations
import json, subprocess, threading, urllib.request
from datetime import datetime

import pytest

from forge.suite import approval, areas, journal, readthrough, safesave, server, settings, workbench
from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

T = datetime(2026, 11, 11, 13, 30, 0)
BILL, OPUS = "Bill", "Claude Opus"


@pytest.fixture
def w(world, monkeypatch):
    cfg, a, tmp = world
    monkeypatch.setattr(settings, "now", lambda path=None: T)
    settings.set_identity(BILL)
    return cfg, a, tmp


def test_the_story_tabs_are_built_not_planned():
    for t in ("people", "quests", "voices", "find"):
        a, tab = areas.find(f"story/{t}")
        assert not tab.get("planned") and tab["screen"] == t
        assert f"{t}:'v-{t}'" in server.SHELL


# ---------------------------------------------------------------- People
def test_a_person_page_has_their_fields_sheet_and_every_line(w):
    _cfg, a, _ = w
    ls = workbench.people(a)
    assert ls[0]["id"] == "wren" and ls[0]["lines"] == 0          # the example's Wren only sings
    p = workbench.person(a, "wren")
    keys = {f["key"]: f for f in p["fields"]}
    assert keys["voice"]["kind"] == "text" and keys["voice"]["pointer"] == "/wren/voice"
    assert p["stand_in"] is True                                    # sprites/wren.png isn't there: wanted
    assert p["count"] == 0 and p["places"] == []
    assert p["play"] is True and p["reactions"] == []
    with pytest.raises(workbench.WorkbenchRefused):
        workbench.person(a, "nobody")


def test_text_fields_edit_through_the_safe_path_and_numbers_need_i_mean_it(w):
    _cfg, a, _ = w
    r = workbench.edit_field(a, "data/characters.json#/wren/voice", "Dry, quick — and kind when it counts.", BILL)
    assert r["ok"] and json.loads((a.root / "data/characters.json").read_text(encoding="utf-8"))["wren"]["voice"].endswith("counts.")
    assert any(e["kind"] == "edit" and "characters.json" in e.get("obj", "") for e in journal.read(a.root))
    safesave.edit(a, "data/characters.json", [("add", "/wren", "hp", 40)], BILL, reason="test")
    with pytest.raises(workbench.WorkbenchRefused, match="I mean it"):
        workbench.edit_field(a, "data/characters.json#/wren/hp", "99", BILL)
    assert workbench.edit_field(a, "data/characters.json#/wren/hp", "55", BILL, i_mean_it=True)["ok"]
    assert json.loads((a.root / "data/characters.json").read_text(encoding="utf-8"))["wren"]["hp"] == 55
    with pytest.raises(workbench.WorkbenchRefused, match="isn't a number"):
        workbench.edit_field(a, "data/characters.json#/wren/hp", "lots", BILL, i_mean_it=True)


# ---------------------------------------------------------------- Quests
def test_a_quest_page_has_steps_reward_missed_and_the_three_branches_side_by_side(w):
    _cfg, a, _ = w
    assert [q["id"] for q in workbench.quests(a)] == ["lamp_oil"]
    q = workbench.quest(a, "lamp_oil")
    assert [s["text"] for s in q["steps"]][0].startswith("Ask the miller") and q["steps"][1]["pointer"] == "/lamp_oil/steps/1"
    assert q["reward"] == {"coin": 20} and q["missed"] == {"flag": "lighthouse_dark"}
    assert [b["key"] for b in q["remembered"]] == ["done", "not_done", "failed"] and all(b["line"] for b in q["remembered"])
    assert q["remembered_who"] == "The ferryman" and q["title_pointer"] == "/lamp_oil/title"
    r = workbench.edit_field(a, "data/quests.json#/lamp_oil/remembered/failed/line", "The can broke on the third landing.", BILL)
    assert r["ok"] and workbench.quest(a, "lamp_oil")["remembered"][2]["line"] == "The can broke on the third landing."
    m = readthrough.mark(a, "data/quests.json#/lamp_oil", "approved", BILL)
    assert m["ok"] and workbench.quest(a, "lamp_oil")["status"] == "approved"


def test_a_session_changing_an_approved_quest_makes_a_proposal(w):
    _cfg, a, _ = w
    readthrough.mark(a, "data/quests.json#/lamp_oil", "approved", BILL)
    r = workbench.edit_field(a, "data/quests.json#/lamp_oil/title", "Oil for the Lamp", OPUS)
    assert r.get("proposed") and workbench.quest(a, "lamp_oil")["title"] == "Lamp Oil"
    assert approval.list_open(a.root)


# ---------------------------------------------------------------- Voice sheets
def test_voice_sheets_are_kept_signed_and_a_session_never_overwrites_a_person(w):
    _cfg, a, _ = w
    r = workbench.save_voice(a, "person", "wren", "talk", "Short sentences. Prices, not feelings.", BILL)
    assert r["ok"] and (a.root / "voices/person/wren.json").is_file()
    workbench.save_voice(a, "person", "wren", "never", "Sweetheart\nawesome\nAwesome", BILL)
    assert workbench.voice(a, "person", "wren")["never"]["value"] == ["awesome", "Sweetheart"]
    with pytest.raises(workbench.WorkbenchRefused, match="never change theirs"):
        workbench.save_voice(a, "person", "wren", "talk", "Chatty.", OPUS)
    assert workbench.save_voice(a, "person", "wren", "exact", ["Pay the song.", "The river takes the rest."], OPUS)["ok"]   # empty → a session may fill
    with pytest.raises(workbench.WorkbenchRefused, match="not more"):
        workbench.save_voice(a, "person", "wren", "exact", "a\nb\nc\nd", BILL)
    assert any(e.get("obj") == "voice:person:wren" for e in journal.read(a.root))
    v = workbench.voices(a)
    assert {"id": "wren", "name": "Wren", "filled": 3} in v["people"] and len(v["places"]) == 3


def test_the_read_through_shows_the_sheets_and_marks_a_never_word(w):
    _cfg, a, _ = w
    pg = readthrough.page(a, "ember_crossing", "all")
    assert pg["play"] is True
    first = pg["lines"][0]
    word = first["text"].split()[0].strip(",.")
    workbench.save_voice(a, "place", "ember_crossing", "never", word, BILL)
    vf = workbench.voices_for(a, "ember_crossing", pg["lines"])
    assert vf["place"]["never"]["value"] == [word] and vf["never_hits"][first["ref"]] == [word]


# ---------------------------------------------------------------- Find & replace
def test_find_previews_every_hit_and_replace_changes_only_the_ticked_ones(w):
    _cfg, a, _ = w
    f = workbench.find(a, "lamp", repl="lantern")
    assert len([h for h in f["hits"] if not h["locked"]]) >= 2 and all("after" in h for h in f["hits"])
    before = {h["ref"]: h["text"] for h in f["hits"]}
    ok = [h["ref"] for h in f["hits"] if not h["locked"]]
    keep = ok[-1]
    r = workbench.replace(a, "lamp", "lantern", ok[:-1], BILL)
    assert len(r["changed"]) == len(ok) - 1 and not r["skipped"]
    after = workbench.find(a, "lamp")
    assert [h["ref"] for h in after["hits"] if not h["locked"]] == [keep]          # the unticked one is untouched
    assert workbench.find(a, "lantern")["hits"]
    assert sum(1 for e in journal.read(a.root) if "find & replace" in str(e.get("note") or e.get("link") or "") or e["kind"] == "edit") >= len(ok) - 1
    assert before[keep] == next(h["text"] for h in after["hits"] if h["ref"] == keep)


def test_song_words_are_shown_locked_and_never_replaced(w):
    _cfg, a, _ = w
    f = workbench.find(a, "river")
    locked = [h for h in f["hits"] if h["locked"]]
    assert locked, "the toll song's line says 'the river takes the rest'"
    r = workbench.replace(a, "river", "stream", [h["ref"] for h in locked], BILL)
    assert not r["changed"] and len(r["skipped"]) == len(locked)
    assert workbench.find(a, "river")["hits"]


def test_whole_word_and_case(w):
    _cfg, a, _ = w
    n_any = len(workbench.find(a, "the")["hits"])
    n_word = len(workbench.find(a, "the", word=True)["hits"])
    assert n_any >= n_word > 0
    assert workbench.find(a, "THE", case=True)["hits"] == []
    with pytest.raises(workbench.WorkbenchRefused):
        workbench.find(a, "")


# ---------------------------------------------------------------- Play from here
def test_play_from_here_runs_the_adapters_command(w, monkeypatch):
    _cfg, a, _ = w
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    r = workbench.play(a, "harbor_hollow", "after")
    assert r["ok"] and "harbor_hollow" in calls[-1][-1]
    r = workbench.play(a, None, None, quest_id="lamp_oil")
    assert r["ok"] and "harbor_hollow" in calls[-1][-1] and "after" in calls[-1][-1]


# ---------------------------------------------------------------- the app
def test_the_app_serves_the_four_screens(w):
    cfg, a, _ = w
    s = server.make_server(cfg, 0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    port = s.server_address[1]
    g = lambda p: json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{p}").read())
    try:
        assert g("/api/suite/people?id=_example")["people"][0]["id"] == "wren"
        assert g("/api/suite/person?id=_example&pid=wren")["name"] == "Wren"
        assert g("/api/suite/quest?id=_example&qid=lamp_oil")["remembered"][0]["key"] == "done"
        assert len(g("/api/suite/voices?id=_example")["places"]) == 3
        assert "never_hits" in g("/api/suite/voicesfor?id=_example&place=ember_crossing&era=all")
        assert g("/api/suite/find?id=_example&q=lamp&repl=x")["hits"]
        r = server.act(cfg, "wb_voice", {"game": "_example", "kind": "place", "vid": "millstone", "field": "talk", "value": "Slow, flour-dusted."})
        assert r["ok"]
        r = server.act(cfg, "wb_edit", {"game": "_example", "ref": "data/quests.json#/lamp_oil/title", "value": "Lamp Oil, Again"})
        assert r["ok"] and r["message"] == "Saved."
        r = server.act(cfg, "wb_replace", {"game": "_example", "q": "Again", "repl": "Twice", "refs": ["data/quests.json#/lamp_oil/title"]})
        assert r["ok"] and r["changed"] == ["data/quests.json#/lamp_oil/title"]
    finally:
        s.shutdown()
