"""BUILD 71 — the voice bench: the mouth rule against the cases file the game reads too; the loudness lane; the words check;
a pretend engine carried speak → hear-less take → both lanes end to end; the card rules (only a person locks, never a
preset, a person's sample needs consent, a song-referenced card needs William's second yes in the game); the licence
gate; nothing written outside the forge's folder; clearing keeps the marked takes."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge.suite import mouthrule as mr
from forge.voice import audio, bench, engines, hear, licences, loud, tools

FIX = Path(__file__).resolve().parent / "fixtures" / "mouth" / "cases.json"


def test_the_mouth_rule_matches_the_cases_file_the_game_reads():
    c = json.loads(FIX.read_text(encoding="utf-8"))
    tr = mr.parse(c["mouth"])
    assert c["blend_sec"] == mr.BLEND_SEC
    for row in c["at"]:
        b = mr.blend_at(tr, row["t"])
        assert mr.shape_at(tr, row["t"]) == row["shape"], row
        assert (b["from"], b["to"]) == (row["from"], row["to"]) and abs(b["w"] - row["w"]) < 1e-3, row
    for f in c["frames"]:
        assert mr.frame_for(f["shape"], f["available"]) == f["frame"], f


def test_the_rule_reads_rhubarbs_file_and_a_plain_list_alike():
    a = mr.parse({"mouthCues": [{"start": 0.0, "end": 0.2, "value": "a"}, {"start": 0.2, "end": 0.5, "value": "C"}]})
    b = mr.parse([[0.0, "A"], [0.2, "C"]])
    assert [r["shape"] for r in a] == ["A", "C"] == [r["shape"] for r in b] and mr.duration(a) == 0.5
    lane = mr.lane(a, offset=-0.1)
    assert lane[0]["to"] == "A" and any(r["to"] == "C" for r in lane)


def _tone(path, bursts=((0.3, 0.6), (0.9, 1.3)), rate=16000, total=1.6):
    t = np.arange(int(rate * total)) / rate
    env = np.zeros_like(t)
    for a, b in bursts:
        env[(t >= a) & (t < b)] = 1.0
    audio.write_wav(path, 0.6 * env * np.sin(2 * np.pi * 200 * t), rate)
    return path


def test_loudness_keeps_silence_shut_and_opens_within_a_burst(tmp_path):
    s, rate = audio.read(_tone(tmp_path / "v.wav"))
    c = loud.cues(s, rate)
    tr = mr.parse(c)
    assert mr.shape_at(tr, 0.1) == "X" and mr.shape_at(tr, 0.45) in ("C", "D") and mr.shape_at(tr, 0.75) == "X"
    assert c["metadata"]["method"] == "loud" and all(x["end"] > x["start"] for x in c["mouthCues"])


def test_the_words_check_names_the_changed_word_and_knows_the_names_list():
    assert hear.compare("Hold the door, Ortega!", "hold the door ortega")["match"]
    d = hear.compare("Hold the door, Ortega!", "hold the floor ortega")
    assert not d["match"] and d["differ"][0]["said"] == "door" and d["differ"][0]["heard"] == "floor"
    assert hear.compare("Bill, it's Sarah.", "bill it's sara", {"Sarah": {"heard_as": ["sara"]}})["match"]


def test_a_pretend_engine_carries_a_take_end_to_end_and_the_card_is_asked_never_taken(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "rhubarb_exe", lambda *a: None)          # loudness lane only; nothing installed
    monkeypatch.setattr(tools, "whisper_ready", lambda *a: False)
    paths = bench.default_paths(tmp_path / "game")
    e = engines.get("pretend")
    wav = tmp_path / "p.wav"
    assert e.speak("Hold the door for me", {}, wav, seed=3)["ok"]
    t = bench.make_take(paths, "Hold the door for me", wav, "sentry_x", "warm", engine="pretend")
    assert t["origin"] == "engine" and t["lanes"] == ["loud"] and t["checks"]["whisper"] == "not installed"
    tk = Path(t["folder"])
    assert (tk / "take.json").exists() and (tk / "loud.mouth.json").exists()
    lanes = bench.lanes_for_face(tk, ["A", "B", "C"])
    assert set(lanes) == {"loud"} and all(r["frame_to"] in ("A", "B", "C") for r in lanes["loud"])


def test_where_a_voice_came_from_is_written_and_cuts_are_always_song(tmp_path):
    paths = bench.default_paths(tmp_path)
    (tmp_path / "voice_cuts" / "sarah").mkdir(parents=True)
    (tmp_path / "stems").mkdir()
    (tmp_path / "voice_samples").mkdir()
    assert bench.origin_of(tmp_path / "voice_cuts" / "sarah" / "a.wav", paths) == "song"
    assert bench.origin_of(tmp_path / "stems" / "b.wav", paths) == "song"
    assert bench.origin_of(tmp_path / "voice_samples" / "c.wav", paths) == "person"
    assert bench.origin_of(tmp_path / "x.wav", paths, engine="kokoro") == "engine"


def test_only_a_person_locks_a_card_never_a_preset_and_a_sample_needs_consent(tmp_path):
    paths = bench.default_paths(tmp_path)
    bench.save_card(paths, "a", {"engine": "kokoro", "way": "preset"}, "Fable")
    with pytest.raises(bench.BenchRefused, match="stock voice"):
        bench.lock_card(paths, "a", "William", by_person=True)
    bench.save_card(paths, "b", {"engine": "qwen3_tts", "way": "reference", "reference_origin": "person"}, "Fable")
    with pytest.raises(bench.BenchRefused, match="agreed"):
        bench.lock_card(paths, "b", "William", by_person=True)
    bench.save_card(paths, "c", {"engine": "qwen3_tts", "way": "reference", "reference_origin": "song"}, "Fable")
    with pytest.raises(bench.BenchRefused, match="person"):
        bench.lock_card(paths, "c", "Opus", by_person=False)
    with pytest.raises(bench.BenchRefused, match="locking"):
        bench.save_card(paths, "c", {"status": "locked"}, "Opus")
    c = bench.lock_card(paths, "c", "William", by_person=True)
    assert c["status"].startswith("locked by William")
    ok, why = bench.usable_in_game(c)
    assert not ok and "second yes" in why
    assert bench.usable_in_game({**c, "game_yes": {"by": "William"}})[0]
    with pytest.raises(bench.BenchRefused, match="locked"):
        bench.save_card(paths, "c", {"engine": "kokoro"}, "Fable")
    with pytest.raises(bench.BenchRefused, match="came from"):
        bench.save_card(paths, "d", {"way": "reference"}, "Fable")


def test_the_licence_gate_refuses_non_commercial_and_unread(tmp_path):
    assert licences.gate({"code": "MIT", "weights": "Apache-2.0", "bundles": "BSD-3-Clause"})[0]
    ok, why = licences.gate({"code": "MPL", "weights": "Coqui Public Model License (non-commercial)", "bundles": "MIT"})
    assert not ok and any("not for a sold game" in w for w in why)
    assert not licences.gate({"code": "MIT", "weights": "", "bundles": "MIT"})[0]
    assert all(e["online"] is False for e in engines.all_engines())
    assert engines.describe("pretend")["licence_ok"]


def test_a_tool_run_leaves_nothing_under_the_profile(tmp_path, monkeypatch):
    from forge import config as cfgmod
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    e = tools.tool_env()
    for k in ("HOME", "USERPROFILE", "TEMP", "TMP", "HF_HOME", "XDG_CACHE_HOME", "APPDATA", "LOCALAPPDATA"):
        assert Path(e[k]).resolve().is_relative_to(tmp_path.resolve()), k
    tools.log({"test": 1})
    assert list((tmp_path / "logs" / "voice").glob("*.log"))


def test_the_stand_in_mouth_says_stand_in_and_draws_every_shape():
    img = Image.new("RGB", (200, 260), (200, 170, 150))
    fr = bench.standin_mouths(img, (80, 170, 120, 190))
    assert set(fr) == set(mr.SHAPES)
    a, d = np.asarray(fr["A"]), np.asarray(fr["D"])
    assert (a[2:14, 2:80] != (200, 170, 150)).any() and (a != d).any()        # the label, and a mouth that opened


def test_verdicts_are_appended_and_clearing_keeps_the_marked(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "rhubarb_exe", lambda *a: None)
    monkeypatch.setattr(tools, "whisper_ready", lambda *a: False)
    paths = bench.default_paths(tmp_path)
    w = _tone(tmp_path / "v.wav")
    t1 = bench.make_take(paths, "one", w)
    t2 = bench.make_take(paths, "two", w)
    bench.verdict(paths, Path(t1["folder"]), ["Sounds like them", "Mouth late"], "good", "William")
    with pytest.raises(bench.BenchRefused):
        bench.verdict(paths, Path(t2["folder"]), ["Lovely"], "", "William")
    r = bench.clear_unmarked(paths)
    assert r == {"cleared": 1, "kept": 1} and Path(t1["folder"]).exists() and not Path(t2["folder"]).exists()
    assert len(Path(paths["verdicts"]).read_text().splitlines()) == 1
    L = bench.learned(paths)
    assert L["engines"]["file"]["sounds_like"] == 1 and L["mouth_verdicts"]["Mouth late"] == 1
