"""BUILD 29b — Art → Floor plans: candidates side by side, paint on the grid with the checks live, save (then protected),
approve (a person's; the maps go into the game, never over another), send by mail with the paint guide."""
from __future__ import annotations
import json, threading, urllib.request

import pytest

from forge.layout import store
from forge.suite import areas, floorplans, games, mail, server, settings
from test_suite_build01 import REPO, world  # noqa: F401


@pytest.fixture
def fp(world):
    cfg, a, tmp = world
    settings.set_identity("Bill")
    return cfg, a, tmp


def _first(cfg):
    return floorplans.generate(cfg, "_example", "ember_crossing", "after", None, 2, "Bill")["made"]


def test_the_tab_is_in_art(fp):
    cfg, _a, _t = fp
    art = next(x for x in areas.AREAS if x["id"] == "art")
    assert "floorplans" in [t["id"] for t in art["tabs"]]


def test_generate_four_then_reroll_takes_the_next_seed(fp):
    cfg, _a, tmp = fp
    made = floorplans.generate(cfg, "_example", "ember_crossing", "after", None, 4, "Bill")
    assert made["archetype"] == "toll_kingdom" and [c["seed"] for c in made["made"]] == [1, 2, 3, 4]
    again = floorplans.generate(cfg, "_example", "ember_crossing", "after", None, 1, "Bill")
    assert [c["seed"] for c in again["made"]] == [5]
    v = floorplans.view(cfg, "_example")
    assert len(v["candidates"]) == 5 and v["sheets"] and v["paint"]["wall"].startswith("#") and v["owner"] == "Bill"
    with pytest.raises(floorplans.FloorPlanRefused):
        floorplans.generate(cfg, "_example", "nowhere", "after", None, 1, "Bill")


def test_open_paint_check_save_and_then_it_is_protected(fp):
    cfg, _a, tmp = fp
    c = _first(cfg)[0]
    s = floorplans.open_set(cfg, "_example", c["folder"])
    m = s["map"]
    assert s["problems"] == [] and len(s["maps"]) >= 2 and len(m["rows"]) == m["h"]
    start = next(e for e in m["entities"] if e["type"] == "spawn" and e["name"] == "start")
    # wall the spawn in: the live check says so, and nothing is written
    edits = [[start["x"] + dx, start["y"] + dy, "wall"] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
             if 0 < start["x"] + dx < m["w"] - 1 and 0 < start["y"] + dy < m["h"] - 1]
    r = floorplans.check(cfg, "_example", c["folder"], m["id"], edits)
    assert not r["ok"] and any("can't be reached" in p for p in r["problems"])
    assert floorplans.open_set(cfg, "_example", c["folder"])["map"]["rows"] == m["rows"]
    # the outer edge stays closed
    r2 = floorplans.check(cfg, "_example", c["folder"], m["id"], [[0, 3, "floor"]])
    assert not r2["ok"] and "outer edge" in r2["problems"][0]
    # a harmless edit saved: the rows change, the folder is protected (a reroll never writes over it)
    x, y = next((x, y) for y, row in enumerate(m["rows"]) for x, ch in enumerate(row)
                if ch == "." and 2 < x < m["w"] - 3 and 2 < y < m["h"] - 3)
    saved = floorplans.save(cfg, "_example", c["folder"], m["id"], [[x, y, "rubble"]], "Bill")
    assert saved["edited"].startswith("Bill") and "edited" in saved["protected"]
    assert floorplans.open_set(cfg, "_example", c["folder"])["map"]["rows"][y][x] == ","
    top, _s = store.load_set(floorplans._folder(cfg, "_example", c["folder"]))
    with pytest.raises(store.LayoutError):
        store.write(top, floorplans._folder(cfg, "_example", c["folder"]), games.adapter(cfg, "_example"))
    # moving the story element
    st = floorplans.open_set(cfg, "_example", c["folder"])["map"]["story"]
    r3 = floorplans.check(cfg, "_example", c["folder"], m["id"], [[st["x"] + 1, st["y"], "story"]])
    assert isinstance(r3["problems"], list)


def test_approve_is_a_persons_and_puts_the_maps_in_the_game(fp):
    cfg, a, tmp = fp
    c = _first(cfg)[1]
    with pytest.raises(floorplans.FloorPlanRefused):
        floorplans.approve(cfg, "_example", c["folder"], "Claude Opus")
    r = floorplans.approve(cfg, "_example", c["folder"], "Bill")
    assert r["approved_by"] == "Bill" and r["installed"]
    assert all((a.root / f).exists() for f in r["installed"])
    with pytest.raises(floorplans.FloorPlanRefused):
        floorplans.save(cfg, "_example", c["folder"], r["top"], [[3, 3, "rubble"]], "Bill")
    with pytest.raises(floorplans.FloorPlanRefused):
        floorplans.approve(cfg, "_example", c["folder"], "Bill")      # already approved


def test_send_to_the_owner_with_the_paint_guide(fp):
    cfg, a, tmp = fp
    c = _first(cfg)[0]
    r = floorplans.send(cfg, "_example", c["folder"], "", "Claude Opus")
    assert r["to"] == "Bill"
    letters = mail.listing(a.root, "Bill", "inbox") if hasattr(mail, "listing") else None
    p = next((a.root / "mail" / "to_bill").glob(f"{r['letter']}.md"))
    text = p.read_text(encoding="utf-8")
    assert "paintguide.png" in text and "right layout" in text


def test_nothing_outside_the_out_folder_is_served(fp):
    cfg, _a, tmp = fp
    with pytest.raises(floorplans.FloorPlanRefused):
        floorplans._folder(cfg, "_example", "../../games")
    with pytest.raises(floorplans.FloorPlanRefused):
        floorplans.open_set(cfg, "_example", "../../../")


def test_the_screen_over_http(fp):
    cfg, _a, tmp = fp
    s = server.make_server(cfg, 0)
    th = threading.Thread(target=s.serve_forever, daemon=True)
    th.start()
    port = s.server_address[1]
    try:
        def post(action, body):
            rq = urllib.request.Request(f"http://127.0.0.1:{port}/api/suite/act/{action}", data=json.dumps(body).encode(),
                                        headers={"Content-Type": "application/json", "X-Forge": "1"}, method="POST")
            return json.loads(urllib.request.urlopen(rq).read())
        r = post("floorplan_generate", {"game": "_example", "place": "ember_crossing", "era": "war", "count": 1})
        assert r["ok"] and len(r["made"]) == 1
        f = r["made"][0]["folder"]
        d = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/suite/floorplans?id=_example").read())
        assert any(c["folder"] == f for c in d["candidates"])
        img = urllib.request.urlopen(f"http://127.0.0.1:{port}/suite/layoutimg?id=_example&f={f}&file={r['made'][0]['guide']}&w=200")
        assert img.headers["Content-Type"].startswith("image/")
        o = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/suite/floorplan?id=_example&f={f}").read())
        assert o["map"]["w"] > 10
        bad = post("floorplan_check", {"game": "_example", "folder": f, "map": o["map"]["id"], "edits": [[0, 0, "floor"]]})
        assert bad["ok"] and bad["problems"]
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/suite/layoutimg?id=_example&f={f}&file=../../plan_set.json")
    finally:
        s.shutdown()
