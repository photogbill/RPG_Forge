"""BUILD 36 — the 3D workshop's methods, job types and stand-in ComfyUI, tested with no graphics card.

The whole line (picture -> body -> skeleton -> motions) runs against a stand-in ComfyUI (forge/threed/standin.py) that
answers like the real one and writes the files a real run would, with planted failures; Blender's steps run against a
stand-in for Blender's Python (tests/fixtures/threed/fake_blender.py). When a real Blender module is at hand
(FORGE_TEST_BPY_PYTHON = a Python with `bpy`), the Blender scripts are also run for real.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from forge.threed import bodies, cardlock, comfyapi, glb, line, motions, rig, rules, standin, template, tidy, trees
from forge.threed.env import RigEnv

REPO = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures" / "threed"
FAKE_BLENDER = [sys.executable, str(FIX / "fake_blender.py")]
BPY = os.environ.get("FORGE_TEST_BPY_PYTHON", "")


def _port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def art(tmp_path):
    srv, si, url = standin.serve(tmp_path / "art_comfy", "art", delay=0.02)
    yield si, url
    srv.shutdown()


def _rigenv(tmp_path) -> RigEnv:
    port = _port()
    cmd = [sys.executable, "-m", "forge.threed.standin", "--kind", "rig", "--port", str(port), "--root", str(tmp_path / "rig"),
           "--delay", "0.02"]
    return RigEnv(root=tmp_path, rig=tmp_path / "rig", port=port, command=cmd, out=tmp_path / "out3d" / "_rig")


def _cfg(tmp_path, url: str, **threed) -> dict:
    return {"_root": str(tmp_path), "comfy": {"url": url}, "threed": {"out_root": str(tmp_path / "out3d"), **threed}}


@pytest.fixture(autouse=True)
def _pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))


# ------------------------------------------------------------------------------------------------ the template
def test_the_copied_template_code_builds_the_exact_requests_the_proven_script_sent():
    """Two requests the first game's trellis_trial.py really sent (2026-11-13, names neutralised) are rebuilt byte for
    byte from the same settings, against the stand-in's knowledge of the nodes."""
    info = json.loads((REPO / "forge" / "threed" / "standin_info_art.json").read_text(encoding="utf-8"))
    tpl = template.load()
    want = json.loads((FIX / "real_request_trellis2_1024.json").read_text(encoding="utf-8"))
    got = template.build_prompt(tpl, info, "forge/trellis_props_1_table.png", "trellis2", 1024, 60000, 2048,
                                "3d/props_1/table__trellis2_r1024")
    assert got == want
    want = json.loads((FIX / "real_request_pixal3d_1024.json").read_text(encoding="utf-8"))
    got = template.build_prompt(tpl, info, "forge/trellis_buildings_1_booth.png", "pixal3d", 1024, 60000, 2048,
                                "3d/buildings_1/booth__pixal3d_r1024")
    assert got == want
    assert not any(n["class_type"] == "ComfySwitchNode" for n in got.values())      # the unused model is cut out
    with pytest.raises(ValueError):
        template.build_prompt(tpl, info, "x.png", "hunyuan", 1024, 1, 1, "p")


# ------------------------------------------------------------------------------------------------ glb, rules, licences
def test_a_glb_is_read_without_blender_and_the_test_dances_are_caught(tmp_path):
    p = glb.box(tmp_path / "b.glb", (0.5, 1.8, 0.3), motions=["Walk_Loop", "Idle_Loop"], joints=3)
    i = glb.info(p)
    assert i["size_m"] == {"width": 0.5, "height": 1.8, "depth": 0.3} and i["floor_y"] == 0.0
    assert i["motions"] == ["Walk_Loop", "Idle_Loop"] and i["skins"] == 1 and i["joints"] == 3 and i["triangles"] == 12
    assert motions.test_dances_in(p) == []
    bad = glb.box(tmp_path / "d.glb", (1, 1, 1), motions=["Walk_Loop", "Hip_Hop_Dancing"], joints=1)
    assert motions.test_dances_in(bad) == ["Hip_Hop_Dancing"]
    assert motions.test_dances_in(tmp_path / "body__mia__capoeira.fbx") == ["capoeira"]
    with pytest.raises(ValueError, match="test dances"):
        motions.refuse_test_dances([p, bad])
    motions.refuse_test_dances([p])
    with pytest.raises(ValueError):
        glb.read_json(tmp_path / "b.glb.prov.json" if False else Path(__file__))


