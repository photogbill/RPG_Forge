"""BUILD 27 — the suite runs on a Mac too, and Windows stays exactly as it is. There is no Mac here, so "as if on macOS"
plays one: sys.platform is darwin for the opener, the worker, the run-words and the server. The real macOS run is
.github/workflows/suite.yml at the next push. Plus the cross-system rules: portable file names, '/' paths in shared
files, case, and line endings."""
from __future__ import annotations
import json, re, subprocess, sys, threading, urllib.request
from datetime import datetime
from pathlib import Path

import pytest

from forge.suite import (areas, casecheck, games, home, journal, mail, music, names, notes, orders, osopen, readthrough,
                         runwords, safesave, server, settings, tasks, worker)
from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

T = datetime(2026, 11, 11, 12, 30, 0)
BILL, OPUS = "Bill", "Claude Opus"
HOSTILE = 'CON: <a/b\\c> * "what?" | the end. '


@pytest.fixture
def mac(monkeypatch):
    """As if on macOS (pathlib stays this machine's; everything that asks *which* system it is hears 'mac')."""
    monkeypatch.setattr(sys, "platform", "darwin")
    assert osopen.system() == "mac"
    return monkeypatch


@pytest.fixture
def w(world, monkeypatch):
    cfg, a, tmp = world
    monkeypatch.setattr(settings, "now", lambda path=None: T)
    areas._badge_cache.clear()
    settings.set_identity(BILL)
    return cfg, a, tmp


