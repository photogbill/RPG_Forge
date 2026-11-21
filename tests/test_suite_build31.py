"""BUILD 31: Characters -> Behaviours — the party off duty as cards, a preview for a place in an era, coverage of where
somebody has too little to do, and approving that is the owner's alone (signed, safely saved, journalled). Runs on a
throwaway copy of the example game with a small set of decks written by the test; nothing real is touched."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.suite import areas, behaviours, journal, server

from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

BILL, OPUS = "Bill", "Claude Opus"

DECKS = {
    "wren": {"id": "wren", "character": "wren", "status": "draft", "behaviours": [
        {"id": "wren_net", "status": "draft", "when": {"place": ["inn", "square"]}, "weight": 2, "do": {"go": "wander", "bark": "Mends a net."}},
        {"id": "wren_song", "status": "approved", "when": {"present": ["stage"]}, "do": {"go": "stage", "sing": {"with": "miller", "track": "t1"}},
         "reactions": [{"who": "miller", "line": "Again!"}]},
        {"id": "wren_kids", "status": "draft", "when": {"present": ["kids"]}, "do": {"go": "near:kids", "bark": "Teaches knots."}, "npc_reaction": "laugh"},
    ]},
    "miller": {"id": "miller", "character": "miller", "status": "draft", "behaviours": [
        {"id": "miller_bread", "status": "draft", "when": {"place": ["inn"], "era": ["after"]}, "do": {"go": "near:bar", "bark": "Asks about the bread."}},
    ]},
}
PLACES = [{"id": "harbour_inn", "name": "The harbour inn", "town": "harbour", "place": "inn", "present": ["kids"]},
          {"id": "harbour_square", "name": "The square", "town": "harbour", "place": "square", "present": []}]


@pytest.fixture
def decks(world):  # noqa: F811
    cfg, a, tmp = world
    d = Path(a.root) / "data" / "behaviours"
    d.mkdir(parents=True, exist_ok=True)
    for k, v in DECKS.items():
        (d / f"{k}.json").write_text(json.dumps(v, indent=2), encoding="utf-8")
    (d / "_npc_reactions.json").write_text('{"id": "_npc_reactions", "reactions": {}}', encoding="utf-8")
    a.behaviours_places = lambda: PLACES
    a.behaviours_eras = lambda: ["war", "after"]
    return cfg, a, tmp


def test_the_tab_is_in_characters_and_the_page_is_wired(decks):
    cfg, a, tmp = decks
    ch = next(x for x in areas.AREAS if x["id"] == "characters")
    ids = [t["id"] for t in ch["tabs"]]
    assert ids[:2] == ["profiles", "characters"] and "behaviours" in ids          # Profiles stays first (BUILD 42)
    t = next(t for t in ch["tabs"] if t["id"] == "behaviours")
    assert t["screen"] == "behaviours" and "behaviours" in t["needs"] and t["holds"]
    shell = (REPO / "forge" / "suite" / "shell.html").read_text(encoding="utf-8")
    assert "v-behaviours" in shell and "/suite/behaviours.js" in shell and "loadBehaviours" in shell
    js = (REPO / "forge" / "suite" / "behaviours.js").read_text(encoding="utf-8")
    for w in ("behaviour_approve", "behaviour_unapprove", "behaviourpreview", "Approve"):
        assert w in js, w
    assert "email" not in js.lower() and "inbox" not in js.lower()                 # cards, not a list of messages
    srv = (REPO / "forge" / "suite" / "server.py").read_text(encoding="utf-8")
    assert "/api/suite/behaviours" in srv and "behaviour_" in srv
    assert areas.needs(cfg, "_example")["characters/behaviours"]["met"] is True


def test_forge_names_no_game(decks):
    src = (REPO / "forge" / "suite" / "behaviours.py").read_text(encoding="utf-8") + (REPO / "forge" / "suite" / "behaviours.js").read_text(encoding="utf-8")
    for word in ("Sarah", "Valkyrie", "Turing", "Chloe", "Aphrodite", "Linden", "Bill's"):
        assert word not in src, word


def test_board_cards_and_coverage(decks):
    cfg, a, tmp = decks
    b = behaviours.board(a)
    assert b["counts"] == {"decks": 2, "behaviours": 4, "approved": 1}
    assert {d["character"] for d in b["decks"]} == {"wren", "miller"}          # the "_" file is not a deck
    w = next(d for d in b["decks"] if d["character"] == "wren")
    assert next(x for x in w["behaviours"] if x["id"] == "wren_song")["what"].startswith("takes the stage")
    assert b["coverage"]["wren"]["harbour_inn|after"] == 2                     # the net and the knots (children there)
    assert b["coverage"]["miller"]["harbour_inn|war"] == 0
    thin = {t["character"] for t in b["thin"]}
    assert thin == {"wren", "miller"}                                           # under three somewhere: shown in warning colour


def test_preview_by_place_and_era(decks):
    cfg, a, tmp = decks
    p = behaviours.preview(a, "harbour_inn", "after")
    m = {x["character"]: x for x in p["members"]}
    assert [b["id"] for b in m["wren"]["could"]] == ["wren_net", "wren_kids"] and m["miller"]["count"] == 1
    assert {x["character"]: x["count"] for x in behaviours.preview(a, "harbour_inn", "war")["members"]}["miller"] == 0
    with pytest.raises(behaviours.BehaviourRefused):
        behaviours.preview(a, "nowhere", "after")
    v = server.behaviours_view(cfg, "behaviourpreview", {"id": ["_example"], "place": ["harbour_square"], "era": ["war"]})
    assert v["place"]["place"] == "square"


def test_approving_is_the_owners(decks):
    cfg, a, tmp = decks
    with pytest.raises(behaviours.BehaviourRefused):
        behaviours.approve(a, "wren", "wren_net", OPUS)                         # a session proposes; it never approves
    r = behaviours.approve(a, "wren", "wren_net", BILL)
    assert r["changed"] and r["status"] == "approved"
    d = json.loads((Path(a.root) / "data" / "behaviours" / "wren.json").read_text(encoding="utf-8"))
    row = next(x for x in d["behaviours"] if x["id"] == "wren_net")
    assert row["status"] == "approved" and row["approved_by"] == BILL
    assert behaviours.approve(a, "wren", "wren_net", BILL)["changed"] is False
    lines = [json.loads(l) for f in sorted(journal.folder(a.root).glob("*.jsonl")) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(l.get("kind") == "edit" and "wren_net" in l.get("obj", "") and l.get("after") == "approved" for l in lines)
    r = server.act_behaviours(cfg, "behaviour_unapprove", {"game": "_example", "deck": "wren", "behaviour": "wren_net"}, BILL)
    assert r["ok"] and r["status"] == "draft"
    r = server.act_behaviours(cfg, "behaviour_approve", {"game": "_example", "deck": "wren", "behaviour": "nope"}, BILL)
    assert not r["ok"] and "nope" in r["message"]


def test_a_game_without_decks_says_what_it_needs(world):  # noqa: F811
    cfg, a, tmp = world
    v = server.behaviours_view(cfg, "behaviours", {"id": ["_example"]})
    assert v.get("missing") and "behaviours" in v["error"]
    assert areas.needs(cfg, "_example")["characters/behaviours"]["met"] is False
