"""BUILD 01 — the suite's foundations: format-preserving JSON, the adapter contract and the example game, the
safe-save path, approved-means-his, the journal, the identity, the worker's state, the app, and the rule that
forge/ names no game. Everything runs on a throwaway copy of games/_example; no real game is needed."""
from __future__ import annotations
import json, os, shutil, threading, urllib.error, urllib.request
from pathlib import Path

import pytest

from forge import config as cfgmod
from forge.suite import approval, games, journal, safesave, settings, worker
from forge.suite.jsondoc import JsonDoc, JsonDocError, TextDoc

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- a throwaway world
@pytest.fixture
def world(tmp_path, monkeypatch):
    """cfg whose games/ holds only a copy of _example, with jobs/out/logs in tmp; settings in tmp; nobody signed in."""
    gdir = tmp_path / "games"
    shutil.copytree(REPO / "games" / "_example", gdir / "_example",
                    ignore=shutil.ignore_patterns("journal", "proposals", "_workbench_*", "WORKBENCH_LOG.md", "__pycache__"))
    cfg = cfgmod.load()
    cfg["allow_external_paths"] = True
    cfg["paths"] = dict(cfg["paths"], games=str(gdir), jobs=str(tmp_path / "jobs"), out=str(tmp_path / "out"),
                        logs=str(tmp_path / "logs"))
    for s in ("pending", "running", "done", "failed", "paused"):
        (tmp_path / "jobs" / s).mkdir(parents=True)
    (tmp_path / "out").mkdir()
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(settings, "PATH", tmp_path / "local" / "suite.json")
    monkeypatch.delenv("FORGE_IDENTITY", raising=False)
    monkeypatch.delenv("FORGE_GAME_ROOTS", raising=False)
    games._loaded.clear()
    a = games.adapter(cfg, "_example")
    return cfg, a, tmp_path


# ---------------------------------------------------------------- jsondoc
STYLES = [
    '{\n "a": 1,\n "b": [1, 2, {"c": "d"}],\n "e": {"f": "g\\u2014h"}\n}\n',
    '{\n  "a": "caf\u00e9 \u2014 \u2726",\n  "list": [\n    "x",\n    "y"\n  ]\n}',
    '{\r\n\t"tabs": true,\r\n\t"n": -1.5e3,\r\n\t"nested": {\r\n\t\t"k": null\r\n\t}\r\n}\r\n',
    '{"compact":true,"x":[1,2,3],"s":"a\\"b\\\\c\\/d"}',
    '[\n {"id": "one", "text": "first"},\n {"id": "two", "text": "second"}\n]\n',
    '{}', '[]', '"just a string"',
]


@pytest.mark.parametrize("text", STYLES)
def test_jsondoc_round_trips_every_style_byte_for_byte(text):
    for raw in (text.encode("utf-8"), b"\xef\xbb\xbf" + text.encode("utf-8")):
        d = JsonDoc.from_bytes(raw)
        assert d.to_bytes() == raw
        assert d.value == json.loads(raw.decode("utf-8-sig"))


def test_jsondoc_set_changes_only_that_value():
    raw = STYLES[0].encode()
    d = JsonDoc.from_bytes(raw)
    assert d.set("/b/2/c", "a new value — with a dash") is True
    out = d.to_bytes().decode()
    assert out == STYLES[0].replace('"d"', '"a new value \\u2014 with a dash"')      # this file escapes non-ASCII
    assert d.get("/b/2/c") == "a new value — with a dash"
    assert d.set("/b/2/c", "a new value — with a dash") is False                     # equal value → no change


def test_jsondoc_add_uses_the_siblings_indentation_and_line_endings():
    d = JsonDoc(STYLES[2])
    d.add("/nested", "status", "approved")
    assert d.text == STYLES[2].replace('"k": null\r\n', '"k": null,\r\n\t\t"status": "approved"\r\n')
    d2 = JsonDoc(STYLES[4])
    d2.add("/1", "status", "draft")                                                  # an inline object stays inline
    assert '{"id": "two", "text": "second", "status": "draft"}' in d2.text
    d3 = JsonDoc('{\n  "a": {},\n  "b": []\n}\n')
    d3.add("/a", "k", {"x": [1, 2]})
    d3.append("/b", "item")
    assert json.loads(d3.text) == {"a": {"k": {"x": [1, 2]}}, "b": ["item"]}
    assert d3.text.startswith('{\n  "a": {\n    "k": {\n      "x": [\n')


