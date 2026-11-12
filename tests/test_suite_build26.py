"""BUILD 26 — every area its own tab: the sidebar of areas, addresses, what each tab needs, the badges; Tasks as a
checklist (not an inbox) with files dropped right on a card; Status — met or not met, at a glance. All on a throwaway
copy of the example game; no real game is touched. The browser smoke test runs only where Playwright + Chromium are
installed (it is skipped elsewhere)."""
from __future__ import annotations
import http.client, json, re, threading, time, urllib.error, urllib.request
from datetime import datetime
from pathlib import Path

import pytest

from forge.suite import areas, buildqueue, journal, mail, music, notes, orders, production, server, settings, status, tasks
from test_suite_build01 import REPO, world  # noqa: F401 — the shared throwaway world

T = datetime(2026, 11, 11, 10, 30, 0)
BILL, OPUS = "Bill", "Claude Opus"
FABLE_L = "20261110-091500_claude-fable_ember-crossing-s-greeting-and-the-harbor"
OPUS_L = "20261110-094000_claude-opus_the-example-game-s-first-build-three-pla"
OGG = b"OggS\x00\x02" + b"\x00" * 200
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00"
       b"\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def w(world, monkeypatch):
    cfg, a, tmp = world
    monkeypatch.setattr(settings, "now", lambda path=None: T)
    areas._badge_cache.clear()
    return cfg, a, tmp


def _no_waiting_build(a):
    q = a.root / "Builds" / "BUILD_QUEUE.md"
    q.write_text(q.read_text(encoding="utf-8").replace("| [!] his ruling on the toll's price |", "| [ ] |"), encoding="utf-8")


@pytest.fixture
def srv(w):
    cfg, a, tmp = w
    s = server.make_server(cfg, 0)
    th = threading.Thread(target=s.serve_forever, daemon=True)
    th.start()
    yield s.server_address[1]
    s.shutdown()


def _get(port, path):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}").read())


def _upload(port, task, name, body: bytes | Path):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    q = f"/api/suite/upload?game=_example&task={urllib.request.quote(task)}&name={urllib.request.quote(name)}"
    if isinstance(body, Path):
        with open(body, "rb") as f:
            c.request("POST", q, body=f, headers={"X-Forge": "1", "Content-Length": str(body.stat().st_size)})
            r = c.getresponse()
            return r.status, json.loads(r.read())
    c.request("POST", q, body=body, headers={"X-Forge": "1", "Content-Length": str(len(body))})
    r = c.getresponse()
    return r.status, json.loads(r.read())


# ---------------------------------------------------------------- A · the frame
def test_every_area_and_tab_has_an_address_a_screen_and_a_needs_line(w):
    cfg, a, _ = w
    ids = [x["id"] for x in areas.AREAS]
    assert ids == ["home", "status", "messages", "tasks", "story", "music", "art", "characters", "workshop", "notes", "settings"]
    music_tabs = [t["name"] for t in next(x for x in areas.AREAS if x["id"] == "music")["tabs"]]
    assert music_tabs == ["Needed", "Singers", "Score inbox", "Briefs & songs"]
    nd = areas.needs(cfg, "_example")
    assert set(nd) == set(areas.addresses()) and len(set(areas.addresses())) == len(areas.addresses())
    for addr, n in nd.items():
        assert n["line"], addr
        t = areas.find(addr)[1]
        assert t["screen"]
    html = server.SHELL
    for a_ in areas.AREAS:                       # every screen a tab names has a section and a loader in the page
        for t in a_["tabs"]:
            assert f"{t['screen']}:'v-" in html, t["screen"]


def test_no_old_screen_is_left_without_a_home():
    old = ["home", "queue", "wanted", "make", "review", "intake", "chars", "library", "bakeoffs", "models", "tools",
           "mail", "orders", "overview", "read", "music"]          # every data-s in the two menus before BUILD 26
    assert sorted(areas.OLD_SCREENS) == sorted(old)
    for s, addr in areas.OLD_SCREENS.items():
        a, t = areas.find(addr)
        assert t["screen"] == s and not t["planned"]
    assert len(set(areas.OLD_SCREENS.values())) == len(old)          # exactly one home each


