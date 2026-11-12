"""BUILD 06 — the Music board and composing together, end to end on a throwaway copy of the example game:
propose → Bill's yes (through the Mail) → a session writes → Bill delivers (cemented) → loop / trim → the words filed →
a build wires it → in game. Plus the inbox, sharing, holding, a blank slot, the profiles, the server and the command line.
No real game is touched."""
from __future__ import annotations
import json, threading, urllib.request
from datetime import datetime
from pathlib import Path

import pytest

from forge import cli_suite
from forge.suite import areas, journal, mail, music, server, settings
from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

T = datetime(2026, 11, 11, 6, 0, 0)
OPUS, BILL = "Claude Opus", "Bill"
OGG = b"OggS\x00\x02" + b"\x00" * 200          # not a real song; the board never decodes audio


@pytest.fixture
def m(world, monkeypatch):
    cfg, a, tmp = world
    monkeypatch.setattr(settings, "now", lambda path=None: T)
    return cfg, a, tmp


def _state(a, sid):
    return music.find(a, sid)["state"]


def test_the_board_shows_every_slot_with_a_state_and_the_gaps(m):
    _cfg, a, _ = m
    b = music.board(a)
    assert {s["id"]: s["state"] for s in b["slots"]} == {"harbor_theme": "needed", "battle": "needed", "ember_song": "needed"}
    assert b["counts"]["needed"] == 3 and b["counts"]["total"] == 3
    assert [g["name"] for g in music.find(a, "ember_song")["singers"]] == ["Wren"]
    assert b["filters"]["places"] == ["ember_crossing", "harbor_hollow"] and b["filters"]["singers"] == ["Wren"]
    assert len(b["next"]) == 3 and all(r["why"] for r in b["next"])
    assert b["sheets"] == [{"id": "wren", "name": "Wren", "kind": "character", "open": 10, "styles": 2, "songs": 0}]
    assert not (a.root / "music" / "board.json").exists()          # reading writes nothing


