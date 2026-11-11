"""BUILD 03 — the Mail, work orders and "while you were away", on a throwaway copy of the example game (its three
example letters included). No real game and no real correspondent's mailbox is touched."""
from __future__ import annotations
import json, os, re, threading, urllib.error, urllib.request
from datetime import datetime
from pathlib import Path

import pytest

from forge import cli_suite
from forge.suite import away, journal, mail, orders, safesave, server, settings
from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

FABLE = "20261110-091500_claude-fable_ember-crossing-s-greeting-and-the-harbor"
OPUS = "20261110-094000_claude-opus_the-example-game-s-first-build-three-pla"
T = datetime(2026, 11, 10, 21, 0, 0)


def test_the_example_letters_read_back_as_letters(world):
    _cfg, a, _ = world
    l = mail.find(a.root, FABLE)
    assert (l.sender, l.to, l.folder) == ("Claude Fable", "Bill", "to_bill")
    assert [q["id"] for q in l.questions] == ["greeting", "harbor_feel"] and l.questions[0]["applies_to"]["pointer"] == "/greeting"
    assert l.body.startswith("Bill,") and "```" not in l.body
    inbox = mail.box(a.root, "Bill")
    assert [x["id"] for x in inbox] == [OPUS, FABLE] and all(x["unread"] for x in inbox)
    assert inbox[1]["open_questions"] == 2
    assert [x["subject"] for x in mail.box(a.root, "Claude Opus")] == ["The miller's second line"]
    assert mail.render(l.headers, l.body, l.questions) == mail.mail_dir(a.root).joinpath("to_bill", FABLE + ".md").read_text(encoding="utf-8")


def test_command_line_and_app_write_identical_letters(world, monkeypatch, tmp_path):
    cfg, a, _ = world
    monkeypatch.setattr(settings, "now", lambda path=None: T)
    settings.set_identity("Bill")
    qf = tmp_path / "q.json"
    qf.write_text(json.dumps([{"question": "Tea or coffee?", "choices": ["Tea", "Coffee"]}]), encoding="utf-8")
    bf = tmp_path / "b.md"
    bf.write_text("Opus,\n\nA question.\n\nBill", encoding="utf-8")
    assert cli_suite.cmd_mail(cfg, ["send", "--to", "Claude Opus", "--subject", "Breakfast", "--body-file", str(bf),
                                    "--questions", str(qf), "--game", "_example"]) == 0
    sent = next((a.root / "mail" / "to_claude").glob("20261110-210000_bill_breakfast.md"))
    cli_bytes = sent.read_bytes()
    os.replace(sent, tmp_path / "cli.md")
    r = server.act(cfg, "mail_send", {"game": "_example", "to": "Claude Opus", "subject": "Breakfast", "body": "Opus,\n\nA question.\n\nBill",
                                      "questions": [{"question": "Tea or coffee?", "choices": ["Tea", "Coffee"]}]})
    assert r["ok"] and sent.read_bytes() == cli_bytes
    # replies too (a free-text answer, so neither one changes the game)
    af = tmp_path / "a.json"
    af.write_text(json.dumps([{"id": "harbor_feel", "text": "A waltz, yes."}]), encoding="utf-8")
    assert cli_suite.cmd_mail(cfg, ["reply", FABLE, "--body", "Thanks.", "--answers", str(af), "--game", "_example"]) == 0
    rep = next((a.root / "mail" / "to_claude").glob("20261110-210000_bill_re-ember*.md"))
    cli_rep = rep.read_bytes()
    os.replace(rep, tmp_path / "cli_reply.md")
    assert server.act(cfg, "mail_reply", {"game": "_example", "letter": FABLE, "body": "Thanks.",
                                          "answers": [{"id": "harbor_feel", "text": "A waltz, yes."}]})["ok"]
    assert rep.read_bytes() == cli_rep


def test_send_with_a_choice_changes_the_data_backs_up_logs_and_says_so(world):
    _cfg, a, _ = world
    rel = "data/places/ember_crossing.json"
    before = a.path(rel).read_bytes()
    r = mail.reply(a.root, FABLE, "Bill", "Done.", answers=[{"id": "greeting", "choice": "Mind the coals."}], adp=a, when=T)
    after = a.path(rel).read_bytes()
    assert after == before.replace(b'"Pay the song."', b'"Mind the coals."')          # tabs and CRLF untouched
    ans = r.answers[0]
    assert ans["applied"]["ok"] and ans["applied"]["message"] == "changed" and (a.root / ans["applied"]["backup"]).read_bytes() == before
    assert "Changed through the suite" in r.body and "Still open: 1 of 2" in r.body
    kinds = [(e["kind"], e.get("obj")) for e in journal.read(a.root)]
    assert ("edit", f"{rel}#/greeting") in kinds and kinds[-1][0] == "letter"
    assert (r.to, r.folder, r.thread, r.h("in_reply_to")) == ("Claude Fable", "to_claude", FABLE, FABLE)