def test_a_planned_tab_shows_its_build_and_needs_not_a_blank(w):
    cfg, _a, _ = w
    # BUILD 17 built the last planned tabs (Notes → Rulings, Idea box, Playtest notes); the mechanism stays for the next one
    for addr in ("notes/rulings", "notes/ideas", "notes/playtest"):
        assert not areas.find(addr)[1]["planned"], addr
    areas.AREAS[-1]["tabs"].append(areas._t("later", "Later", "planned", ("game",), planned=99, holds="something still to come"))
    try:
        n = areas.needs(cfg, "_example")["settings/later"]
        assert n["planned"] == 99 and "BUILD 99" in n["line"] and len(n["line"]) > 40
    finally:
        areas.AREAS[-1]["tabs"].pop()


def test_needs_say_what_is_missing_and_what_brings_it(w):
    cfg, a, _ = w
    nd = areas.needs(cfg, "_example")
    assert nd["messages/inbox"]["met"] is True and "✓" in nd["messages/inbox"]["line"]
    assert nd["notes/open"]["met"] is None and nd["notes/open"]["line"].startswith("Nothing yet")     # empty, not broken
    (a.root / "data" / "music.json").write_text("{}", encoding="utf-8")
    from forge.suite import games
    games._loaded.clear()
    nd = areas.needs(cfg, "_example")
    assert nd["music/needed"]["met"] is False and "music slots" in nd["music/needed"]["line"]


def test_the_last_place_is_remembered_per_game_on_this_computer(w):
    areas.remember_place("_example", "music/singers/wren")
    assert areas.last_place("_example") == "music/singers/wren"
    areas.remember_place("_example", "nowhere/at-all")                       # not an address → ignored
    assert areas.last_place("_example") == "music/singers/wren"
    assert json.loads(settings.PATH.read_text(encoding="utf-8"))["last_place"] == {"_example": "music/singers/wren"}


def test_badges_answer_fast_and_a_missing_area_counts_zero(w):
    cfg, a, _ = w
    settings.set_identity(BILL)
    t0 = time.time()
    b = areas.badges(cfg, "_example", fresh=True)
    assert time.time() - t0 < 1.0
    assert b["messages"] == 2 and b["music"] == 3 and b["notes"] == 0 and b["tasks"] >= 3 and b["art"] == 0
    assert set(b) >= {"messages", "tasks", "notes", "music", "art", "worker"}
    import shutil
    shutil.rmtree(a.root / "mail")
    b = areas.badges(cfg, "_example", fresh=True)
    assert b["messages"] == 0                                               # no mail folder → 0, not an error


def test_the_app_serves_areas_badges_and_every_old_screen_at_its_new_address(srv):
    port = srv
    d = _get(port, "/api/suite/areas?id=_example")
    assert [x["id"] for x in d["areas"]][:4] == ["home", "status", "messages", "tasks"] and d["old"]["music"] == "music/needed"
    assert set(d["needs"]) == set(areas.addresses())
    b = _get(port, "/api/suite/badges?id=_example")
    assert "worker" in b and b["music"] == 3
    html = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode("utf-8")
    assert 'id="areas"' in html and 'id="atabs"' in html and "function route()" in html and "hashchange" in html
    assert 'id="t-art"' not in html and "nav-story" not in html                   # the Art | Story switch is gone
    assert "Ctrl" not in re.sub(r"<[^>]+>", "", html.split("<script>")[0])         # no area shortcuts on Ctrl/Cmd + digit


# ---------------------------------------------------------------- B2 · Tasks: a checklist, not an inbox
def _review_waiting(monkeypatch, n):
    monkeypatch.setattr(production, "review", lambda cfg, gid, st, limit=40: {"waiting": [{"id": f"j{i}"} for i in range(n)]})


def test_five_things_waiting_make_exactly_five_cards_each_with_a_real_go(w, monkeypatch):
    cfg, a, _ = w
    _no_waiting_build(a)
    # answer the Opus letter, so only the Fable letter still has open questions
    mail.reply(a.root, OPUS_L, BILL, "Done.", answers=[{"id": q["id"], "text": "yes"} for q in mail.find(a.root, OPUS_L).questions])
    music.propose(a, "ember_song", OPUS, "Scene: the toll.\nForm: three verses.", style="style-1")     # a proposed brief (+ its letter)
    orders.add(a.root, OPUS, BILL, "Check the harbor map against the sketch", priority="soon")           # a work order
    _review_waiting(monkeypatch, 4)                                                                       # pictures waiting
    cards = tasks.gather(cfg, "_example", BILL, ui_state=object())
    kinds = sorted(c["kind"] for c in cards)
    assert kinds == ["brief", "letter", "order", "profile", "review"], [c["title"] for c in cards]
    by = {c["kind"]: c for c in cards}
    assert by["letter"]["go"] == f"messages/inbox/{FABLE_L}" and by["letter"]["count"] == 2
    assert by["brief"]["go"] == "music/needed/ember_song" and "yes / no / I'll write it" in by["brief"]["title"]
    assert by["profile"]["go"] == "music/singers/wren" and by["review"]["go"] == "art/review" and by["review"]["count"] == 4
    assert by["order"]["go"] is None and by["order"]["checkable"]
    for c in cards:
        if c["go"]:
            assert areas.find(c["go"]), c["go"]
    assert cards[0]["kind"] == "brief"                                    # unblocking first


