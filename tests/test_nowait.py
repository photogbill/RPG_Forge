"""Don't wait for me (nowait.py, 2026-11-17) — the owner's standing instruction: an open question takes its sender's
default or is left to a named assistant, so nothing waits on the owner's schedule; every stand-in answer is marked, is
never the owner's ruling, and is replaced by the owner's own answer whenever it comes. All on a throwaway copy of the
example game."""
from __future__ import annotations
import json, threading, urllib.request
from datetime import datetime, timedelta

import pytest

from forge.suite import areas, journal, mail, nowait, orders, rulings, server, settings, tasks
from forge import cli_suite
from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

T = datetime(2026, 11, 17, 12, 30, 0)
BILL, FABLE, OPUS = "Bill", "Claude Fable", "Claude Opus"
FABLE_L = "20261110-091500_claude-fable_ember-crossing-s-greeting-and-the-harbor"
OPUS_L = "20261110-094000_claude-opus_the-example-game-s-first-build-three-pla"


@pytest.fixture
def w(world, monkeypatch):
    cfg, a, tmp = world
    clock = {"t": T}
    monkeypatch.setattr(settings, "now", lambda path=None: clock["t"])
    areas._badge_cache.clear()
    rulings._CACHE.clear()
    return cfg, a, clock


def _letter_cards(cfg, who=BILL):
    return {c["id"]: c for c in tasks.gather(cfg, "_example", who) if c["kind"] == "letter"}


def test_off_by_default_and_only_a_person_can_set_it(w):
    cfg, a, _ = w
    assert nowait.get()["mode"] == "wait" and nowait.get()["defer_to"] is None      # no name is built in
    r = nowait.sweep(a.root, a)
    assert r["taken"] == [] and r["deferred"] == [] and len(_letter_cards(cfg)) == 2
    with pytest.raises(nowait.NoWaitRefused):
        nowait.set_mode(FABLE, "default")
    with pytest.raises(nowait.NoWaitRefused):
        nowait.set_mode(BILL, "default", defer_to="Bill")          # questions are left to an assistant
    with pytest.raises(nowait.NoWaitRefused):
        nowait.set_mode(BILL, "sometimes")
    with pytest.raises(nowait.NoWaitRefused):
        nowait.set_mode(BILL, "defer")                               # …and it has to be said which one
    st = nowait.set_mode(BILL, "default", after_hours=4)
    assert (st["mode"], st["after_hours"], st["person"], st["defer_to"]) == ("default", 4.0, BILL, None)
    assert nowait.set_mode(BILL, "defer", defer_to=FABLE)["defer_to"] == FABLE
    assert json.loads(settings.PATH.read_text(encoding="utf-8"))["nowait"]["mode"] == "defer"


def test_what_a_question_falls_back_to():
    q = {"choices": ["Mind the coals.", "Pay the song."], "recommendation": "Mind the coals", "default": "Keep it until you say"}
    assert nowait.resolution(q) == {"how": "default", "text": "Keep it until you say"}       # the default first, kept as words
    assert nowait.resolution({**q, "default": ""}) == {"how": "recommendation", "choice": "Mind the coals."}
    assert nowait.resolution({"choices": [{"label": "Vocal", "value": True}], "default": "vocal"}) == {"how": "default", "choice": "Vocal"}
    assert nowait.resolution({"question": "what should it feel like?"}) is None


