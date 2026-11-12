"""BUILD 07 — the town read-through and a note on anything, on a throwaway copy of the example game: pick a town, read
it in order, rewrite a line, approve a run of lines, flag one as generic with a note — and the next session finds all of
it in its digest. Plus conflicts, locks, the sameness meter, side by side and the notes threads."""
from __future__ import annotations
import json, threading, urllib.request
from datetime import datetime

import pytest

from forge.suite import approval, areas, away, journal, notes, readthrough, server, settings
from test_suite_build01 import REPO, world  # noqa: F401

BILL, OPUS = "Bill", "Claude Opus"
T = datetime(2026, 11, 11, 7, 0, 0)


@pytest.fixture
def w(world, monkeypatch):
    cfg, a, tmp = world
    monkeypatch.setattr(settings, "now", lambda path=None: T)
    settings.set_identity(BILL)
    return cfg, a, tmp


def test_towns_and_a_page_in_order(w):
    _cfg, a, _ = w
    ts = readthrough.towns(a)
    assert [t["id"] for t in ts] == ["ember_crossing", "harbor_hollow", "millstone"]
    assert {t["id"]: t["lines"] for t in ts} == {"ember_crossing": 1, "harbor_hollow": 2, "millstone": 2}
    p = readthrough.page(a, "harbor_hollow")
    assert [l["text"][:12] for l in p["lines"]] == ["I still clim", "Oil's gone. "]
    assert p["counts"] == {"lines": 2, "approved": 1, "flagged": 0, "draft": 1, "locked": 0, "meter": p["counts"]["meter"], "notes": 0}
    assert [q["id"] for q in p["quests"]] == ["lamp_oil"]
    assert {s["label"] for s in p["sheet"]} >= {"name", "summary", "greeting"}
    assert set(p["hashes"]) == {"data/dialogue/harbor_keeper.json", "data/places/harbor_hollow.json"}
    after = readthrough.page(a, "harbor_hollow", "after")
    assert [l["text"][:4] for l in after["lines"]] == ["Oil'"] and after["quests"]
    assert readthrough.page(a, "ember_crossing")["lines"][0]["locked"]           # a song's own words show locked
    with pytest.raises(ValueError):
        readthrough.page(a, "nowhere")


def test_the_morning_rewrite_approve_flag_note_and_the_digest_next_day(w):
    cfg, a, _ = w
    p = readthrough.page(a, "millstone")
    h = p["hashes"]["data/dialogue/millstone_miller.json"]
    l0, l1 = p["lines"]
    # rewrite a line in place
    r = server.act(cfg, "read_edit", {"game": "_example", "ref": l0["ref"], "field": "text", "hash": h,
                                      "value": "Everything that crosses the bridge gets weighed. You too."})
    assert r["ok"] and r["hash"] != h
    # approve, by keyboard (one action per line), then flag the generic one with a note
    r = server.act(cfg, "read_mark", {"game": "_example", "ref": l0["ref"], "status": "approved", "hash": r["hash"]})
    assert r["ok"]
    hp = readthrough.page(a, "harbor_hollow")
    l1 = hp["lines"][1]
    r = server.act(cfg, "read_mark", {"game": "_example", "ref": l1["ref"], "status": "flagged", "hash": hp["hashes"][l1["file"]],
                                      "note": "any town could say this — use 'Weighed and fair.'", "label": "Keeper: Oil's gone"})
    assert r["ok"]
    d = json.loads((a.root / "data/dialogue/millstone_miller.json").read_text(encoding="utf-8"))
    assert d["lines"][0]["text"].startswith("Everything that crosses") and d["lines"][0]["status"] == "approved" and d["lines"][0]["approved_by"] == BILL
    d2 = json.loads((a.root / "data/dialogue/harbor_keeper.json").read_text(encoding="utf-8"))
    assert d2["lines"][1]["status"] == "flagged" and "approved_by" not in d2["lines"][1]
    th = notes.threads(a.root, l1["ref"])
    assert th[0]["tag"] == "generic" and th[0]["who"] == BILL and "Weighed and fair" in th[0]["text"]
    # a note on its own (B3), then the next session's digest has all of it
    assert server.act(cfg, "read_note", {"game": "_example", "ref": "place:millstone", "text": "The mill should sound like a ledger."})["ok"]
    dg = away.digest(a.root, OPUS)
    kinds = {s["kind"]: s for s in dg["sections"]}
    assert {"edit", "approve", "flag", "note"} <= set(kinds)
    assert "~~river town~~" not in kinds["edit"]["entries"][0]["diff"] and "**crosses the bridge**" in kinds["edit"]["entries"][0]["diff"]
    assert any("Weighed and fair" in e.get("note", "") for e in kinds["note"]["entries"])
    assert "Lines and fields rewritten" in away.markdown(dg)


