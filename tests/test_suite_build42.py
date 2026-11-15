"""BUILD 42: Characters -> Profiles — the cast as editable pages drawn from the game's own schema, a board of what's
missing, the five states and who may set them, safe saving and undo, the fill that never overwrites a person, 'differs',
and 'find it in the songs'. Runs on a throwaway copy of the example game; nothing real is touched."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.suite import areas, journal, profiles, rulings, server, settings

from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

BILL, OPUS = "Bill", "Claude Opus"


def _p(a, pid):
    return json.loads((Path(a.root) / "profiles" / f"{pid}.json").read_text(encoding="utf-8"))


def test_the_tab_is_first_in_characters_and_the_page_is_wired(world):  # noqa: F811
    cfg, a, tmp = world
    ch = next(x for x in areas.AREAS if x["id"] == "characters")
    assert [t["id"] for t in ch["tabs"]][:2] == ["profiles", "characters"]
    t = ch["tabs"][0]
    assert t["name"] == "Profiles" and t["screen"] == "profiles" and "profiles" in t["needs"] and t["holds"]
    shell = (REPO / "forge" / "suite" / "shell.html").read_text(encoding="utf-8")
    assert "v-profiles" in shell and "/suite/profiles.js" in shell and "loadProfiles" in shell
    js = (REPO / "forge" / "suite" / "profiles.js").read_text(encoding="utf-8")
    for fn in ("profile_set", "profile_entry_add", "profile_entry_confirm", "profile_none", "profile_undo", "profile_q_mail",
               "profile_order", "profile_fill", "Find it in the songs", "Add a character", "keepalive", "differs"):
        assert fn in js, fn
    assert "email" not in js.lower() and "inbox" not in js.lower()        # a page of cards and a table, not a list of messages
    srv = (REPO / "forge" / "suite" / "server.py").read_text(encoding="utf-8")
    assert "/api/suite/profiles" in srv and "/api/suite/profilesongs" in srv
    need = areas.needs(cfg, "_example")["characters/profiles"]
    assert need["met"] is True


def test_forge_names_no_game_and_the_page_comes_from_the_schema(world):  # noqa: F811
    cfg, a, tmp = world
    src = (REPO / "forge" / "suite" / "profiles.py").read_text(encoding="utf-8") + (REPO / "forge" / "suite" / "profiles.js").read_text(encoding="utf-8")
    for word in ("Sarah", "Valkyrie", "Turing", "Chloe", "Mont Ross", "Bill's"):
        assert word not in src, word
    b = profiles.board(a)
    assert [r["id"] for r in b["rows"]] == ["close", "range", "other"] and b["section"] == "arms"
    assert b["schema"]["states"]["owner"]["label"] == "Bill's word"
    assert {l["id"] for l in b["lines"]} == {"wren", "miller"}
    w = next(l for l in b["lines"] if l["id"] == "wren")
    assert w["cells"]["close"]["state"] == "songs" and w["cells"]["close"]["text"] == "boat hook"
    assert w["cells"]["range"]["state"] == "open" and "open" in w["flags"] and "no:range" in w["flags"]
    # a different schema draws a different page, with no forge change
    sp = Path(a.root) / "profiles" / "_schema.json"
    s = json.loads(sp.read_text(encoding="utf-8"))
    s["sections"][1]["rows"] = [{"id": "spells", "label": "Spells"}]
    sp.write_text(json.dumps(s), encoding="utf-8")
    b2 = profiles.board(a)
    assert [r["id"] for r in b2["rows"]] == ["spells"] and b2["lines"][0]["cells"]["spells"]["state"] == "open"


def test_a_persons_typing_is_his_word_at_once_and_goes_into_the_book(world):  # noqa: F811
    cfg, a, tmp = world
    settings.set_identity(BILL)
    r = server.act(cfg, "profile_entry_add", {"game": "_example", "p": "miller", "section": "arms", "row": "close",
                                              "entry": {"what": "a millstone pick", "state": "proposed"}})
    assert r["ok"], r
    e = _p(a, "miller")["arms"]["close"]["entries"][0]
    assert e["state"] == "owner" and e["by"] == BILL and e["source"]["date"] and e["source"]["ruling"].startswith("r:")
    book = rulings._recorded_raw(Path(a.root))
    assert any("The Miller" in x["text"] and "millstone pick" in x["text"] and x["by"] == BILL for x in book)
    # the journal has it as an edit (so the digest, "while you were away", has it)
    lines = journal.read(Path(a.root))
    assert any(l["kind"] == "edit" and l["obj"].startswith("profiles/miller.json") and l["who"] == BILL for l in lines)
    from forge.suite import away
    d = away.digest(Path(a.root), OPUS) if hasattr(away, "digest") else None
    if d is not None:
        assert "miller" in json.dumps(d, ensure_ascii=False)


def test_a_session_cannot_set_the_owners_word_or_none_on_its_own(world):  # noqa: F811
    cfg, a, tmp = world
    root = Path(a.root)
    with pytest.raises(profiles.ProfileRefused):
        profiles.add_entry(a, "miller", "arms", "range", {"what": "a sling", "state": "owner"}, OPUS)
    with pytest.raises(profiles.ProfileRefused):
        profiles.set_none(a, "miller", "arms", "range", "he never needs one", OPUS)
    with pytest.raises(profiles.ProfileRefused):                      # a ruling an assistant made is no ruling
        e = rulings.record(root, OPUS, "x", by=BILL, source="in chat")
        bad = dict(e, id="r:fake", by=OPUS)
        rulings._append(root, bad)
        profiles.add_entry(a, "miller", "arms", "range", {"what": "a sling", "state": "owner", "source": {"ruling": "r:fake"}}, OPUS)
    # a session may write down his ruling, by its id
    rr = rulings.record(root, OPUS, "The Miller carries a sling.", by=BILL, source="in chat, 2026-11-14: \"the miller has a sling\"")
    r = profiles.add_entry(a, "miller", "arms", "range", {"what": "a sling", "state": "owner", "source": {"ruling": rr["id"]}}, OPUS)
    assert r["ok"] and r["entry"]["state"] == "owner"
    # without a state a session's entry is a proposal; "in the songs" needs the quote
    r = profiles.add_entry(a, "miller", "arms", "other", {"what": "weighs a lie"}, OPUS)
    assert r["entry"]["state"] == "proposed"
    with pytest.raises(profiles.ProfileRefused):
        profiles.add_entry(a, "miller", "arms", "other", {"what": "x", "state": "songs"}, OPUS)
    # and it never edits or takes off a person's entry
    settings.set_identity(BILL)
    profiles.add_entry(a, "wren", "arms", "range", {"what": "a sling"}, BILL)
    eid = _p(a, "wren")["arms"]["range"]["entries"][0]["id"]
    with pytest.raises(profiles.ProfileRefused):
        profiles.edit_entry(a, "wren", "arms", "range", eid, {"what": "a slingshot"}, OPUS)
    with pytest.raises(profiles.ProfileRefused):
        profiles.remove_entry(a, "wren", "arms", "range", eid, OPUS)
    # the checker refuses a file that claims his word without him (someone editing the JSON by hand)
    s = profiles.load_schema(a)
    p = _p(a, "miller")
    p["arms"]["close"]["entries"] = [{"id": "x", "what": "axe", "state": "owner", "by": OPUS, "source": {}}]
    assert profiles.check(s, p, {}) and "owner" in profiles.check(s, p, {})[0]


def test_none_on_purpose_needs_a_reason_and_a_person(world):  # noqa: F811
    cfg, a, tmp = world
    with pytest.raises(profiles.ProfileRefused):
        profiles.set_none(a, "miller", "arms", "range", "  ", BILL)
    r = profiles.set_none(a, "miller", "arms", "range", "a future game's problem", BILL)
    assert r["ok"]
    b = profiles.board(a)
    m = next(l for l in b["lines"] if l["id"] == "miller")
    assert m["cells"]["range"]["state"] == "none" and "future game" in m["cells"]["range"]["text"] and "no:range" in m["flags"]
    with pytest.raises(profiles.ProfileRefused):
        profiles.clear_none(a, "miller", "arms", "range", OPUS)
    assert profiles.clear_none(a, "miller", "arms", "range", BILL)["ok"]


def test_safe_saving_conflicts_and_undo(world):  # noqa: F811
    cfg, a, tmp = world
    pg = profiles.page(a, "wren")
    h = pg["hash"]
    assert profiles.set_field(a, "wren", "notes", "notes", "first thought", BILL, h)["ok"]
    with pytest.raises(profiles.ProfileRefused):                      # an old page can't overwrite a newer one
        profiles.set_field(a, "wren", "notes", "notes", "stale", BILL, h)
    profiles.set_field(a, "wren", "notes", "notes", "second thought", BILL)
    profiles.set_field(a, "wren", "who", "other_names", "the Toll-Singer; Wren of the Crossing", BILL)
    assert _p(a, "wren")["who"]["other_names"] == ["the Toll-Singer", "Wren of the Crossing"]
    assert list((Path(a.root) / "_workbench_backups").rglob("wren.*.json"))           # every save keeps the old version
    assert profiles.page(a, "wren")["undo"]["what"].startswith("Other names")
    profiles.undo(a, "wren", BILL)
    assert _p(a, "wren")["who"]["other_names"] == []
    profiles.undo(a, "wren", BILL)                                     # undo again walks back one more
    assert _p(a, "wren")["notes"]["notes"] == "first thought"
    profiles.undo(a, "wren", BILL)
    assert _p(a, "wren")["notes"]["notes"] == ""
    # an assistant can't undo a person's change; a hand edit outside the suite stops undo
    profiles.set_field(a, "wren", "notes", "notes", "mine", BILL)
    with pytest.raises(profiles.ProfileRefused):
        profiles.undo(a, "wren", OPUS)
    f = Path(a.root) / "profiles" / "wren.json"
    f.write_text(f.read_text(encoding="utf-8").replace("mine", "changed in Notepad"), encoding="utf-8")
    with pytest.raises(profiles.ProfileRefused):
        profiles.undo(a, "wren", BILL)
    # a broken value is refused by the checker and nothing is written
    with pytest.raises(profiles.ProfileRefused):
        profiles.set_field(a, "wren", "who", "kind", "dragon", BILL)
    assert _p(a, "wren")["who"]["kind"] == "human"


def test_add_a_character_asks_only_for_a_name(world):  # noqa: F811
    cfg, a, tmp = world
    settings.set_identity(BILL)
    r = server.act(cfg, "profile_add", {"game": "_example", "name": "Lighthouse Keeper"})
    assert r["ok"] and r["id"] == "lighthouse_keeper"
    p = _p(a, "lighthouse_keeper")
    assert p["who"]["name"] == "Lighthouse Keeper" and set(p["arms"]) == {"close", "range", "other"}
    assert not server.act(cfg, "profile_add", {"game": "_example", "name": ""})["ok"]
    assert server.act(cfg, "profile_add", {"game": "_example", "name": "Lighthouse Keeper"})["id"] == "lighthouse_keeper_2"
    assert not server.act_profiles(cfg, "profile_add", {"game": "_example", "name": "X"}, None)["ok"]          # signed, always


def test_the_fill_is_idempotent_and_never_overwrites_a_person(world):  # noqa: F811
    cfg, a, tmp = world
    root = Path(a.root)
    rr = rulings.record(root, OPUS, "Wren has no ranged weapon: the river is her range.", by=BILL, source="in chat")
    seeds = [{"id": "wren", "who": {"name": "Wren", "other_names": ["the Toll-Singer"], "first": "Ember Crossing", "line": "seeded"},
              "arms": {"range": {"none": {"reason": "the river is her range", "source": {"ruling": rr["id"]}}},
                       "other": {"entries": [{"what": "sings the toll", "state": "songs",
                                              "source": {"kind": "lyric", "text": "Coin for the crossing, coin for the day", "song": "The Toll"}},
                                             {"what": "a guess", "state": "owner", "source": {}}]}},
              "questions": ["What does she do with the coins?"]},
             {"id": "ferryman", "who": {"name": "The Ferryman", "kind": "human"}}]
    profiles.set_field(a, "wren", "who", "first", "the Crossing (Bill)", BILL)
    r1 = profiles.fill(a, OPUS, seeds)
    assert r1["made"] == ["ferryman"] and r1["changed"] == ["wren"] and r1["kept_for_person"] >= 1
    w = _p(a, "wren")
    assert w["who"]["first"] == "the Crossing (Bill)" and w["who"]["other_names"] == ["the Toll-Singer"]   # his field kept, an empty one filled
    assert w["who"]["line"].startswith("The toll-singer")          # a field already written (by anyone) is not replaced by a seed
    assert w["arms"]["range"]["none"]["by"] == BILL and w["arms"]["range"]["none"]["recorded_by"] == OPUS
    oth = w["arms"]["other"]["entries"]
    assert oth[0]["state"] == "songs" and oth[1]["state"] == "proposed"       # "owner" with no ruling is only a proposal
    assert any("cites no ruling" in s for s in r1["skipped"])
    assert w["questions"][0]["text"].startswith("What does she do")
    before = {p.name: p.read_bytes() for p in (root / "profiles").glob("*.json")}
    r2 = profiles.fill(a, OPUS, seeds)                                        # again: nothing changes
    assert r2["made"] == [] and r2["changed"] == [] and r2["entries_added"] == 0
    assert before == {p.name: p.read_bytes() for p in (root / "profiles").glob("*.json")}
    # a person's 'none' is never overwritten; the fill never edits a person's entry
    profiles.set_none(a, "ferryman", "arms", "close", "he only poles the boat", BILL)
    profiles.fill(a, OPUS, [{"id": "ferryman", "arms": {"close": {"entries": [{"what": "an oar", "state": "proposed"}]}}}])
    assert _p(a, "ferryman")["arms"]["close"]["entries"] == []
    # the button runs the adapter's own seeds
    settings.set_identity(BILL)
    r = server.act(cfg, "profile_fill", {"game": "_example"})
    assert r["ok"] and "new page" in r["message"]


def test_differs_from_the_games_data_says_so_and_changes_nothing(world):  # noqa: F811
    cfg, a, tmp = world
    root = Path(a.root)
    arms_before = (root / "data" / "arms.json").read_bytes()
    w = profiles.page(a, "wren")
    assert w["differs"] == []                                   # the boat hook is linked by its game id
    m = profiles.page(a, "miller")
    assert m["differs"] and "flail" in m["differs"][0] and "nothing yet" in m["differs"][0]
    b = profiles.board(a)
    assert "differs" in next(l for l in b["lines"] if l["id"] == "miller")["flags"]
    assert "differs" not in next(l for l in b["lines"] if l["id"] == "wren")["flags"]
    profiles.set_none(a, "miller", "arms", "close", "he never fights", BILL)
    assert "none, on purpose" in profiles.page(a, "miller")["differs"][0]
    assert (root / "data" / "arms.json").read_bytes() == arms_before


def test_find_it_in_the_songs_quotes_lines_near_weapon_words(world):  # noqa: F811
    cfg, a, tmp = world
    r = profiles.find_in_songs(a, "wren")
    lines = [h["line"] for h in r["hits"]]
    assert "I keep a boat hook for the ones who will not pay" in lines
    assert r["words"][:2] == ["hook", "knife"]                          # the word list is the game's own file
    m = profiles.find_in_songs(a, "miller")
    assert any("knife the Miller keeps" in h["line"] and h["why"] == "named in the line" for h in m["hits"])
    assert any("sling" in h["line"] for h in m["hits"])                # sung by him
    # one click puts the line in as the source, state "in the songs" — even for a person
    h = next(h for h in m["hits"] if "knife" in h["line"])
    rr = profiles.add_entry(a, "miller", "arms", "close", {"what": "knife", "state": "songs",
                                                           "source": {"kind": "lyric", "text": h["line"], "song": h["song"]}}, BILL)
    assert rr["entry"]["state"] == "songs" and rr["entry"]["source"]["text"] == h["line"]
    # the lyric file itself is never written
    assert "knife the Miller keeps" in (Path(a.root) / "data" / "lyrics.json").read_text(encoding="utf-8")


def test_questions_go_out_as_mail_and_confirmed_weapons_as_work_orders(world):  # noqa: F811
    cfg, a, tmp = world
    root = Path(a.root)
    q = profiles.add_question(a, "miller", "Does the Miller own a knife, or only the song?", OPUS)["question"]
    r = profiles.mail_question(a, "miller", q["id"], OPUS)
    assert r["ok"] and r["letter"]
    letters = list((root / "mail").rglob(f"{r['letter']}.md"))
    assert letters and "Does the Miller own a knife" in letters[0].read_text(encoding="utf-8")
    assert _p(a, "miller")["questions"][0]["mailed"]["to"] == "Bill"
    profiles.add_entry(a, "miller", "arms", "close", {"what": "millstone pick"}, BILL)
    eid = _p(a, "miller")["arms"]["close"]["entries"][0]["id"]
    o = profiles.work_order(a, "miller", "arms", "close", eid, BILL)
    assert o["ok"] and "millstone pick" in o["order"]["title"] and o["order"]["for"] == "Claude"
    pe = profiles.add_entry(a, "miller", "arms", "other", {"what": "a guess"}, OPUS)["entry"]
    with pytest.raises(profiles.ProfileRefused):                        # only a confirmed entry becomes an order
        profiles.work_order(a, "miller", "arms", "other", pe["id"], OPUS)
    profiles.confirm_entry(a, "miller", "arms", "other", pe["id"], BILL)
    assert _p(a, "miller")["arms"]["other"]["entries"][0]["state"] == "owner"
    with pytest.raises(profiles.ProfileRefused):
        profiles.confirm_entry(a, "miller", "arms", "other", pe["id"], OPUS)
    assert not list((root / "project").glob("**/*")) if (root / "project").exists() else True    # nothing in the game's data


def test_the_suite_endpoints_answer(world):  # noqa: F811
    cfg, a, tmp = world
    v = server.profiles_view(cfg, "profiles", {"id": ["_example"]})
    assert v["lines"] and v["rows"]
    v = server.profiles_view(cfg, "profile", {"id": ["_example"], "p": ["wren"]})
    assert v["name"] == "Wren" and v["voice"]["text"] and v["hash"]
    v = server.profiles_view(cfg, "profilesongs", {"id": ["_example"], "p": ["wren"]})
    assert v["hits"]
    assert "error" in server.profiles_view(cfg, "profile", {"id": ["_example"], "p": ["nobody"]})
    (Path(a.root) / "profiles" / "_schema.json").rename(Path(a.root) / "profiles" / "_schema.off")
    v = server.profiles_view(cfg, "profiles", {"id": ["_example"]})
    assert v["missing"] and v["can_fill"]
    assert areas.needs(cfg, "_example")["characters/profiles"]["met"] is False
