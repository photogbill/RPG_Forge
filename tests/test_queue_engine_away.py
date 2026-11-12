"""2026-11-11: ComfyUI crashed at 19:17 and the worker failed every queued job in seconds ('not reachable'). Now a job
that finds ComfyUI away goes back to pending and the worker waits; a job that keeps losing ComfyUI mid-render is failed
after COMFY_RELEASES tries (it may be what crashes it)."""
from __future__ import annotations
import json
from types import SimpleNamespace

from forge import queue as qmod
from forge.queue import Queue, run_worker


class FakeComfy:
    def __init__(self, ups):
        self.ups = list(ups)
        self.url = "http://127.0.0.1:8188"

    def is_up(self):
        return self.ups.pop(0) if self.ups else True


def _job():
    return {"type": "render", "name": "x", "prompt": "a cat", "checkpoint": "a.safetensors", "seed": 1, "size": [64, 64]}


def test_engine_away_before_the_job_puts_it_back_and_waits(tmp_path, monkeypatch):
    monkeypatch.setattr(qmod.time, "sleep", lambda s: None)
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    jid = q.submit(_job())
    calls = {"n": 0}

    def render(job, ctx, out):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise RuntimeError("ComfyUI is not reachable at http://127.0.0.1:8188 — start it")
        return {"outputs": []}

    ctx = SimpleNamespace(comfy=FakeComfy([False, True, True, True]))
    run_worker(q, {"render": render}, ctx, gpu=True, once=True)
    assert (tmp_path / "jobs" / "done" / f"{jid}.json").exists()
    assert not list((tmp_path / "jobs" / "failed").glob("*.json"))
    assert "comfy_waits" not in json.loads((tmp_path / "jobs" / "done" / f"{jid}.json").read_text(encoding="utf-8"))


def test_a_job_that_keeps_losing_comfy_mid_render_is_failed_after_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(qmod.time, "sleep", lambda s: None)
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    jid = q.submit(_job())

    def render(job, ctx, out):
        raise ConnectionResetError("[WinError 10054] An existing connection was forcibly closed by the remote host")

    run_worker(q, {"render": render}, SimpleNamespace(comfy=FakeComfy([])), gpu=True, once=True)
    f = tmp_path / "jobs" / "failed" / f"{jid}.json"
    assert f.exists() and json.loads(f.read_text(encoding="utf-8"))["comfy_waits"] == qmod.COMFY_RELEASES


def test_a_real_error_still_fails_at_once(tmp_path, monkeypatch):
    monkeypatch.setattr(qmod.time, "sleep", lambda s: None)
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    jid = q.submit(_job())

    def render(job, ctx, out):
        raise ValueError("bad prompt")

    run_worker(q, {"render": render}, SimpleNamespace(comfy=FakeComfy([])), gpu=True, once=True)
    assert (tmp_path / "jobs" / "failed" / f"{jid}.json").exists()