def test_the_rules_warn_and_never_refuse():
    assert rules.apose_check("standing in a relaxed A-pose, arms well away from the body") == []
    hits = rules.apose_check("standing with his arms at his sides, holding a lantern")
    assert "arms at the sides" in hits and "holding something" in hits and "the words never ask for an A-pose" in hits
    assert rules.apose_check("A-pose, no crossed arms, hands empty, not holding a weapon") == []        # negated: fine
    chips = {c["word"] for c in rules.look_chips("a long grey trench coat, a pleated skirt, loose long hair, a tail and wings")}
    assert {"long coat", "skirt or dress", "loose long hair", "tail", "wings"} <= chips
    assert rules.look_chips("short cropped hair, no cape, a fitted jacket") == []
    assert rules.height_check(1.75) == "" and "centimetres" in rules.height_check(175) and rules.height_check("x")
    assert rules.rigger_for("people") == ("mia", False) and rules.rigger_for("animal") == ("unirig", True)
    assert len(rules.KNOWN_FAULTS) >= 5


def test_every_tool_has_a_licence_line_and_the_test_dances_are_not_commercial():
    from forge.threed import licences
    assert licences.all_ok(["flux2_klein_4b", "trellis2", "pixal3d", "comfy_template", "mia", "unirig", "quaternius_ual", "blender"])
    assert not licences.all_ok(["mixamo_test_dances"]) and not licences.all_ok(["something_unknown"])
    assert any("CC0" in l for l in licences.lines(["quaternius_ual"]))


# ------------------------------------------------------------------------------------------------ the card lock
def test_the_card_lock_is_held_by_one_at_a_time_and_a_dead_holder_is_taken_over(tmp_path):
    path = tmp_path / "card.lock"
    a = cardlock.CardLock(None, "first", path=path, check_others=False, poll=0.05)
    a.acquire()
    assert cardlock.state(path=path)["held"] and cardlock.state(path=path)["holder"] == "first"
    b = cardlock.CardLock(None, "second", path=path, check_others=False, poll=0.05, wait_minutes=0.01)
    with pytest.raises(cardlock.CardBusy, match="first"):
        b.acquire()
    a.release()
    assert not cardlock.state(path=path)["held"]
    with cardlock.CardLock(None, "second", path=path, check_others=False, poll=0.05) as l2:
        assert l2.held and cardlock.state(path=path)["holder"] == "second"
    # a holder that stopped beating long ago is taken over
    path.write_text(json.dumps({"holder": "crashed", "pid": 999999, "host": "elsewhere", "since": "earlier", "beat": time.time() - 3600}))
    c = cardlock.CardLock(None, "third", path=path, check_others=False, poll=0.05, wait_minutes=0.05)
    c.acquire()
    assert cardlock.state(path=path)["holder"] == "third"
    c.release()


def test_the_card_lock_waits_while_the_other_comfyui_holds_the_card(tmp_path, art):
    """The 2026-11-13 scripts don't know the lock: a running rigging ComfyUI (or a busy art one) still counts."""
    si, url = art
    env = _rigenv(tmp_path)
    proc = env.start_comfy(tmp_path / "rigcomfy.log")
    try:
        for _ in range(100):
            if env.is_up():
                break
            time.sleep(0.1)
        lk = cardlock.CardLock(None, "art work", path=tmp_path / "card.lock", art_url=url, rig_url=env.url, side="art",
                               poll=0.05, wait_minutes=0.01)
        assert "rigging ComfyUI" in lk.others_busy()
        with pytest.raises(cardlock.CardBusy, match="rigging ComfyUI"):
            lk.acquire()
        assert not (tmp_path / "card.lock").exists()          # a lock it could not use is given straight back
    finally:
        from forge.threed.env import stop
        stop(proc)
    lk = cardlock.CardLock(None, "art work", path=tmp_path / "card.lock", art_url=url, rig_url=env.url, side="art", poll=0.05)
    lk.acquire()
    lk.release()


