"""BUILD 17 — team memory: the rulings book (searched before anyone asks, warning when data contradicts a ruling), the
idea box, playtest notes in the inbox, and where the game stands. On a throwaway copy of the example game."""
from __future__ import annotations
import json, threading, urllib.parse, urllib.request
from datetime import datetime, timedelta

import pytest

from forge.suite import areas, games, ideas, journal, mail, notes, orders, playtest, rulings, safesave, server, settings, standing
from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

T = datetime(2026, 11, 11, 16, 0, 0)
BILL, FABLE, OPUS = "Bill", "Claude Fable", "Claude Opus"
FABLE_LETTER = "20261110-091500_claude-fable_ember-crossing-s-greeting-and-the-harbor"
GREETING_Q = "What should everyone in Ember Crossing say when you walk in?"


@pytest.fixture
def w(world, monkeypatch):
    cfg, a, tmp = world
    clock = {"t": T}

    def now(path=None):
        clock["t"] += timedelta(seconds=1)
        return clock["t"]
    monkeypatch.setattr(settings, "now", now)
    settings.set_identity(BILL)
    rulings._CACHE.clear()
    return cfg, a, tmp


@pytest.fixture
def srv(w):
    cfg, a, tmp = w
    s = server.make_server(cfg, 0)
    th = threading.Thread(target=s.serve_forever, daemon=True)
    th.start()
    yield s.server_address[1]
    s.shutdown()


def _get(port, path):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}").read())


def _post(port, action, body):
    rq = urllib.request.Request(f"http://127.0.0.1:{port}/api/suite/act/{action}", data=json.dumps(body).encode("utf-8"),
                                headers={"Content-Type": "application/json", "X-Forge": "1"}, method="POST")
    return json.loads(urllib.request.urlopen(rq).read())


def _answer_greeting(a):
    """Bill answers Fable's greeting question in the Mail — that answer is now a ruling."""
    return mail.reply(a.root, FABLE_LETTER, BILL, "Coals it is.", answers=[{"id": "greeting", "choice": "Mind the coals."}], adp=a)


# ---------------------------------------------------------------- the frame
def test_the_notes_tabs_are_built_not_planned():
    for t in ("rulings", "ideas", "playtest"):
        _a, tab = areas.find(f"notes/{t}")
        assert not tab.get("planned") and tab["screen"] == t
        assert f"{t}:'v-{t}'" in server.SHELL and f"load{t.capitalize()}" in server.SHELL
    assert 'id="h-stand"' in server.SHELL                # Home opens with where the game stands


# ---------------------------------------------------------------- the rulings book
def test_an_answer_in_the_mail_becomes_a_dated_ruling_with_what_it_changed(w):
    _cfg, a, _ = w
    _answer_greeting(a)
    b = rulings.book(a.root, a)
    r = next(e for e in b["rulings"] if e["kind"] == "answer")
    assert r["question"] == GREETING_Q and r["answer"].startswith("Mind the coals.")
    assert r["by"] == BILL and r["when"].startswith("2026-11-11")
    assert r["applies_to"] == {"file": "data/places/ember_crossing.json", "pointer": "/greeting"} and r["value"] == "Mind the coals."
    assert rulings.search(a.root, "ember crossing greeting", a)[0]["id"] == r["id"]