def test_the_whole_loop_on_the_example_game(m):
    _cfg, a, _ = m
    sid = "ember_song"
    # 1 · propose — a song's brief names a style, and not one that is still open
    with pytest.raises(music.MusicRefused, match="names which style"):
        music.propose(a, sid, OPUS, "A toll song.")
    with pytest.raises(music.MusicRefused, match="still open"):
        music.propose(a, sid, OPUS, "A toll song.", style="style-2")
    with pytest.raises(music.MusicRefused, match="no style-7"):
        music.propose(a, sid, OPUS, "A toll song.", style="style-7")
    r = music.propose(a, sid, OPUS, "Scene: the toll. Wren sings the price instead of saying it.\nForm: three verses, the turn in the third.",
                      style="style-1")
    assert r["ok"] and r["brief"] == "music/briefs/ember-song.md" and _state(a, sid) == "proposed"
    brief = (a.root / r["brief"]).read_text(encoding="utf-8")
    assert "Wren's style-1 (Toll-road folk" in brief and "by Claude Opus" in brief
    letter = mail.find(a.root, r["letter"])
    assert (letter.sender, letter.to, letter.folder) == (OPUS, BILL, "to_bill")
    q = letter.questions[0]
    assert q["choices"] == music.VERDICT_CHOICES and q["applies_to"] == {"file": "music/board.json", "pointer": "/slots/ember_song/verdict"}
    # 2 · no lyric before his yes; a session can't agree with itself
    with pytest.raises(music.MusicRefused, match="no lyric before Bill says yes"):
        music.write_song(a, sid, OPUS, "The Toll", "[Verse 1]\nla")
    with pytest.raises(music.MusicRefused, match="only a person answers"):
        music.answer(a, sid, OPUS, "yes")
    # Bill answers in the Mail: the choice lands in the board file through the safe path
    rep = mail.reply(a.root, letter.id, BILL, "Yes — go.", answers=[{"id": "verdict", "choice": "yes"}], adp=a)
    assert rep.answers[0]["applied"]["message"] == "changed"
    assert _state(a, sid) == "agreed"
    # 3 · write — every version kept, credited
    w = music.write_song(a, sid, OPUS, "The Toll", "dry female alto, half-spoken folk waltz, 92 BPM\n\n[Verse 1]\nla la", note="v1")
    assert w["file"] == "music/songs/ember-song/the-toll.v1.md" and _state(a, sid) == "written"
    music.write_song(a, sid, OPUS, "The Toll", "dry female alto\n\n[Verse 1]\nla la la")
    s = music.find(a, sid)
    assert [v["n"] for v in s["versions"]] == [1, 2] and (a.root / "music/songs/ember-song/the-toll.v1.md").exists()
    assert {"what": "song v2", "by": OPUS} in s["credits"] and {"what": "brief", "by": OPUS} in s["credits"]
    # 4 · deliver — Bill's alone; copied, the music data pointed at it, cemented, journaled
    with pytest.raises(music.MusicRefused, match="delivering a track is a person.s"):
        music.deliver(a, sid, OPUS, data=OGG, filename="toll.ogg")
    with pytest.raises(music.MusicRefused, match="not an audio file"):
        music.deliver(a, sid, BILL, data=b"x", filename="toll.txt")
    d = music.deliver(a, sid, BILL, data=OGG, filename="The Toll (final).ogg")
    assert d["ok"] and d["file"] == "music/audio/ember-song.ogg" and d["state"] == "delivered"
    assert (a.root / d["file"]).read_bytes() == OGG
    md = json.loads((a.root / "data/music.json").read_text(encoding="utf-8"))
    assert md["ember_song"]["file"] == "music/audio/ember-song.ogg"
    s = music.find(a, sid)
    assert s["cemented"] and s["delivered"]["by"] == BILL and s["delivered"]["at"] == "2026-11-11T06:00:00"
    kinds = [(e["who"], e["kind"]) for e in journal.read(a.root)]
    assert (OPUS, "propose") in kinds and (BILL, "deliver") in kinds and (BILL, "music") in kinds
    # cemented: a session can only propose — not rewrite, not re-brief, not replace
    with pytest.raises(music.MusicRefused, match="delivered"):
        music.write_song(a, sid, OPUS, "The Toll", "new words")
    with pytest.raises(music.MusicRefused, match="cemented"):
        music.propose(a, sid, OPUS, "again", style="style-1")
    with pytest.raises(music.MusicRefused, match="cemented"):
        music.set_audio(a, sid, OPUS, 1.0, 2.0)
    # 5 · loop points and trim (his), written to the music data too
    with pytest.raises(music.MusicRefused, match="ends before"):
        music.set_audio(a, sid, BILL, 5.0, 2.0)
    assert music.set_audio(a, sid, BILL, 1.5, 62.25, -3.0)["ok"]
    md = json.loads((a.root / "data/music.json").read_text(encoding="utf-8"))
    assert (md["ember_song"]["loop_start"], md["ember_song"]["loop_end"], md["ember_song"]["trim_db"]) == (1.5, 62.25, -3.0)
    # 6 · the words as delivered, confirmed by him, filed once
    with pytest.raises(music.MusicRefused, match="only a person confirms"):
        music.confirm_lyric(a, sid, OPUS, "la")
    c = music.confirm_lyric(a, sid, BILL, "[Verse 1]\nla la la (as sung)")
    assert c["file"] == "music/songs/ember-song/as_delivered.txt" and "as sung" in (a.root / c["file"]).read_text(encoding="utf-8")
    with pytest.raises(music.MusicRefused, match="never overwritten"):
        music.confirm_lyric(a, sid, BILL, "different")
    # 7 · a build wires it to its scene → in game
    md["ember_song"]["plays"] = ["ember_crossing"]
    (a.root / "data/music.json").write_text(json.dumps(md, indent=1) + "\n", encoding="utf-8")
    assert _state(a, sid) == "in game"
    assert music.board(a)["counts"]["in game"] == 1