# ------------------------------------------------------------------------------------------------ bodies
def _spec(objs, **kw):
    d = {"batch": "t", "models": ["trellis2"], "resolutions": [1024], "picture": {"always": "in an A-pose", "negative": "text"},
         "objects": objs}
    d.update(kw)
    return d


def test_bodies_paint_model_resume_and_go_on_past_a_failure(tmp_path, art):
    si, url = art
    cfg = _cfg(tmp_path, url)
    picked = tmp_path / "picked.png"
    picked.write_bytes(standin.png())
    out = tmp_path / "out3d" / "t"
    rows = bodies.run(cfg, _spec([{"id": "a", "prompt": "a person"},
                                  {"id": "b", "image": str(picked)},
                                  {"id": "c_PLANT_FAIL", "image": str(picked)},
                                  {"id": "d_PLANT_NOFILE", "image": str(picked)}]), out)
    by = {r["id"]: r for r in rows}
    assert by["a"]["ok"] and by["b"]["ok"] and not by["c_PLANT_FAIL"]["ok"] and not by["d_PLANT_NOFILE"]["ok"]
    assert "planted failure" in by["c_PLANT_FAIL"]["error"] and "no .glb" in by["d_PLANT_NOFILE"]["error"]
    assert (out / "pictures" / "a.png").exists() and glb.info(out / "models" / "a__trellis2.glb")["triangles"] == 12
    prov = json.loads((out / "models" / "a__trellis2.prov.json").read_text())
    assert prov["picture"]["prompt"] == "a person in an A-pose" and prov["model"] == "trellis2" and prov["commercial_ok"]
    assert any("FLUX.2" in l for l in prov["licences"]) and any("TRELLIS.2" in l for l in prov["licences"])
    assert json.loads((out / "models" / "b__trellis2.prov.json").read_text())["picture"] == {"from_file": str(picked)}
    assert "2 of 4 models made" in (out / "REPORT.txt").read_text()
    assert not cardlock.state(cfg)["held"]                            # the lock was given back
    assert si.freed >= 1                                              # its models were put away
    n = len(si.seen)
    again = bodies.run(cfg, _spec([{"id": "a", "prompt": "a person"}, {"id": "b", "image": str(picked)}]), out)
    assert all(r.get("note") == "already there" for r in again) and len(si.seen) == n      # nothing sent twice


def test_out_of_memory_steps_down_the_resolutions_and_a_hang_is_stopped(tmp_path, art):
    si, url = art
    cfg = _cfg(tmp_path, url)
    pic = tmp_path / "p.png"
    pic.write_bytes(standin.png())
    rows = bodies.run(cfg, _spec([{"id": "big_PLANT_OOM_ONCE", "image": str(pic)}], resolutions=[1536, 1024]), tmp_path / "o1")
    assert rows[0]["ok"] and rows[0]["resolution"] == 1024 and "out of memory" in rows[0]["tries"][0]["error"].lower()
    t0 = time.time()
    rows = bodies.run(cfg, _spec([{"id": "stuck_PLANT_HANG", "image": str(pic)}], seconds_per_model=2), tmp_path / "o2")
    assert not rows[0]["ok"] and "no answer" in rows[0]["error"] and time.time() - t0 < 30
    assert si.interrupted >= 1