def test_free_text_changes_nothing_and_a_wrong_choice_is_refused(world):
    _cfg, a, _ = world
    rel = "data/places/ember_crossing.json"
    before = a.path(rel).read_bytes()
    r = mail.reply(a.root, FABLE, "Bill", "", answers=[{"id": "greeting", "text": "Something about ash, you pick"}], adp=a, when=T)
    assert a.path(rel).read_bytes() == before and "applied" not in r.answers[0]
    r2 = mail.reply(a.root, OPUS, "Bill", "", answers=[{"id": "battle_vocal", "choice": "Opera"}], adp=a, when=T)
    assert not r2.answers[0]["applied"]["ok"] and "isn't one of" in r2.answers[0]["applied"]["message"]
    r3 = mail.reply(a.root, OPUS, "Bill", "", answers=[{"id": "battle_vocal", "choice": "Vocal"}], adp=a, when=T)
    assert r3.answers[0]["applied"]["ok"] and a.load("data/music.json")["battle"]["vocal"] is True    # a {label, value} choice


def test_a_partly_answered_letter_keeps_its_open_questions_open(world):
    _cfg, a, _ = world
    mail.reply(a.root, FABLE, "Bill", "", answers=[{"id": "greeting", "choice": "Cross quick."},
                                                   {"id": "harbor_feel", "talk": True}], adp=a, when=T)
    v = mail.thread_view(a.root, FABLE, "Bill")
    assert v["open_questions"] == 1
    qs = {q["id"]: q for q in v["letters"][0]["questions"]}
    assert qs["greeting"]["answer"]["choice"] == "Cross quick." and qs["harbor_feel"]["answer"] is None
    assert qs["harbor_feel"]["parked"] == "talk"
    assert next(x for x in mail.box(a.root, "Bill") if x["id"] == FABLE)["open_questions"] == 1
    mail.reply(a.root, FABLE, "Bill", "", answers=[{"id": "harbor_feel", "text": "Slow waltz."}], adp=a, when=T)
    assert mail.thread_view(a.root, FABLE, "Bill")["open_questions"] == 0


def test_read_state_archive_drafts_and_search(world):
    _cfg, a, _ = world
    assert mail.unread_count(a.root, "Bill") == 2
    mail.mark_read(a.root, "Bill", FABLE)
    assert mail.unread_count(a.root, "Bill") == 1 and mail.unread_count(a.root, "Claude Opus") == 1
    assert (a.root / "mail" / "to_bill" / f"{FABLE}.md").read_text(encoding="utf-8").count("status: sent") == 1   # never rewritten
    mail.archive(a.root, "Bill", FABLE)
    assert [x["id"] for x in mail.box(a.root, "Bill", "archive")] == [FABLE] and FABLE not in [x["id"] for x in mail.box(a.root, "Bill")]
    mail.unarchive(a.root, "Bill", FABLE)
    assert FABLE in [x["id"] for x in mail.box(a.root, "Bill")]
    d = mail.save_draft(a.root, "Bill", "Claude Fable", "Half a thought", "Not done yet")
    assert [x["id"] for x in mail.box(a.root, "Bill", "drafts")] == [d.id] and not mail.box(a.root, "Claude Fable")[:0]
    d2 = mail.save_draft(a.root, "Bill", "Claude Fable", "A whole thought", "Done now", draft_id=d.id)
    assert d2.id == d.id and mail.find(a.root, d.id).subject == "A whole thought"
    s = mail.send_edited_draft(a.root, d.id, "Bill", "Claude Fable", "A whole thought", "Done now")
    assert s.folder == "to_claude" and not mail.box(a.root, "Bill", "drafts") and (a.root / "mail" / "drafts" / "_sent" / f"{d.id}.md").exists()
    assert [x["id"] for x in mail.box(a.root, "Bill", "all", query="weighs")] == ["20261110-100500_bill_the-miller-s-second-line"]
    assert "Bill" in mail.correspondents(a.root) and "Claude Fable" in mail.correspondents(a.root)


def test_a_work_order_he_types_is_on_the_list_a_session_reads(world, capsys):
    cfg, a, _ = world
    settings.set_identity("Bill")
    r = server.act(cfg, "order_add", {"game": "_example", "for": "Claude", "title": "Rewrite the miller, less generic",
                                      "priority": "now", "object": "data/dialogue/millstone_miller.json#/lines/1"})
    assert r["ok"]
    orders.add(a.root, "Claude Opus", "Bill", "Make the harbor theme", priority="someday")
    capsys.readouterr()
    assert cli_suite.cmd_orders(cfg, ["list", "--for", "Claude Opus", "--game", "_example"]) == 0
    out = capsys.readouterr().out
    assert "Rewrite the miller, less generic" in out and "[now" in out and "harbor theme" not in out
    oid = r["order"]["id"]
    o = orders.close(a.root, oid, "Claude Opus", "rewritten: he weighs the player")
    assert o["status"] == "done" and orders.listing(a.root, "claude") == []
    assert [x["id"] for x in orders.listing(a.root, "claude", None)] == [oid]
    assert orders.groups(a.root, ["Bill", "Claude Fable"]) == ["bill", "claude"]
    with pytest.raises(ValueError):
        orders.add(a.root, "Bill", "Claude", "x", priority="yesterday")