def test_a_question_already_answered_is_caught_before_it_is_asked_again(w):
    """The build's done-when: the same question — or the same question reworded — doesn't reach the owner twice."""
    _cfg, a, _ = w
    _answer_greeting(a)
    for q in (GREETING_Q, "What should everyone say when you walk into Ember Crossing — the greeting?"):
        with pytest.raises(rulings.AlreadyRuled) as ex:
            mail.send(a.root, OPUS, BILL, "One more thing", "Bill,\n\nA question.", questions=[{"id": "g2", "question": q}], adp=a)
        assert "already" in str(ex.value) and "Mind the coals" in str(ex.value)
    assert not any("one-more-thing" in p.name for p in (a.root / "mail" / "to_bill").glob("*.md"))   # nothing was sent
    assert any(e["kind"] == "refused" and e.get("obj") == "rulings" for e in journal.read(a.root))
    # a genuinely new question goes through; so does an old one that says why it's asked again
    mail.send(a.root, OPUS, BILL, "The harbor at night", "Bill,", questions=[{"question": "Should the harbor's lamps stay lit after the war?"}], adp=a)
    mail.send(a.root, OPUS, BILL, "Coals again", "Bill,", adp=a,
              questions=[{"question": GREETING_Q, "asked_again": "the town burned a second time in the new draft"}])
    # a person is never refused (the page warns them instead), and a draft isn't checked
    mail.send(a.root, BILL, FABLE, "Greeting?", "Fable,", questions=[{"question": GREETING_Q}], adp=a)
    mail.save_draft(a.root, OPUS, BILL, "draft", "x", questions=[{"question": GREETING_Q}])


def test_marked_lines_in_the_notes_are_rulings_but_the_marks_legend_is_not(w):
    _cfg, a, _ = w
    (a.root / "NOTES.md").write_text(
        "# Notes\n\n✦ is the owner's ruling; ◆ is a proposal.\n\n## Rulings, 2026-11-09\n\n"
        "- ✦ The toll-keeper is the only one who sings in Ember Crossing (14:05).\n"
        "- ◆ The harbor keeper might hum.\n\n"
        "| town | status |\n|---|---|\n| millstone | ✦ approved |\n\n"
        "```\n✦ inside a code block is an example\n```\n", encoding="utf-8")
    b = rulings.book(a.root, a)
    marked = [e for e in b["rulings"] if e["kind"] == "marked"]
    assert [e["text"] for e in marked] == ["✦ The toll-keeper is the only one who sings in Ember Crossing (14:05)."]
    assert marked[0]["when"] == "2026-11-09 14:05" and marked[0]["where"] == "NOTES.md:7" and marked[0]["heading"] == "Rulings, 2026-11-09"
    assert rulings.check(a.root, "In Ember Crossing, is the toll-keeper the only one who sings?", a)
    assert not rulings.check(a.root, "What does the miller grind at Millstone?", a)       # a cousin isn't caught


def test_the_adapter_says_where_the_rulings_are_written(w, monkeypatch):
    _cfg, a, _ = w
    (a.root / "Builds" / "LATER.md").write_text("- ✦ The bridge is rebuilt from what the fire left, every plank.\n", encoding="utf-8")
    assert not any(e.get("file") == "Builds/LATER.md" for e in rulings.book(a.root, a)["rulings"])
    monkeypatch.setattr(type(a), "ruling_files", lambda self: ("*.md", "Builds/*.md"), raising=False)
    rulings._CACHE.clear()
    assert any(e.get("file") == "Builds/LATER.md" for e in rulings.book(a.root, a)["rulings"])


def test_recording_a_chat_ruling_and_who_may(w):
    _cfg, a, _ = w
    with pytest.raises(ValueError, match="where the person said it"):
        rulings.record(a.root, OPUS, "The harbor theme is a waltz.", by=BILL)
    with pytest.raises(ValueError, match="a person's to make"):
        rulings.record(a.root, OPUS, "The harbor theme is a waltz.", by=OPUS, source="me")
    e = rulings.record(a.root, OPUS, "The harbor theme is a slow waltz on one instrument.", by=BILL,
                       source="in chat, 2026-11-11 15:40: “a slow waltz, one instrument”", question="What should the harbor's theme feel like?")
    assert e["by"] == BILL and e["recorded_by"] == OPUS
    hits = rulings.check(a.root, "The harbor's theme — what should it feel like?", a)
    assert hits and hits[0]["id"] == e["id"]
    with pytest.raises(ValueError, match="person's decision"):
        rulings.retire(a.root, OPUS, e["id"], "changed my mind")
    rulings.retire(a.root, BILL, e["id"], "it's a march now")
    assert not rulings.check(a.root, "The harbor's theme — what should it feel like?", a)           # retired: no longer turns questions back
    kept = next(x for x in rulings.search(a.root, "harbor theme", a, include_retired=True) if x["id"] == e["id"])
    assert kept["retired"]["why"] == "it's a march now"                                            # …but it stays in the book
    assert rulings.path(a.root).read_text(encoding="utf-8").count("\n") == 2                       # append-only