def test_jsondoc_refuses_broken_files_and_bad_pointers_in_plain_words():
    with pytest.raises(JsonDocError, match="line 2"):
        JsonDoc('{\n "a": 1,,\n}')
    d = JsonDoc('{"a/b": {"~x": 1}, "l": [0]}')
    assert d.get("/a~1b/~0x") == 1
    with pytest.raises(JsonDocError, match="no item"):
        d.node("/l/5")
    with pytest.raises(JsonDocError):
        JsonDoc.from_bytes(b'{"a": "\xff"}')
    assert TextDoc.from_bytes(b"line\r\nline").to_bytes() == b"line\r\nline"


# ---------------------------------------------------------------- the adapter contract and every game
def test_example_game_through_its_adapter(world):
    _cfg, a, _ = world
    s = a.summary()
    assert s["root_exists"] and not s["errors"]
    assert (s["places"]["count"], s["lines"]["count"], s["quests"]["count"], s["music_slots"]["count"], s["people"]["count"]) == (3, 5, 1, 3, 1)
    assert s["lines"]["locked"] == 1 and s["lines"]["by_status"] == {"approved": 2, "draft": 2, "flagged": 1}
    # BUILD 06: a slot's status is the game's own word (needed · written · in game · inherits); the board adds the rest
    assert {m.id: m.status for m in a.music_slots()} == {"harbor_theme": "needed", "battle": "needed", "ember_song": "needed"}
    assert [l.text for l in a.lines("millstone")][0].startswith("Everything that comes through")
    assert str(a.lines()[0].ref).startswith("data/dialogue/")


def test_every_game_round_trips_every_data_file_byte_identical():
    """Every game this install has (the example everywhere; a real game where its folder is connected)."""
    cfg = cfgmod.load()
    checked = 0
    for gid in games.game_ids(cfg):
        if not games.has_adapter(cfg, gid):
            continue
        a = games.adapter(cfg, gid)
        if not a.root.is_dir():
            continue
        for rel in a.data_files():
            raw = a.path(rel).read_bytes()
            doc = a.read_doc(rel)
            assert doc.to_bytes() == raw, f"{gid}: {rel}"
            if isinstance(doc, JsonDoc):
                assert doc.value == json.loads(raw.decode("utf-8-sig")), f"{gid}: {rel}"
            checked += 1
    assert checked >= 9


def test_picker_lists_games_and_a_relative_game_root_hangs_off_the_game_folder(world):
    cfg, a, tmp = world
    ls = games.listing(cfg)
    assert [g["id"] for g in ls] == ["_example"] and ls[0]["root_exists"] and ls[0]["adapter"]
    assert a.root == tmp / "games" / "_example" / "game"


# ---------------------------------------------------------------- the safe-save path
LINE = "data/dialogue/harbor_keeper.json"


def test_a_valid_edit_backs_up_replaces_and_journals(world):
    _cfg, a, _ = world
    before = a.path(LINE).read_bytes()
    r = safesave.edit(a, LINE, [("set", "/lines/1/text", "No oil, no light. Bring me a can?")], "Bill",
                      expected_hash=safesave.file_hash(before), reason="tighter")
    assert r["ok"] and r["changed"]
    after = a.path(LINE).read_bytes()
    assert after == before.replace(b"Oil's gone. If you find any, the lamp'd thank you. So would I.",
                                   b"No oil, no light. Bring me a can?")         # only those bytes changed
    assert (a.root / r["backup"]).read_bytes() == before
    e = journal.read(a.root)[-1]
    assert (e["who"], e["kind"], e["obj"], e["after"]) == ("Bill", "edit", f"{LINE}#/lines/1/text", "No oil, no light. Bring me a can?")
    assert "No oil, no light" in (a.root / "WORKBENCH_LOG.md").read_text(encoding="utf-8")
    assert not any((a.root / "_workbench_tmp").rglob("*.json"))


def test_an_invalid_save_leaves_the_file_untouched(world):
    _cfg, a, _ = world
    before = a.path(LINE).read_bytes()
    r = safesave.edit(a, LINE, [("set", "/lines/1/text", "   ")], "Bill")                   # the game's checker: no words
    assert not r["ok"] and any("has no words" in p for p in r["refused"])
    assert a.path(LINE).read_bytes() == before
    assert not (a.root / "_workbench_backups").exists()
    r2 = safesave.edit(a, LINE, [("set", "/lines/1/status", "maybe")], "Bill")
    assert not r2["ok"] and a.path(LINE).read_bytes() == before
    with pytest.raises(safesave.SaveRefused):
        safesave.save(a, LINE, b"{ not json", safesave.file_hash(before))
    assert a.path(LINE).read_bytes() == before
    assert journal.read(a.root)[-1]["kind"] == "refused"