def test_answers_from_the_board_and_the_mail_mean_the_same(m):
    _cfg, a, _ = m
    music.propose(a, "battle", OPUS, "An instrumental: drums and a low fiddle.")      # instrumental: no style needed
    assert _state(a, "battle") == "proposed"
    assert music.answer(a, "battle", BILL, "not yet")["ok"] and _state(a, "battle") == "proposed"
    assert music.answer(a, "battle", BILL, "I'll write this one")["ok"]
    s = music.find(a, "battle")
    assert s["own"] and s["state"] == "needed"
    with pytest.raises(music.MusicRefused, match="Bill's own"):
        music.propose(a, "battle", OPUS, "again")
    with pytest.raises(music.MusicRefused, match="Bill's own"):
        music.write_song(a, "battle", OPUS, "x", "y")
    assert music.next_useful(music.slots(a))[0]["id"] != "battle"                 # his own isn't "next" for a session
    assert music.hold(a, "battle", BILL, False)["ok"] and not music.find(a, "battle")["own"]
    with pytest.raises(music.MusicRefused):
        music.hold(a, "battle", OPUS, True)


def test_a_written_ruling_marks_a_slot_his_from_the_start(m):
    _cfg, a, _ = m
    with pytest.raises(music.MusicRefused, match="quote the ruling"):
        music.record_own(a, "ember_song", OPUS, "he said so")
    r = music.record_own(a, "ember_song", OPUS, "data/notes.md:3 — “I'll write the toll song”")
    assert r["ok"] and music.find(a, "ember_song")["own"] and "notes.md:3" in music.find(a, "ember_song")["own_ruling"]
    with pytest.raises(music.MusicRefused, match="own"):
        music.propose(a, "ember_song", OPUS, "x", style="style-1")
    with pytest.raises(music.MusicRefused):
        music.hold(a, "ember_song", OPUS, False)                      # only a person releases it
    assert music.hold(a, "ember_song", BILL, False)["ok"] and not music.find(a, "ember_song")["own"]


def test_the_inbox_guesses_and_delivers_from_it(m):
    _cfg, a, _ = m
    inbox = a.root / "score_inbox"
    inbox.mkdir()
    (inbox / "harbor_theme_final.ogg").write_bytes(OGG + b"h")
    (inbox / "notes.txt").write_text("not audio", encoding="utf-8")
    rows = music.inbox(a)
    assert [r["name"] for r in rows] == ["harbor_theme_final.ogg"] and rows[0]["guess"]["id"] == "harbor_theme"
    r = music.deliver(a, "harbor_theme", BILL, inbox_name="harbor_theme_final.ogg")
    assert r["file"] == "music/harbor_theme.ogg" and r["state"] == "in game"       # wired already: it plays at once
    assert music.inbox(a)[0]["delivered_to"] == "harbor_theme" and music.inbox(a)[0]["guess"] is None
    assert music.audio_file(a, inbox_name="harbor_theme_final.ogg").name == "harbor_theme_final.ogg"
    assert music.audio_file(a, "harbor_theme").read_bytes() == OGG + b"h"
    # delivering again (his) backs the old one up first
    r2 = music.deliver(a, "harbor_theme", BILL, data=OGG + b"v2", filename="harbor v2.ogg")
    assert r2["backup"] and (a.root / r2["backup"]).read_bytes() == OGG + b"h"
    assert len(json.loads((a.root / "music/board.json").read_text(encoding="utf-8"))["slots"]["harbor_theme"]["earlier_deliveries"]) == 1


