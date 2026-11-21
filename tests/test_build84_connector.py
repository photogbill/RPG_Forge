"""BUILD 84 part 4 — the connector: status in a second or two, the extension file, one name for two ways in.

Status took 25 to 77 seconds on 2026-11-19. Two things cost it: every finished job file was opened to count the queue
(16,700 of them), and the world list was read three times, each reading asking the disk once a made thing a folder where
that thing's Review entry was. These tests build a forge of that shape (smaller, so they stay quick) and count what
status asks the disk, and check that the quick way gives the same answer as the slow one.
"""
from __future__ import annotations

import builtins
import io
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

import pytest

from forge import eta
from forge.mcpserver import bundle, claude_settings, ops
from forge.queue import Queue
from forge.suite import approve_all
from forge.suite import threed as suite3d
from forge.threed import world

REPO = Path(__file__).resolve().parents[1]


def _cfg(tmp_path, gid="g1") -> dict:
    (tmp_path / "games" / gid).mkdir(parents=True)
    (tmp_path / "games" / gid / "forge.game.json").write_text(json.dumps({"id": gid}), encoding="utf-8")
    return {"_root": str(tmp_path), "default_game": gid, "threed": {"out_root": str(tmp_path / "out3d")},
            "comfy": {"url": "http://127.0.0.1:9"},
            "paths": {"games": str(tmp_path / "games"), "out": str(tmp_path / "out"), "jobs": str(tmp_path / "jobs"),
                      "logs": str(tmp_path / "logs"), "palettes": str(tmp_path / "palettes"), "models": str(tmp_path / "models")},
            "allow_external_paths": True}


