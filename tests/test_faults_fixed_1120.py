"""Faults found on 2026-11-19 and fixed on 2026-11-20 (William: "When you find faults, if you can fix them please do."):
the put-in report names the tests that fail, and a materials command stopped with Ctrl+C leaves no job behind.
(The tiler's fault has its tests in test_night4_tools.py; the stuck-job faults in test_build93_stuck_jobs.py.)"""
import json

import pytest

from forge import config as cfgmod


# ------------------------------------------------------------------ put_in_waiting_changes.bat: its report names names
def _package(tmp_path):
    from forge import sync_when_idle as sw
    pkg = tmp_path / "_xfer" / "waiting" / "tonight"
    f = pkg / "files" / "a" / "new.py"
    f.parent.mkdir(parents=True)
    f.write_text("x = 1\n", encoding="utf-8")
    (pkg / "manifest.json").write_text(json.dumps({"title": "tonight", "tests": ["tests/test_a.py"],
                                                   "files": [{"path": "a/new.py", "base_md5": None, "new_md5": sw.md5(f)}]}), encoding="utf-8")
    return pkg


def _in_a_folder(tmp_path, monkeypatch, runs):
    """`_one` against a forge in a folder (its own check / apply / put_back, pointed at that folder), with pytest's
    answers given: `runs` = [(the failing tests, pytest's last line), …] for 'before' then 'after'."""
    from forge import sync_when_idle as sw
    root = tmp_path / "forge_root"
    root.mkdir()
    check, apply, put_back = sw.check, sw.apply, sw.put_back
    monkeypatch.setattr(sw, "check", lambda p, r=None: check(p, root))
    monkeypatch.setattr(sw, "apply", lambda p, r=None: apply(p, root))
    monkeypatch.setattr(sw, "put_back", lambda p, applied, r=None: put_back(p, applied, root))
    it = iter(runs)
    monkeypatch.setattr(sw, "_failing", lambda tests: next(it))
    return sw, root


def test_a_failure_that_was_there_before_is_named_in_the_report(tmp_path, monkeypatch):
    """Until now the report kept only pytest's last line ("1 failed, 24 passed"). One test failed on the PC, before and
    after every package, from 2026-11-18 — and nobody could say which without sitting at the window."""
    old = "tests/test_suite_x.py::test_the_time_zone"
    sw, root = _in_a_folder(tmp_path, monkeypatch, [({old}, "1 failed, 24 passed"), ({old}, "1 failed, 52 passed")])
    pkg, said = _package(tmp_path), []
    assert sw._one({}, pkg, said.append) == 0 and (root / "a" / "new.py").read_text() == "x = 1\n"
    rep = (pkg / "APPLIED.txt").read_text(encoding="utf-8")
    assert f"failing before the change: {old}" in rep and f"failing after it as well (not this package's): {old}" in rep
    assert any(old in s for s in said) and any("not this package's" in s for s in said)


def test_a_new_failure_still_puts_everything_back_and_a_clean_run_says_nothing_extra(tmp_path, monkeypatch):
    new = "tests/test_a.py::test_broken_by_this"
    sw, root = _in_a_folder(tmp_path, monkeypatch, [(set(), "24 passed"), ({new}, "1 failed, 23 passed")])
    pkg, said = _package(tmp_path), []
    assert sw._one({}, pkg, said.append) == 1 and not (root / "a" / "new.py").exists()
    assert new in (pkg / "NOT_APPLIED.txt").read_text(encoding="utf-8") and not (pkg / "APPLIED.txt").exists()
    (tmp_path / "second").mkdir()
    sw2, root2 = _in_a_folder(tmp_path / "second", monkeypatch, [(set(), "24 passed"), (set(), "25 passed")])
    pkg2 = _package(tmp_path / "second")
    assert sw2._one({}, pkg2, said.append) == 0
    assert "failing" not in (pkg2 / "APPLIED.txt").read_text(encoding="utf-8")