def test_bodies_say_so_when_comfyui_is_not_there(tmp_path):
    cfg = _cfg(tmp_path, f"http://127.0.0.1:{_port()}")
    rows = bodies.run(cfg, _spec([{"id": "a", "prompt": "x"}]), tmp_path / "o")
    assert not rows[0]["ok"] and "not answering" in rows[0]["error"]


# ------------------------------------------------------------------------------------------------ skeletons
def test_skeletons_people_keep_their_fingers_animals_get_unirig_and_the_rigging_comfyui_is_stopped(tmp_path, art):
    si, url = art
    env = _rigenv(tmp_path)
    cfg = _cfg(tmp_path, url)
    body = glb.box(tmp_path / "body.glb", (0.5, 1.8, 0.3))
    rows = rig.rig_bodies(cfg, [{"id": "p", "glb": str(body), "kind": "people"},
                                {"id": "dog", "glb": str(body), "kind": "animal"},
                                {"id": "gone", "glb": str(tmp_path / "missing.glb")}], tmp_path / "rig_out", env=env, art_url=url)
    by = {r["body"]: r for r in rows}
    assert by["p"]["ok"] and by["p"]["rigger"] == "mia" and by["dog"]["ok"] and by["dog"]["rigger"] == "unirig"
    assert not by["gone"]["ok"] and "not there" in by["gone"]["error"]
    req = json.loads((tmp_path / "rig_out" / "p__mia.request.json").read_text())
    assert req["3"]["inputs"]["no_fingers"] is False                       # people keep their finger bones
    assert json.loads((tmp_path / "rig_out" / "dog__unirig.request.json").read_text())["3"]["class_type"] == "UniRigAutoRig"
    for f in ("p__mia.fbx", "p__mia_preview.glb", "p__orientation.png", "dog__unirig.fbx", "REPORT.txt"):
        assert (tmp_path / "rig_out" / f).exists(), f
    assert not env.is_up()                                                 # it stopped what it started
    assert not cardlock.state(cfg)["held"]


def test_skeletons_say_so_when_the_rigging_comfyui_is_not_installed(tmp_path):
    env = RigEnv(root=tmp_path, rig=tmp_path / "no_rig", port=_port())
    rows = rig.rig_bodies(_cfg(tmp_path, "http://127.0.0.1:1"), [{"id": "p", "glb": "x.glb"}], tmp_path / "o", env=env)
    assert not rows[0]["ok"] and "not installed" in rows[0]["error"] and "3D tools" in rows[0]["error"]


# ------------------------------------------------------------------------------------------------ Blender steps (stand-in)
def test_motions_tidy_and_trees_through_a_stand_in_blender(tmp_path):
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig")
    lib = glb.box(tmp_path / "lib.glb", (0.5, 1.8, 0.3), motions=["Walk_Loop"], joints=2)
    fbx = tmp_path / "body__mia.fbx"
    fbx.write_bytes(b"fbx")
    r = motions.fit(env, lib, fbx, tmp_path / "m" / "body_moves.glb", height=1.6, travel=lib, skip=["Dance_Loop"], python=FAKE_BLENDER)
    assert r["ok"] and "Dance_Loop" not in r["sheet"]["motions"] and r["sheet"]["left_out"] == ["Dance_Loop"]
    assert motions.speeds(r["sheet"])["Walk_Loop"] == 0.98 and glb.info(tmp_path / "m" / "body_moves.glb")["size_m"]["height"] == 1.6
    bad = motions.fit(env, lib, fbx, tmp_path / "m" / "PLANT_BLENDER_FAIL.glb", python=FAKE_BLENDER)
    assert not bad["ok"] and "planted" in bad["error"]
    assert not motions.fit(env, tmp_path / "nolib.glb", fbx, tmp_path / "x.glb", python=FAKE_BLENDER)["ok"]
    src = glb.box(tmp_path / "prop.glb", (0.7, 1.0, 0.4))
    t = tidy.tidy(env, src, tmp_path / "prop_tidy.glb", size={"width": 1.4}, python=FAKE_BLENDER)
    assert t["ok"] and abs(glb.info(tmp_path / "prop_tidy.glb")["size_m"]["width"] - 1.4) < 1e-3
    g = trees.grow(env, tmp_path / "trees", trees.sheets()[0], 5, python=FAKE_BLENDER)
    assert g["ok"] and g["glb"].endswith("broadleaf_seed5.glb") and len(g["views"]) == 1
    nob = RigEnv(root=tmp_path, rig=tmp_path / "rig")
    assert "no Blender" in motions.fit(nob, lib, fbx, tmp_path / "y.glb")["error"]