def test_answering_the_letter_removes_its_card_by_itself_and_a_letter_with_no_question_makes_none(w):
    cfg, a, _ = w
    ids = {c["id"] for c in tasks.gather(cfg, "_example", BILL)}
    assert f"letter:{FABLE_L}" in ids
    mail.send(a.root, OPUS, BILL, "Just so you know", "Bill,\n\nThe harbor is painted.\n\nOpus")      # no question
    ids2 = {c["id"] for c in tasks.gather(cfg, "_example", BILL)}
    assert ids2 == ids
    l = mail.find(a.root, FABLE_L)
    mail.reply(a.root, FABLE_L, BILL, "Both.", answers=[{"id": q["id"], "text": "fine"} for q in l.questions])
    assert f"letter:{FABLE_L}" not in {c["id"] for c in tasks.gather(cfg, "_example", BILL)}


def test_reading_a_card_changes_nothing_and_dismissing_needs_a_reason_and_is_journaled(w):
    cfg, a, _ = w
    n = len(tasks.gather(cfg, "_example", BILL))
    mail.mark_read(a.root, BILL, FABLE_L)                                  # reading the letter is not doing it
    tasks.board(cfg, "_example", BILL)
    assert len(tasks.gather(cfg, "_example", BILL)) == n
    with pytest.raises(tasks.TaskRefused, match="reason"):
        tasks.tick(cfg, "_example", "profile:wren", BILL, "", dismiss=True)
    r = tasks.tick(cfg, "_example", "profile:wren", BILL, "I'll do the profiles on the weekend", dismiss=True)
    assert r["ok"] and len(tasks.gather(cfg, "_example", BILL)) == n - 1
    e = journal.read(a.root, kinds=("task",))[-1]
    assert e["who"] == BILL and e["obj"] == "profile:wren" and "dismissed" in e["note"] and "weekend" in e["note"]
    # the card comes back when what it's about changes (a spot filled → the count changes)
    music.fill_spot(a, "wren", "/voice/constant", "dry", BILL)
    assert "profile:wren" in {c["id"] for c in tasks.gather(cfg, "_example", BILL)}
    assert any("dismissed" in d["note"] for d in tasks.done(a.root, BILL))


def test_a_ticked_work_order_is_closed_in_its_own_file_and_an_old_card_rises_amber(w, monkeypatch):
    cfg, a, _ = w
    _no_waiting_build(a)
    old = orders.add(a.root, OPUS, BILL, "An old chore", priority="someday", when=datetime(2026, 11, 1, 9, 0))
    new = orders.add(a.root, OPUS, BILL, "A new chore", priority="someday")
    cards = tasks.gather(cfg, "_example", BILL)
    oc = next(c for c in cards if c["id"] == f"order:{old['id']}")
    nc = next(c for c in cards if c["id"] == f"order:{new['id']}")
    assert oc["overdue"] and not nc["overdue"] and cards.index(oc) < cards.index(nc)
    tasks.tick(cfg, "_example", f"order:{old['id']}", BILL)
    assert orders.listing(a.root, "bill", "done")[0]["id"] == old["id"]
    assert f"order:{old['id']}" not in {c["id"] for c in tasks.gather(cfg, "_example", BILL)}


def test_tasks_never_look_like_email(w):
    html = server.SHELL
    body = html[html.index("function cardHtml"):html.index("async function loadTasks")]
    assert "unread" not in body and "mark as read" not in body.lower() and 'type="checkbox"' in body and "Go →" in body


def test_the_next_seven_then_groups(w):
    cfg, a, _ = w
    for i in range(10):
        orders.add(a.root, OPUS, BILL, f"Chore {i}", priority="soon")
    b = tasks.board(cfg, "_example", BILL)
    assert len(b["next"]) == 7 and sum(len(g["cards"]) for g in b["groups"]) == b["count"] - 7