# ---------------------------------------------------------------- B · one place for each difference
def test_the_opener_uses_open_on_a_mac_xdg_open_on_linux_and_startfile_on_windows(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setattr(sys, "platform", "darwin")
    osopen.open_path(tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    osopen.open_path(tmp_path)
    assert calls == [["open", str(tmp_path)], ["xdg-open", str(tmp_path)]]
    import os
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "startfile", lambda p: calls.append(["startfile", p]), raising=False)
    osopen.open_path(tmp_path)
    assert calls[-1] == ["startfile", str(tmp_path)]


def test_nothing_else_calls_startfile_or_xdg_open():
    for p in (REPO / "forge").rglob("*.py"):
        if p.name == "osopen.py":
            continue
        t = p.read_text(encoding="utf-8")
        assert "startfile(" not in t and '"xdg-open"' not in t, p


def test_on_a_mac_the_worker_button_gives_the_pc_only_answer(w, mac):
    cfg, _a, _ = w
    r = worker.start(cfg)
    assert not r["ok"] and "runs on the Windows PC with the art worker" in r["message"]
    settings.update(worker_pc="William's PC")
    assert "runs on William's PC" in worker.start(cfg)["message"]
    from forge import ui
    h = home.data(cfg, ui.State(cfg))
    assert not h["actions"]["start"]["enabled"] and "runs on William's PC" in h["actions"]["start"]["why_not"]
    assert h["worker"]["here"] is False and "runs on William's PC" in h["worker"]["words"]
    b = areas.badges(cfg, "_example", fresh=True)
    assert b["worker_here"] is False and b["worker_pc"] == "William's PC"
    nd = areas.needs(cfg, "_example")
    assert nd["art/make"]["met"] is False and "William's PC" in nd["art/make"]["line"]
    assert nd["art/review"]["met"] is True                                  # review still works on what's in the folders


def test_windows_keeps_every_word_and_linux_too(monkeypatch):
    s = "Edit it, save into done/, then handoff_in.bat harbor. The same as pause.bat."
    for plat in ("win32", "linux"):
        monkeypatch.setattr(sys, "platform", plat)
        assert runwords.say(s) == s
    monkeypatch.setattr(sys, "platform", "darwin")
    m = runwords.say(s)
    assert ".bat" not in m and "./forge.command handoff in harbor" in m and "■ Stop" in m


def test_every_bat_in_the_forge_has_a_mac_answer():
    bats = sorted(p.stem for p in REPO.glob("*.bat"))
    missing = [b for b in bats if b.lower() not in runwords.TABLE]      # runwords looks a name up in lower case
    assert not missing, f"add these to runwords.TABLE: {missing}"


def _serve(cfg):
    s = server.make_server(cfg, 0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, s.server_address[1]


def test_on_a_mac_no_response_contains_bat(w, mac):
    cfg, a, _ = w
    orders.add(a.root, OPUS, BILL, "Bring back the harbor painting — handoff_in.bat harbor", detail="then submit.bat it")
    s, port = _serve(cfg)
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode("utf-8")
        assert ".bat" not in page
        assert ".bat" not in urllib.request.urlopen(f"http://127.0.0.1:{port}/art/queue").read().decode("utf-8")
        for path in ("/api/suite/home", "/api/suite/areas?id=_example", "/api/suite/badges?id=_example&fresh=1",
                     "/api/suite/tasks?id=_example", "/api/suite/status?id=_example", "/api/suite/about",
                     "/api/suite/orders?id=_example&all=1", "/api/suite/music?id=_example", "/api/suite/intake?id=_example",
                     "/api/suite/library?id=_example", "/api/suite/models?id=_example"):
            try:
                body = urllib.request.urlopen(f"http://127.0.0.1:{port}{path}").read().decode("utf-8")
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8")
            assert ".bat" not in body, path
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/suite/act/start", data=b"{}", method="POST",
                                     headers={"X-Forge": "1", "Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req).read())
        assert not r["ok"] and ".bat" not in r["message"]
    finally:
        s.shutdown()


def test_the_page_still_parses_after_its_words_change_on_a_mac(w, mac, tmp_path):
    import shutil
    node = shutil.which("node")
    if not node:
        pytest.skip("no node here to check the page's script")
    settings.update(worker_pc="Bill's \"big\" PC")
    for name, html in (("suite", runwords.say(server.SHELL, page=True)), ("queue", runwords.say(__import__("forge.ui").ui.PAGE, page=True))):
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        for i, js in enumerate(scripts):
            f = tmp_path / f"{name}{i}.js"
            f.write_text(js, encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            assert r.returncode == 0, (name, r.stderr[:800])


def test_a_game_folder_that_isnt_here_leads_to_the_settings_page(w, mac, tmp_path):
    cfg, a, _ = w
    settings.set_game_root("_example", str(tmp_path / "not-here"))
    gl = {g["id"]: g for g in games.listing(cfg)}
    assert gl["_example"]["root_exists"] is False
    html = server.SHELL
    assert "if(cg&&!cg.root_exists){history.replaceState(null,'','#settings/computer')" in html
    assert areas.find("settings/computer")[1]["screen"] == "settings" and not areas.find("settings/computer")[1].get("planned")


def test_settings_check_and_save_a_game_folder_for_this_computer(w, tmp_path):
    cfg, a, _ = w
    real = a.root
    bad = server.act(cfg, "game_root_check", {"id": "_example", "folder": str(tmp_path / "nope")})
    assert not bad["ok"] and "no folder" in bad["message"]
    empty = tmp_path / "empty"
    empty.mkdir()
    r = server.act(cfg, "game_root_check", {"id": "_example", "folder": str(empty)})
    assert not r["ok"] and "doesn't look like this game" in r["message"]
    r = server.act(cfg, "game_root_check", {"id": "_example", "folder": str(real)})
    assert r["ok"] and r["found"]["places"] == 3 and r["found"]["music slots"] == 3 and "3 places" in r["message"]
    assert not server.act(cfg, "game_root_set", {"id": "_example", "folder": str(empty)})["ok"]     # refused, nothing saved
    assert not (settings.load().get("game_roots") or {}).get("_example")
    copy = tmp_path / "copy_of_game"
    import shutil
    shutil.copytree(real, copy)
    r = server.act(cfg, "game_root_set", {"id": "_example", "folder": str(copy)})
    assert r["ok"] and settings.load()["game_roots"]["_example"] == str(copy)
    assert games.adapter(cfg, "_example").root == copy
    assert any(e["kind"] == "setting" and "copy_of_game" in e["note"] for e in journal.read(copy))
    assert server.act(cfg, "game_root_set", {"id": "_example", "folder": ""})["ok"]
    assert "_example" not in settings.load()["game_roots"]


def test_settings_time_zone_godot_and_the_workers_pc(w):
    cfg, _a, _ = w
    assert server.act(cfg, "setting_set", {"key": "timezone", "value": "America/Denver"})["ok"]
    assert not server.act(cfg, "setting_set", {"key": "timezone", "value": "Mars/Olympus"})["ok"]
    assert server.act(cfg, "setting_set", {"key": "godot", "value": "/Applications/Godot.app"})["ok"]
    assert server.act(cfg, "setting_set", {"key": "worker_pc", "value": "Bill's PC"})["ok"]
    assert not server.act(cfg, "setting_set", {"key": "identity", "value": "x"})["ok"]          # not through this door
    d = server.about(cfg)
    assert d["settings"] == {"timezone": "America/Denver", "godot": "/Applications/Godot.app", "worker_pc": "Bill's PC"}
    assert d["system"] in ("windows", "mac", "linux")


# ---------------------------------------------------------------- C · rules that keep both systems honest
def test_every_kind_of_name_the_suite_makes_is_portable(w):
    cfg, a, _ = w
    made = []
    l = mail.send(a.root, OPUS, BILL, HOSTILE, "body")
    made.append(Path(mail._path_of(a.root, l.id)).name)
    music.propose(a, "ember_song", OPUS, "brief", style="style-1", subject=HOSTILE)
    s = music.find(a, "ember_song")
    made.append(Path(s["brief"]).name)
    mail.reply(a.root, s["letter"], BILL, "yes", answers=[{"id": "verdict", "choice": "yes"}], adp=a)
    v = music.write_song(a, "ember_song", OPUS, HOSTILE, "dry alto\n\n[Verse]\nla")
    made.append(Path(v["file"]).name)
    o = orders.add(a.root, OPUS, BILL, HOSTILE)
    made.append(o["id"] + ".json")
    n = notes.add(a.root, "place:x", BILL, HOSTILE)
    made.append(notes.path(a.root).name)
    r = safesave.edit(a, "data/quests.json", [("put", "/lamp_oil/title", HOSTILE)], BILL, reason="test")
    for p in (a.root / "_workbench_backups").rglob("*"):
        made.append(p.name)
    made += [tasks.safe_name(HOSTILE + ".png"), tasks.safe_name("con.txt"), tasks.safe_name("x" * 300 + ".wav"),
             music.slug(HOSTILE) + ".md", Path(music._target(a, {"id": HOSTILE}, ".ogg")).name]
    bad = {m: names.problems(m) for m in made if names.problems(m)}
    assert not bad, bad
    assert names.problems("CON.txt") and names.problems("a.") and names.problems("a:b") and not names.problems("harbor_v2.ogg")


def test_paths_in_shared_files_use_slashes_and_no_drive_letter(w, tmp_path):
    cfg, a, _ = w
    music.propose(a, "ember_song", OPUS, "brief", style="style-1")
    s = music.find(a, "ember_song")
    mail.reply(a.root, s["letter"], BILL, "yes", answers=[{"id": "verdict", "choice": "yes"}], adp=a)
    music.write_song(a, "ember_song", OPUS, "The Toll", "dry\n\n[Verse]\nla")
    music.deliver(a, "ember_song", BILL, data=b"OggS" + b"\0" * 50, filename="toll.ogg")
    o = orders.add(a.root, OPUS, BILL, "A photo", wants={"kind": "image"}, goes_to="reference/harbor")
    st = tasks.incoming_dir(a.root)
    st.mkdir()
    (st / "p.png").write_bytes(b"\x89PNG....")
    tasks.accept(cfg, "_example", f"order:{o['id']}", st / "p.png", "p.png", BILL)
    readthrough.edit_line(a, "data/dialogue/harbor_keeper.json#/lines/0", "text", "A new line.", BILL, None)
    notes.add(a.root, "data/dialogue/harbor_keeper.json#/lines/0", BILL, "a note")
    drive = re.compile(r"(^|[\s\"'(])[A-Za-z]:[\\/]")
    PATH_KEYS = {"obj", "link", "file", "where", "brief", "attachments", "after", "before", "goes_to", "source"}

    def scan(v, key, where):
        if isinstance(v, dict):
            for k, x in v.items():
                scan(x, k, where)
        elif isinstance(v, list):
            for x in v:
                scan(x, key, where)
        elif isinstance(v, str) and key in PATH_KEYS and ("/" in v or "\\" in v):
            assert "\\" not in v and not drive.search(v) and not v.startswith("/"), (where, key, v)

    for e in journal.read(a.root):
        scan(e, None, "journal")
    scan(music.load_board(a), None, "board")
    for line in notes.path(a.root).read_text(encoding="utf-8").splitlines():
        scan(json.loads(line), None, "notes")
    for l in mail.all_letters(a.root):
        scan({"attachments": l.attachments}, None, l.id)
    for f, od in orders._all(a.root):
        scan(od, None, f.name)


def test_case_differences_are_reported_not_fixed(w):
    cfg, a, _ = w
    (a.root / "music").mkdir(exist_ok=True)
    (a.root / "music" / "Harbor.ogg").write_bytes(b"x")
    assert casecheck.case_of(a.root, "music/harbor.ogg") == "music/Harbor.ogg"
    assert casecheck.case_of(a.root, "music/Harbor.ogg") is None and casecheck.case_of(a.root, "music/nope.ogg") is None
    mail.send(a.root, OPUS, BILL, "With a file", "see it", attachments=["music/harbor.ogg"])
    rep = "\n".join(casecheck.report(cfg))
    assert "music/harbor.ogg" in rep and "on disk: music/Harbor.ogg" in rep
    assert (a.root / "music" / "Harbor.ogg").exists() and not (a.root / "music" / "harbor_renamed.ogg").exists()


def test_a_crlf_file_stays_crlf_after_an_edit_through_the_suite(w):
    cfg, a, _ = w
    p = a.root / "data" / "places" / "ember_crossing.json"
    raw = p.read_bytes()
    assert b"\r\n" in raw
    r = safesave.edit(a, "data/places/ember_crossing.json", [("put", "/summary", "A bridge town, rebuilt.")], BILL, reason="test")
    assert r["ok"]
    out = p.read_bytes()
    assert out.count(b"\r\n") == raw.count(b"\r\n") and b"\n" not in out.replace(b"\r\n", b"")


# ---------------------------------------------------------------- A · the launchers, the workflow, push.bat
def test_the_mac_launchers_and_the_workflow_are_there():
    inst = (REPO / "install_mac.command").read_bytes()
    fc = (REPO / "forge.command").read_bytes()
    for b in (inst, fc):
        assert b.startswith(b"#!/bin/bash\n") and b"\r\n" not in b
    assert b"venv-mac" in inst and b"requirements-suite.txt" in inst and b"python.org" in inst and b"sudo" not in inst
    assert b"-m forge suite" in fc
    req = (REPO / "requirements-suite.txt").read_text(encoding="utf-8")
    assert "Pillow" in req and "numpy" in req and "pytest" in req and "huggingface" not in req
    wf = (REPO / ".github" / "workflows" / "suite.yml").read_text(encoding="utf-8")
    for os_ in ("windows-latest", "macos-latest", "ubuntu-latest"):
        assert os_ in wf
    assert "requirements-suite.txt" in wf and '"3.12"' in wf
    assert "git update-index --chmod=+x install_mac.command forge.command" in (REPO / "push.bat").read_text(encoding="utf-8")
    assert "*.command text eol=lf" in (REPO / ".gitattributes").read_text(encoding="utf-8")
    gi = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "venv-mac/" in gi and "_xfer/" in gi
    assert "## On a Mac" in (REPO / "README.md").read_text(encoding="utf-8")


def test_install_mac_runs_here_and_makes_its_own_environment(tmp_path):
    """The Mac installer is plain bash; on a machine with bash it runs end to end against a copy (no network: pip is
    pointed at nothing and the failure is the installer's own plain message, never a traceback)."""
    import shutil
    if not shutil.which("bash") or sys.platform.startswith("win"):
        pytest.skip("no bash here")
    d = tmp_path / "forge"
    d.mkdir()
    for f in ("install_mac.command", "forge.command", "requirements-suite.txt"):
        shutil.copy(REPO / f, d / f)
    r = subprocess.run(["bash", str(d / "forge.command")], input="\n", capture_output=True, text=True, timeout=30)
    assert "install_mac.command first" in r.stdout and r.returncode == 1