def test_species_sheets_come_from_the_forge_and_the_game_wins():
    names = {s["name"]: s for s in trees.sheets()}
    assert {"broadleaf", "young_broadleaf"} <= set(names) and all(s["where"] == "forge" for s in names.values())
    for s in names.values():
        assert set(s["numbers"]) >= {"height", "trunk_radius", "crown_radius"}
    assert set(trees.SLIDERS) <= set(names["broadleaf"]["numbers"])


# ------------------------------------------------------------------------------------------------ the whole line
def test_the_whole_line_against_the_stand_ins_with_one_report(tmp_path, art):
    si, url = art
    env = _rigenv(tmp_path)
    cfg = _cfg(tmp_path, url)
    lib = glb.box(tmp_path / "lib.glb", (0.5, 1.8, 0.3), motions=["Walk_Loop"], joints=2)
    pic = tmp_path / "p.png"
    pic.write_bytes(standin.png())
    spec = {"batch": "line1", "picture": {"always": "A-pose"}, "rig": {}, "motions": {"library": str(lib), "travel": str(lib)},
            "objects": [{"id": "a", "prompt": "a person", "real_size_m": {"height": 1.7}},
                        {"id": "b_PLANT_FAIL", "image": str(pic)},
                        {"id": "cat", "prompt": "a cat", "kind": "animal"},
                        {"id": "d", "prompt": "never dances", "skip_motions": ["Dance_Loop"]}]}
    est = line.estimate(spec)
    assert est["to_make"] == {"pictures": 3, "bodies": 4, "skeletons": 4, "motions": 4} and est["total_seconds"] > 0
    rows = line.run(cfg, spec, env=env, blender_python=FAKE_BLENDER)
    by = {r["id"]: r for r in rows}
    assert by["a"]["motions"] and by["cat"]["motions"] and by["d"]["motions"]
    assert not by["b_PLANT_FAIL"]["body"] and by["b_PLANT_FAIL"]["why"].startswith("3D body")
    out = tmp_path / "out3d" / "line1"
    assert "3 of 4 bodies came through" in (out / "REPORT.txt").read_text()
    assert (out / "models" / "cat__trellis2_welded.glb").exists() and (out / "rig" / "cat__unirig.fbx").exists()
    assert "Dance_Loop" not in json.loads((out / "moves" / "d_moves.json").read_text())["motions"]
    assert json.loads((out / "moves" / "a_moves.json").read_text())["height_m"] == 1.7
    assert line.estimate(spec, line.status(cfg, spec, out))["to_make"]["motions"] == 1         # only the failed one is left
    n = len(si.seen)
    line.run(cfg, spec, env=env, blender_python=FAKE_BLENDER)                                    # resumable
    assert len(si.seen) - n <= 2                                                                 # only the failed body is tried again


