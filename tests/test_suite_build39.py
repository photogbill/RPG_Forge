"""BUILD 39 in the suite: 3D -> World list, the world queue's card in 3D -> Runs, and a thing from the world list in
Art -> Review & approve. Runs on a throwaway copy of the example game; nothing real is touched."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from forge.suite import areas, server, threed, world3d
from forge.threed import glb, world as wq
from forge.threed.meshio import Glb

from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

BILL, OPUS = "Bill", "Claude Opus"


def _entry(cfg, eid="barrier", **kw):
    return {"id": eid, "kind": "prop", "tier": "large_prop", "words": "a concrete barrier", "real_size_m": {"width": 3.0},
            "first": {"where": "the approach", "order": 1.0}, **kw}


def test_the_world_list_tab_is_there_and_its_page_and_actions_are_wired(world):  # noqa: F811
    cfg, a, tmp = world
    a3 = next(x for x in areas.AREAS if x["id"] == "3d")
    t = next(t for t in a3["tabs"] if t["id"] == "world")
    assert t["name"] == "World list" and t["t3"] == "world" and t["holds"]
    js = (REPO / "forge" / "suite" / "threed.js").read_text(encoding="utf-8")
    for fn in ("worldTab", "wqDetail", "threed_world_start", "threed_world_stop", "threed_world_straighten", "threed_world_through",
               "threed_world_add", "Stop after this one"):
        assert fn in js, fn
    assert "/api/suite/threed/world" in (REPO / "forge" / "suite" / "server.py").read_text(encoding="utf-8")


def test_adding_holding_and_who_may_do_what(world):  # noqa: F811
    cfg, a, tmp = world
    r = server.act_threed(cfg, "threed_world_add", {"game": "_example", "entry": _entry(cfg)}, OPUS)
    assert r["ok"] and r["id"] == "barrier"
    assert not server.act_threed(cfg, "threed_world_add", {"game": "_example", "entry": _entry(cfg)}, BILL)["ok"]   # already there
    assert not server.act_threed(cfg, "threed_world_add", {"game": "_example", "entry": _entry(cfg)}, None)["ok"]   # sign first
    v = world3d.view(cfg, "_example", with_machine=False)
    assert [i["id"] for i in v["items"]] == ["barrier"] and v["items"][0]["shown"] == "wanted" and v["next"] == "barrier"
    assert v["estimate"]["to_make"] == 1 and set(v["tiers"]) >= {"principal", "crowd", "hand_prop"}
    # the order of need is the person's; holding is anyone's
    r = server.act_threed(cfg, "threed_world_rank", {"game": "_example", "id": "barrier", "rank": 2}, OPUS)
    assert not r["ok"] and "person" in r["message"]
    assert server.act_threed(cfg, "threed_world_rank", {"game": "_example", "id": "barrier", "rank": 2}, BILL)["ok"]
    assert server.act_threed(cfg, "threed_world_hold", {"game": "_example", "id": "barrier", "hold": True}, OPUS)["ok"]
    v = world3d.view(cfg, "_example", with_machine=False)
    assert v["items"][0]["shown"] == "on hold" and v["items"][0]["rank"] == 2 and v["next"] is None
    raw = json.loads((Path(cfg["paths"]["games"]) / "_example" / "wanted_3d" / "barrier.json").read_text())
    assert raw["hold"] is True and raw["rank"] == 2 and raw["added"]["by"] == OPUS
    # starting the launcher and letting a held thing past its checks are the person's
    assert not server.act_threed(cfg, "threed_world_start", {"game": "_example"}, OPUS)["ok"]
    assert not server.act_threed(cfg, "threed_world_through", {"game": "_example", "id": "barrier"}, OPUS)["ok"]
    r = server.act_threed(cfg, "threed_world_stop", {"game": "_example"}, OPUS)
    assert r["ok"] and world3d.view(cfg, "_example", with_machine=False)["stop_asked"]
    # the journal has every one of them, signed
    log = "\n".join(p.read_text(encoding="utf-8") for p in (Path(cfg["paths"]["games"]) / "_example").rglob("journal/*.jsonl"))
    assert "3d:world:barrier" in log and OPUS in log


def test_runs_shows_the_world_queue(world):  # noqa: F811
    cfg, a, tmp = world
    wq.add_entry(cfg, "_example", _entry(cfg), who=BILL)
    r = threed.runs(cfg, "_example")
    w = r["world"]
    assert w["total"] == 1 and w["next"] == "barrier" and w["counts"] == {"wanted": 1} and not w["launcher"]["running"]
    assert "hours" in w["estimate"]["words"] or "minute" in w["estimate"]["words"]


def test_a_made_thing_goes_to_review_with_its_checks_and_is_approved_by_the_person(world):  # noqa: F811
    cfg, a, tmp = world
    wq.add_entry(cfg, "_example", _entry(cfg), who=BILL)
    e = wq.load(cfg, "_example")[0][0]
    out = wq.item_dir(cfg, "_example", "barrier")
    model = glb.box(out / "barrier.glb", (3.0, 0.8, 0.6))
    st = {"state": "made", "tries": 1, "engine": "trellis2", "picture": None, "model": wq._rel(cfg, model), "tidy": {"pieces_after": 1},
          "checks": ["Sits level: 0.2° off level — passes (the limit is 2.0°).", "Blank glass: none."], "check_picture": None}
    st["try"] = wq.to_review(cfg, "_example", e, st)
    wq.write_state(cfg, "_example", "barrier", st)
    rv = threed.review_list(cfg, "_example")
    item = next(x for x in rv["waiting"] if x["id"] == st["try"])
    assert item["from"] == "world" and item["checks"] == st["checks"] and item["commercial_ok"]
    assert any("TRELLIS.2" in l for l in item["licences"]) and any("FLUX.2" in l for l in item["licences"])
    assert item["dest"].endswith("props/barrier.glb") and item["files"] == [st["model"]]
    r = threed.decide(cfg, "_example", st["try"], "approve", BILL)
    assert r["ok"]
    assert wq.status(cfg, "_example")["items"][0]["shown"] == "approved"
    plan = threed.deliver(cfg, "_example", BILL, dry=True)
    assert any(p["what"] == "prop/barrier" for p in plan["plan"])
    assert any(m["kind"] == "world" and m["file"] == st["model"] for m in threed.models(cfg, "_example"))   # in the Viewer too