def test_data_that_contradicts_a_ruling_is_warned_about(w):
    _cfg, a, _ = w
    _answer_greeting(a)                                             # sets /greeting to "Mind the coals." and pins it
    assert json.loads((a.root / "data/places/ember_crossing.json").read_text(encoding="utf-8"))["greeting"] == "Mind the coals."
    assert rulings.conflicts(a.root, a) == []
    r = safesave.edit(a, "data/places/ember_crossing.json", [("set", "/greeting", "Cross quick.")], FABLE, reason="test")
    assert r["ok"] and r["changed"] and "Mind the coals" in r["warnings"][0]                       # saved, but warned
    cs = rulings.conflicts(a.root, a)
    assert len(cs) == 1 and cs[0]["now"] == "Cross quick." and cs[0]["ruled"] == "Mind the coals."
    assert any(e["kind"] == "conflict" and e.get("link", "").startswith("a:") for e in journal.read(a.root))
    # an edit elsewhere in the same file doesn't repeat the warning
    r2 = safesave.edit(a, "data/places/ember_crossing.json", [("set", "/summary", "A bridge town.")], FABLE, reason="test")
    assert r2["ok"] and not r2.get("warnings")


# ---------------------------------------------------------------- the idea box
def test_an_idea_is_one_line_filed_with_what_he_was_looking_at_and_says_where_it_went(w):
    _cfg, a, _ = w
    i = ideas.add(a.root, BILL, "  A lullaby the miller   hums  ", at="story/read/millstone", label="Story › Read-through › millstone")
    assert i["text"] == "A lullaby the miller hums" and i["at"] == "story/read/millstone" and i["time"].startswith("2026-11-11")
    with pytest.raises(ValueError):
        ideas.add(a.root, BILL, "   ")
    assert [x["id"] for x in ideas.listing(a.root)] == [i["id"]]
    o = ideas.to_task(a.root, i["id"], OPUS, "Claude Opus")
    assert o["for"] == OPUS and "lullaby" in o["detail"] and o["object"] == "story/read/millstone"
    assert ideas.listing(a.root) == [] and ideas.listing(a.root, "sorted")[0]["sorted"]["where"].startswith("work order")
    j = ideas.add(a.root, BILL, "Ember Crossing's bridge creaks in the after")
    n = ideas.to_note(a.root, j["id"], OPUS, "place:ember_crossing", label="Ember Crossing")
    assert notes.threads(a.root, "place:ember_crossing")[0]["tag"] == "idea" and n["text"].startswith("Ember Crossing's bridge")
    k = ideas.add(a.root, BILL, "Maybe a sequel")
    ideas.sort(a.root, k["id"], OPUS, "kept")
    assert [x["id"] for x in ideas.listing(a.root)] == [k["id"]]                     # kept stays visible
    with pytest.raises(ValueError, match="say where"):
        ideas.sort(a.root, k["id"], OPUS, "file")
    assert ideas.counts(a.root) == {"open": 1, "sorted": 2, "all": 3}
    assert sum(1 for e in journal.read(a.root) if e.get("obj") == "ideas") >= 6


# ---------------------------------------------------------------- playtest notes
def _notes_file(a, recs):
    d = a.root / "playtest"
    (d / "shots").mkdir(parents=True, exist_ok=True)
    (d / "shots" / "20261111_150000.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (d / "notes.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs) + '{"torn":', encoding="utf-8")
    (d / "art_feedback.json").write_text("[]", encoding="utf-8")