# ------------------------------------------------------------------------------------------------ the queue
def test_the_job_types_run_through_the_queue(tmp_path, art):
    from forge import plugins, schema
    from forge.jobs.common import Context
    from forge.queue import Queue, run_worker
    si, url = art
    plugins.load(job_types=schema.JOB_TYPES)
    for t in ("model_3d", "rig_body", "fit_motions", "grow_tree", "line_3d"):
        assert t in schema.JOB_TYPES
    assert schema.needs_gpu({"type": "model_3d"}) and not schema.needs_gpu({"type": "fit_motions", "fbx": "x"})
    assert schema.validate({"type": "rig_body"}) == ["rig_body: missing required field 'glb'"]
    port = _port()
    lib = glb.box(tmp_path / "lib.glb", (0.5, 1.8, 0.3), motions=["Walk_Loop"], joints=2)
    cfg = _cfg(tmp_path, url, rig_root=str(tmp_path / "rig"), rig_port=port, blender_python=FAKE_BLENDER,
               rig_command=[sys.executable, "-m", "forge.threed.standin", "--kind", "rig", "--port", str(port), "--root",
                            str(tmp_path / "rig"), "--delay", "0.02"],
               motion_library=str(lib), motion_travel=str(lib))
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    ctx = Context(cfg=cfg, root=tmp_path)
    handlers = plugins.load(job_types=schema.JOB_TYPES)
    jid = q.submit({"type": "model_3d", "name": "hero", "prompt": "a person", "kind": "body"})
    assert run_worker(q, handlers, ctx, gpu=True, once=True) == 1
    done = json.loads((tmp_path / "jobs" / "done" / f"{jid}.json").read_text())
    res = done["result"]
    assert res["model"] == f"out/{jid}/hero__trellis2.glb" and res["picture"] == f"out/{jid}/picture.png"
    prov = json.loads((tmp_path / "out" / jid / "prov.json").read_text())
    assert prov["kind"] == "model_3d" and "A full-body character reference picture" in prov["picture"]["prompt"]
    assert (tmp_path / "out" / jid / "run.log").read_text().strip()
    rid = q.submit({"type": "rig_body", "name": "hero", "glb": res["model"]})
    run_worker(q, handlers, ctx, gpu=True, once=True)
    rres = json.loads((tmp_path / "jobs" / "done" / f"{rid}.json").read_text())["result"]
    assert rres["rigger"] == "mia" and rres["fbx"].endswith("hero__mia.fbx")
    fid = q.submit({"type": "fit_motions", "name": "hero", "fbx": rres["fbx"], "height": 1.8, "skip": ["Dance_Loop"]})
    run_worker(q, handlers, ctx, gpu=False, once=True)
    fres = json.loads((tmp_path / "jobs" / "done" / f"{fid}.json").read_text())["result"]
    assert "Walk_Loop" in fres["motions"] and "Dance_Loop" not in fres["motions"] and fres["speeds"]["Walk_Loop"] == 0.98
    pid = q.submit({"type": "model_3d", "name": "crate", "prompt": "a wooden crate", "kind": "prop", "real_size_m": {"width": 0.9}})
    run_worker(q, handlers, ctx, gpu=True, once=True)
    pres = json.loads((tmp_path / "jobs" / "done" / f"{pid}.json").read_text())["result"]
    assert pres["engine"] == "trellis2" and pres["tidy"]["pieces_after"] == 1 and abs(pres["info"]["size_m"]["width"] - 0.9) < 1e-3
    assert (tmp_path / "out" / pid / "crate__trellis2_raw.glb").exists()
    bid = q.submit({"type": "model_3d", "name": "hut", "prompt": "a hut", "kind": "building"})
    run_worker(q, handlers, ctx, gpu=True, once=True)
    assert json.loads((tmp_path / "jobs" / "done" / f"{bid}.json").read_text())["result"]["engine"] == "pixal3d"
    tid = q.submit({"type": "grow_tree", "species": "young_broadleaf", "count": 2, "seed": 3})
    run_worker(q, handlers, ctx, gpu=False, once=True)
    tres = json.loads((tmp_path / "jobs" / "done" / f"{tid}.json").read_text())["result"]
    assert [t["seed"] for t in tres["trees"]] == [3, 4]
    xid = q.submit({"type": "model_3d", "name": "nothing"})
    run_worker(q, handlers, ctx, gpu=True, once=True)
    assert "needs a picture" in json.loads((tmp_path / "jobs" / "failed" / f"{xid}.json").read_text())["error"]
    lst = tmp_path / "list.json"
    lst.write_text(json.dumps({"batch": "night", "objects": [{"id": "z", "prompt": "a person"}]}))
    lid = q.submit({"type": "line_3d", "list": str(lst)})
    run_worker(q, handlers, ctx, gpu=True, once=True)
    lres = json.loads((tmp_path / "jobs" / "done" / f"{lid}.json").read_text())["result"]
    assert lres["through"] == 1 and (tmp_path / "out3d" / "night" / "REPORT.txt").exists()
    assert not cardlock.state(cfg)["held"]