def test_take_the_defaults_settles_every_question_and_marks_them_stand_ins(w):
    cfg, a, _ = w
    nowait.set_mode(BILL, "default")
    r = nowait.sweep(a.root, a)
    assert {(t["id"], t["how"]) for t in r["taken"]} == {("greeting", "default"), ("harbor_feel", "default"), ("battle_vocal", "default")}
    assert r["deferred"] == [] and _letter_cards(cfg) == {}                     # nothing waits on Bill
    # the default that is one of the choices changed the data, in the asker's name, through the safe path
    assert json.loads(a.path("data/music.json").read_text(encoding="utf-8"))["battle"]["vocal"] is False
    # the default that is only words changed nothing
    assert json.loads(a.path("data/places/ember_crossing.json").read_bytes().decode("utf-8-sig"))["greeting"] == "Pay the song."
    letters = mail.all_letters(a.root)
    sent = [l for l in letters if l.subject.startswith("Went ahead: ")]
    assert len(sent) == 2 and all(l.folder == "to_bill" and l.to == BILL for l in sent)
    by_sender = {l.sender: l for l in sent}
    assert set(by_sender) == {FABLE, OPUS}                                    # each asker's own fallback, in their name
    for l in sent:
        assert all(x["stand_in"] == "default" and x["for"] == BILL for x in l.answers)
        assert "nobody typed it" in l.body and "None of this is Bill's ruling" in l.body
    assert mail.unread_count(a.root, BILL) >= 2                                # he is told, in his inbox
    # the book lists them as provisional, never as his ruling — and still stops the question being asked again
    b = [e for e in rulings.book(a.root, a)["rulings"] if e.get("provisional")]
    assert len(b) == 3 and all(e["by"] in (FABLE, OPUS) and "not their ruling" in e["text"] for e in b)
    assert rulings.check(a.root, "Ordinary fights: instrumental or vocal?", a)
    # running it again does nothing
    again = nowait.sweep(a.root, a)
    assert again["taken"] == [] and again["deferred"] == [] and len(mail.all_letters(a.root)) == len(letters)
    dd = nowait.decided(a.root, BILL)
    assert {d["id"] for d in dd} == {"greeting", "harbor_feel", "battle_vocal"}
    notes = [e["note"] for e in journal.read(a.root, kinds=("letter",))]
    assert any("stand-in answers" in n and "written by the forge" in n for n in notes)


def test_his_own_answer_replaces_the_stand_in(w):
    cfg, a, clock = w
    nowait.set_mode(BILL, "default")
    nowait.sweep(a.root, a)
    clock["t"] = T + timedelta(hours=3)
    l = mail.reply(a.root, FABLE_L, BILL, "Mine now.", answers=[{"id": "greeting", "choice": "Mind the coals."}], adp=a)
    assert l.answers[0]["applied"]["message"] == "changed"
    assert json.loads(a.path("data/places/ember_crossing.json").read_bytes().decode("utf-8-sig"))["greeting"] == "Mind the coals."
    v = mail.thread_view(a.root, FABLE_L, BILL)
    q = {x["id"]: x for c in v["letters"] for x in c["questions"]}
    assert q["greeting"]["answer"]["by"] == BILL and not q["greeting"]["answer"].get("stand_in")
    assert q["harbor_feel"]["answer"]["stand_in"] == "default"
    assert {d["id"] for d in nowait.decided(a.root, BILL)} == {"harbor_feel", "battle_vocal"}
    rulings._CACHE.clear()
    e = next(e for e in rulings.book(a.root, a)["rulings"] if e["id"] == f"a:{FABLE_L}#greeting")
    assert e["by"] == BILL and not e.get("provisional")