def test_a_hash_conflict_writes_nothing_and_shows_both_versions(world):
    _cfg, a, _ = world
    opened = safesave.file_hash(a.path(LINE).read_bytes())
    p = a.path(LINE)
    p.write_bytes(p.read_bytes().replace(b"Oil's gone.", b"The oil's gone."))           # someone else saved meanwhile
    theirs = p.read_bytes()
    r = safesave.edit(a, LINE, [("set", "/lines/1/text", "Mine.")], "Bill", expected_hash=opened)
    assert not r["ok"] and r["conflict"]["yours"] == {"/lines/1/text": "Mine."}
    assert r["conflict"]["theirs"]["/lines/1/text"].startswith("The oil's gone.")
    assert p.read_bytes() == theirs
    with pytest.raises(safesave.SaveConflict):
        safesave.save(a, LINE, b"{}", opened)


def test_ids_and_a_songs_own_words_are_never_edited(world):
    _cfg, a, _ = world
    r = safesave.edit(a, "data/places/millstone.json", [("set", "/id", "mill")], "Bill")
    assert not r["ok"] and "ids are never edited" in r["refused"][0]
    song = "data/dialogue/ember_toll.json"
    before = a.path(song).read_bytes()
    r = safesave.edit(a, song, [("set", "/lines/0/text", "new words")], "Bill")
    assert not r["ok"] and "locked" in r["refused"][0] and a.path(song).read_bytes() == before


def test_unknown_fields_survive_and_tabs_and_crlf_are_kept(world):
    _cfg, a, _ = world
    rel = "data/places/ember_crossing.json"
    before = a.path(rel).read_bytes()
    r = safesave.edit(a, rel, [("set", "/summary", "A bridge town rebuilt from ash.")], "Bill")
    assert r["ok"]
    after = a.path(rel).read_bytes()
    assert b"\r\n\t\"_editor_note\"" in after and after.count(b"\r\n") == before.count(b"\r\n")


# ---------------------------------------------------------------- approved means his
def test_an_assistant_proposes_a_change_to_what_bill_approved(world):
    _cfg, a, _ = world
    before = a.path(LINE).read_bytes()
    r = safesave.edit(a, LINE, [("set", "/lines/0/text", "A different line.")], "Claude Opus", reason="tighter rhythm")
    assert r["ok"] and r["proposed"]["to"] == "Bill" and r["proposed"]["changes"][0]["before"].startswith("I still climb")
    assert a.path(LINE).read_bytes() == before                                    # nothing changed in the game
    assert [p["id"] for p in approval.list_open(a.root)] == [r["proposed"]["id"]]
    assert journal.read(a.root)[-1]["kind"] == "propose"
    assert not approval.accept(a, r["proposed"]["id"], "Claude Opus")["ok"]       # only the owner accepts
    ok = approval.accept(a, r["proposed"]["id"], "Bill")
    assert ok["ok"] and a.root.joinpath(LINE).read_text(encoding="utf-8").count("A different line.") == 1
    assert approval.load(a.root, r["proposed"]["id"])["status"] == "accepted"
    assert safesave.edit(a, LINE, [("set", "/lines/0/text", "His own edit.")], "Bill")["changed"]   # the owner edits freely


def test_a_stale_proposal_refuses_instead_of_overwriting(world):
    _cfg, a, _ = world
    p = safesave.edit(a, LINE, [("set", "/lines/0/text", "Proposal.")], "Claude Fable")["proposed"]
    safesave.edit(a, LINE, [("set", "/lines/0/text", "Bill rewrote it first.")], "Bill")
    r = approval.accept(a, p["id"], "Bill")
    assert not r["ok"] and "changed since" in r["message"] and approval.load(a.root, p["id"])["status"] == "stale"
    assert "Bill rewrote it first." in a.path(LINE).read_text(encoding="utf-8")


def test_marking_status_signs_approval_and_an_assistant_cannot_approve(world):
    _cfg, a, _ = world
    rel = "data/dialogue/millstone_miller.json"
    assert not approval.mark(a, rel, "/lines/0", "approved", "Claude Opus")["ok"]
    assert approval.mark(a, rel, "/lines/0", "approved", "Bill")["ok"]
    line = a.load(rel)["lines"][0]
    assert (line["status"], line["approved_by"]) == ("approved", "Bill")
    assert approval.mark(a, rel, "/lines/1", "draft", "Claude Opus")["ok"]          # unapproved lines are anyone's
    assert approval.mark(a, rel, "/lines/0", "flagged", "Bill")["ok"]
    assert a.load(rel)["lines"][0]["approved_by"] is None                           # no longer approved → unsigned
    assert [e["kind"] for e in journal.read(a.root)][-1] == "flag"