REC = [
    {"time": "2026-11-11T15:00:00", "tester": "Bill", "category": "Writing", "text": "The toll-keeper sounds like everyone else",
     "context": "dialogue", "map": "ember_crossing", "era": "after", "dialogue": "ember_toll", "shot": "shots/20261111_150000.png"},
    {"time": "2026-11-11T15:01:00", "tester": "Bill", "category": "Bug", "text": "Walked through the bridge rail", "map": "ember_crossing"},
    {"time": "2026-11-11T15:02:00", "tester": "Bill", "category": "Music", "text": "Too loud at the harbor", "map": "harbor_hollow"},
]


def test_playtest_notes_arrive_as_letters_and_each_goes_where_it_can_be_worked_on(w):
    cfg, a, _ = w
    _notes_file(a, REC)
    box = playtest.inbox(a.root, a)
    assert box["new"] == 3 and box["by_category"]["Writing"] == 1 and box["notes"][-1]["shot"] == "playtest/shots/20261111_150000.png"
    assert box["notes"][-1]["place"] == "ember_crossing"
    r = playtest.take_in(cfg, "_example", BILL, to="Claude")
    assert r["ok"] and r["taken"] == 3 and len(r["letters"]) == 3
    inbox = mail.box(a.root, OPUS, "inbox")
    subs = {l["subject"] for l in inbox}
    assert {"Playtest notes — Writing", "Playtest notes — Bug", "Playtest notes — Music"} <= subs
    wl = next(l for l in mail.all_letters(a.root) if l.subject == "Playtest notes — Writing")
    assert wl.attachments == ["playtest/shots/20261111_150000.png"] and "toll-keeper" in wl.body
    th = notes.threads(a.root)
    assert any(t["obj"].startswith("data/dialogue/ember_toll.json#") and "[playtest · Writing]" in t["text"] for t in th)   # on the line
    assert any(t["obj"] == "place:harbor_hollow" and "Too loud" in t["text"] for t in th)                                   # music → place
    o = orders.listing(a.root, "claude", "open")
    assert len(o) == 1 and o[0]["title"].startswith("[Bug]") and o[0]["priority"] == "now"
    # never taken in twice; a new note later replies in its category's thread
    assert playtest.take_in(cfg, "_example", BILL)["taken"] == 0
    _notes_file(a, REC + [{"time": "2026-11-11T16:30:00", "tester": "Bill", "category": "Bug", "text": "Stuck at the toll gate",
                            "map": "ember_crossing"}])
    r2 = playtest.take_in(cfg, "_example", BILL)
    assert r2["taken"] == 1
    again = next(l for l in mail.all_letters(a.root) if l.id == r2["letters"][0])
    first = next(l for l in mail.all_letters(a.root) if l.subject == "Playtest notes — Bug")
    assert again.subject == "Re: Playtest notes — Bug" and again.thread == first.thread


def test_the_playtest_tab_needs_line_says_nothing_yet_before_the_first_note(w):
    cfg, a, _ = w
    n = areas.needs(cfg, "_example")["notes/playtest"]
    assert n["met"] is None and "first note" in n["line"]
    _notes_file(a, REC[:1])
    assert areas.needs(cfg, "_example")["notes/playtest"]["met"] is True


# ---------------------------------------------------------------- where the game stands
def test_home_says_where_the_game_stands_and_the_next_thing_for_each_of_us(w):
    cfg, a, _ = w
    _notes_file(a, REC[:1])
    ideas.add(a.root, BILL, "A lullaby the miller hums")
    orders.add(a.root, BILL, "Claude", "Rewrite the miller, less generic", priority="now")
    d = standing.data(cfg, "_example", None)
    assert d["available"]
    labels = {t["label"]: t for t in d["tiles"]}
    assert "Lines approved" in labels and "Questions answered" in labels
    q = labels["Questions answered"]
    assert q["of"] >= 2 and 0 <= q["have"] <= q["of"]
    ai = [x["title"] for x in d["next_ai"]]
    assert ai[0] == "Rewrite the miller, less generic"
    assert any("playtest" in x for x in ai) and any("idea" in x for x in ai)
    assert d["memory"]["ideas_open"] == 1 and d["memory"]["playtest_new"] == 1