def test_approving_a_run_of_lines_with_the_keyboard(w):
    cfg, a, _ = w
    # a town with a dozen lines (the example's are few): add them through the safe path, then approve each in turn
    rel = "data/dialogue/harbor_keeper.json"
    d = json.loads((a.root / rel).read_text(encoding="utf-8"))
    d["lines"] += [{"who": "Net-mender", "text": f"Knot {i}: the tide keeps its own ledger.", "era": "after", "status": "draft"} for i in range(12)]
    (a.root / rel).write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    p = readthrough.page(a, "harbor_hollow", "after")
    h = p["hashes"][rel]
    for l in p["lines"]:
        r = server.act(cfg, "read_mark", {"game": "_example", "ref": l["ref"], "status": "approved", "hash": h})
        assert r["ok"], r
        h = r["hash"] or h
    p2 = readthrough.page(a, "harbor_hollow", "after")
    assert p2["counts"]["approved"] == 13 and p2["counts"]["draft"] == 0
    assert sum(1 for e in journal.read(a.root) if e["kind"] == "approve" and e["obj"].endswith("/status")) == 13


def test_two_writers_locks_and_who_may_approve(w):
    cfg, a, _ = w
    p = readthrough.page(a, "harbor_hollow")
    l = p["lines"][1]
    stale = p["hashes"][l["file"]]
    raw = (a.root / l["file"]).read_text(encoding="utf-8").replace("Oil's gone.", "Oil's all gone.")
    (a.root / l["file"]).write_text(raw, encoding="utf-8")                       # a session changed it meanwhile
    r = server.act(cfg, "read_edit", {"game": "_example", "ref": l["ref"], "field": "text", "value": "x", "hash": stale})
    assert not r["ok"] and r["conflict"]["theirs"] == {l["pointer"] + "/text": raw and json.loads(raw)["lines"][1]["text"]}
    r = server.act(cfg, "read_edit", {"game": "_example", "ref": l["ref"], "field": "text", "value": "Keep mine.", "hash": r["conflict"]["current_hash"]})
    assert r["ok"]
    lock = readthrough.page(a, "ember_crossing")["lines"][0]
    r = server.act(cfg, "read_edit", {"game": "_example", "ref": lock["ref"], "field": "text", "value": "new words"})
    assert not r["ok"] and "locked" in r["message"]
    assert approval.mark(a, l["file"], l["pointer"], "approved", OPUS)["ok"] is False     # approving is a person's call
    # an approved line someone else edits becomes a proposal for its owner
    settings.set_identity("Wren")
    first = readthrough.page(a, "harbor_hollow")["lines"][0]
    r = server.act(cfg, "read_edit", {"game": "_example", "ref": first["ref"], "field": "text", "value": "Changed by Wren."})
    assert r["ok"] and r.get("proposed")


def test_the_sameness_meter_and_side_by_side(w):
    _cfg, a, _ = w
    rel = "data/dialogue/harbor_keeper.json"
    d = json.loads((a.root / rel).read_text(encoding="utf-8"))
    d["lines"].append({"who": "Gull-seller", "text": "Hello, traveller. Welcome to our town.", "era": "before", "status": "draft"})
    d["lines"].append({"who": "Gull-seller", "text": "Mind the fair tide, the harbor never forgets a face.", "era": "before", "status": "draft"})
    (a.root / rel).write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    p = readthrough.page(a, "harbor_hollow", "before")
    by = {l["text"][:5]: l["meter"] for l in p["lines"]}
    assert "also in millstone" in by["Hello"]
    assert by["Mind "] == []                                                     # 'harbor' and the greeting's words belong here
    assert p["meter"]["greeting"] == "Fair tide." and "Lighthouse Keeper" not in p["meter"]["never_greet"]
    m = readthrough.page(a, "millstone", "before")
    assert any("also in harbor_hollow" in x for l in m["lines"] for x in l["meter"])


def test_notes_thread_reply_and_resolve(w):
    _cfg, a, _ = w
    n = notes.add(a.root, "music:battle", BILL, "Drums only, no strings.", label="the battle slot")
    notes.add(a.root, "music:battle", OPUS, "Understood — noted on the board.", reply_to=n["id"])
    t = notes.threads(a.root, "music:battle")
    assert len(t) == 1 and t[0]["open"] and [r["who"] for r in t[0]["replies"]] == [OPUS]
    assert notes.counts(a.root) == {"music:battle": 1}
    notes.add(a.root, "music:battle", BILL, "", resolves=n["id"])
    assert not notes.threads(a.root, "music:battle")[0]["open"] and notes.counts(a.root) == {}
    with pytest.raises(ValueError):
        notes.add(a.root, "x", BILL, "hi", tag="shout")
    with pytest.raises(ValueError):
        notes.add(a.root, "x", "", "hi")


def test_the_screen_and_its_routes(w):
    cfg, a, _ = w
    srv = server.make_server(cfg, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        port = srv.server_address[1]
        ts = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/suite/towns?id=_example").read())
        assert [t["id"] for t in ts["towns"]][:1] == ["ember_crossing"]
        pg = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/suite/read?id=_example&place=harbor_hollow&era=after").read())
        assert pg["counts"]["lines"] == 1 and pg["era"] == "after"
        nt = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/suite/notes?id=_example").read())
        assert nt == {"threads": []}
        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode("utf-8")
        assert "story/read" in areas.addresses() and "function loadRead" in html and "rtFlag" in html
    finally:
        srv.shutdown()