def test_a_question_with_no_fallback_goes_to_the_named_assistant_who_decides_it(w):
    cfg, a, clock = w
    asked = mail.send(a.root, OPUS, BILL, "The ferry", "Two things.", questions=[
        {"id": "bell", "question": "Does the ferry ring a bell when it docks at the harbor?"},
        {"id": "fare", "question": "What is the ferry's fare across the strait?", "default": "Two coins", "choices": ["Two coins", "A song"]}],
        when=T - timedelta(hours=1))
    nowait.set_mode(BILL, "default")                                           # nobody named yet: the one with no fallback waits
    r = nowait.sweep(a.root, a)
    assert ("fare", "default") in {(t["id"], t["how"]) for t in r["taken"]} and r["deferred"] == []
    assert _letter_cards(cfg)[f"letter:{asked.id}"]["count"] == 1 and nowait.sweep(a.root, a)["taken"] == []
    nowait.set_mode(BILL, "default", defer_to=FABLE)
    r = nowait.sweep(a.root, a)
    assert r["taken"] == []

    assert [(d["id"], d["to"]) for d in r["deferred"]] == [("bell", FABLE)]
    assert _letter_cards(cfg) == {}                                            # Bill's list is clear either way
    o = [x for x in orders.listing(a.root, FABLE, "open") if x.get("nowait") == asked.id]
    assert len(o) == 1 and o[0]["priority"] == "now" and o[0]["object"] == f"mail:{asked.id}" and o[0]["by"] == BILL
    p = nowait.pending(a.root, FABLE)
    assert len(p) == 1 and [q["id"] for q in p[0]["questions"]] == ["bell"] and nowait.pending(a.root, OPUS) == []
    v = mail.thread_view(a.root, asked.id, BILL)
    assert next(q for q in v["letters"][0]["questions"] if q["id"] == "bell")["deferred"]["to"] == FABLE
    # only the assistant it was left to decides it; a person just answers the letter
    with pytest.raises(nowait.NoWaitRefused):
        nowait.decide(a.root, a, asked.id, OPUS, [{"id": "bell", "text": "yes"}])
    with pytest.raises(nowait.NoWaitRefused):
        nowait.decide(a.root, a, asked.id, BILL, [{"id": "bell", "text": "yes"}])
    with pytest.raises(nowait.NoWaitRefused):
        nowait.decide(a.root, a, asked.id, FABLE, [{"id": "fare", "text": "free"}])      # not one left to Fable
    clock["t"] = T + timedelta(minutes=5)
    l = nowait.decide(a.root, a, asked.id, FABLE, [{"id": "bell", "text": "Yes — one stroke", "note": "the keeper's lines lean on it"}])
    assert l.sender == FABLE and l.to == BILL and l.answers[0]["stand_in"] == "deferred" and "They stand until you say otherwise" in l.body
    assert nowait.pending(a.root) == [] and nowait.deferred(a.root) == {}
    assert [x for x in orders.listing(a.root, FABLE, "open") if x.get("nowait")] == []      # the "your call" order closed itself
    d = next(d for d in nowait.decided(a.root, BILL) if d["id"] == "bell")
    assert d["how"] == "deferred" and d["by"] == FABLE and d["answer"] == "Yes — one stroke"


def test_leave_it_to_the_assistant_defers_everything_and_his_answer_takes_it_back(w):
    cfg, a, clock = w
    nowait.set_mode(BILL, "defer", defer_to=FABLE)
    r = nowait.sweep(a.root, a)
    assert r["taken"] == [] and len(r["deferred"]) == 3 and _letter_cards(cfg) == {}
    assert len(mail.all_letters(a.root)) == 3                                  # no letter is written until someone decides
    assert sum(len(p["questions"]) for p in nowait.pending(a.root, FABLE)) == 3
    assert nowait.sweep(a.root, a)["deferred"] == []                           # once
    clock["t"] = T + timedelta(hours=1)
    mail.reply(a.root, OPUS_L, BILL, "", answers=[{"id": "battle_vocal", "choice": "Vocal"}], adp=a)
    nowait.sweep(a.root, a)
    assert [p["letter"] for p in nowait.pending(a.root)] == [FABLE_L]
    assert [x["nowait"] for x in orders.listing(a.root, FABLE, "open") if x.get("nowait")] == [FABLE_L]
    assert nowait.decided(a.root, BILL) == []                                  # his answer is his, not a stand-in


def test_the_wait_first_hours_and_parked_questions_are_respected(w):
    cfg, a, clock = w
    fresh = mail.send(a.root, FABLE, BILL, "Fresh one", "One thing.", when=T - timedelta(hours=2),
                      questions=[{"id": "q1", "question": "Should the lighthouse lamp be lit in the after era?", "default": "Lit"}])
    mail.reply(a.root, OPUS_L, BILL, "", answers=[{"id": "battle_vocal", "talk": True}], when=T - timedelta(hours=1))
    nowait.set_mode(BILL, "default", after_hours=12)
    r = nowait.sweep(a.root, a)
    took = {t["letter"] for t in r["taken"]}
    assert FABLE_L in took and fresh.id not in took and OPUS_L not in took     # too new; "talk to me" is left alone
    assert set(_letter_cards(cfg)) == {f"letter:{fresh.id}", f"letter:{OPUS_L}"}
    clock["t"] = T + timedelta(hours=11)
    assert {t["letter"] for t in nowait.sweep(a.root, a)["taken"]} == {fresh.id}
    # the button on the letter is his own act: it takes the parked one too
    out = nowait.settle(a.root, a, OPUS_L, BILL, "default")
    assert [t["id"] for t in out["taken"]] == ["battle_vocal"] and _letter_cards(cfg) == {}
    # a person's questions are never stood in for
    theirs = mail.send(a.root, "Wren", BILL, "From a person", "Hm?", questions=[{"id": "x", "question": "Is the tide table printed anywhere?", "default": "No"}])
    assert nowait.sweep(a.root, a)["taken"] == []
    with pytest.raises(nowait.NoWaitRefused):
        nowait.settle(a.root, a, theirs.id, BILL, "default")