def test_sharing_a_theme_and_opening_a_blank_slot(m):
    _cfg, a, _ = m
    with pytest.raises(music.MusicRefused):
        music.share(a, "battle", OPUS, "harbor_theme")
    assert music.share(a, "battle", BILL, "harbor_theme")["ok"]
    s = music.find(a, "battle")
    assert s["via"] == "harbor_theme" and s["state"] == music.find(a, "harbor_theme")["state"]
    with pytest.raises(music.MusicRefused, match="itself shares"):
        music.share(a, "ember_song", BILL, "battle")
    assert music.share(a, "battle", BILL, None)["ok"] and not music.find(a, "battle").get("via")
    with pytest.raises(music.MusicRefused, match="a person opens it"):
        music.open_slot(a, OPUS, "An idea")
    r = music.open_slot(a, BILL, "The Ferryman's Count", "the ferry at night", True, "Wren")
    assert r["id"] == "opened:the-ferrymans-count" and _state(a, r["id"]) == "needed"
    assert [g["name"] for g in music.find(a, r["id"])["singers"]] == ["Wren"]
    with pytest.raises(music.MusicRefused, match="already"):
        music.open_slot(a, BILL, "The Ferryman's Count")


def test_profiles_are_his_to_fill_and_the_md_follows(m):
    _cfg, a, _ = m
    sh = music.sheet(a, "wren")
    assert len(sh["_open"]) == 10 and sh["_open"][0]["pointer"] == "/voice/constant"
    with pytest.raises(music.MusicRefused, match="William's to change"):
        music.fill_spot(a, "wren", "/voice/constant", "dryness", OPUS)
    assert music.fill_spot(a, "wren", "/voice/constant", "the dryness — always", BILL)["ok"]
    sh = music.sheet(a, "wren")
    assert sh["voice"]["constant"] == {"value": "the dryness — always", "by": BILL, "at": "2026-11-11T06:00:00"} and len(sh["_open"]) == 9
    md = (a.root / "music/styles/wren.md").read_text(encoding="utf-8")
    assert "the dryness — always — *Bill*" in md and md.index("## 1. The voice") < md.index("## 2.1 Style 1") < md.index("## 3. How") < md.index("## 4. Style notes") < md.index("## 5. Open spots")


def test_the_suite_app_and_command_line(m, capsys):
    cfg, a, _ = m
    assert server.act(cfg, "music_propose", {"game": "_example", "slot": "ember_song", "brief": "x"})["ok"] is False   # nobody signed in
    settings.set_identity(BILL)
    r = server.act(cfg, "music_open", {"game": "_example", "title": "Lighthouse"})
    assert r["ok"]
    r = server.act(cfg, "music_deliver", {"game": "_example", "slot": "battle", "filename": "b.ogg",
                                          "data": "data:audio/ogg;base64," + __import__("base64").b64encode(OGG).decode()})
    assert r["ok"] and (a.root / "music/audio/battle.ogg").read_bytes() == OGG
    srv = server.make_server(cfg, 0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        port = srv.server_address[1]
        b = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/suite/music?id=_example").read())
        assert {s["id"] for s in b["slots"]} >= {"battle", "ember_song", "opened:lighthouse"}
        req = urllib.request.Request(f"http://127.0.0.1:{port}/suite/audio?id=_example&slot=battle", headers={"Range": "bytes=0-9"})
        resp = urllib.request.urlopen(req)
        assert resp.status == 206 and resp.headers["Content-Range"] == f"bytes 0-9/{len(OGG)}" and resp.read() == OGG[:10]
        sh = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/suite/sheet?id=_example&sheet=wren").read())
        assert sh["sheet"]["name"] == "Wren" and sh["md"].startswith("# Wren")
        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode("utf-8")
        assert "music/needed" in areas.addresses() and "function loadMusic" in html      # BUILD 26: Music is its own area
    finally:
        srv.shutdown()
    assert cli_suite.cmd_music(cfg, ["board", "--game", "_example"]) == 0
    out = capsys.readouterr().out
    assert "in game 1" in out and "[in game" in out and "opened:lighthouse" in out
    assert cli_suite.cmd_music(cfg, ["write", "ember_song", "--title", "x", "--file", __file__, "--who", OPUS, "--game", "_example"]) == 1
    assert "no lyric before Bill says yes" in capsys.readouterr().out


def test_the_public_code_names_no_game():
    src = (REPO / "forge" / "suite" / "music.py").read_text(encoding="utf-8").lower()
    for word in ("turing", "valkyrie", "sarah", "calliope", "suno-songs"):
        assert word not in src