def _a_night(tmp_path, cfg, done=600, made=60):
    """A forge after a night's work: finished jobs (some of them tombstones), failed and parked ones, two waiting; a world
    list with `made` things made and sent to Review, some wanted, one held."""
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    words = "a long description of the picture " * 30
    for i in range(done):
        job = {"id": f"20261119-0000{i % 60:02d}-thing_{i}-{i:04x}", "type": "icon", "name": f"thing_{i}", "prompt": words,
               "started_at": "2026-11-19T01:00:00", "finished_at": "2026-11-19T01:01:10", "result": {"seconds": 70.0}}
        if i % 50 == 0:                                   # a job that was moved on left this behind
            job = {"id": job["id"], "moved_to": str(tmp_path / "jobs" / "pending" / "x.json"), "tombstone": True}
        (tmp_path / "jobs" / "done" / f"{job['id']}.json").write_text(json.dumps(job), encoding="utf-8")
    for i in range(7):
        (tmp_path / "jobs" / "failed" / f"f{i}.json").write_text(json.dumps({"id": f"f{i}", "type": "icon", "error": words}), encoding="utf-8")
    for i in range(3):
        (tmp_path / "jobs" / "paused" / f"p{i}.json").write_text(json.dumps({"id": f"p{i}", "type": "icon", "prompt": words}), encoding="utf-8")
    for i in range(2):
        (tmp_path / "jobs" / "pending" / f"w{i}.json").write_text(json.dumps({"id": f"w{i}", "type": "icon", "prompt": words}), encoding="utf-8")
    (tmp_path / "jobs" / "done" / "half_written.json").write_text("{", encoding="utf-8")       # counted, as before
    entries = [{"id": f"thing_{i}", "kind": "prop", "words": "a crate", "real_size_m": {"height": 1.0}, "first": {"order": i}}
               for i in range(made + 12)]
    lists = tmp_path / "games" / "g1" / "wanted_3d"
    lists.mkdir(parents=True, exist_ok=True)
    (lists / "needs.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
    es = {e["id"]: e for e in world.load(cfg, "g1")[0]}
    for i in range(made):
        eid = f"thing_{i}"
        st = {"state": "made", "tries": 1, "model": f"out3d/world/g1/{eid}/{eid}.glb", "engine": "trellis2",
              "checks": ["Sits level: 0.0° off level — passes (the limit is 2°)."]}
        st["try"] = world.to_review(cfg, "g1", es[eid], st)
        world.write_state(cfg, "g1", eid, st)
    world.write_state(cfg, "g1", f"thing_{made}", {"state": "held", "why": ["Loose pieces: 1 piece not joined to the rest"],
                                                    "check_results": [{"check": "loose", "ok": False}]})
    return q


# ------------------------------------------------------------------------------------------------ status
def test_the_quick_count_of_the_art_queue_is_the_same_count(tmp_path):
    cfg = _cfg(tmp_path)
    q = _a_night(tmp_path, cfg, done=300, made=3)
    slow = q.status()
    assert ops.count_jobs(tmp_path / "jobs") == slow
    assert slow["done"] == 300 - 6 + 1 and slow["failed"] == 7 and slow["paused"] == 3 and slow["pending"] == 2
    shutil.rmtree(tmp_path / "jobs" / "paused")
    assert "paused" not in ops.count_jobs(tmp_path / "jobs")                  # a folder that is not there is nothing parked


def test_the_quick_estimate_is_the_same_estimate(tmp_path):
    cfg = _cfg(tmp_path)
    _a_night(tmp_path, cfg, done=120, made=2)
    slow = eta.estimate(cfg)
    fast = ops.eta_fast(cfg)
    assert fast == {"pending": slow["pending"], "hours": round(slow["seconds"] / 3600, 1)} and fast["pending"] == 2
    assert ops.eta_fast(cfg, 0) == {"pending": 0, "hours": 0.0}


def test_the_list_finds_every_review_entry_in_one_walk_and_says_what_it_said_before(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _a_night(tmp_path, cfg, done=5, made=25)
    tries = tmp_path / "games" / "g1" / "threed"

    def decided(eid, state):                              # what Review & approve writes when a person decides
        tid = world.read_state(cfg, "g1", eid)["try"]
        f = tries / "tries" / eid / f"{tid}.json"
        t = json.loads(f.read_text(encoding="utf-8"))
        t["review"]["state"] = state
        f.write_text(json.dumps(t), encoding="utf-8")
        return tid
    decided("thing_3", "approved")
    decided("thing_4", "rejected")
    gone = decided("thing_7", "approved")
    (tries / "approved.json").write_text(json.dumps({"thing_7": {"try": gone, "delivered": "2026-11-19T10:00:00"}}), encoding="utf-8")
    world.write_state(cfg, "g1", "thing_5", {**world.read_state(cfg, "g1", "thing_5"), "try": "world-thing_5-gone"})
    items, _ = world.merged(cfg, "g1")
    by = {e["id"]: e for e in items}
    slow = {eid: world.review_state(cfg, "g1", e["st"]) for eid, e in by.items() if e["state"] == "made"}   # the old way
    assert {eid: e["review"] for eid, e in by.items() if e["state"] == "made"} == slow
    assert by["thing_3"]["shown"] == "approved" and by["thing_4"]["shown"] == "turned down" and by["thing_5"]["review"] is None
    assert by["thing_6"]["review"] == "waiting" and by["thing_7"]["shown"] == "delivered"
    globs = []
    real = Path.glob
    monkeypatch.setattr(Path, "glob", lambda self, pat, **kw: (globs.append((self.name, pat)), real(self, pat, **kw))[1])
    world.merged(cfg, "g1")
    assert not [g for g in globs if g[0] == "tries"]                          # nobody goes through the folders a thing at a time


def test_status_at_the_size_of_a_night_asks_the_disk_little_and_says_how_long_it_took(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _a_night(tmp_path, cfg, done=600, made=60)
    before = {"art": Queue(tmp_path / "jobs", tmp_path / "out").status(), "plan": approve_all.world_plan(cfg, "g1")}
    opened, merges = [], []
    real_open, real_merged = builtins.open, world.merged

    def counting(f, *a, **k):
        opened.append(str(f))
        return real_open(f, *a, **k)
    monkeypatch.setattr(builtins, "open", counting)
    monkeypatch.setattr(io, "open", counting)
    monkeypatch.setattr(world, "merged", lambda *a, **k: (merges.append(1), real_merged(*a, **k))[1])
    t0 = time.time()
    a = ops.handle({"op": "status"}, cfg)
    took = time.time() - t0
    monkeypatch.undo()
    r = a["result"]
    assert a["status"] == "done" and r["art_queue"] == before["art"]
    assert r["world_queue"]["counts"] == {"made": 60, "held": 1, "wanted": 11} and r["world_queue"]["to_make"] == 11
    assert r["approvals"]["world_list_waiting"] == before["plan"]["count"] and r["approvals"]["review_waiting"] == 60
    assert r["approvals"]["left_for_a_look"] == before["plan"]["left"]
    # what it asked the disk: the finished jobs are counted from the listing — only the small files (tombstones, a
    # half-written one) and the newest few hundred for the estimate are opened, never all of them twice over
    done_dir = str(tmp_path / "jobs" / "done")
    done_opens = [f for f in opened if f.startswith(done_dir)]
    assert len(set(done_opens)) <= 400 + 13 and len(done_opens) <= 400 + 13 + 13
    assert len(merges) == 1                                                   # the list is read once and handed on
    cfg_reads = [f for f in opened if f.endswith("suite.json") or f.endswith("forge.game.json")]
    assert len(cfg_reads) <= 12                                               # not twice a model in Review
    assert len(opened) < 600 + 60 * 3 + 200
    tk = r["took_seconds"]
    assert set(tk) == {"all", "art_queue", "art_queue_time", "world_queue", "around_the_clock", "comfyui", "disk", "approvals"}
    assert tk["all"] >= max(v for k, v in tk.items() if k != "all") and took < 5.0


def test_where_a_model_goes_is_asked_of_the_game_once_and_is_the_same_answer(tmp_path):
    cfg = _cfg(tmp_path)
    _a_night(tmp_path, cfg, done=3, made=4)
    rows = suite3d.review_list(cfg, "g1")["waiting"]
    assert len(rows) == 4
    for row in rows:
        t = suite3d.load_try(cfg, "g1", row["id"])
        assert row["dest"] == suite3d.dest_rel(cfg, "g1", t) and row["dest"].endswith(f"/{t['who']}.glb")


# ------------------------------------------------------------------------------------------------ the extension file
def test_the_extension_file_starts_the_connector_that_is_in_the_folder(tmp_path):
    out = bundle.build(tmp_path / "local" / "mcp" / "rpg-forge.mcpb", r"D:\RPG_Forge", True)
    assert out.exists() and not out.with_name(out.name + ".part").exists()
    with zipfile.ZipFile(out) as z:
        assert sorted(z.namelist()) == ["manifest.json", "server/launch.py"]
        m = json.loads(z.read("manifest.json").decode("utf-8"))
        launch = z.read("server/launch.py").decode("utf-8")
    assert m["name"] == bundle.NAME == claude_settings.NAME == "rpg-forge" and m["manifest_version"] and m["version"]
    mc = m["server"]["mcp_config"]
    assert mc == {"command": r"D:\RPG_Forge\venv_mcp\Scripts\python.exe", "args": ["-m", "forge.mcpserver"],
                  "env": {"PYTHONPATH": r"D:\RPG_Forge"}}
    assert m["server"]["entry_point"] == "server/launch.py" and m["compatibility"]["platforms"] == ["win32"]
    compile(launch, "launch.py", "exec")
    assert repr(r"D:\RPG_Forge") in launch and 'run_module("forge.mcpserver"' in launch
    mac = bundle.manifest("/Users/bill/RPG_Forge", False)
    assert mac["server"]["mcp_config"]["command"] == "/Users/bill/RPG_Forge/venv_mcp/bin/python"
    assert "win32" not in mac["compatibility"]["platforms"]
    assert bundle.python_of("D:\\RPG_Forge\\", True) == r"D:\RPG_Forge\venv_mcp\Scripts\python.exe"


def test_the_extension_names_the_tools_the_connector_really_has():
    from forge.mcpserver import server
    src = (REPO / "forge" / "mcpserver" / "server.py").read_text(encoding="utf-8")
    listed = [n for n, _ in bundle.TOOLS]
    assert len(set(listed)) == len(listed) == 7
    for n in listed:
        assert f"def {n}(" in src, n                                          # each is a tool the server defines
    tools_line = src[src.index("server._forge_tools = ["):]
    tools_line = tools_line[: tools_line.index("]")]
    assert sorted(listed) == sorted(x.strip().strip('"') for x in tools_line.split("[", 1)[1].replace("\n", " ").split(","))
    assert server.config_block()["rpg-forge"]["args"] == bundle.manifest("x", True)["server"]["mcp_config"]["args"]


def test_the_two_launchers_say_the_extension_way_and_never_ask_william_to_edit_them():
    setup = (REPO / "mcp_setup.bat").read_text(encoding="utf-8")
    ext = (REPO / "mcp_extension.bat").read_text(encoding="utf-8")
    assert "mcp_extension.bat" in setup and "Microsoft Store" in setup
    assert "forge.mcpserver.bundle" in ext and "claude_settings --after-extension" in ext
    assert ext.index("forge.mcpserver.bundle") < ext.index("--after-extension")
    doc = (REPO / "docs" / "MCP.md").read_text(encoding="utf-8")
    for words in ("mcp_extension.bat", "Install Extension", "One name, two ways in", "took_seconds"):
        assert words in doc, words


# ------------------------------------------------------------------------------------------------ one name, two ways in
def test_the_store_install_is_named_and_the_settings_entry_can_be_taken_out_again(tmp_path, capsys, monkeypatch):
    store = tmp_path / "AppData" / "Local" / "Packages" / "Claude_abc" / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
    plain = tmp_path / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    assert claude_settings.is_store_install(store) and not claude_settings.is_store_install(plain)
    assert not claude_settings.is_store_install(None)
    # a Store install of something else (a Python whose temp folder lives under Packages) is not Claude's
    other = tmp_path / "Packages" / "PythonSoftwareFoundation.Python.3.11_x" / "LocalCache" / "Local" / "Temp" / "Claude" / "c.json"
    assert not claude_settings.is_store_install(other)
    store.parent.mkdir(parents=True)
    store.write_text(json.dumps({"mcpServers": {"blender": {"command": "b"}}, "theme": "dark"}), encoding="utf-8")
    block = {"rpg-forge": {"command": "py", "args": ["-m", "forge.mcpserver"], "env": {"PYTHONPATH": "D:/RPG_Forge"}}}
    assert not claude_settings.has_entry(store)
    assert claude_settings.merge(store, block)[0] == "added" and claude_settings.has_entry(store)
    # setting up on a Store install says so, and says the extension way
    monkeypatch.setattr(claude_settings, "settings_file", lambda: store)
    monkeypatch.setattr(claude_settings, "config_block", lambda: block)
    assert claude_settings.main([], ask=lambda _q: "y") == 0
    said = capsys.readouterr().out
    assert "Microsoft Store install" in said and "mcp_extension.bat" in said
    # the tidy-up after the extension: N leaves it, Y takes it out and keeps everything else and a copy
    assert claude_settings.main(["--after-extension"], ask=lambda _q: "n") == 0 and claude_settings.has_entry(store)
    assert "Left as it is" in capsys.readouterr().out
    assert claude_settings.main(["--after-extension"], ask=lambda _q: "Y") == 0
    said = capsys.readouterr().out
    data = json.loads(store.read_text(encoding="utf-8"))
    assert data == {"mcpServers": {"blender": {"command": "b"}}, "theme": "dark"} and "Done: removed" in said
    backups = list(store.parent.glob("claude_desktop_config.before-rpg-forge-removed-*.json"))
    assert len(backups) == 1 and "rpg-forge" in json.loads(backups[0].read_text(encoding="utf-8"))["mcpServers"]
    assert claude_settings.main(["--after-extension"], ask=lambda _q: pytest.fail("nothing to ask")) == 0
    assert "Nothing to tidy" in capsys.readouterr().out
    assert claude_settings.remove(store)[0].startswith("not there") and claude_settings.remove(plain)[0].startswith("there is no")