# ---------------------------------------------------------------- B2 · files dropped on a card
def _written(a):
    music.propose(a, "ember_song", OPUS, "Scene: the toll.", style="style-1")
    l = mail.find(a.root, music.find(a, "ember_song")["letter"])
    mail.reply(a.root, l.id, BILL, "Yes.", answers=[{"id": "verdict", "choice": "yes"}], adp=a)
    music.write_song(a, "ember_song", OPUS, "The Toll", "dry alto\n\n[Verse 1]\nla la")
    assert music.find(a, "ember_song")["state"] == "written"


def test_an_ogg_dropped_on_the_music_task_delivers_and_cements_the_slot(w, srv):
    cfg, a, _ = w
    settings.set_identity(BILL)
    _written(a)
    card = next(c for c in tasks.gather(cfg, "_example", BILL) if c["kind"] == "track")
    assert card["wants"]["kind"] == "audio" and card["wants_line"].startswith("wants: one audio file → Music")
    st, r = _upload(srv, card["id"], "the toll.ogg", OGG)
    assert st == 200 and r["ok"] and r["done"], r
    s = music.find(a, "ember_song")
    assert s["cemented"] and s["delivered"]["by"] == BILL and (a.root / s["delivered"]["file"]).read_bytes() == OGG
    assert r["step"] and "confirm the words" in r["step"]                    # a vocal: one more step
    ids = {c["id"] for c in tasks.gather(cfg, "_example", BILL)}
    assert "track:ember_song" not in ids and "words:ember_song" in ids
    assert not list((a.root / "_incoming").glob("*"))                      # handed on, nothing left raw
    assert any(e["kind"] == "deliver" and e["obj"] == "music:ember_song" for e in journal.read(a.root))


def test_a_png_on_an_order_that_wants_an_image_lands_in_its_folder_with_a_journal_line(w, srv):
    cfg, a, _ = w
    settings.set_identity(BILL)
    o = orders.add(a.root, OPUS, BILL, "A reference photo for the harbor", wants={"kind": "image"}, goes_to="reference/harbor")
    card = next(c for c in tasks.gather(cfg, "_example", BILL) if c["id"] == f"order:{o['id']}")
    assert card["wants_line"] == "wants: one image → reference/harbor/"
    st, r = _upload(srv, card["id"], "dock.png", PNG)
    assert st == 200 and r["ok"] and r["done"]
    assert (a.root / "reference/harbor/dock.png").read_bytes() == PNG
    assert orders.listing(a.root, "bill", "done")[0]["received"][0]["name"] == "dock.png"
    assert any(e["kind"] == "task" and "reference/harbor/dock.png" in (e.get("after") or "") for e in journal.read(a.root))


def test_a_wrong_type_is_refused_with_nothing_written(w, srv):
    cfg, a, _ = w
    settings.set_identity(BILL)
    _written(a)
    st, r = _upload(srv, "track:ember_song", "cover.png", PNG)
    assert st == 400 and not r["ok"] and "wants audio" in r["message"] and ".png" in r["message"]
    assert not (a.root / "_incoming").exists() or not list((a.root / "_incoming").iterdir())
    assert music.find(a, "ember_song")["state"] == "written"


def test_a_session_cannot_tick_a_persons_task_by_uploading(w, srv, monkeypatch):
    cfg, a, _ = w
    _written(a)
    monkeypatch.setenv("FORGE_IDENTITY", OPUS)
    st, r = _upload(srv, "track:ember_song", "x.ogg", OGG)
    assert st == 400 and "person's act" in r["message"] and music.find(a, "ember_song")["state"] == "written"


def test_a_200_mb_file_streams_through(w, srv, tmp_path):
    cfg, a, _ = w
    settings.set_identity(BILL)
    o = orders.add(a.root, OPUS, BILL, "The long mix", wants={"kind": "audio"}, goes_to="score_drafts")
    big = tmp_path / "long mix.wav"
    with open(big, "wb") as f:
        f.truncate(200 * 1024 * 1024)
    st, r = _upload(srv, f"order:{o['id']}", big.name, big)
    assert st == 200 and r["ok"], r
    assert (a.root / "score_drafts/long mix.wav").stat().st_size == 200 * 1024 * 1024