def test_an_edit_needs_a_name(world):
    _cfg, a, _ = world
    assert not safesave.edit(a, LINE, [("set", "/lines/1/text", "x")], "")["ok"]


# ---------------------------------------------------------------- journal and identity
def test_journal_appends_reads_filters_and_survives_a_torn_line(world):
    _cfg, a, _ = world
    journal.append(a.root, "Bill", "test", "a test action", note="the journal records it")
    (a.root / "journal" / next(iter(os.listdir(a.root / "journal")))).open("a", encoding="utf-8").write('{"torn": ')
    threads = [threading.Thread(target=journal.append, args=(a.root, f"T{i}", "note"), kwargs={"view": False}) for i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    es = journal.read(a.root)
    assert es[0]["kind"] == "test" and es[0]["note"] == "the journal records it"
    assert len([e for e in es if e["who"].startswith("T")]) >= 19                   # the torn line ate at most one
    assert journal.read(a.root, who="Bill")[0]["obj"] == "a test action"
    with pytest.raises(ValueError):
        journal.append(a.root, "", "edit")


def test_identity_setting_and_the_session_override(world, monkeypatch):
    assert settings.identity() is None
    assert settings.set_identity("  Bill  ") == "Bill" and settings.identity() == "Bill"
    monkeypatch.setenv("FORGE_IDENTITY", "Claude Opus")
    assert settings.identity() == "Claude Opus" and settings.is_assistant(settings.identity())
    with pytest.raises(ValueError):
        settings.set_identity("")


def test_default_game_never_comes_from_code(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    assert cfgmod.default_game() == "_example"
    (tmp_path / "games" / "mygame").mkdir(parents=True)
    (tmp_path / "games" / "mygame" / "forge.game.json").write_text("{}")
    assert cfgmod.default_game() == "mygame"
    assert cfgmod.default_game({"default_game": "other"}) == "other"


# ---------------------------------------------------------------- the worker's state
def _log(tmp, *lines):
    (tmp / "logs" / "forge_2026-11-10.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_worker_state_from_process_running_folder_and_log(world, monkeypatch):
    cfg, _a, tmp = world
    _log(tmp, "2026-11-10 17:12:58,520 [INFO] forge.queue: claimed J1",
         "2026-11-10 17:14:12,770 [INFO] forge.queue: done J1",
         "2026-11-10 17:14:12,812 [INFO] forge.queue: idle — waiting for jobs in D:\\RPG_Forge\\jobs\\pending")
    w = worker.state(cfg, procs=[{"pid": 7, "cmdline": "python -m forge worker --gpu"}])
    assert (w["state"], w["since"]) == ("idle", "2026-11-10 17:14:12")
    assert worker.state(cfg, procs=[])["state"] == "stopped"
    assert worker.state(cfg, procs=None)["state"] == "unknown" and "idle" in worker.state(cfg, procs=None)["words"]
    (tmp / "jobs" / "running" / "J2.json").write_text(json.dumps({"id": "J2", "name": "harbor", "type": "render",
                                                                  "started_at": "2026-11-10T18:00:00"}))
    assert worker.state(cfg, procs=[{"pid": 7, "cmdline": "x"}])["state"] == "rendering"
    assert worker.state(cfg, procs=[])["state"] == "stopped-mid-job"
    from datetime import datetime, timedelta
    fresh = (datetime.now() - timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S")
    _log(tmp, f"{fresh},000 [INFO] forge.queue: claimed J2")
    assert worker.state(cfg, procs=[])["state"] == "rendering"         # a job in running/ and a log 3 min old: not "stopped"
    monkeypatch.setattr(worker, "processes", lambda timeout=8.0: [])
    assert not worker.start(cfg)["ok"] and not (tmp / "jobs" / "pending" / "J2.json").exists()   # nothing requeued
    (tmp / "jobs" / "running" / "J2.json").replace(tmp / "jobs" / "done" / "J2.json")
    assert worker.state(cfg, procs=[])["state"] == "unknown"           # nothing running, log fresh: can't tell, won't guess
    assert not worker.start(cfg)["ok"]
    assert worker._is_worker('"D:\\RPG_Forge\\venv\\Scripts\\python.exe" -m forge worker --gpu')
    assert not worker._is_worker("python -m forge suite")


def test_start_refuses_when_a_worker_is_running_or_unknown(world, monkeypatch):
    cfg, _a, _ = world
    monkeypatch.setattr(worker, "processes", lambda timeout=8.0: [{"pid": 1, "cmdline": "python -m forge worker"}])
    assert not worker.start(cfg)["ok"]
    monkeypatch.setattr(worker, "processes", lambda timeout=8.0: None)
    assert "can't tell" in worker.start(cfg)["message"]


# ---------------------------------------------------------------- the app
def _serve(cfg):
    from forge.suite import server
    srv = server.make_server(cfg, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _post(base, action, body, header=True):
    req = urllib.request.Request(base + "/api/suite/act/" + action, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-Forge": "1"} if header else {})})
    return json.loads(urllib.request.urlopen(req).read())


def test_the_suite_app_end_to_end(world, monkeypatch):
    cfg, a, tmp = world
    monkeypatch.setattr(worker, "processes", lambda timeout=8.0: [])
    (tmp / "jobs" / "pending" / "P1.json").write_text(json.dumps({"id": "P1", "type": "render", "batch": "b"}))
    srv, base = _serve(cfg)
    try:
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "RPG<b>_</b>Forge" in page and 'id="game"' in page and ">Story<" in page
        assert b"/api/state" in urllib.request.urlopen(base + "/art/queue").read()       # the dashboard, same code
        g = json.loads(urllib.request.urlopen(base + "/api/suite/games").read())
        assert g["current"] == "_example" and g["identity"] is None
        h = json.loads(urllib.request.urlopen(base + "/api/suite/home").read())
        assert h["worker"]["state"] == "stopped" and h["counts"]["pending"] == 1
        assert h["actions"]["start"]["enabled"] and h["actions"]["pause"]["enabled"] and not h["actions"]["resume"]["enabled"]
        try:
            _post(base, "pause", {}, header=False)
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 403
        assert _post(base, "identity", {"name": "Bill"})["identity"] == "Bill"
        assert _post(base, "pick", {"id": "_example"})["ok"] and not _post(base, "pick", {"id": "nope"})["ok"]
        assert _post(base, "pause", {})["ok"] and (tmp / "jobs" / "paused" / "P1.json").exists()
        assert _post(base, "resume", {})["ok"] and (tmp / "jobs" / "pending" / "P1.json").exists()
        kinds = [e["kind"] for e in journal.read(a.root)]
        assert kinds.count("queue") == 2 and "setting" in kinds                          # signed actions, in the journal
        v = json.loads(urllib.request.urlopen(base + "/api/suite/game?id=_example&fresh=1").read())
        assert v["summary"]["lines"]["count"] == 5 and v["journal"][0]["who"] == "Bill"
        assert b"Workbench log" in urllib.request.urlopen(base + "/suite/text?what=worklog&id=_example").read()
    finally:
        srv.shutdown()


# ---------------------------------------------------------------- forge/ names no game
# Files the running art worker reloads may not be edited while it runs; their old default game names go in BUILD 16
# (wiring day, W9). This list may only shrink: a file that no longer names a game must come off it.
UNTIL_WIRING_DAY: set = set()          # BUILD 16 (wiring day): emptied — every file under forge/ is game-agnostic now


def _game_names() -> list[str]:
    names = set()
    for p in (REPO / "games").iterdir():
        if p.is_dir() and not p.name.startswith(("_", ".")) and (p / "forge.game.json").exists():
            names |= {p.name.lower(), p.name.replace("_", " ").lower()}
    return sorted(names)


def test_forge_names_no_game():
    names = _game_names()
    hits = {}
    for f in sorted((REPO / "forge").rglob("*")):
        if f.suffix not in (".py", ".html", ".json", ".md", ".txt") or "__pycache__" in f.parts:
            continue
        low = f.read_text(encoding="utf-8", errors="replace").lower()
        found = [n for n in names if n in low]
        if found:
            hits[f.relative_to(REPO).as_posix()] = found
    assert set(hits) - UNTIL_WIRING_DAY == set(), f"forge/ must not name a game: {sorted(set(hits) - UNTIL_WIRING_DAY)}"
    if names:                                       # on a public clone there is no real game to look for
        assert UNTIL_WIRING_DAY <= set(hits), f"no longer naming a game — take off the list: {sorted(UNTIL_WIRING_DAY - set(hits))}"
