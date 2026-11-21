"""Song review (2026-11-19) — William's Suno rules, voice locks, not generic, complex enough; never a word changed.

✦ William, 2026-11-19 14:57: "build an automatic music lyric review tool into forge … ensures that its complex and up to the
quality expected of this game."
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from forge import song_review as sr

GOOD_STYLE = ("1960s Italian film-comedy lounge bossa nova, the tune carried by a dry mallet vibraphone with a raised-eyebrow "
              "swagger, breathy alto flute answering every phrase, nylon-string guitar comping, plucked upright bass, brushed "
              "snare, typewriter keys as percussion with a carriage bell on the turnarounds, starts with the typewriter alone, "
              "the band slides in, lifts a key for the last chorus and ends on the bell, close dry studio sound, wry, 104 BPM, "
              "B minor, Instrumental")
GOOD_TAGS = ("[Instrumental]\n\n[Intro - typewriter keys alone]\n\n[Verse - bass and nylon guitar slide in, the vibraphone "
             "states the tune]\n\n[Chorus - alto flute answers the vibraphone]\n\n[Verse - vibraphone again, flute trills]\n\n"
             "[Solo - alto flute over typewriter and bass]\n\n[Chorus - up a key, both leads together]\n\n[Outro - typewriter "
             "alone, one last carriage bell]\n\n[End]")
VOCAL_STYLE = ("Virtuoso Operatic Soprano, female vocals only, intimate piano ballad opening, cello and harp, orchestral strings "
               "swell into hard rock with heavy guitars and pounding drums, close warm studio sound, builds then falls back to "
               "piano alone, 70 BPM rising to 140, D minor")
VOCAL_LYRICS = """[Verse 1: Virtuoso operatic soprano, intimate]
The rain wrote numbers on the window glass
I counted every drop the way you taught
A kettle cooling where you left it last
Your coat still holding all the warmth it caught

[Pre-Chorus: soprano rising, strings enter]
The hallway light is buzzing like a hive
I keep the porch lamp burning past midnight

[Chorus: full soprano over heavy guitars]
I built the house around the room you left
I nailed the shutters down against the storm
I kept your boots beside the door, the left
Still muddy from the field where we were born

[Verse 2: soprano, quieter, piano and cello]
The orchard dropped its apples on the road
The tractor rusts beneath the sycamore
I learned the gate's complaint, the creek's slow code
The way the floorboard groans beside the door

[Bridge: soprano alone, then the band crashes in]
Tell me where the river bends tonight
Tell me if the ferry still runs late

