"""BUILD 83 Part A — the forge as an MCP connector for Claude Fable and Claude Opus.

✦ William, 2026-11-19 14:22: "Now we need to build MCP into RPG_Forge so that Fable and Opus can utilize it."
The operations run against a forge in a temporary folder. The last test starts the real connector over stdio and talks to it
with the MCP library's own client; it is skipped where the library is not installed (it lives in venv_mcp, not here).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from forge.mcpserver import ops, server

REPO = Path(__file__).resolve().parents[1]


def _cfg(tmp_path, gid="g1", entries=None):
    d = tmp_path / "games" / gid / "wanted_3d"
    d.mkdir(parents=True, exist_ok=True)
    (d / "list.json").write_text(json.dumps({"entries": entries or [{"id": "crate", "kind": "prop", "words": "A crate."}]}),
                                 encoding="utf-8")
    (tmp_path / "games" / gid / "forge.game.json").write_text(json.dumps({"id": gid}), encoding="utf-8")
    for s in ("pending", "running", "done", "failed"):
        (tmp_path / "jobs" / s).mkdir(parents=True, exist_ok=True)
    return {"_root": str(tmp_path), "default_game": gid, "threed": {"out_root": str(tmp_path / "out3d")},
            "paths": {"games": str(tmp_path / "games"), "out": str(tmp_path / "out"), "jobs": str(tmp_path / "jobs"),
                      "logs": str(tmp_path / "logs"), "palettes": str(tmp_path / "palettes"), "models": str(tmp_path / "models")},
            "allow_external_paths": True}


def _tree(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = hashlib.md5(p.read_bytes()).hexdigest()
    return out


def call(cfg, op, inp=None, who="Claude Opus", **kw):
    return ops.handle({"op": op, "input": inp or {}, "who": who, **kw}, cfg)


JOB = {"type": "concept", "name": "inn_dusk", "prompt": "A roadside inn at dusk, lamps lit."}


# ------------------------------------------------------------------------------------------------ the shape of every answer
def test_an_unknown_operation_says_where_to_look(tmp_path):
    a = call(_cfg(tmp_path), "jobs.explode")
    assert a["status"] == "error" and a["code"] == "invalid_input" and "forge_search" in a["next"]


def test_a_change_is_signed_by_a_claude_and_never_as_the_person(tmp_path):
    cfg = _cfg(tmp_path)
    for who in ("", "William", "Bill"):
        a = call(cfg, "jobs.submit", {"job": JOB}, who=who)
        assert a["status"] == "error" and a["code"] == "invalid_input" and "Claude" in a["message"]
    assert not list((tmp_path / "jobs" / "pending").glob("*.json"))


def test_a_missing_field_is_named(tmp_path):
    a = call(_cfg(tmp_path), "world.make_again", {})
    assert a["code"] == "invalid_input" and "id" in a["message"]


# ------------------------------------------------------------------------------------------------ the art queue
def test_a_dry_run_says_what_would_be_queued_and_writes_nothing(tmp_path):
    cfg = _cfg(tmp_path)
    before = _tree(tmp_path)
    a = call(cfg, "jobs.submit", {"job": JOB}, dry_run=True)
    assert a["status"] == "dry_run" and a["files_written"] == 0 and a["jobs"][0]["gpu"] is True
    assert _tree(tmp_path) == before


def test_a_job_is_queued_and_can_be_found(tmp_path):
    cfg = _cfg(tmp_path)
    a = call(cfg, "jobs.submit", {"job": JOB})
    assert a["status"] == "running" and len(a["jobs"]) == 1
    jid = a["jobs"][0]
    j = json.loads((tmp_path / "jobs" / "pending" / f"{jid}.json").read_text(encoding="utf-8"))
    assert j["submitted_by"] == "Claude Opus" and j["prompt"].startswith("A roadside inn")
    g = call(cfg, "jobs.get", {"id": jid})
    assert g["status"] == "done" and g["result"]["job"]["state"] == "pending"
    lst = call(cfg, "jobs.list", {"state": "pending"})
    assert [r["id"] for r in lst["result"]["jobs"]] == [jid]


def test_a_bad_job_is_refused_in_the_forge_s_own_words(tmp_path):
    a = call(_cfg(tmp_path), "jobs.submit", {"job": {"type": "concept", "name": "x"}})
    assert a["status"] == "error" and a["code"] == "refused" and "prompt" in a["message"]


def test_a_retried_call_with_the_same_key_is_never_done_twice(tmp_path):
    cfg = _cfg(tmp_path)
    a = call(cfg, "jobs.submit", {"job": JOB}, key="inn-1")
    b = call(cfg, "jobs.submit", {"job": JOB}, key="inn-1")
    assert a["jobs"] == b["jobs"] and b.get("repeat") is True
    assert len(list((tmp_path / "jobs" / "pending").glob("*.json"))) == 1
    c = call(cfg, "jobs.submit", {"job": {**JOB, "prompt": "Something else."}}, key="inn-1")
    assert c["code"] == "conflict"
    assert len(list((tmp_path / "jobs" / "pending").glob("*.json"))) == 1


def test_a_key_whose_call_never_finished_is_not_guessed_at(tmp_path):
    cfg = _cfg(tmp_path)
    c = ops.Ctx(cfg, "g1", "Claude Opus")
    h = hashlib.sha1(json.dumps({"op": "jobs.submit", "input": {"job": JOB}, "game": "g1"}, sort_keys=True).encode()).hexdigest()[:16]
    ops._write_keys(c, {"k": {"op": "jobs.submit", "hash": h, "at": __import__("time").time(), "state": "in progress"}})
    assert call(cfg, "jobs.submit", {"job": JOB}, key="k")["code"] == "in_progress"
    ops._write_keys(c, {"k": {"op": "jobs.submit", "hash": h, "at": __import__("time").time() - 3600, "state": "in progress"}})
    assert call(cfg, "jobs.submit", {"job": JOB}, key="k")["code"] == "outcome_unknown"


def test_job_types_come_from_the_schema(tmp_path):
    a = call(_cfg(tmp_path), "jobs.types", {"type": "concept"})
    assert a["result"][0]["type"] == "concept" and "prompt" in a["result"][0]["required"]


# ------------------------------------------------------------------------------------------------ the world list
def test_world_things_go_through_the_workbench_s_own_actions(tmp_path):
    cfg = _cfg(tmp_path)
    entry = {"id": "lantern", "kind": "prop", "words": "A brass storm lantern.", "real_size_m": {"height": 0.4}}
    before = _tree(tmp_path)
    d = call(cfg, "world.add", {"entry": entry}, dry_run=True)
    assert d["status"] == "dry_run" and _tree(tmp_path) == before
    a = call(cfg, "world.add", {"entry": entry})
    assert a["status"] == "done" and a["result"]["id"] == "lantern"
    lst = call(cfg, "world.list", {"find": "lantern"})
    assert lst["result"]["items"][0]["id"] == "lantern"
    again = call(cfg, "world.add", {"entry": entry}, dry_run=True)
    assert again["code"] == "conflict"
    h = call(cfg, "world.hold", {"id": "lantern"})
    assert h["status"] == "done"
    assert call(cfg, "world.list", {"find": "lantern"})["result"]["items"][0]["hold"] is True


def test_a_thing_not_on_the_list_is_not_found(tmp_path):
    a = call(_cfg(tmp_path), "world.make_again", {"id": "unicorn"}, dry_run=True)
    assert a["code"] == "not_found"


# ------------------------------------------------------------------------------------------------ approvals (BUILD 78)
def test_approving_is_not_claude_opus_s(tmp_path):
    cfg = _cfg(tmp_path)
    a = call(cfg, "approvals.all", {"page": "world"}, who="Claude Opus")
    assert a["status"] == "needs_approval" and "William" in a["waits_on"]


def test_approving_waits_for_the_person_when_fable_is_not_allowed(tmp_path):
    cfg = _cfg(tmp_path)                       # this made-up game has no approvals.json: the setting is off
    a = call(cfg, "approvals.all", {"page": "world"}, who="Claude Fable", dry_run=True)
    assert a["status"] == "needs_approval"


# ------------------------------------------------------------------------------------------------ every change, dry
def test_every_change_s_dry_run_writes_nothing(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "games" / "g1" / "places").mkdir(parents=True)
    (tmp_path / "games" / "g1" / "places" / "court.place.json").write_text(json.dumps({"id": "court"}), encoding="utf-8")
    sample = {"jobs.submit": {"job": JOB}, "jobs.submit_batch": {"batch": {"batch": "b", "jobs": [JOB]}},
              "world.add": {"entry": {"id": "cup", "kind": "prop", "words": "A tin cup."}}, "world.try_again": {"ids": ["crate"]},
              "world.match_and_release": {"ids": ["crate"]}, "world.release_as_made": {"ids": ["crate"]},
              "world.place_again": {"ids": ["crate"]}, "approvals.all": {"page": "world"}, "approvals.undo": {"uid": "x"},
              "places.compile": {"place": "court"}, "places.take_pictures": {"place": "court"},
              "provide.add": {"title": "t", "why": "w", "helps": "h"}, "mail.to_bill": {"subject": "s", "body": "b"}}
    before = _tree(tmp_path)
    changes = [o for o in ops.OPS.values() if o.kind == "change"]
    assert len(changes) >= 15
    for o in changes:
        inp = sample.get(o.name) or {"id": "crate"}
        a = call(cfg, o.name, inp, who="Claude Fable", dry_run=True)
        assert a["status"] in ("dry_run", "error", "needs_approval"), (o.name, a)
        assert _tree(tmp_path) == before, o.name


# ------------------------------------------------------------------------------------------------ status, places, search
def test_status_shows_what_it_can_and_never_fails(tmp_path):
    a = call(_cfg(tmp_path), "status")
    r = a["result"]
    assert a["status"] == "done" and r["game"] == "g1" and "art_queue" in r and "world_queue" in r
    assert r["world_queue"]["to_make"] == 1 and r["world_queue"]["under_a_day"] is True


def test_places_list_and_show(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "games" / "g1" / "places").mkdir(parents=True)
    (tmp_path / "games" / "g1" / "places" / "court.place.json").write_text(json.dumps({"id": "court", "name": "The court"}),
                                                                          encoding="utf-8")
    assert call(cfg, "places.list")["result"]["places"][0]["id"] == "court"
    s = call(cfg, "places.show", {"place": "court"})
    assert s["status"] == "done" and s["result"]["name"] == "The court" and "areas.check" in s["result"]["area_check"]
    assert call(cfg, "places.show", {"place": "nowhere"})["code"] == "not_found"


def test_search_finds_the_operation_and_its_input():
    r = server.search("approve")
    assert any(o["op"] == "approvals.all" for o in r["operations"])
    r = server.search("concept painting")
    assert any(t["type"] == "concept" for t in r["job_types"])
    assert len(server.search("")["operations"]) == len(ops.OPS)


# ------------------------------------------------------------------------------------------------ pictures
def test_a_picture_is_shown_downsized_and_only_from_inside_the_forge(tmp_path, monkeypatch):
    from PIL import Image
    monkeypatch.setattr(server, "ROOT", tmp_path)
    (tmp_path / "out").mkdir()
    Image.new("RGBA", (3000, 1500), (200, 10, 10, 128)).save(tmp_path / "out" / "big.png")
    data, line = server.picture_bytes("out/big.png", 1024)
    assert data[:2] == b"\xff\xd8" and "3000×1500" in line and "1024×512" in line
    with pytest.raises(ValueError):
        server.picture_bytes(str(tmp_path.parent / "elsewhere.png"))
    with pytest.raises(ValueError):
        server.picture_bytes("out/../../etc/passwd")


# ------------------------------------------------------------------------------------------------ across the process line
def test_an_operation_runs_in_its_own_process_and_answers_in_one_line():
    a = server.run_op({"op": "jobs.types", "input": {"type": "concept"}}, timeout=120)
    assert a["status"] == "done" and a["result"][0]["type"] == "concept"


def test_claude_s_settings_keep_every_other_entry(tmp_path):
    from forge.mcpserver import claude_settings
    p = tmp_path / "claude_desktop_config.json"
    p.write_text(json.dumps({"mcpServers": {"blender": {"command": "uvx", "args": ["blender-mcp"]}}, "other": 1}), encoding="utf-8")
    what, backup = claude_settings.merge(p, server.config_block())
    d = json.loads(p.read_text(encoding="utf-8"))
    assert what == "added" and backup.exists() and d["other"] == 1
    assert set(d["mcpServers"]) == {"blender", "rpg-forge"} and d["mcpServers"]["blender"]["args"] == ["blender-mcp"]
    assert claude_settings.merge(p, server.config_block())[0].startswith("already")
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError):
        claude_settings.merge(p, server.config_block())
    assert p.read_text(encoding="utf-8") == "{ not json"          # a file it can't read is never overwritten


# ------------------------------------------------------------------------------------------------ the real connector, over stdio
def test_the_real_connector_over_stdio():
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "forge.mcpserver"], env=env, cwd=str(REPO))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = sorted(t.name for t in (await s.list_tools()).tools)
                found = await s.call_tool("forge_search", {"query": "world list"})
                types = await s.call_tool("forge_call", {"op": "jobs.types", "input": {"type": "concept"}})
                refused = await s.call_tool("forge_call", {"op": "jobs.submit", "input": {"job": JOB}, "who": "William"})
                media = next(p for p in (REPO / "docs" / "media").iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
                pic = await s.call_tool("forge_pictures", {"path": f"docs/media/{media.name}", "max_side": 256})
                return names, found, types, refused, pic

    names, found, types, refused, pic = asyncio.run(go())
    assert names == sorted(["forge_status", "forge_search", "forge_call", "forge_job", "forge_wait", "forge_area",
                            "forge_pictures"])
    assert "world.list" in found.content[0].text
    assert json.loads(types.content[0].text)["result"][0]["type"] == "concept"
    assert json.loads(refused.content[0].text)["code"] == "invalid_input"
    kinds = [c.type for c in pic.content]
    mime = getattr(pic.content[1], "mime_type", None) or getattr(pic.content[1], "mimeType", None)   # 2.x / 1.x names
    assert kinds == ["text", "image"] and mime == "image/jpeg"