# ------------------------------------------------------------------ a materials command stopped with Ctrl+C
def test_ctrl_c_in_a_materials_command_leaves_no_job_in_running(tmp_path, monkeypatch):
    from forge import schema
    from forge.materials import __main__ as mm
    schema.validate({"type": "material_mix", "inputs": ["a"]})        # the plug-ins are loaded now (a later load would undo the stand-in)
    from forge.plugins import materials as plug
    base = cfgmod.load()
    cfg = {**base, "paths": {**base["paths"], "jobs": str(tmp_path / "jobs"), "out": str(tmp_path / "out"), "logs": str(tmp_path / "logs")},
           "allow_external_paths": True}

    def stopped(job, ctx, out):
        raise KeyboardInterrupt

    monkeypatch.setitem(plug.HANDLERS, "material_mix", stopped)
    with pytest.raises(KeyboardInterrupt):
        mm.submit_and_run(cfg, [{"type": "material_mix", "name": "mix_a", "inputs": ["a", "b", "c"]}], "materials/test")
    assert not list((tmp_path / "jobs" / "running").glob("*.json"))
    (failed,) = (tmp_path / "jobs" / "failed").glob("*.json")
    assert "stopped before it finished" in json.loads(failed.read_text())["error"]


# ------------------------------------------------------------------ a tileable Filter Forge set, and the game's normal
def test_a_tileable_filter_forge_set_gets_the_games_normal_healed_with_it(tmp_path):
    """`tileable: true` healed each raw channel but left the game's own normal (<slot>_n.png) as it was rendered, so the
    healed colour had nothing to sit on. Now there is a <slot>_n_tile.png, cut by the same geometry and flipped the
    same way as <slot>_n.png."""
    import xml.etree.ElementTree as ET
    import numpy as np
    from PIL import Image
    from forge.ops import lighting
    from forge.night3b import ffdriver as ff
    from test_filter_forge import fixture_filter
    from test_scene import ctx_with
    from test_night4_tools import _texture

    def renderer(exe, task_file, out, timeout):                     # a set that does NOT tile; the normal DirectX-style
        t = ET.parse(task_file).getroot()
        yy, xx = np.mgrid[0:96, 0:128]
        h = np.clip(np.hypot(xx - 30, yy - 70) / 110.0, 0, 1)
        for task in t.findall("Task"):
            res = task.find("Result").get("path")
            ch = res.rsplit("_", 1)[1][:-4]
            if ch == "final":
                _texture(4, 128, 96).save(res)
            elif ch == "height":
                Image.fromarray((h * 65535).astype(np.uint16)).save(res)
            elif ch == "normal":
                lighting.normal_map(Image.fromarray((h * 255).astype(np.uint8)).convert("RGB"), invert_y=True).save(res[:-4] + "-normal.png")
        return 0, f"Tasks completed {len(t.findall('Task'))}. Tasks failed 0.\n"

    out = tmp_path / "out" / "FF9"
    out.mkdir(parents=True)
    job = {"id": "FF9", "type": "filter_forge", "name": "ff9", "filter": str(fixture_filter(tmp_path)), "size": [128, 96],
           "channels": {"final": 0, "normal": 4, "height": 5}, "slot_name": "ground", "tileable": True, "tile_band": 0.2}
    res = ff.render(job, ctx_with(None), out, runner=renderer)
    til = res["measured"]["tileable"]
    assert til["final"]["shift"] == til["normal"]["shift"] == til["height"]["shift"] and til["final"]["lead"] == "final"
    assert "ground_n_tile.png" in res["outputs"] and (out / "ground_n_tile.png").is_file()
    raw = np.asarray(Image.open(out / til["normal"]["file"]).convert("RGB")).astype(int)
    game = np.asarray(Image.open(out / "ground_n_tile.png")).astype(int)
    assert res["measured"]["normal_flipped_by_forge"] is True
    assert np.abs(game[..., 1] - (255 - raw[..., 1])).max() <= 1 and np.abs(game[..., 0] - raw[..., 0]).max() <= 1     # the same flip as ground_n.png
    assert not np.array_equal(game, np.asarray(Image.open(out / "ground_n.png")).astype(int))                        # and it is the healed one
