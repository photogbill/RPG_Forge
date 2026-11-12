"""User Needs To Provide Image (2026-11-11) — the forge pool (games/<game>/provide_requests.json) becomes task cards for
the game's owner, once; on-hold requests wait; the Art tab exists and shows the cards; a dropped picture lands where the
request says. All on a throwaway copy of the example game."""
from __future__ import annotations
import http.client, json, urllib.request
from datetime import datetime

import pytest

from forge.suite import areas, orders, provide, server, settings, tasks
from test_suite_build01 import world  # noqa: F401 — the shared throwaway world

T = datetime(2026, 11, 11, 18, 0, 0)
BILL, OPUS = "Bill", "Claude Opus"
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00"
       b"\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def w(world, monkeypatch):
    cfg, a, tmp = world
    monkeypatch.setattr(settings, "now", lambda path=None: T)
    areas._badge_cache.clear()
    return cfg, a, tmp


def _req(cfg, **kw):
    base = dict(by=OPUS, title="A photo of the harbor at dusk", why="the model invents a different harbor every time",
                helps="one photo of any small harbor at dusk")
    base.update(kw)
    return provide.add(cfg, "_example", **base)


def test_a_request_is_kept_forge_side_and_needs_its_why_and_what_helps(w):
    cfg, a, _ = w
    r = _req(cfg, count=2)
    assert provide.path(cfg, "_example").is_file()
    assert r["id"] == "a_photo_of_the_harbor_at_dusk" and r["goes_to"] == "reference/provided/a_photo_of_the_harbor_at_dusk"
    assert _req(cfg)["id"] == "a_photo_of_the_harbor_at_dusk_2"          # same title → a new id, never a clash
    with pytest.raises(provide.ProvideRefused):
        provide.add(cfg, "_example", OPUS, "x", "", "y")
    with pytest.raises(provide.ProvideRefused):
        provide.add(cfg, "_example", OPUS, "x", "y", "z", kind="audio")


def test_sync_files_open_requests_once_for_the_owner_and_skips_on_hold(w):
    cfg, a, _ = w
    _req(cfg, rid="harbor")
    _req(cfg, rid="tower", title="The tower layout", status="on_hold", hold_until="the next bake-off")
    r = provide.sync(cfg, "_example")
    assert r == {"filed": ["harbor"], "unreachable": False}
    assert provide.sync(cfg, "_example")["filed"] == []                   # idempotent
    o = [x for x in orders.listing(a.root, BILL) if x.get("provide")]
    assert len(o) == 1 and o[0]["provide"] == "harbor" and o[0]["for"] == BILL and o[0]["by"] == OPUS
    assert o[0]["wants"] == {"kind": "image", "count": 1} and o[0]["goes_to"] == "reference/provided/harbor"
    assert "Why the forge can't make it" in o[0]["detail"] and "What would help" in o[0]["detail"]
    # a dismissed/closed order is never re-filed
    orders.close(a.root, o[0]["id"], BILL, status="dropped")
    assert provide.sync(cfg, "_example")["filed"] == []
    # opening the held one files it
    provide.set_status(cfg, "_example", "tower", "open")
    assert provide.sync(cfg, "_example")["filed"] == ["tower"]


def test_extra_fields_never_replace_an_orders_own(w):
    cfg, a, _ = w
    o = orders.add(a.root, OPUS, BILL, "x", extra={"provide": "p", "title": "hijack", "status": "done"})
    assert o["provide"] == "p" and o["title"] == "x" and o["status"] == "open"


def test_the_cards_are_marked_and_the_view_lists_the_pool(w):
    cfg, a, _ = w
    _req(cfg, rid="harbor")
    _req(cfg, rid="tower", title="The tower layout", status="on_hold")
    v = provide.view(cfg, "_example", BILL)
    assert [c["provide"] for c in v["cards"]] == ["harbor"] and v["cards"][0]["area"] == "art"
    assert v["cards"][0]["wants"]["kind"] == "image"
    st = {r["id"]: r["state"] for r in v["pool"]}
    assert st == {"harbor": "waiting on you", "tower": "on_hold"}
    assert any(c.get("provide") == "harbor" for c in tasks.gather(cfg, "_example", BILL))   # on Tasks too


def test_the_art_tab_exists_with_a_screen_in_the_page(w):
    t = areas.find("art/provide")
    assert t and t[1]["name"] == "User Needs To Provide Image" and t[1]["screen"] == "provide"
    assert "provide:'v-provide'" in server.SHELL and 'id="v-provide"' in server.SHELL and "function loadProvide" in server.SHELL


@pytest.fixture
def srv(w):
    s = server.make_server(w[0], 0)
    import threading
    th = threading.Thread(target=s.serve_forever, daemon=True)
    th.start()
    yield s.server_address[1]
    s.shutdown()


def test_a_dropped_picture_lands_where_the_request_says(w, srv):
    cfg, a, _ = w
    settings.set_identity(BILL)
    _req(cfg, rid="harbor")
    v = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{srv}/api/suite/provide?id=_example").read())
    card = v["cards"][0]
    c = http.client.HTTPConnection("127.0.0.1", srv, timeout=60)
    c.request("POST", f"/api/suite/upload?game=_example&task={urllib.request.quote(card['id'])}&name=dusk.png", body=PNG,
              headers={"X-Forge": "1", "Content-Length": str(len(PNG))})
    r = json.loads(c.getresponse().read())
    assert r["ok"] and r["done"], r
    assert (a.root / "reference" / "provided" / "harbor" / "dusk.png").read_bytes() == PNG
    v = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{srv}/api/suite/provide?id=_example").read())
    assert v["cards"] == [] and v["pool"][0]["state"] == "provided"


def test_the_gui_can_open_or_hold_a_request_signed(w):
    cfg, a, _ = w
    _req(cfg, rid="tower", status="on_hold")
    assert not server.act(cfg, "provide_status", {"game": "_example", "id": "tower", "status": "open"})["ok"]   # unsigned
    settings.set_identity(BILL)
    r = server.act(cfg, "provide_status", {"game": "_example", "id": "tower", "status": "open"})
    assert r["ok"] and provide.load(cfg, "_example")[0]["status"] == "open"
    assert not server.act(cfg, "provide_status", {"game": "_example", "id": "nope", "status": "open"})["ok"]