def test_the_plugin_loads_without_pulling_in_the_worker_and_the_docs_list_the_types():
    code = ("import sys; import forge.plugins.threed as p; "
            "assert 'forge.jobs' not in sys.modules, 'the plug-in imported forge.jobs at load time'; "
            "assert sorted(p.HANDLERS) == sorted(p.JOB_TYPES); print('ok')")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    doc = (REPO / "docs" / "JOB_TYPES.md").read_text(encoding="utf-8")
    for t in ("model_3d", "rig_body", "fit_motions", "grow_tree", "line_3d"):
        assert f"`{t}`" in doc or f"## {t}" in doc, t


def test_the_3d_code_names_no_game_and_no_character():
    banned = ["turing accords", "turing_accords", "sarah", "valkyrie", "minerva", "aegis", "nemesis", "calliope", "boneyard", "mont ross"]
    for d in ("forge/threed", "forge/plugins/threed.py"):
        for f in sorted((REPO / d).rglob("*") if (REPO / d).is_dir() else [REPO / d]):
            if f.suffix in (".py", ".json", ".md", ".html", ".txt"):
                low = f.read_text(encoding="utf-8", errors="replace").lower()
                assert not [b for b in banned if b in low], (f, [b for b in banned if b in low])


def test_the_stand_in_answers_like_comfyui(tmp_path):
    srv, si, url = standin.serve(tmp_path / "s", "rig", delay=0.01)
    try:
        (si.input / "3d").mkdir(parents=True, exist_ok=True)
        glb.box(si.input / "3d" / "x.glb")
        info = comfyapi.object_info(url)
        assert "3d/x.glb" in info["UniRigLoadMesh"]["input"]["required"]["file_path"][1]["options"]
        bad = comfyapi.post(url, "/prompt", {"prompt": {"1": {"class_type": "NoSuchNode", "inputs": {}}}})
        assert bad["http_error"] == 400 and "NoSuchNode" in json.dumps(bad)
        req = rig.build_rig({"id": "x"}, "mia")
        assert comfyapi.check_against(req, info) == []
        entry = comfyapi.run(url, req, 20, poll=0.05)
        assert entry["status"]["status_str"] == "success" and (si.output / "x__mia_mia.fbx").exists()
        with pytest.raises(RuntimeError, match="mesh not found"):
            comfyapi.run(url, rig.build_rig({"id": "nobody"}, "mia"), 20, poll=0.05)
    finally:
        srv.shutdown()


# ------------------------------------------------------------------------------------------------ real Blender (optional)
@pytest.mark.skipif(not BPY, reason="set FORGE_TEST_BPY_PYTHON to a Python with Blender's bpy to run the Blender scripts for real")
def test_the_blender_scripts_for_real(tmp_path):
    env = RigEnv(root=tmp_path, rig=tmp_path / "rig")
    src = glb.box(tmp_path / "prop.glb", (0.7, 1.0, 0.4))
    t = tidy.tidy(env, src, tmp_path / "tidy.glb", size={"height": 2.0}, python=BPY)
    assert t["ok"], t
    i = glb.info(tmp_path / "tidy.glb")
    assert abs(i["size_m"]["height"] - 2.0) < 1e-3 and abs(i["floor_y"]) < 1e-4
    g = trees.grow(env, tmp_path / "trees", trees.sheets()[1], 7, python=BPY, views=1, size=96, samples=2)
    assert g["ok"], g
    assert glb.info(Path(g["glb"]))["triangles"] > 1000
