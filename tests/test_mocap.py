"""Motion capture (2026-11-15) — the takes list is kept forge-side (games/<game>/mocap_takes.json); a take needs its
title, character and what to perform; statuses move forward only with the footage's whereabouts; the tab exists, the
page and its script are served, and the actions are signed. All on a throwaway copy of the example game."""
from __future__ import annotations
import json, urllib.request

import pytest

from forge.suite import areas, mocap, server
from test_suite_build01 import world  # noqa: F401 — the shared throwaway world

BILL = "Bill"


def test_a_take_is_kept_forge_side_and_needs_its_words(world):
    cfg, a, tmp = world
    t = mocap.add(cfg, "_example", by=BILL, title="The bow", who="the heroine", perform="a deep bow, then a second")
    assert mocap.path(cfg, "_example").is_file() and t["status"] == "needed" and t["id"] == "the_bow"
    assert mocap.add(cfg, "_example", by=BILL, title="The bow", who="x", perform="y")["id"] == "the_bow_2"
    with pytest.raises(mocap.MocapRefused):
        mocap.add(cfg, "_example", by=BILL, title="", who="x", perform="y")
    with pytest.raises(mocap.MocapRefused):
        mocap.add(cfg, "_example", by="", title="t", who="x", perform="y")
    with pytest.raises(mocap.MocapRefused):
        mocap.add(cfg, "_example", by=BILL, title="t", who="x", perform="y", priority="whenever")


def test_filmed_needs_the_footage_and_every_change_is_signed(world):
    cfg, a, tmp = world
    t = mocap.add(cfg, "_example", by=BILL, title="The run", who="the heroine", perform="a run and a stop")
    with pytest.raises(mocap.MocapRefused):
        mocap.set_field(cfg, "_example", t["id"], "status", "filmed", BILL)
    mocap.set_field(cfg, "_example", t["id"], "footage", "D:/footage/run_take1.mp4", BILL)
    r = mocap.set_field(cfg, "_example", t["id"], "status", "filmed", BILL)
    assert r["status"] == "filmed" and len(r["history"]) == 3
    with pytest.raises(mocap.MocapRefused):
        mocap.set_field(cfg, "_example", t["id"], "by", "someone", BILL)
    with pytest.raises(mocap.MocapRefused):
        mocap.set_field(cfg, "_example", t["id"], "status", "lost", BILL)
    with pytest.raises(FileNotFoundError):
        mocap.set_field(cfg, "_example", "nope", "notes", "x", BILL)
    v = mocap.view(cfg, "_example")
    assert v["counts"]["filmed"] == 1 and v["guide"] and v["takes"][-1]["status"] == "filmed"


def test_the_tab_is_in_the_sidebar():
    ar = next(x for x in areas.AREAS if x["id"] == "mocap")
    assert [t["id"] for t in ar["tabs"]] == ["takes", "howto"] and all(t["screen"] == "mocap" for t in ar["tabs"])
