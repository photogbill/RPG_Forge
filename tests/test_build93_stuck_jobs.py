"""BUILD 93 — a job left in jobs/running by a window that was closed does not stall the world queue: the queue writes
who claimed a job, and `machine_busy` takes a GPU job for work in progress only while that process is there (or cannot
be asked about)."""
import json
import os
import socket
import subprocess
import sys

from forge import config as cfgmod
from forge.queue import Queue
from forge.threed import world


def _cfg(tmp_path):
    base = cfgmod.load()
    return {**base, "paths": {**base["paths"], "jobs": str(tmp_path / "jobs"), "out": str(tmp_path / "out"), "logs": str(tmp_path / "logs")},
            "allow_external_paths": True}


def _gone_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_a_claim_says_who_has_the_job(tmp_path):
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    q.submit({"type": "render", "name": "a", "prompt": "x"})
    jid, job = q.claim()
    on_disk = json.loads((tmp_path / "jobs" / "running" / f"{jid}.json").read_text())
    assert job["worker"] == on_disk["worker"] == {"pid": os.getpid(), "host": socket.gethostname()}
    q.finish(jid, result={"outputs": []})
    done = json.loads((tmp_path / "jobs" / "done" / f"{jid}.json").read_text())
    assert "worker" not in done and "worker" not in json.loads((tmp_path / "out" / jid / "job.json").read_text())     # only a running job says so
    from forge import dedupe
    assert "worker" in dedupe.RECEIPT_KEYS                                         # so two jobs that differ only in who ran them are the same job


def test_who_is_gone_and_who_is_not():
    here = socket.gethostname()
    assert world.claimer_gone({"worker": {"pid": _gone_pid(), "host": here}}) is True
    assert world.claimer_gone({"worker": {"pid": os.getpid(), "host": here}}) is False            # alive: work in progress
    assert world.claimer_gone({"worker": {"pid": _gone_pid(), "host": "another-computer"}}) is False   # cannot be asked: as before
    assert world.claimer_gone({}) is False and world.claimer_gone({"worker": "x"}) is False       # an older job file: as before
    assert world.claimer_gone({"worker": {"pid": "not a number", "host": here}}) is False


def test_the_world_queue_waits_for_a_live_gpu_job_and_not_for_a_dead_one(tmp_path, monkeypatch):
    from forge.threed import cardlock, comfyapi
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(comfyapi, "is_up", lambda url, timeout=3.0: "8188" in url)       # the art ComfyUI answers; no rigging one
    monkeypatch.setattr(comfyapi, "queue_count", lambda url: 0)
    monkeypatch.setattr(cardlock, "state", lambda *a, **k: {"held": False})
    assert world.machine_busy(cfg, "http://127.0.0.1:8188", "http://127.0.0.1:1") == ""
    run = tmp_path / "jobs" / "running"
    run.mkdir(parents=True, exist_ok=True)
    here = socket.gethostname()
    job = {"id": "J", "type": "render", "name": "a_picture", "prompt": "x"}
    (run / "J.json").write_text(json.dumps({**job, "worker": {"pid": os.getpid(), "host": here}}))
    assert world.machine_busy(cfg, "http://127.0.0.1:8188", "http://127.0.0.1:1") == "the art worker is on a GPU job (render a_picture)"
    (run / "J.json").write_text(json.dumps({**job, "worker": {"pid": _gone_pid(), "host": here}}))
    assert world.machine_busy(cfg, "http://127.0.0.1:8188", "http://127.0.0.1:1") == ""         # the window was closed: the queue goes on
    (run / "J.json").write_text(json.dumps(job))                                                # a file that does not say: as before
    assert "the art worker is on a GPU job" in world.machine_busy(cfg, "http://127.0.0.1:8188", "http://127.0.0.1:1")
    # a CPU job in running never held the queue up, dead or alive
    (run / "J.json").write_text(json.dumps({"id": "J", "type": "remove_bg", "name": "b", "inputs": ["a.png"]}))
    assert world.machine_busy(cfg, "http://127.0.0.1:8188", "http://127.0.0.1:1") == ""


def test_a_file_that_is_not_a_job_does_not_hide_the_jobs_after_it(tmp_path, monkeypatch):
    """A tombstone (what the queue leaves in running/ where a finished job could not be moved) has no type. Reading it
    used to stop the whole look at running/, so a GPU job sorted after it was not seen and the world queue would have
    started a model on top of it."""
    from forge.threed import cardlock, comfyapi
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(comfyapi, "is_up", lambda url, timeout=3.0: "8188" in url)
    monkeypatch.setattr(comfyapi, "queue_count", lambda url: 0)
    monkeypatch.setattr(cardlock, "state", lambda *a, **k: {"held": False})
    run = tmp_path / "jobs" / "running"
    run.mkdir(parents=True, exist_ok=True)
    (run / "A_tombstone.json").write_text(json.dumps({"id": "A", "moved_to": "somewhere", "tombstone": True}))
    (run / "B_unknown.json").write_text(json.dumps({"id": "B", "type": "a_type_from_a_plug_in_that_is_gone", "name": "b"}))
    (run / "C_not_json.json").write_text("{half a file")
    assert world.machine_busy(cfg, "http://127.0.0.1:8188", "http://127.0.0.1:1") == ""           # none of them is work on the card
    (run / "D_live.json").write_text(json.dumps({"id": "D", "type": "render", "name": "d", "prompt": "x",
                                                 "worker": {"pid": os.getpid(), "host": socket.gethostname()}}))
    assert world.machine_busy(cfg, "http://127.0.0.1:8188", "http://127.0.0.1:1") == "the art worker is on a GPU job (render d)"