def test_the_badge_on_notes_counts_ideas_and_playtest_notes(w):
    cfg, a, _ = w
    _notes_file(a, REC[:2])
    ideas.add(a.root, BILL, "one")
    b = areas.badges(cfg, "_example", fresh=True)
    assert b["ideas"] == 1 and b["playtest"] == 2 and b["notes"] >= 3


# ---------------------------------------------------------------- the page and the command line
def test_the_page_endpoints_and_actions(w, srv):
    _cfg, a, _ = w
    _answer_greeting(a)
    d = _get(srv, "/api/suite/rulings?id=_example&q=greeting")
    assert d["rulings"][0]["kind"] == "answer" and d["summary"]["by_kind"]["answer"] == 1
    c = _get(srv, "/api/suite/rulecheck?id=_example&q=" + urllib.parse.quote(GREETING_Q) + "&q=" + urllib.parse.quote("Is the moon made of cheese?"))
    assert c["checked"][0]["rulings"] and not c["checked"][1]["rulings"]
    assert _post(srv, "idea_add", {"game": "_example", "text": "A song for the toll", "at": "story/read/ember_crossing"})["ok"]
    iid = _get(srv, "/api/suite/ideas?id=_example")["ideas"][0]["id"]
    assert _post(srv, "idea_task", {"game": "_example", "id": iid, "for": "Claude"})["ok"]
    assert _get(srv, "/api/suite/ideas?id=_example")["counts"]["open"] == 0
    r = _post(srv, "rule_record", {"game": "_example", "text": "The bridge creaks.", "source": "said at the table", "by": BILL})
    assert r["ok"] and r["ruling"]["recorded_by"] == BILL
    settings.set_identity(OPUS)
    r = _post(srv, "mail_send", {"game": "_example", "to": BILL, "subject": "again", "body": "x", "questions": [{"question": GREETING_Q}]})
    assert not r["ok"] and "already" in r["message"]                                                 # the page shows why
    settings.set_identity(BILL)
    assert _get(srv, "/api/suite/playtest?id=_example")["has_file"] is False
    assert _get(srv, "/api/suite/standing?id=_example")["available"]


def test_command_line(w, capsys, monkeypatch):
    cfg, a, _ = w
    from forge import cli_suite
    _answer_greeting(a)
    monkeypatch.setenv("FORGE_IDENTITY", OPUS)
    assert cli_suite.cmd_rulings(cfg, ["check", GREETING_Q, "--game", "_example"]) == 1
    assert "ALREADY RULED" in capsys.readouterr().out
    assert cli_suite.cmd_rulings(cfg, ["check", "Is the moon made of cheese?", "--game", "_example"]) == 0
    assert cli_suite.cmd_rulings(cfg, ["record", "The harbor is quiet at night.", "--by", BILL, "--source", "chat 16:10",
                                       "--file", "data/places/ember_crossing.json", "--pointer", "/greeting", "--value", '"Pay the song."',
                                       "--game", "_example"]) == 0
    assert cli_suite.cmd_rulings(cfg, ["conflicts", "--game", "_example"]) == 1                     # two rulings now disagree with each other's data
    assert cli_suite.cmd_idea(cfg, ["A ballad for the ferry", "--game", "_example"]) == 0
    assert cli_suite.cmd_idea(cfg, ["list", "--game", "_example"]) == 0
    assert "ballad" in capsys.readouterr().out
    _notes_file(a, REC[:1])
    assert cli_suite.cmd_playtest(cfg, ["in", "--game", "_example"]) == 0
    assert "Took in 1" in capsys.readouterr().out


def test_no_new_module_names_a_game_or_a_correspondent():
    import re
    names = re.compile(r"\b(Bill|Fable|Opus|turing)\b", re.I)
    for f in ("rulings.py", "ideas.py", "playtest.py", "standing.py"):
        text = (REPO / "forge" / "suite" / f).read_text(encoding="utf-8")
        assert not [l for l in text.splitlines() if names.search(l)], f