def test_three_of_five_reference_images_keeps_the_card_open(w, srv):
    cfg, a, _ = w
    settings.set_identity(BILL)
    o = orders.add(a.root, OPUS, BILL, "Five reference photos", wants={"kind": "image", "count": 5}, goes_to="reference/set")
    for i in range(3):
        st, r = _upload(srv, f"order:{o['id']}", f"ref{i}.png", PNG)
        assert st == 200 and r["ok"] and not r["done"]
    assert r["progress"] == "3 of 5"
    card = next(c for c in tasks.gather(cfg, "_example", BILL) if c["id"] == f"order:{o['id']}")
    assert card["progress"] == "3 of 5" and len(card["received"]) == 3


def test_a_half_finished_upload_delivers_nothing(w, srv):
    cfg, a, _ = w
    settings.set_identity(BILL)
    o = orders.add(a.root, OPUS, BILL, "One file", wants={"kind": "any"}, goes_to="drop")
    c = http.client.HTTPConnection("127.0.0.1", srv, timeout=10)
    c.putrequest("POST", f"/api/suite/upload?game=_example&task=order:{o['id']}&name=half.bin")
    c.putheader("X-Forge", "1")
    c.putheader("Content-Length", "100000")
    c.endheaders()
    c.send(b"x" * 1000)
    c.sock.shutdown(1)                                # the browser goes away half-way
    try:
        c.getresponse().read()
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.3)
    assert not (a.root / "drop").exists()
    assert not list((a.root / "_incoming").glob("half.bin")) and not list((a.root / "_incoming").glob("*half.bin"))


# ---------------------------------------------------------------- B3 · Status
def test_status_missing_music_list_is_red_and_names_what_is_missing(w):
    cfg, a, _ = w
    (a.root / "data" / "music.json").write_text("{}", encoding="utf-8")
    from forge.suite import games
    games._loaded.clear()
    g = status.glance(cfg, "_example")
    t = next(t for r in g["rows"] for t in r["tiles"] if t["id"] == "music")
    assert t["state"] == "not" and "no music list" in t["detail"]


def test_status_an_answered_letter_turns_messages_green(w):
    cfg, a, _ = w
    settings.set_identity(BILL)
    q = lambda: next(t for r in status.glance(cfg, "_example")["rows"] for t in r["tiles"] if t["id"] == "questions")
    assert q()["state"] == "not" and q()["value"] == "3"
    for lid in (FABLE_L, OPUS_L):
        mail.reply(a.root, lid, BILL, "ok", answers=[{"id": x["id"], "text": "ok"} for x in mail.find(a.root, lid).questions])
    assert q()["state"] == "met"


def test_status_builds_a_started_build_is_amber_with_its_progress_line(w):
    cfg, a, _ = w
    b = status.builds(cfg, "_example")
    t = {x["n"]: x for x in b["tiles"]}
    assert t["01"]["state"] == "met" and t["02"]["state"] == "partly" and "keeper's quest is in" in t["02"]["detail"]
    assert t["03"]["state"] == "not" and "toll's price" in t["03"]["detail"] and t["04"]["todo"]
    assert b["tally"] == {"met": 1, "partly": 1, "not": 1}


def test_status_a_tile_with_no_data_is_grey_not_green(w, monkeypatch):
    cfg, a, _ = w
    from forge.suite import readthrough
    monkeypatch.setattr(readthrough, "towns", lambda adp: (_ for _ in ()).throw(RuntimeError("broken")))
    g = status.glance(cfg, "_example")
    tiles = {t["id"]: t for r in g["rows"] for t in r["tiles"]}
    assert tiles["places"]["state"] == "none" and "couldn't" in tiles["places"]["detail"]
    assert tiles["tasks"]["state"] == "none"                       # nobody signed in → can't tell, not green


def test_status_every_tile_go_opens_a_real_address(w):
    cfg, a, _ = w
    settings.set_identity(BILL)
    for tab in (status.glance(cfg, "_example"), status.builds(cfg, "_example"), status.completeness(cfg, "_example")):
        tiles = [t for r in tab.get("rows", [{"tiles": tab.get("tiles", [])}]) for t in r["tiles"]]
        assert tiles
        for t in tiles:
            assert t["go"] and areas.find(t["go"]), t


def test_the_game_tab_reads_the_games_own_checklist(w):
    cfg, a, _ = w
    c = status.completeness(cfg, "_example")
    states = {t["label"]: t["state"] for t in c["tiles"]}
    assert states == {"Places with a map": "met", "Quests approved": "partly", "Music slots with audio": "not", "Title screen": "not"}
    assert status.parse_line("Maps painted: 0 of 77") == {"item": "Maps painted", "have": 0, "of": 77, "detail": "0 of 77"}