def test_while_you_were_away_shows_what_others_did_with_diffs(world, capsys):
    cfg, a, _ = world
    journal.append(a.root, "Claude Opus", "session", "start", when=datetime(2026, 11, 10, 8, 0))
    safesave.edit(a, "data/dialogue/harbor_keeper.json", [("set", "/lines/1/text", "Oil's gone. Bring some up, and the lamp burns again.")],
                  "Bill", now=datetime(2026, 11, 10, 9, 0))
    mail.send(a.root, "Bill", "Claude Opus", "Read the keeper", "I rewrote him.", when=datetime(2026, 11, 10, 9, 5))
    d = away.digest(a.root, "Claude Opus")
    assert d["since"] == "2026-11-10T08:00:00" and d["people"] == ["Bill"]
    sec = {s["kind"]: s for s in d["sections"]}
    diff = sec["edit"]["entries"][0]["diff"]
    assert diff.startswith("Oil's gone. ~~If you find any,~~ **Bring some up, and** the") and diff.endswith("**lamp burns again.**")
    assert sec["letter"]["entries"][0]["note"].startswith("to Claude Opus: Read the keeper")
    settings.set_identity("Claude Opus")
    capsys.readouterr()
    assert cli_suite.cmd_away(cfg, ["--game", "_example", "--mark"]) == 0
    assert "Lines and fields rewritten (1)" in capsys.readouterr().out
    assert (a.root / "journal" / "DIGEST_for_claude.md").exists()
    assert away.digest(a.root, "Claude Opus")["count"] == 0                     # --mark: the next digest starts here


def test_what_happens_during_a_session_reaches_the_next_digest(world):
    _cfg, a, _ = world
    journal.append(a.root, "Claude Opus", "session", "start", when=datetime(2026, 11, 10, 20, 0))
    journal.append(a.root, "Bill", "flag", "a line", note="generic", when=datetime(2026, 11, 10, 20, 20))   # mid-session
    journal.append(a.root, "Claude Opus", "letter", "mail/to_bill/x.md", when=datetime(2026, 11, 10, 20, 40))  # the session's letter
    d = away.digest(a.root, "Claude Opus")
    assert d["since"] == "2026-11-10T20:00:00" and [s["kind"] for s in d["sections"]] == ["flag"]


def test_the_mail_over_http(world, monkeypatch):
    cfg, a, _ = world
    from forge.suite import worker
    monkeypatch.setattr(worker, "processes", lambda timeout=8.0: [])
    settings.set_identity("Bill")
    srv = server.make_server(cfg, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    get = lambda p: json.loads(urllib.request.urlopen(base + p).read())

    def post(action, body, header=True):
        req = urllib.request.Request(base + "/api/suite/act/" + action, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **({"X-Forge": "1"} if header else {})})
        return json.loads(urllib.request.urlopen(req).read())
    try:
        g = get("/api/suite/games")
        assert g["games"][0]["unread"] == 2 and g["people"] == ["Bill"]                     # assistants aren't offered as "you"
        box = get("/api/suite/mail?id=_example&box=inbox")
        assert box["unread"] == 2 and box["letters"][0]["id"] == OPUS and "Claude Fable" in box["correspondents"]
        v = get(f"/api/suite/letter?id=_example&letter={FABLE}")
        assert v["open_questions"] == 2 and v["letters"][0]["questions"][0]["choices"][0] == "Mind the coals."
        assert post("mail_read", {"game": "_example", "letter": FABLE})["ok"]
        assert get("/api/suite/games")["games"][0]["unread"] == 1
        r = post("mail_reply", {"game": "_example", "letter": FABLE, "body": "",
                                "answers": [{"letter": FABLE, "id": "greeting", "choice": "Mind the coals."}]})
        assert r["ok"] and "greeting: changed" in r["message"]
        assert get(f"/api/suite/letter?id=_example&letter={FABLE}")["open_questions"] == 1
        assert post("order_add", {"game": "_example", "for": "Claude", "title": "Look at the harbor"})["ok"]
        o = get("/api/suite/orders?id=_example")
        assert {g["group"] for g in o["groups"]} == {"bill", "claude"} and o["me"] == "bill"
        assert get("/api/suite/away?id=_example")["count"] >= 0
        try:
            post("mail_send", {"game": "_example", "to": "x", "subject": "y", "body": "z"}, header=False)
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 403
        try:
            urllib.request.urlopen(base + "/suite/gamefile?id=_example&rel=../../forge.game.json")
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.shutdown()


def test_no_suite_module_names_a_correspondent():
    names = re.compile(r"\b(Bill|Fable|Opus)\b")          # the names people and sessions sign with
    files = sorted((REPO / "forge" / "suite").glob("*.py")) + [REPO / "forge" / "suite" / "shell.html", REPO / "forge" / "cli_suite.py"]
    hits = [f"{f.name}:{i}" for f in files for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if names.search(line)]
    assert hits == [], f"the suite names a correspondent: {hits}"