[Outro: piano alone, soprano whispered]
The kettle's cold. I'll warm it up again."""


def _profiles(tmp_path, voices):
    d = tmp_path / "styles"
    d.mkdir()
    for name, words in voices.items():
        (d / f"{name.lower()}.json").write_text(json.dumps({"id": name.lower(), "name": name,
                                                             "voice": {"delivery": {"value": words}}}), encoding="utf-8")
    return sr.load_profiles(d)


def checks(result, level=None):
    return [f["check"] for f in result["findings"] if level is None or f["level"] == level]


# ------------------------------------------------------------------------------------------------ instrumentals
def test_a_specific_instrumental_is_ready():
    r = sr.review(sr.song("Carriage Return", GOOD_STYLE, GOOD_TAGS, instrumental=True))
    assert r["verdict"] == "ready", r["findings"]
    assert r["score"] >= 80


def test_words_in_an_instrumental_s_lyrics_box_fail():
    r = sr.review(sr.song("Night Shift", GOOD_STYLE, GOOD_TAGS + "\nThe night is long and cold", instrumental=True))
    assert r["verdict"] == "fails" and "words" in checks(r, "fail")


def test_a_generic_thin_style_needs_work():
    r = sr.review(sr.song("Battle", "epic cinematic emotional powerful music, intense, dramatic", "[Intro]\n[Verse]\n[End]",
                          instrumental=True))
    assert r["verdict"] in ("needs work", "fails")
    assert {"style length", "instruments", "generic", "structure"} <= set(checks(r))


def test_an_over_long_style_box_fails():
    r = sr.review(sr.song("Long", GOOD_STYLE + ", " + "x" * 1000, GOOD_TAGS, instrumental=True))
    assert "style length" in checks(r, "fail")


def test_artist_names_fail_but_gilmour_and_queen_esque_are_allowed():
    r = sr.review(sr.song("A", GOOD_STYLE + ", in the style of Hans Zimmer", GOOD_TAGS, instrumental=True))
    assert "artist name" in checks(r)
    ok = sr.review(sr.song("B", GOOD_STYLE + ", soaring Gilmour Guitar, Queen-esque stacked harmonies", GOOD_TAGS, instrumental=True))
    assert "artist name" not in checks(ok)


# ------------------------------------------------------------------------------------------------ songs with words
def test_a_rich_song_with_its_singer_s_voice_is_ready(tmp_path):
    prof = _profiles(tmp_path, {"Sarah": ["Virtuoso Operatic Soprano", "female vocals only"]})
    r = sr.review(sr.song("Room You Left", VOCAL_STYLE, VOCAL_LYRICS, instrumental=False, singers=["Sarah"]), prof)
    assert r["verdict"] == "ready", r["findings"]
    assert r["measures"]["mattr"] >= 0.8 and not r["measures"]["cliches"]


def test_a_singer_with_no_voice_on_file_is_never_given_one(tmp_path):
    prof = _profiles(tmp_path, {"Sarah": ["soprano"]})
    r = sr.review(sr.song("New Song", VOCAL_STYLE, VOCAL_LYRICS, instrumental=False, singers=["Tommy"]), prof,
                  {"canon_hint": "the master write-up"})
    f = next(x for x in r["findings"] if x["check"] == "voice lock")
    assert f["level"] == "fail" and "canon" in f["message"] and "ask William" in f["message"]


def test_the_wrong_voice_for_the_singer_fails(tmp_path):
    prof = _profiles(tmp_path, {"Valkyrie": ["Heldentenor", "male vocals only"]})
    style = VOCAL_STYLE.replace("Virtuoso Operatic Soprano, female vocals only", "female vocals, bright pop soprano")
    r = sr.review(sr.song("Wrong", style, VOCAL_LYRICS.replace("soprano", "voice"), instrumental=False, singers=["Valkyrie"]), prof)
    assert "voice lock" in checks(r, "fail")


def test_a_no_in_the_style_never_counts_as_the_voice(tmp_path):
    prof = _profiles(tmp_path, {"Bill": ["gentle baritone"]})
    style = VOCAL_STYLE.replace("Virtuoso Operatic Soprano, female vocals only", "tenor lead, no baritone")
    r = sr.review(sr.song("Gentle", style, VOCAL_LYRICS.replace("soprano", "tenor"), instrumental=False, singers=["Bill"]), prof)
    assert "voice lock" in checks(r)


def test_suno_rules_in_the_words():
    lyr = VOCAL_LYRICS + "\n[Male vocal: deep baritone]\nI SAID NO\n[Female vocal: soprano]\nSarah: come home now"
    r = sr.review(sr.song("Rules", VOCAL_STYLE, lyr, instrumental=False))
    got = set(checks(r))
    assert {"single voice", "all caps", "dialogue"} <= got
    assert "single voice" in checks(r, "fail")


def test_acronyms_are_not_all_caps_and_cliches_are_named():
    lyr = VOCAL_LYRICS + "\nThe MEHA trucks are rolling past the AI line\nWe will rise, we will rise, set me free"
    r = sr.review(sr.song("Words", VOCAL_STYLE, lyr, instrumental=False))
    assert "all caps" not in checks(r)
    assert any("set me free" in f["message"] for f in r["findings"] if f["check"] == "cliché")


def test_thin_repetitive_words_need_work():
    lyr = "[Verse]\n" + "\n".join(["my heart my soul my love forever"] * 10) + "\n[Chorus]\n" + "\n".join(["fire in my soul"] * 6)
    r = sr.review(sr.song("Thin", VOCAL_STYLE, lyr, instrumental=False))
    assert r["verdict"] != "ready"
    assert {"repetition", "imagery", "vocabulary"} & set(checks(r))


# ------------------------------------------------------------------------------------------------ across a sheet
def test_titles_never_reused_and_never_a_character_s_name(tmp_path):
    prof = _profiles(tmp_path, {"Calliope": ["mezzo-soprano"]})
    a = sr.song("The Ping", GOOD_STYLE, GOOD_TAGS, instrumental=True, source="sheet.json #1")
    b = sr.song("The Ping", GOOD_STYLE.replace("bossa nova", "surf rock"), GOOD_TAGS, instrumental=True, source="sheet.json #2")
    c = sr.song("Calliope", GOOD_STYLE, GOOD_TAGS, instrumental=True, source="x.md")
    res = sr.review_all([a, b, c], prof)
    assert res[0]["verdict"] == res[1]["verdict"] == "fails" and "title reused" in checks(res[0])
    assert "title" in checks(res[2], "fail")


def test_two_styles_too_alike_in_one_sheet_are_flagged():
    a = sr.song("One", GOOD_STYLE, GOOD_TAGS, instrumental=True, source="sheet.json #1")
    b = sr.song("Two", GOOD_STYLE, GOOD_TAGS, instrumental=True, source="sheet.json #2")
    res = sr.review_all([a, b])
    assert "variety" in checks(res[0]) and res[0]["verdict"] != "ready"


# ------------------------------------------------------------------------------------------------ reading sheets, never changing them
def test_sheets_are_read_and_never_changed(tmp_path):
    master = tmp_path / "sheet.json"
    master.write_text(json.dumps({"pieces": [
        {"number": "1", "title": "Carriage Return", "style": GOOD_STYLE, "lyrics": GOOD_TAGS, "has_words": False, "status": "to_make"},
        {"number": "2", "title": "Done Already", "style": GOOD_STYLE, "lyrics": GOOD_TAGS, "has_words": False, "status": "made_filed"},
        {"number": "3", "title": "Room You Left", "style": VOCAL_STYLE, "lyrics": VOCAL_LYRICS, "has_words": True,
         "voices": ["Sarah"], "status": "to_make"}]}), encoding="utf-8")
    md = tmp_path / "songs" / "Four_Syllables.md"
    md.parent.mkdir()
    md.write_text("# Four Syllables\n**Character:** Calliope — Synthetic Land\n\n## Suno — Style\n```\n" + VOCAL_STYLE +
                  "\n```\n\n## Suno — Lyrics\n```\n" + VOCAL_LYRICS + "\n```\n", encoding="utf-8")
    (tmp_path / "songs" / "brief.md").write_text("# A brief\nNo sheet yet.\n", encoding="utf-8")
    before = {p: hashlib.md5(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*") if p.is_file()}
    songs, skipped = sr.collect([master, tmp_path / "songs"])
    assert [s["title"] for s in songs] == ["Carriage Return", "Room You Left", "Four Syllables"]
    assert songs[1]["singers"] == ["Sarah"] and songs[2]["singers"] == ["Calliope"] and not songs[2]["instrumental"]
    assert any("Done Already" in s for s in skipped) and any("brief.md" in s for s in skipped)
    res = sr.review_all(songs)
    rep = sr.write_report(res, skipped, tmp_path / "out")
    assert "Song review" in rep.read_text(encoding="utf-8")
    after = {p: hashlib.md5(p.read_bytes()).hexdigest() for p in before}
    assert before == after                                   # not a word of a sheet changed


def test_the_gate():
    assert sr.ready({"verdict": "ready"}) and not sr.ready({"verdict": "needs work"}) and not sr.ready({"verdict": "fails"})


def test_the_connector_reviews_a_draft(tmp_path):
    from forge.mcpserver import ops
    cfg = {"_root": str(tmp_path), "default_game": "g1", "allow_external_paths": True,
           "paths": {"games": str(tmp_path / "games"), "out": str(tmp_path / "out"), "jobs": str(tmp_path / "jobs"),
                     "logs": str(tmp_path / "logs")}}
    (tmp_path / "games" / "g1").mkdir(parents=True)
    a = ops.handle({"op": "music.review", "input": {"title": "Carriage Return", "style": GOOD_STYLE, "lyrics": GOOD_TAGS}}, cfg)
    assert a["status"] == "done" and a["result"]["verdict"] == "ready" and a["result"]["kind"] == "instrumental"
    b = ops.handle({"op": "music.review", "input": {"style": "epic cinematic music", "lyrics": "[Intro]\nla la la"}}, cfg)
    assert b["result"]["verdict"] in ("fails", "needs work")


def test_a_portrait_brief_is_not_a_song_and_a_spoken_piece_is_not_judged_as_one(tmp_path):
    brief = tmp_path / "Portrait_Brief.md"
    brief.write_text("# Calliope — what she looks like\n\n## Style\nFantastic realism, warm light, a library at dusk.\n", encoding="utf-8")
    assert sr.parse_md(brief)[0] is None
    r = sr.review(sr.song("Sarah's briefing — Spoken", "spoken word monologue, female voice, low strings under, 70 BPM",
                          "[Spoken: commanding]\nWe go in at dawn.\nWe come out together.", instrumental=False))
    assert r["kind"] == "spoken" and "structure" not in checks(r) and "length" not in checks(r)


def test_the_same_song_in_a_sheet_and_its_own_file_is_not_a_reused_title():
    a = sr.song("Four Syllables", VOCAL_STYLE, VOCAL_LYRICS, instrumental=False, source="sheet.json #9")
    b = sr.song("Four Syllables", VOCAL_STYLE, VOCAL_LYRICS, instrumental=False, source="Calliope_Songs/Four_Syllables.md")
    assert "title reused" not in checks(sr.review_all([a, b])[0])
