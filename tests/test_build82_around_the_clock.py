"""BUILD 82 — art around the clock: the never-stop launcher and the daily redo.

✦ William, 2026-11-19 13:56: "ok, lets build the never stop launcher". No graphics card, nothing generated: the launcher
runs against a stand-in machine on a pretend clock; the redo runs against a world list in a temporary folder.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from forge import around_the_clock as atc
from forge.threed import redo, world


# ------------------------------------------------------------------------------------------------ the stand-ins
class FakeProc:
    def __init__(self):
        self.rc = None

    def poll(self):
        return self.rc


class FakeMachine:
    def __init__(self, tmp_path, t0):
        self.heart = tmp_path / "_around_the_clock.json"
        self.up = False
        self.rig = False
        self.holder = ""
        self.foreign = {"running": False}
        self.marks = 0.0
        self.comfy_starts = 0
        self.procs: list[FakeProc] = []
        self.redos: list[tuple] = []
        self.redo_result = {"again": ["a"], "fresh": [], "released": ["c"], "tired": [], "errors": [], "report": "R.txt"}
        self.redo_raises = None
        self.est = {"to_make": 400, "seconds": 400 * 350, "words": "about 39 hours"}
        self.awake: list[bool] = []
        self.cleared = 0
        self.why_not = ""

    def comfy_up(self):
        return self.up

    def rig_up(self):
        return self.rig

    def card_holder(self):
        return self.holder

    def start_comfy(self):
        if self.why_not:
            return self.why_not
        self.comfy_starts += 1
        return ""

    def queue_state(self):
        return self.foreign

    def start_queue(self):
        p = FakeProc()
        self.procs.append(p)
        return p

    def stop_marks(self):
        return self.marks

    def clear_old_stop(self):
        self.cleared += 1

    def estimate(self):
        return self.est

    def redo(self, releases, approver):
        self.redos.append((releases, approver))
        if self.redo_raises:
            raise self.redo_raises
        return self.redo_result

    def redo_plan(self):
        return {"again": [], "fresh": [], "release": {"count": 0}, "left": [], "tired": []}

    def heart_path(self):
        return self.heart

    def pid_alive(self, pid):
        return True

    def keep_awake(self, on):
        self.awake.append(on)


class T:
    """A pretend clock: 2026-11-19 14:00 local, moved on by hand."""

    def __init__(self):
        self.t = datetime(2026, 11, 19, 14, 0, 0).timestamp()

    def __call__(self):
        return self.t

    def go(self, s):
        self.t += s


@pytest.fixture
def rig(tmp_path):
    t = T()
    m = FakeMachine(tmp_path, t())
    said: list[str] = []
    c = atc.Clock(m, "g1", now=t, sleep=lambda s: None, out=said.append)
    c.started = t()
    return t, m, c, said


def _ticks(t, c, n, every=atc.TICK):
    out = None
    for _ in range(n):
        out = c.tick()
        if out:
            return out
        t.go(every)
    return out


# ------------------------------------------------------------------------------------------------ ComfyUI
def test_a_comfyui_that_is_down_at_the_start_is_started_at_once_and_given_time_to_come_up(rig):
    t, m, c, said = rig
    c.tick()
    assert m.comfy_starts == 1 and any("Starting ComfyUI" in s for s in said)
    _ticks(t, c, 8)                                    # 4 minutes, still not answering: no second start yet
    assert m.comfy_starts == 1
    m.up = True
    c.tick()
    assert c.comfy_failed == 0 and c.comfy_waiting_since is None


def test_comfyui_that_stops_mid_run_is_given_90_seconds_then_started(rig):
    t, m, c, said = rig
    m.up = True
    c.tick()
    m.up = False
    t.go(30)
    c.tick()
    t.go(30)
    c.tick()
    assert m.comfy_starts == 0                         # 30 s down: still within the grace
    t.go(60)
    c.tick()
    assert m.comfy_starts == 1                         # 90 s down: started


def test_comfyui_is_never_started_while_another_step_holds_the_card_or_the_rigging_comfyui_runs(rig):
    t, m, c, said = rig
    m.holder = "rig_body walker"
    _ticks(t, c, 6)
    assert m.comfy_starts == 0
    assert sum("has the graphics card" in s for s in said) == 1        # said once, not every 30 s
    m.holder = ""
    m.rig = True
    _ticks(t, c, 4)
    assert m.comfy_starts == 0 and any("rigging ComfyUI" in s for s in said)
    m.rig = False
    c.tick()
    assert m.comfy_starts == 1


def test_comfyui_starts_are_rate_limited_and_slow_down_after_three_that_did_not_come_up(rig):
    t, m, c, said = rig
    _ticks(t, c, 2 * 60 * 60 // atc.TICK)              # two hours, ComfyUI never comes up
    first_two_hours = m.comfy_starts
    assert 3 <= first_two_hours <= 12                  # every ~10 min at first, then every 30
    assert c.comfy_failed >= atc.COMFY_SLOW_AFTER
    before = m.comfy_starts
    _ticks(t, c, 60 * 60 // atc.TICK)
    assert m.comfy_starts - before <= 2                # the slow pace: about one in 30 minutes


def test_a_reason_comfyui_cannot_be_started_is_said_once(rig):
    t, m, c, said = rig
    m.why_not = "start_comfy.bat is missing — run install_comfy.bat"
    _ticks(t, c, 50)
    assert sum("was not started" in s for s in said) == 1


# ------------------------------------------------------------------------------------------------ the world queue
def test_the_world_queue_is_started_and_started_again_when_it_stops_by_itself(rig):
    t, m, c, said = rig
    m.up = True
    c.tick()
    assert len(m.procs) == 1 and c.proc is m.procs[0]
    m.procs[0].rc = 1                                  # it crashed
    t.go(30)
    c.tick()
    assert c.proc is None and any("stopped by itself" in s for s in said)
    t.go(29)
    c.tick()
    assert len(m.procs) == 1                           # the 30 s back-off is not over yet
    t.go(2)
    c.tick()
    assert len(m.procs) == 2                           # started again
    m.procs[1].rc = 1
    t.go(30)
    c.tick()
    t.go(40)
    c.tick()
    assert len(m.procs) == 2                           # the second stop waits 60 s
    t.go(30)
    c.tick()
    assert len(m.procs) == 3


def test_the_back_off_never_waits_more_than_15_minutes_and_a_crash_loop_is_said_loudly(rig):
    t, m, c, said = rig
    m.up = True
    for _ in range(8):
        if c.next_start > t():
            t.go(c.next_start - t() + 1)
        c.tick()                                       # started (again)
        assert c.proc is not None
        c.proc.rc = 1
        t.go(5)
        c.tick()                                       # seen to have stopped by itself
        assert c.proc is None and c.next_start - t() <= atc.BACKOFF_MAX
    assert any("times in the last hour" in s for s in said)


def test_when_someone_chooses_stop_the_launcher_stops_too(rig):
    t, m, c, said = rig
    m.up = True
    c.tick()
    t.go(600)
    m.marks = t()                                      # 3D -> Runs -> Stop: the queue writes STOP.done and stops
    m.procs[0].rc = 0
    assert c.tick() == "stop asked"
    assert len(m.procs) == 1


def test_a_stop_from_before_the_launcher_started_is_not_meant_for_it(rig):
    t, m, c, said = rig
    m.marks = t() - 3600
    m.up = True
    assert c.tick() is None and len(m.procs) == 1


def test_a_stop_chosen_while_the_queue_waits_to_be_started_again_is_obeyed(rig):
    t, m, c, said = rig
    m.up = True
    c.tick()
    m.procs[0].rc = 1
    t.go(5)
    c.tick()                                           # in its back-off
    t.go(5)
    m.marks = t()
    assert c.tick() == "stop asked"


def test_a_world_queue_started_elsewhere_is_watched_not_doubled(rig):
    t, m, c, said = rig
    m.up = True
    m.foreign = {"running": True, "step": "making", "item": "x"}
    _ticks(t, c, 5)
    assert not m.procs and c.watching
    m.foreign = {"running": False}
    c.tick()
    assert len(m.procs) == 1 and any("started elsewhere has stopped" in s for s in said)


def test_a_world_queue_started_elsewhere_that_was_stopped_on_purpose_stops_the_launcher(rig):
    t, m, c, said = rig
    m.up = True
    m.foreign = {"running": True}
    _ticks(t, c, 3)
    m.foreign = {"running": False}
    m.marks = t()
    assert c.tick() == "stop asked" and not m.procs


# ------------------------------------------------------------------------------------------------ the launcher itself
def test_one_launcher_a_game(rig, tmp_path):
    t, m, c, said = rig
    m.heart.write_text(json.dumps({"pid": 999999, "host": c.host, "step": "the world queue is running", "beat": t() - 10,
                                   "started": t() - 3600}), encoding="utf-8")
    assert c.run(max_ticks=1) == "already running"
    assert not m.procs and not m.awake


def test_a_stale_heartbeat_does_not_block_a_new_launcher(rig):
    t, m, c, said = rig
    m.heart.write_text(json.dumps({"pid": 999999, "host": c.host, "step": "running", "beat": t() - 600}), encoding="utf-8")
    m.up = True
    assert c.run(max_ticks=1) == "ticks"
    assert len(m.procs) == 1 and m.cleared == 1


def test_it_keeps_the_computer_awake_while_it_runs_and_lets_go_after(rig):
    t, m, c, said = rig
    m.up = True
    c.run(max_ticks=2)
    assert m.awake == [True, False]
    hb = json.loads(m.heart.read_text(encoding="utf-8"))
    assert hb["step"] == "stopped" and hb["queue"]["starts"] == 1


# ------------------------------------------------------------------------------------------------ the daily redo, in the launcher
def test_the_redo_runs_at_start_when_never_run_and_then_at_five_the_next_morning(rig):
    t, m, c, said = rig
    m.up = True
    c.tick()
    assert len(m.redos) == 1 and m.redos[0] == (True, "Claude Fable")
    assert any("1 tried again" in s and "1 released" in s for s in said)
    t.go(3 * 3600)
    c.tick()
    assert len(m.redos) == 1                           # not twice in a day
    t.t = datetime(2026, 11, 20, 4, 59).timestamp()
    c.tick()
    assert len(m.redos) == 1
    t.t = datetime(2026, 11, 20, 5, 0, 30).timestamp()
    c.tick()
    assert len(m.redos) == 2


def test_a_redo_from_the_last_launcher_is_remembered(rig):
    t, m, c, said = rig
    m.heart.write_text(json.dumps({"pid": 1, "host": "elsewhere", "step": "stopped", "beat": t() - 7200,
                                   "redo": {"last": t() - 7200}}), encoding="utf-8")
    m.up = True
    c.run(max_ticks=1)
    assert m.redos == []


def test_a_redo_that_fails_is_said_and_stops_nothing(rig):
    t, m, c, said = rig
    m.up = True
    m.redo_raises = RuntimeError("Blender went away")
    assert c.tick() is None
    assert any("did not finish" in s for s in said) and len(m.procs) == 1
    t.go(60)
    c.tick()
    assert len(m.redos) == 1                           # not retried every 30 s


def test_no_redo_and_no_releases_are_honoured(tmp_path):
    t = T()
    m = FakeMachine(tmp_path, t())
    c = atc.Clock(m, "g1", redo=False, now=t, sleep=lambda s: None, out=lambda s: None)
    c.started = t()
    m.up = True
    c.tick()
    assert m.redos == []
    c2 = atc.Clock(m, "g1", releases=False, now=t, sleep=lambda s: None, out=lambda s: None)
    c2.started = t()
    c2.tick()
    assert m.redos == [(False, "Claude Fable")]


# ------------------------------------------------------------------------------------------------ the backlog
def test_the_backlog_is_said_every_hour_and_under_a_day_comes_first(rig):
    t, m, c, said = rig
    m.up = True
    c.tick()
    assert any("400 things" in s for s in said) and not any("UNDER A DAY" in s for s in said)
    m.est = {"to_make": 60, "seconds": 60 * 350, "words": "about 6 hours"}
    t.go(1800)
    c.tick()
    assert not any("60 things" in s for s in said)     # once an hour
    t.go(1800)
    c.tick()
    assert any("60 things" in s and "UNDER A DAY" in s for s in said)
    m.est = {"to_make": 0, "seconds": 0, "words": "nothing to make"}
    t.go(3600)
    c.tick()
    assert any("graphics card is idle" in s for s in said)
    assert c.backlog["to_make"] == 0 and c.backlog["under_a_day"]


# ------------------------------------------------------------------------------------------------ the redo itself (forge/threed/redo.py)
def _cfg(tmp_path, entries, gid="g1"):
    d = tmp_path / "games" / gid / "wanted_3d"
    d.mkdir(parents=True, exist_ok=True)
    (d / "list.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return {"_root": str(tmp_path), "threed": {"out_root": str(tmp_path / "out3d")},
            "paths": {"games": str(tmp_path / "games"), "out": str(tmp_path / "out"), "jobs": str(tmp_path / "jobs")},
            "allow_external_paths": True}


ENTRIES = [
    {"id": "crate", "kind": "prop", "words": "A wooden crate."},
    {"id": "gatehog", "kind": "body", "tier": "crowd", "words": "A feral hog."},
    {"id": "loose", "kind": "prop", "words": "A bicycle."},
    {"id": "kept", "kind": "prop", "words": "A cello.", "hold": True},
    {"id": "fine", "kind": "prop", "words": "A chair."},
]


def _states(cfg):
    world.write_state(cfg, "g1", "crate", {"state": "failed", "error": "ComfyUI went away"})
    world.write_state(cfg, "g1", "gatehog", {"state": "held", "held_by": "picture gate", "why": ["The picture gate: no face."]})
    world.write_state(cfg, "g1", "loose", {"state": "held", "why": ["Loose pieces: 3 parts float free."],
                                           "check_results": [{"check": "loose", "ok": False}]})
    world.write_state(cfg, "g1", "kept", {"state": "held", "why": ["held on purpose"]})
    world.write_state(cfg, "g1", "fine", {"state": "made"})


@pytest.fixture
def no_approvals(monkeypatch):
    from forge.suite import approve_all
    calls = []
    monkeypatch.setattr(approve_all, "world_plan", lambda cfg, gid: {"count": 0, "lines": [], "left": [],
                                                                     "groups": {"repair": ["loose"], "unclear": []}})
    monkeypatch.setattr(approve_all, "may_approve", lambda cfg, gid, who: True)
    monkeypatch.setattr(approve_all, "world_approve_all", lambda cfg, gid, who: calls.append(who) or {"done": [], "refused": []})
    return calls


def test_the_redo_plans_by_the_forge_s_own_buttons(tmp_path, no_approvals):
    cfg = _cfg(tmp_path, ENTRIES)
    _states(cfg)
    p = redo.plan(cfg, "g1")
    assert p["again"] == ["crate"]
    assert sorted(p["fresh"]) == ["gatehog", "loose"]
    assert ("kept", "held on purpose, or waiting for its words") in p["left"]
    assert not any(eid == "loose" for eid, _ in p["left"])          # a loose piece is made again, not left
    assert world.read_state(cfg, "g1", "crate")["state"] == "failed"  # planning changes nothing


def test_the_redo_puts_back_what_can_go_and_writes_its_report(tmp_path, no_approvals):
    cfg = _cfg(tmp_path, ENTRIES)
    _states(cfg)
    r = redo.do(cfg, "g1", now=datetime(2026, 11, 20, 5, 0))
    assert r["again"] == ["crate"] and sorted(r["fresh"]) == ["gatehog", "loose"]
    assert world.read_state(cfg, "g1", "crate")["state"] == "wanted"
    assert world.read_state(cfg, "g1", "gatehog")["state"] == "wanted"
    assert world.read_state(cfg, "g1", "kept")["state"] == "held"    # on purpose: untouched
    assert world.read_state(cfg, "g1", "fine")["state"] == "made"
    rep = world.world_dir(cfg, "g1") / "REDO_2026-11-20.txt"
    assert "Try again (failed)" in rep.read_text(encoding="utf-8")
    counts = json.loads((world.world_dir(cfg, "g1") / "_redo_counts.json").read_text(encoding="utf-8"))
    assert counts["crate"]["n"] == 1 and counts["crate"]["hash"]
    assert no_approvals == []                          # nothing to release: BUILD 78's button not pressed


def test_three_times_put_back_and_still_not_past_goes_to_needs_better_words(tmp_path, no_approvals):
    cfg = _cfg(tmp_path, ENTRIES[:1])
    for day in range(3):
        world.write_state(cfg, "g1", "crate", {"state": "failed", "error": "the same miss"})
        r = redo.do(cfg, "g1", now=datetime(2026, 11, 20 + day, 5, 0))
        assert r["again"] == ["crate"]
    world.write_state(cfg, "g1", "crate", {"state": "failed", "error": "the same miss"})
    r = redo.do(cfg, "g1", now=datetime(2026, 11, 23, 5, 0))
    assert r["again"] == [] and r["tired"][0]["id"] == "crate"
    assert world.read_state(cfg, "g1", "crate")["state"] == "failed"
    nb = (world.world_dir(cfg, "g1") / "NEEDS_BETTER_WORDS.md").read_text(encoding="utf-8")
    assert "| crate |" in nb and "the same miss" in nb


def test_the_count_starts_over_when_its_words_change(tmp_path, no_approvals):
    cfg = _cfg(tmp_path, ENTRIES[:1])
    counts = {"crate": {"n": 3, "hash": "not-the-same", "history": []}}
    (world.world_dir(cfg, "g1")).mkdir(parents=True, exist_ok=True)
    (world.world_dir(cfg, "g1") / "_redo_counts.json").write_text(json.dumps(counts), encoding="utf-8")
    world.write_state(cfg, "g1", "crate", {"state": "failed"})
    r = redo.do(cfg, "g1")
    assert r["again"] == ["crate"]
    c = json.loads((world.world_dir(cfg, "g1") / "_redo_counts.json").read_text(encoding="utf-8"))["crate"]
    assert c["n"] == 1


def test_releases_go_through_build_78_and_only_when_the_setting_allows(tmp_path, monkeypatch):
    from forge.suite import approve_all
    cfg = _cfg(tmp_path, ENTRIES[:1])
    calls = []
    monkeypatch.setattr(approve_all, "world_plan", lambda cfg, gid: {"count": 2, "lines": ["2 go"], "left": [],
                                                                     "groups": {"repair": [], "unclear": []}})
    monkeypatch.setattr(approve_all, "world_approve_all",
                        lambda cfg, gid, who: calls.append(who) or {"done": [{"id": "x"}, {"id": "y"}], "refused": [],
                                                                     "message": "2 released, signed Claude Fable, for William."})
    monkeypatch.setattr(approve_all, "may_approve", lambda cfg, gid, who: True)
    r = redo.do(cfg, "g1")
    assert calls == ["Claude Fable"] and r["released"] == ["x", "y"]
    monkeypatch.setattr(approve_all, "may_approve", lambda cfg, gid, who: False)
    r = redo.do(cfg, "g1")
    assert calls == ["Claude Fable"] and r["released"] == [] and "is off" in r["release_skipped"]
    r = redo.do(cfg, "g1", releases=False)
    assert calls == ["Claude Fable"] and "switched off" in r["release_skipped"]