def test_the_build_queue_reader(tmp_path):
    q = tmp_path / "BUILD_QUEUE.md"
    q.write_text("| | # |\n|---|---|\n| [x] 2026-11-10 | 01 | SUITE | **One** | — | 1 |\n| [!] the towns | 08 | GAME | Two | 02 | 1 |\n", encoding="utf-8")
    (tmp_path / "BUILD_08_GAME_Two.md").write_text("# B\n**Progress (x):** half way.\n", encoding="utf-8")
    b = buildqueue.read(q)
    assert [(x["n"], x["mark"], x["title"]) for x in b] == [("01", "x", "One"), ("08", "!", "Two")]
    assert b[1]["waiting_for"] == "the towns" and b[1]["progress"] == "Progress (x): half way." and b[0]["done_on"] == "2026-11-10"


def test_music_briefs_and_songs_are_read_from_the_board_only(w):
    cfg, a, _ = w
    _written(a)
    items = music.briefs_and_songs(a)
    assert [x["what"] for x in items][:2] in (["song v1", "brief"], ["brief", "song v1"])
    assert all(x["slot"] == "ember_song" for x in items)
    letter = mail.find(a.root, music.find(a, "ember_song")["letter"])
    assert "(#music/needed/ember_song)" in letter.body                  # the brief's letter links to its row


def test_a_note_addressed_to_bill_becomes_his_task(w):
    cfg, a, _ = w
    n = notes.add(a.root, "place:harbor_hollow", OPUS, "Is the harbor's bell one word or two?", tag="question", to=BILL,
                  label="Harbor Hollow")
    c = next(c for c in tasks.gather(cfg, "_example", BILL) if c["kind"] == "note")
    assert c["go"] == f"notes/open/{n['id']}" and "Harbor Hollow" in c["title"]


# ---------------------------------------------------------------- the browser smoke test (Playwright + Chromium)
def _playwright():
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        b = None
        for kw in ({}, {"channel": "chrome"}, {"channel": "msedge"}):      # Playwright's own Chromium, else the machine's Chrome
            try:
                b = p.chromium.launch(**kw)
                break
            except Exception:  # noqa: BLE001
                continue
        if b is None:
            p.stop()
            return None, None
        return p, b
    except Exception:  # noqa: BLE001
        return None, None


def test_browser_opens_every_area_and_tab_without_a_page_error(w, srv):
    cfg, a, tmp = w
    settings.set_identity(BILL)
    p, b = _playwright()
    if b is None:
        pytest.skip("Playwright with Chromium isn't installed here")
    shots = REPO / "out" / "screens"
    shots.mkdir(parents=True, exist_ok=True)
    errors = []
    try:
        page = b.new_page(viewport={"width": 1500, "height": 950})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv}/#home/today")
        page.wait_for_selector("#areas .arow")
        for a_ in areas.AREAS:
            for i, t in enumerate(a_["tabs"]):
                page.evaluate(f"go('{a_['id']}/{t['id']}')")
                page.wait_for_timeout(350)
                assert page.evaluate("location.hash") == f"#{a_['id']}/{t['id']}" or page.evaluate("location.hash").startswith(f"#{a_['id']}/{t['id']}/")
                assert page.inner_text("#needsl").strip(), t["id"]
                if t.get("planned"):
                    assert f"BUILD {t['planned']:02d}" in page.inner_text("#v-planned")
                if i == 0:
                    page.screenshot(path=str(shots / f"area_{a_['id']}.png"))
        # an address round-trips through a reload, and Back returns to the previous tab
        page.evaluate("go('music/singers')")
        page.wait_for_timeout(300)
        page.reload()
        page.wait_for_selector("#atabs button.on")
        assert page.inner_text("#atabs button.on") == "Singers"
        page.evaluate("go('tasks/for-you')")
        page.wait_for_timeout(300)
        page.go_back()
        page.wait_for_timeout(400)
        assert page.evaluate("location.hash") == "#music/singers" and page.inner_text("#atabs button.on") == "Singers"
        # a link in a letter opens the right tab
        page.evaluate("go('messages/inbox/" + FABLE_L + "')")
        page.wait_for_timeout(600)
        assert "Ember Crossing" in page.inner_text("#mread")
    finally:
        b.close()
        p.stop()
    assert not errors, errors