def test_a_default_never_overwrites_what_a_person_approved(w):
    cfg, a, _ = w
    p = a.path("data/places/ember_crossing.json")
    raw = p.read_bytes()
    p.write_bytes(raw.replace(b'"status": "draft"', b'"status": "approved"'))
    asked = mail.send(a.root, OPUS, BILL, "The greeting again", "One.", when=T - timedelta(hours=1), questions=[
        {"id": "g", "question": "Swap the town greeting for the short crossing one?", "default": "Cross quick.",
         "choices": ["Cross quick.", "Pay the song."], "applies_to": {"file": "data/places/ember_crossing.json", "pointer": "/greeting"},
         "asked_again": "a new option"}])
    out = nowait.settle(a.root, a, asked.id, BILL, "default")
    assert "proposed" in out["taken"][0]["applied"]
    assert json.loads(p.read_bytes().decode("utf-8-sig"))["greeting"] == "Pay the song."


def test_the_page_the_actions_and_the_command_line(w, capsys):
    cfg, a, clock = w
    settings.set_identity(BILL)
    s = server.make_server(cfg, 0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    port = s.server_address[1]
    try:
        get = lambda path: json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}").read())
        d = get("/api/suite/tasks?id=_example")
        assert d["nowait"]["setting"]["mode"] == "wait" and d["nowait"]["mine"] and FABLE in d["nowait"]["assistants"]
        assert sum(1 for c in d["next"] if c["kind"] == "letter") == 2
        assert not server.act(cfg, "nowait_letter", {"game": "_example", "letter": OPUS_L, "how": "defer"})["ok"]    # nobody named
        r = server.act(cfg, "nowait_letter", {"game": "_example", "letter": OPUS_L, "how": "defer", "defer_to": FABLE})
        assert r["ok"] and "left to Claude Fable" in r["message"]
        r = server.act(cfg, "nowait_set", {"game": "_example", "mode": "default", "after_hours": "0", "defer_to": FABLE})
        assert r["ok"] and "took their default" in r["message"]
        d = get("/api/suite/tasks?id=_example")
        assert not [c for c in d["next"] if c["kind"] == "letter"] and len(d["nowait"]["decided"]) == 3
        v = get(f"/api/suite/letter?id=_example&letter={FABLE_L}")
        assert v["nowait"]["mode"] == "default" and v["open_questions"] == 0
        assert areas.badges(cfg, "_example", None, fresh=True)["tasks"] == d["count"]
    finally:
        s.shutdown()
    page = (REPO / "forge" / "suite" / "shell.html").read_text(encoding="utf-8")
    for needle in ("nowait_set", "nowait_letter", "Don't wait for me", "Went ahead without you"):
        assert needle in page
    # an assistant's session: the setting can't be changed; a question sent now doesn't wait
    assert cli_suite.cmd_nowait(cfg, ["set", "wait", "--who", FABLE]) == 1
    qf = a.root / "q.json"
    qf.write_text(json.dumps([{"id": "oar", "question": "Does the ferryman keep a spare oar aboard?", "default": "Yes"}]), encoding="utf-8")
    capsys.readouterr()
    assert cli_suite.cmd_mail(cfg, ["send", "--from", OPUS, "--to", BILL, "--subject", "Oars", "--body", "One.", "--questions", str(qf), "--game", "_example"]) == 0
    out = capsys.readouterr().out
    assert "nothing here waits" in out and "oar: took the default → Yes" in out
    assert cli_suite.cmd_nowait(cfg, ["show", "--game", "_example"]) == 0 and "still standing: 4" in capsys.readouterr().out
    assert cli_suite.cmd_nowait(cfg, ["pending", "--who", FABLE, "--game", "_example"]) == 0
