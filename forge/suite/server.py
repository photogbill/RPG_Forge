"""The suite: one local web app for every game — `forge.bat` → http://127.0.0.1:8770

A game picker is the first control; two sides, **Art** and **Story**. Art's first screens are Home (the worker, the
queue, the disk, three safe buttons) and Queue & pictures (the dashboard that `ui.bat` has always shown — served by
the same code). Story shows what the suite can read from the chosen game until the Mail (BUILD 03) and the
Workbench (BUILD 07) arrive. BUILD 04 adds Sprite intake (click a figure, pick its facing → the game sheet) and
Characters (the registry as pages, the face sheet, make the set) — sprites.py and cast.py. BUILD 12 adds Make a
picture (picture.py), Review & approve → Deliver and the Wanted board (production.py). BUILD 14 adds Called out and
mark-up, the prompt library, bake-offs, models and outside tools (finishing.py).

BUILD 26 turns the two halves into **one sidebar of areas** (areas.py): Home · Status · Messages · Tasks · Story · Music ·
Art · Characters · Workshop · Notes · Settings, each with a strip of tabs and an address (`#music/needed`). Tasks is a
checklist of everything waiting on the person, with files dropped right on a card (tasks.py; big files stream in through
POST /api/suite/upload); Status shows every requirement met or not met (status.py).

Bound to 127.0.0.1 — nothing outside this PC can reach it. Every POST needs the `X-Forge: 1` header (a page on
another site cannot send it without a preflight this server never answers). Every action is logged to the forge log,
and to the chosen game's journal when it is reachable, signed with the identity setting.
"""
from __future__ import annotations
import base64, io, json, os, subprocess, threading, time, traceback, webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import config as cfgmod
from .. import ui
from ..log import get
from . import approval, areas, away, osopen, runwords, cast, finishing, games, home, journal, mail, music, notes, orders, picture, production, readthrough, settings, sprites, status, tasks, worker, workbench
from . import ideas, playtest, rulings, standing   # BUILD 17: team memory
from . import floorplans   # BUILD 29b: Art → Floor plans (the generator in the suite)
from . import provide   # User Needs To Provide Image (2026-11-11): the forge pool of pictures the forge can't make

log = get("suite")
HOST, PORT = "127.0.0.1", 8770
_summary_cache: dict[str, tuple[float, dict]] = {}


def current_game(cfg: dict) -> str:
    ids = games.game_ids(cfg)
    last = settings.load().get("last_game")
    if last in ids:
        return last
    d = cfgmod.default_game(cfg)
    return d if d in ids else (ids[0] if ids else "")


def _journal(cfg: dict, kind: str, obj: str | None = None, note: str | None = None) -> None:
    who = settings.identity()
    gid = current_game(cfg)
    if not who or not gid:
        return
    try:
        root = games.game_root(cfg, gid)
        if root and root.is_dir():
            journal.append(root, who, kind, obj, note=note)
    except Exception as e:  # noqa: BLE001 — an action is never undone because its journal line failed
        log.warning("suite: journal line not written (%s)", e)


def game_view(cfg: dict, gid: str, fresh: bool = False) -> dict:
    hit = _summary_cache.get(gid)
    if hit and not fresh and time.time() - hit[0] < 20:
        return hit[1]
    out: dict = {"id": gid, "has_adapter": games.has_adapter(cfg, gid)}
    if not out["has_adapter"]:
        out["error"] = f"games/{gid} has no workbench_adapter.py yet, so the suite can't read this game's story files."
    else:
        try:
            a = games.adapter(cfg, gid)
            out["summary"] = a.summary()
            if a.root.is_dir():
                out["proposals"] = approval.list_open(a.root)
                out["journal"] = list(reversed(journal.read(a.root, limit=15)))
        except Exception as e:  # noqa: BLE001
            log.error("suite: game view %s: %s", gid, traceback.format_exc())
            out["error"] = f"{type(e).__name__}: {e}"
    _summary_cache[gid] = (time.time(), out)
    return out


def act_floorplan(cfg: dict, action: str, body: dict, who) -> dict:
    """Art → Floor plans (BUILD 29b). Generating and editing are anyone's (signed); approving is a person's."""
    gid = str(body.get("game") or current_game(cfg))
    f = str(body.get("folder") or "")
    try:
        if action == "floorplan_generate":
            r = floorplans.generate(cfg, gid, str(body.get("place") or ""), str(body.get("era") or ""),
                                    body.get("archetype") or None, int(body.get("count") or 4), who,
                                    body.get("size") or None)
            return {"ok": True, "message": f"{len(r['made'])} new candidates ({r['archetype']}).", **r}
        if action == "floorplan_check":
            r = floorplans.check(cfg, gid, f, str(body.get("map") or ""), body.get("edits") or [])
            return {"ok": True, "message": "clean" if r["ok"] else f"{len(r['problems'])} problems", "clean": r["ok"],
                    "problems": r["problems"]}
        if action == "floorplan_save":
            r = floorplans.save(cfg, gid, f, str(body.get("map") or ""), body.get("edits") or [], who)
            return {"ok": True, "message": "Saved. This plan is yours now — a reroll never writes over it."
                    + (f" {len(r['problems'])} problems still listed." if r["problems"] else ""), "candidate": r}
        if action == "floorplan_approve":
            r = floorplans.approve(cfg, gid, f, who)
            return {"ok": True, "message": f"Approved: {len(r['installed'])} maps are in the game. {r['plan']}", "result": r}
        if action == "floorplan_send":
            r = floorplans.send(cfg, gid, f, str(body.get("question") or ""), who)
            return {"ok": True, "message": f"Sent to {r['to']} — it's in the Mail.", **r}
    except floorplans.FloorPlanRefused as e:
        return {"ok": False, "message": str(e)}
    return {"ok": False, "message": f"unknown action {action}"}


def act(cfg: dict, action: str, body: dict) -> dict:
    who = settings.identity()
    if action == "identity":
        name = settings.set_identity(str(body.get("name") or ""))
        log.info("suite: identity on this install is now %s", name)
        _journal(cfg, "setting", "identity", f"this install now signs as {name}")
        return {"ok": True, "message": f"Hello, {name}. Everything you do here is signed with that name.", "identity": name}
    if action == "pick":
        gid = str(body.get("id") or "")
        if gid not in games.game_ids(cfg):
            return {"ok": False, "message": f"there is no game '{gid}' in games/"}
        settings.update(last_game=gid)
        return {"ok": True, "message": f"opened {gid}"}
    if action == "start":
        r = worker.start(cfg)
        if r["ok"]:
            _journal(cfg, "queue", "worker", "started the art worker from Home")
        return r
    if action in ("pause", "resume"):
        r = ui.act(cfg, action, {})          # the dashboard's own action — the same as pause.bat / resume.bat
        if r.get("ok"):
            _journal(cfg, "queue", "queue", r.get("message"))
        return r
    if action == "game_root_check":
        return games.check_root(cfg, str(body.get("id") or current_game(cfg)), str(body.get("folder") or ""))
    if action == "game_root_set":
        gid = str(body.get("id") or current_game(cfg))
        if gid not in games.game_ids(cfg):
            return {"ok": False, "message": f"there is no game '{gid}' in games/"}
        folder = str(body.get("folder") or "").strip()
        r = games.check_root(cfg, gid, folder) if folder else {"ok": True, "message": "Forgotten — back to the game's own setting."}
        if not r["ok"]:
            return r
        settings.set_game_root(gid, folder)
        games._loaded.pop(gid, None)
        _summary_cache.pop(gid, None)
        areas._badge_cache.pop(gid, None)
        _journal(cfg, "setting", "game_root", f"{gid} is read from {folder or 'its forge.game.json'} on this computer")
        return {**r, "message": "Saved for this computer. " + r["message"]}
    if action == "setting_set":
        try:
            settings.set_value(str(body.get("key") or ""), body.get("value"))
        except ValueError as e:
            return {"ok": False, "message": str(e)}
        return {"ok": True, "message": "Saved for this computer."}
    if action == "place":
        areas.remember_place(str(body.get("game") or current_game(cfg)), str(body.get("addr") or ""))
        return {"ok": True, "message": "ok"}
    if action == "provide_status":   # open an on-hold request now, put one on hold, or withdraw it (the pool file, forge-side)
        gid = str(body.get("game") or current_game(cfg))
        if not who:
            return {"ok": False, "message": "set who you are first (bottom left) — everything here is signed"}
        try:
            r = provide.set_status(cfg, gid, str(body.get("id") or ""), str(body.get("status") or ""))
        except FileNotFoundError:
            return {"ok": False, "message": "that request isn't in the pool"}
        except provide.ProvideRefused as e:
            return {"ok": False, "message": str(e)}
        _journal(cfg, "art", f"provide:{r['id']}", f"{who} set the picture request '{r['title']}' to {r['status']}")
        areas._badge_cache.pop(gid, None)
        word = {"open": "Opened — it's a task now.", "on_hold": "On hold.", "withdrawn": "Withdrawn — kept in the pool, struck through."}
        return {"ok": True, "message": word.get(r["status"], "Saved."), "request": r}
    if action in ("task_tick", "task_dismiss"):
        gid = str(body.get("game") or current_game(cfg))
        try:
            r = tasks.tick(cfg, gid, str(body.get("id") or ""), who or "", str(body.get("reason") or ""),
                           dismiss=action == "task_dismiss", ui_state=getattr(SuiteHandler, "state", None))
        except tasks.TaskRefused as e:
            return {"ok": False, "message": str(e)}
        areas._badge_cache.pop(gid, None)
        return r
    if action.startswith(("mail_", "order_", "away_")):
        return act_story(cfg, action, body, who)
    if action.startswith(("intake_", "tool_", "char_", "wanted_", "review_", "deliver_", "make_", "fin_")):
        return act_art(cfg, action, body, who)
    if action.startswith("music_"):
        return act_music(cfg, action, body, who)
    if action.startswith("read_"):
        return act_read(cfg, action, body, who)
    if action.startswith("wb_"):
        return act_workbench(cfg, action, body, who)
    if action.startswith(("rule_", "idea_", "playtest_")):
        return act_memory(cfg, action, body, who)
    if action.startswith("floorplan_"):
        return act_floorplan(cfg, action, body, who)
    if action == "open":
        what = str(body.get("what") or "")
        paths = {"log": cfgmod.path_of(cfg, "logs"), "jobs": cfgmod.path_of(cfg, "jobs"), "out": cfgmod.path_of(cfg, "out")}
        gid = current_game(cfg)
        if what == "game" and gid:
            paths["game"] = games.game_root(cfg, gid)
        p = paths.get(what)
        if p is None or not Path(p).exists():
            return {"ok": False, "message": f"nothing to open for '{what}'"}
        if what == "log":
            today = sorted(Path(p).glob("forge_*.log"))
            p = today[-1] if today else p
        try:
            osopen.open_path(p)                    # Explorer / Finder / the default program — as a double-click
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"couldn't open it ({e}); it is at {p}"}
        return {"ok": True, "message": f"opened {p}"}
    return {"ok": False, "message": f"unknown action {action}"}


def act_story(cfg: dict, action: str, body: dict, who: str | None) -> dict:
    """The Mail, work orders and the away digest — every one signed, every one through the same functions the
    command line uses (mail.py, orders.py, away.py)."""
    if not who:
        return {"ok": False, "message": "set who you are first (top right) — letters and orders are signed"}
    gid = str(body.get("game") or current_game(cfg))
    root = games.game_root(cfg, gid)
    if not root or not root.is_dir():
        return {"ok": False, "message": f"the game folder for {gid} isn't reachable"}
    _summary_cache.pop(gid, None)
    try:
        if action == "mail_send":
            args = (str(body.get("to") or "").strip(), str(body.get("subject") or "").strip(), str(body.get("body") or ""))
            qs = body.get("questions") or None
            adp = games.adapter(cfg, gid) if games.has_adapter(cfg, gid) else None
            if body.get("draft_id"):
                l = mail.send_edited_draft(root, str(body["draft_id"]), who, *args, questions=qs, adp=adp)
            else:
                l = mail.send(root, who, *args, questions=qs, adp=adp)
            return {"ok": True, "message": f"Sent to {l.to}.", "id": l.id}
        if action == "mail_draft":
            l = mail.save_draft(root, who, str(body.get("to") or ""), str(body.get("subject") or ""), str(body.get("body") or ""),
                                body.get("questions") or None, draft_id=body.get("draft_id") or None)
            return {"ok": True, "message": "Saved as a draft.", "id": l.id}
        if action == "mail_reply":
            adp = games.adapter(cfg, gid) if games.has_adapter(cfg, gid) else None
            l = mail.reply(root, str(body.get("letter")), who, str(body.get("body") or ""), answers=body.get("answers") or [], adp=adp)
            applied = [a for a in l.answers if a.get("applied")]
            msg = f"Sent to {l.to}."
            if applied:
                msg += " " + " ".join(f"{a['id']}: {a['applied']['message']}." for a in applied)
            return {"ok": True, "message": msg, "id": l.id, "answers": l.answers}
        if action == "mail_read":
            mail.mark_read(root, who, str(body.get("letter")), bool(body.get("read", True)))
            return {"ok": True, "message": "ok"}
        if action == "mail_archive":
            mail.archive(root, who, str(body.get("letter")))
            return {"ok": True, "message": "Archived — it's under Archive whenever you want it."}
        if action == "mail_unarchive":
            mail.unarchive(root, who, str(body.get("letter")))
            return {"ok": True, "message": "Back in the inbox."}
        if action == "order_add":
            o = orders.add(root, who, str(body.get("for") or ""), str(body.get("title") or ""), str(body.get("detail") or ""),
                           str(body.get("priority") or "soon"), body.get("object") or None,
                           wants=body.get("wants") or None, goes_to=body.get("goes_to") or None, effort=body.get("effort") or None)
            return {"ok": True, "message": f"On the list for {o['for']}.", "order": o}
        if action == "order_close":
            o = orders.close(root, str(body.get("id")), who, str(body.get("note") or ""), str(body.get("status") or "done"))
            return {"ok": True, "message": f"Marked {o['status']}.", "order": o}
        if action == "away_seen":
            journal.append(root, who, "seen", "the away digest", note="caught up")
            return {"ok": True, "message": "Caught up."}
    except FileNotFoundError as e:
        return {"ok": False, "message": f"not found: {e}"}
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": False, "message": f"unknown action {action}"}


def _num(v):
    return None if v in (None, "") else float(v)


def act_music(cfg: dict, action: str, body: dict, who: str | None) -> dict:
    """The Music board (BUILD 06) — every action signed, every one through music.py (the same functions sessions use
    from the command line: python -m forge music …)."""
    if not who:
        return {"ok": False, "message": "set who you are first (top right) — everything on the board is signed"}
    gid = str(body.get("game") or current_game(cfg))
    if not games.has_adapter(cfg, gid):
        return {"ok": False, "message": f"{gid} has no Story adapter yet — the Music board reads its slots through it"}
    adp = games.adapter(cfg, gid)
    sid = str(body.get("slot") or "")
    try:
        if action == "music_deliver":
            data = None
            if body.get("data"):
                data = base64.b64decode(str(body["data"]).split(",", 1)[-1], validate=False)
            return music.deliver(adp, sid, who, data=data, filename=str(body.get("filename") or ""), inbox_name=body.get("inbox") or None,
                                 loop_start=_num(body.get("loop_start")), loop_end=_num(body.get("loop_end")), trim_db=_num(body.get("trim_db")))
        if action == "music_audio":
            return music.set_audio(adp, sid, who, _num(body.get("loop_start")), _num(body.get("loop_end")), _num(body.get("trim_db")))
        if action == "music_answer":
            return music.answer(adp, sid, who, str(body.get("verdict") or ""), str(body.get("note") or ""))
        if action == "music_propose":
            return music.propose(adp, sid, who, str(body.get("brief") or ""), body.get("style") or None, body.get("subject") or None)
        if action == "music_write":
            return music.write_song(adp, sid, who, str(body.get("title") or ""), str(body.get("text") or ""), str(body.get("note") or ""))
        if action == "music_lyric":
            return music.confirm_lyric(adp, sid, who, str(body.get("text") or ""), str(body.get("title") or ""))
        if action == "music_share":
            return music.share(adp, sid, who, body.get("other") or None)
        if action == "music_hold":
            return music.hold(adp, sid, who, bool(body.get("on", True)))
        if action == "music_open":
            return music.open_slot(adp, who, str(body.get("title") or ""), str(body.get("purpose") or ""), body.get("vocal"), body.get("singers"))
        if action == "music_sheet":
            return music.fill_spot(adp, str(body.get("sheet") or ""), str(body.get("pointer") or ""), body.get("value"), who)
    except music.MusicRefused as e:
        journal.append(adp.root, who, "refused", f"music:{sid}" if sid else "music", note=str(e))
        return {"ok": False, "message": str(e)}
    return {"ok": False, "message": f"unknown action {action}"}


def _save_words(r: dict, done: str) -> dict:
    if r.get("proposed"):
        return {"ok": True, "message": f"{r['proposed'].get('to') or 'Its owner'} approved this — your change went to them as a proposal.", "proposed": r["proposed"]}
    if r.get("ok"):
        return {"ok": True, "message": done if r.get("changed", True) else "Already so — nothing to change.", "hash": r.get("hash")}
    if r.get("conflict"):
        return {"ok": False, "message": "The file changed underneath (a session or another program) — nothing was written. Both versions are below.",
                "conflict": r["conflict"]}
    return {"ok": False, "message": "Not saved: " + "; ".join(r.get("refused") or ["refused"])}


def act_read(cfg: dict, action: str, body: dict, who: str | None) -> dict:
    """The read-through (BUILD 07): edit a line, rule on it, pin a note — signed, journaled, through the safe path."""
    if not who:
        return {"ok": False, "message": "set who you are first (top right) — every change is signed"}
    gid = str(body.get("game") or current_game(cfg))
    if not games.has_adapter(cfg, gid):
        return {"ok": False, "message": f"{gid} has no Story adapter yet"}
    adp = games.adapter(cfg, gid)
    _summary_cache.pop(gid, None)
    ref = str(body.get("ref") or "")
    h = body.get("hash") or None
    try:
        if action == "read_edit":
            return _save_words(readthrough.edit_line(adp, ref, str(body.get("field") or "text"), str(body.get("value") or ""), who, h), "Saved.")
        if action == "read_mark":
            st = str(body.get("status") or "")
            r = readthrough.mark(adp, ref, st, who, h, note=body.get("note") or None, label=body.get("label") or None)
            return _save_words(r, {"approved": "Approved.", "flagged": "Flagged.", "draft": "Left as a draft."}.get(st, "Saved."))
        if action == "read_note":
            n = notes.add(adp.root, ref, who, str(body.get("text") or ""), tag=str(body.get("tag") or "note"),
                          reply_to=body.get("reply_to") or None, label=body.get("label") or None)
            return {"ok": True, "message": "Noted — the next session sees it in its digest.", "note": n}
        if action == "read_resolve":
            n = notes.add(adp.root, ref, who, "", resolves=str(body.get("note") or ""), label=body.get("label") or None)
            return {"ok": True, "message": "Resolved.", "note": n}
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": False, "message": f"unknown action {action}"}


def memory_view(cfg: dict, what: str, q: dict, ui_state=None) -> dict:
    """Team memory (BUILD 17): the rulings book, a question checked against it, the idea box, playtest notes, and where
    the game stands. Read-only."""
    gid = q.get("id", [current_game(cfg)])[0]
    one = lambda k, d="": q.get(k, [d])[0]
    if what == "standing":
        return standing.data(cfg, gid, ui_state)
    root = games.game_root(cfg, gid)
    if not root or not root.is_dir():
        return {"error": f"the game folder for {gid} isn't reachable from this computer"}
    adp = games.adapter(cfg, gid) if games.has_adapter(cfg, gid) else None
    if what == "rulings":
        kinds = [k for k in one("kind").split(",") if k] or None
        rows = rulings.search(root, one("q"), adp, limit=int(one("limit", "200") or 200), kinds=kinds,
                              include_retired=bool(one("retired")))
        return {"rulings": rows, "summary": rulings.summary(root, adp), "conflicts": rulings.conflicts(root, adp),
                "files": rulings.book(root, adp)["files"]}
    if what == "rulecheck":
        qs = [x for x in q.get("q", []) if str(x).strip()]
        return {"checked": [{"question": x, "rulings": rulings.check(root, x, adp)} for x in qs]}
    if what == "ideas":
        return {"ideas": ideas.listing(root, one("state", "open") or "open"), "counts": ideas.counts(root)}
    return playtest.inbox(root, adp)


def act_memory(cfg: dict, action: str, body: dict, who: str | None) -> dict:
    """The rulings book, the idea box, playtest notes — signed, through rulings.py / ideas.py / playtest.py (the same
    functions as python -m forge rulings | idea | playtest)."""
    if not who:
        return {"ok": False, "message": "set who you are first (bottom left) — everything here is signed"}
    gid = str(body.get("game") or current_game(cfg))
    root = games.game_root(cfg, gid)
    if not root or not root.is_dir():
        return {"ok": False, "message": f"the game folder for {gid} isn't reachable"}
    areas._badge_cache.pop(gid, None)
    try:
        if action == "rule_record":
            at = body.get("applies_to") or None
            e = rulings.record(root, who, str(body.get("text") or ""), by=str(body.get("by") or "") or None,
                               source=str(body.get("source") or ""), question=str(body.get("question") or ""),
                               applies_to=at, value=body.get("value") if at else None)
            return {"ok": True, "message": "In the rulings book.", "ruling": e}
        if action == "rule_retire":
            rulings.retire(root, who, str(body.get("id") or ""), str(body.get("why") or ""))
            return {"ok": True, "message": "Marked as no longer holding — it stays in the book, struck through."}
        if action == "idea_add":
            i = ideas.add(root, who, str(body.get("text") or ""), at=body.get("at") or None, obj=body.get("obj") or None,
                          label=body.get("label") or None)
            return {"ok": True, "message": "In the idea box.", "idea": i}
        if action == "idea_sort":
            ideas.sort(root, str(body.get("id") or ""), who, str(body.get("to") or ""), str(body.get("where") or ""),
                       str(body.get("note") or ""))
            return {"ok": True, "message": "Sorted — the idea says where it went."}
        if action == "idea_task":
            o = ideas.to_task(root, str(body.get("id") or ""), who, str(body.get("for") or ""), str(body.get("priority") or "soon"))
            return {"ok": True, "message": f"A task for {o['for']} now.", "order": o}
        if action == "idea_note":
            n = ideas.to_note(root, str(body.get("id") or ""), who, str(body.get("obj") or ""), body.get("label") or None,
                              body.get("to") or None)
            return {"ok": True, "message": "Pinned as a note there.", "note": n}
        if action == "playtest_in":
            r = playtest.take_in(cfg, gid, who, to=str(body.get("to") or "Claude"))
            _summary_cache.pop(gid, None)
            return r
    except FileNotFoundError as e:
        return {"ok": False, "message": f"not found: {e}"}
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": False, "message": f"unknown action {action}"}


def act_workbench(cfg: dict, action: str, body: dict, who: str | None) -> dict:
    """People, Quests, Voice sheets, Find & replace, Play from here (BUILD 07b) — signed, through the safe path."""
    gid = str(body.get("game") or current_game(cfg))
    if not games.has_adapter(cfg, gid):
        return {"ok": False, "message": f"{gid} has no Story adapter yet"}
    adp = games.adapter(cfg, gid)
    _summary_cache.pop(gid, None)
    try:
        if action == "wb_play":
            return workbench.play(adp, body.get("place") or None, body.get("era") or None, body.get("quest") or None)
        if not who:
            return {"ok": False, "message": "set who you are first — every change is signed"}
        if action == "wb_edit":
            return _save_words(workbench.edit_field(adp, str(body.get("ref") or ""), body.get("value"), who, body.get("hash") or None,
                                                    bool(body.get("i_mean_it"))), "Saved.")
        if action == "wb_mark":
            st = str(body.get("status") or "")
            r = readthrough.mark(adp, str(body.get("ref") or ""), st, who, body.get("hash") or None, note=body.get("note") or None,
                                 label=body.get("label") or None)
            return _save_words(r, {"approved": "Approved.", "flagged": "Flagged.", "draft": "Left as a draft."}.get(st, "Saved."))
        if action == "wb_voice":
            return workbench.save_voice(adp, str(body.get("kind") or ""), str(body.get("vid") or ""), str(body.get("field") or ""),
                                        body.get("value"), who)
        if action == "wb_replace":
            return workbench.replace(adp, str(body.get("q") or ""), str(body.get("repl") or ""), list(body.get("refs") or []), who,
                                     bool(body.get("case")), bool(body.get("word")))
    except workbench.WorkbenchRefused as e:
        return {"ok": False, "message": str(e)}
    except FileNotFoundError as e:
        return {"ok": False, "message": f"not found: {e}"}
    return {"ok": False, "message": f"unknown action {action}"}


def act_art(cfg: dict, action: str, body: dict, who: str | None) -> dict:
    """Sprite intake and Characters — every write signed, every one through the forge's own functions (intake via
    run_now, the registry via night4/characters, the face sheet via reviews, the set via the submit shim)."""
    gid = str(body.get("game") or current_game(cfg))
    if gid not in games.game_ids(cfg):
        return {"ok": False, "message": f"there is no game '{gid}' in games/"}
    try:
        if action == "intake_upload":
            if not who:
                return {"ok": False, "message": "set who you are first (top right) — what you take in is signed"}
            data = base64.b64decode(str(body.get("data") or "").split(",", 1)[-1] or b"", validate=False)
            p = sprites.save_upload(cfg, gid, str(body.get("character") or ""), body.get("variant") or None,
                                    str(body.get("filename") or "sheet.png"), data)
            v = sprites.open_sheet(cfg, gid, str(body.get("character")), body.get("variant") or None, p,
                                   tool=body.get("tool") or None, who=who)
            if body.get("tool"):
                sprites.remember_tool(cfg, gid, str(body["tool"]))
            sprites._sign(cfg, gid, who, "art", f"sprite intake · {sprites.who_dir(v['character'], v['variant'])} · {p.name}",
                          note=f"took in a sheet ({v['found']} figure(s) found) — kept at {p}")
            v["message"] = f"Kept {p.name} — {v['found']} figure(s) found. Click each one and say which way it faces."
            return v
        if action == "intake_open":
            v = sprites.open_sheet(cfg, gid, str(body.get("character") or ""), body.get("variant") or None,
                                   str(body.get("sheet") or ""), tool=body.get("tool") or None,
                                   fresh=bool(body.get("fresh")), who=who)
            if body.get("tool"):
                sprites.remember_tool(cfg, gid, str(body["tool"]))
            v["message"] = (f"{v['found']} figure(s) found. " + ("This is the forge's guess — click each figure and say which "
                            "way it faces." if not v["checked"] else f"Checked by {v.get('checked_by') or 'a person'}."))
            return v
        if action == "intake_save":
            return sprites.save_mapping(cfg, gid, body.get("mapping"), body.get("rev"), body.get("figures") or [],
                                        body.get("mirror") or [], who, bool(body.get("mirror_anyway")),
                                        body.get("holes"))
        if action == "intake_make":
            return sprites.make_sheet(cfg, gid, body.get("mapping"), who)
        if action == "tool_add":
            return sprites.add_tool(cfg, gid, str(body.get("name") or ""), str(body.get("version") or ""),
                                    str(body.get("commercial") or ""), str(body.get("condition") or ""),
                                    str(body.get("where") or ""), who)
        if action == "char_face":
            return cast.make_face_sheet(cfg, gid, str(body.get("cid") or ""), who)
        if action == "char_plan":
            return cast.plan_set(cfg, gid, str(body.get("cid") or ""), body.get("variant") or None)
        if action == "char_queue":
            return cast.queue_set(cfg, gid, str(body.get("cid") or ""), body.get("variant") or None, who)
        if action == "char_edit":
            return cast.edit(cfg, gid, str(body.get("cid") or ""), str(body.get("variant") or ""), str(body.get("field") or ""),
                             body.get("value"), body.get("rev"), who)
        # BUILD 12 — the Wanted board, Review & approve → Deliver, Make a picture
        if action == "wanted_plan":
            if not who:
                return {"ok": False, "message": "set who you are first (top right) — a plan is signed"}
            return production.make_plan(cfg, gid, who)
        if action == "wanted_select":
            return production.plan_selection(cfg, gid, body.get("names") or [])
        if action == "wanted_queue":
            return production.queue_selection(cfg, gid, body.get("names") or [], who)
        if action == "wanted_sheet":
            return production.town_sheet(cfg, gid, body.get("town") or None, who)
        state = getattr(SuiteHandler, "state", None) or ui.State(cfg)
        if action == "review_approve":
            pick = body.get("pick")
            return production.approve(cfg, gid, str(body.get("jid") or ""), str(body.get("wanted") or ""), who,
                                      as_set=bool(body.get("set")), pick=int(pick) if pick not in (None, "") else None,
                                      dry=bool(body.get("dry", True)))
        if action == "review_redo":
            return production.redo(cfg, gid, str(body.get("jid") or ""), str(body.get("note") or ""), who, state)
        if action == "review_out":
            return production.send_out(cfg, gid, str(body.get("jid") or ""), who)
        if action == "deliver_run":
            return production.deliver(cfg, gid, who, dry=bool(body.get("dry", True)), fit=bool(body.get("fit")))
        if action == "make_preview":
            return picture.preview(cfg, gid, body.get("form") or {})
        if action == "make_queue":
            return picture.queue(cfg, gid, body.get("form") or {}, who)
        # BUILD 14 — Called out, mark-up, the prompt library, bake-offs, outside tools, the model shelf
        if action == "fin_callout":
            return finishing.callout(cfg, gid, str(body.get("action") or ""), str(body.get("draft") or ""), who)
        if action == "fin_takein":
            return finishing.take_in(cfg, gid, who)
        if action == "fin_markup":
            return finishing.markup(cfg, gid, str(body.get("jid") or ""), str(body.get("file") or ""), body.get("shapes") or [],
                                    str(body.get("note") or ""), str(body.get("fix") or ""), who, state)
        if action == "fin_block":
            return finishing.edit_block(cfg, gid, str(body.get("name") or ""), str(body.get("text") or ""), who)
        if action == "fin_ab":
            return finishing.ab_draft(cfg, gid, str(body.get("block") or ""), str(body.get("batch") or ""), who)
        if action == "fin_bakeoff":
            return finishing.bakeoff_act(cfg, gid, str(body.get("action") or ""), str(body.get("file") or ""), who)
        if action == "fin_handin":
            return finishing.hand_in(cfg, gid, str(body.get("name") or ""), body.get("tool") or None, who)
        if action == "fin_open":
            return finishing.open_folder(cfg, str(body.get("path") or ""))
        if action == "fin_models":
            return {"ok": True, **finishing.models(cfg, gid, scan=bool(body.get("scan")))}
    except (sprites.IntakeRefused, cast.CastRefused, production.ProductionRefused, picture.MakeRefused,
            finishing.FinishRefused) as e:
        return {"ok": False, "message": str(e)}
    except FileNotFoundError as e:
        return {"ok": False, "message": f"not found: {e}"}
    return {"ok": False, "message": f"unknown action {action}"}


_thumbs: dict[tuple, bytes] = {}


def picture_bytes(src: Path, w: int | None) -> tuple[bytes, str]:
    """A picture as is, or a JPEG no wider than w (kept in memory while the file is unchanged)."""
    types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
    if not w:
        return src.read_bytes(), types.get(src.suffix.lower(), "application/octet-stream")
    from PIL import Image
    key = (str(src), src.stat().st_mtime, int(w))
    if key not in _thumbs:
        with Image.open(src) as im:
            im = im.convert("RGBA")
            k = min(1.0, int(w) / max(1, im.width))
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))))
            bg = Image.new("RGBA", im.size, (40, 40, 46, 255))
            bg.alpha_composite(im)
            buf = io.BytesIO()
            bg.convert("RGB").save(buf, "JPEG", quality=86)
        if len(_thumbs) > 300:
            _thumbs.clear()
        _thumbs[key] = buf.getvalue()
    return _thumbs[key], "image/jpeg"


def _tail(p: Path, n: int = 400) -> str:
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return f"(no file at {p})"
    return "\n".join(lines[-n:])


class SuiteHandler(ui.Handler):
    cfg: dict = None

    def _json(self, obj, code=200):
        super()._json(runwords.deep(obj), code)        # on a Mac no .bat is ever shown (BUILD 27)

    def _game_root(self, q: dict) -> Path:
        gid = q.get("id", [current_game(self.cfg)])[0]
        root = games.game_root(self.cfg, gid)
        if not root or not root.is_dir():
            raise FileNotFoundError(f"game folder for {gid}")
        return root

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/":
                self._send(200, runwords.say(SHELL, page=True).encode("utf-8"), "text/html; charset=utf-8")
            elif u.path == "/art/queue":
                page = runwords.say(ui.PAGE.replace("</head>", "<style>header h1{display:none}</style></head>", 1), page=True)
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif u.path == "/api/suite/games":
                cur = current_game(self.cfg)
                who = settings.identity()
                ls = games.listing(self.cfg)
                for g in ls:
                    g["unread"] = 0
                    if who and g["root_exists"]:
                        try:
                            g["unread"] = mail.unread_count(games.game_root(self.cfg, g["id"]), who)
                        except OSError:
                            pass
                names = []
                try:
                    r = games.game_root(self.cfg, cur)
                    names = [n for n in mail.correspondents(r) if not settings.is_assistant(n)] if r and r.is_dir() else []
                except OSError:
                    pass
                self._json({"games": ls, "current": cur, "identity": who, "people": names})
            elif u.path == "/api/suite/areas":
                gid = q.get("id", [current_game(self.cfg)])[0]
                self._json({"areas": areas.public(), "needs": areas.needs(self.cfg, gid), "last": areas.last_place(gid),
                            "old": areas.OLD_SCREENS})
            elif u.path == "/api/suite/badges":
                gid = q.get("id", [current_game(self.cfg)])[0]
                self._json(areas.badges(self.cfg, gid, self.state, fresh=bool(q.get("fresh"))))
            elif u.path == "/api/suite/tasks":
                gid = q.get("id", [current_game(self.cfg)])[0]
                try:
                    provide.sync(self.cfg, gid)      # a new picture request shows up on Tasks without anyone running anything
                except Exception as e:  # noqa: BLE001 — the pool never stops Tasks from opening
                    log.warning("provide: sync before Tasks failed: %s", e)
                self._json(tasks.board(self.cfg, gid, settings.identity(), self.state))
            elif u.path == "/api/suite/floorplans":
                gid = q.get("id", [current_game(self.cfg)])[0]
                try:
                    self._json(floorplans.view(self.cfg, gid))
                except floorplans.FloorPlanRefused as e:
                    self._json({"error": str(e)})
            elif u.path == "/api/suite/floorplan":
                gid = q.get("id", [current_game(self.cfg)])[0]
                try:
                    self._json(floorplans.open_set(self.cfg, gid, q.get("f", [""])[0], q.get("map", [None])[0]))
                except floorplans.FloorPlanRefused as e:
                    self._json({"error": str(e)}, 404)
            elif u.path == "/suite/layoutimg":
                gid = q.get("id", [current_game(self.cfg)])[0]
                name = Path(q.get("file", [""])[0]).name
                try:
                    fol = floorplans._folder(self.cfg, gid, q.get("f", [""])[0])
                except floorplans.FloorPlanRefused:
                    raise FileNotFoundError("plan")
                src = fol / name
                if not name.endswith(".png") or not src.is_file():
                    raise FileNotFoundError("picture")
                w = q.get("w", [None])[0]
                body, ctype = picture_bytes(src, int(w) if w and w.isdigit() else None)
                self._send(200, body, ctype)
            elif u.path == "/api/suite/provide":
                gid = q.get("id", [current_game(self.cfg)])[0]
                self._json(provide.view(self.cfg, gid, settings.identity(), self.state))
            elif u.path == "/api/suite/tasksdone":
                root = self._game_root(q)
                self._json({"done": tasks.done(root, settings.identity())})
            elif u.path == "/api/suite/status":
                gid = q.get("id", [current_game(self.cfg)])[0]
                tab = q.get("tab", ["glance"])[0]
                self._json(status.builds(self.cfg, gid) if tab == "builds" else status.completeness(self.cfg, gid) if tab == "game"
                           else status.glance(self.cfg, gid, self.state))
            elif u.path == "/api/suite/briefs":
                gid = q.get("id", [current_game(self.cfg)])[0]
                self._json({"items": music.briefs_and_songs(games.adapter(self.cfg, gid))} if games.has_adapter(self.cfg, gid)
                           else {"error": f"{gid} has no Story adapter yet", "items": []})
            elif u.path in ("/api/suite/people", "/api/suite/person", "/api/suite/quests", "/api/suite/quest", "/api/suite/voices",
                            "/api/suite/voice", "/api/suite/find", "/api/suite/voicesfor"):
                gid = q.get("id", [current_game(self.cfg)])[0]
                if not games.has_adapter(self.cfg, gid):
                    self._json({"error": f"{gid} has no Story adapter yet"}, 404)
                    return
                adp = games.adapter(self.cfg, gid)
                one = lambda k: q.get(k, [""])[0]
                try:
                    if u.path == "/api/suite/people":
                        self._json({"people": workbench.people(adp)})
                    elif u.path == "/api/suite/person":
                        self._json(workbench.person(adp, one("pid")))
                    elif u.path == "/api/suite/quests":
                        self._json({"quests": workbench.quests(adp)})
                    elif u.path == "/api/suite/quest":
                        self._json(workbench.quest(adp, one("qid")))
                    elif u.path == "/api/suite/voices":
                        self._json(workbench.voices(adp))
                    elif u.path == "/api/suite/voice":
                        self._json(workbench.voice(adp, one("kind"), one("vid")))
                    elif u.path == "/api/suite/voicesfor":
                        pg = readthrough.page(adp, one("place"), one("era") or "all")
                        self._json(workbench.voices_for(adp, one("place"), [{**l, "ref": l["ref"]} for l in pg["lines"]]))
                    else:
                        self._json(workbench.find(adp, one("q"), q.get("repl", [None])[0], bool(one("case")), bool(one("word"))))
                except (workbench.WorkbenchRefused, ValueError) as e:
                    self._json({"error": str(e)}, 404)
            elif u.path in ("/api/suite/rulings", "/api/suite/rulecheck", "/api/suite/ideas", "/api/suite/playtest",
                            "/api/suite/standing"):
                self._json(memory_view(self.cfg, u.path.rsplit("/", 1)[-1], q, self.state))
            elif u.path == "/api/suite/about":
                self._json(about(self.cfg))
            elif u.path == "/api/suite/home":
                self._json(home.data(self.cfg, self.state))
            elif u.path == "/api/suite/game":
                gid = q.get("id", [current_game(self.cfg)])[0]
                self._json(game_view(self.cfg, gid, fresh=bool(q.get("fresh"))))
            elif u.path == "/api/suite/mail":
                root, who = self._game_root(q), settings.identity() or ""
                self._json({"letters": mail.box(root, who, q.get("box", ["inbox"])[0], q.get("q", [None])[0]),
                            "unread": mail.unread_count(root, who), "who": who,
                            "correspondents": [n for n in mail.correspondents(root, who) if n != who]})
            elif u.path == "/api/suite/letter":
                root = self._game_root(q)
                self._json(mail.thread_view(root, q.get("letter", [""])[0], settings.identity() or ""))
            elif u.path == "/api/suite/orders":
                root, who = self._game_root(q), settings.identity() or ""
                names = mail.correspondents(root, who)
                gs = orders.groups(root, names)
                show = None if q.get("all") else "open"
                label = {}
                for n in names:
                    label.setdefault(mail.group_of(n), n.split()[0])
                self._json({"groups": [{"group": g, "label": label.get(g, g.title()), "orders": orders.listing(root, g, show)} for g in gs],
                            "me": mail.group_of(who) if who else None, "names": names})
            elif u.path == "/api/suite/away":
                root, who = self._game_root(q), settings.identity()
                self._json(away.digest(root, who) if who else {"count": 0, "sections": [], "since": None, "people": []})
            elif u.path == "/api/suite/towns":
                gid = q.get("id", [current_game(self.cfg)])[0]
                self._json({"towns": readthrough.towns(games.adapter(self.cfg, gid))} if games.has_adapter(self.cfg, gid)
                           else {"error": f"{gid} has no Story adapter yet"})
            elif u.path == "/api/suite/read":
                gid = q.get("id", [current_game(self.cfg)])[0]
                try:
                    self._json(readthrough.page(games.adapter(self.cfg, gid), q.get("place", [""])[0], q.get("era", ["all"])[0] or "all"))
                except ValueError as e:
                    self._json({"error": str(e)}, 404)
            elif u.path == "/api/suite/notes":
                root = self._game_root(q)
                obj = q.get("obj", [None])[0]
                self._json({"threads": notes.threads(root, obj, open_only=bool(q.get("open", [""])[0]))})
            elif u.path == "/api/suite/music":
                gid = q.get("id", [current_game(self.cfg)])[0]
                if not games.has_adapter(self.cfg, gid):
                    self._json({"error": f"{gid} has no Story adapter yet"}, 404)
                else:
                    self._json(music.board(games.adapter(self.cfg, gid)))
            elif u.path == "/api/suite/sheet":
                gid = q.get("id", [current_game(self.cfg)])[0]
                try:
                    sh = music.sheet(games.adapter(self.cfg, gid), q.get("sheet", [""])[0])
                    self._json({"sheet": sh, "md": music.render_sheet(sh)})
                except music.MusicRefused as e:
                    self._json({"error": str(e)}, 404)
            elif u.path == "/suite/audio":
                gid = q.get("id", [current_game(self.cfg)])[0]
                p = music.audio_file(games.adapter(self.cfg, gid), q.get("slot", [None])[0], q.get("inbox", [None])[0])
                self._send_file_ranged(p, music.AUDIO_MIME.get(p.suffix.lower(), "application/octet-stream"))
            elif u.path == "/suite/gamefile":
                root = self._game_root(q)
                rel = q.get("rel", [""])[0]
                src = (root / rel).resolve()
                types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
                         ".md": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8", ".json": "text/plain; charset=utf-8"}
                if root.resolve() not in src.parents or not src.is_file() or src.suffix.lower() not in types:
                    raise FileNotFoundError(rel)
                self._send(200, src.read_bytes(), types[src.suffix.lower()])
            elif u.path == "/api/suite/intake":
                gid = q.get("id", [current_game(self.cfg)])[0]
                self._json({"candidates": sprites.candidates(self.cfg, gid), "mappings": sprites.mappings(self.cfg, gid),
                            "characters": cast.listing(self.cfg, gid), "tools": sprites.tools(self.cfg, gid),
                            "words": sprites.WORDS})
            elif u.path == "/suite/picture":
                gid = q.get("id", [current_game(self.cfg)])[0]
                try:
                    src = sprites.allowed_picture(self.cfg, gid, q.get("path", [""])[0])
                except sprites.IntakeRefused:
                    raise FileNotFoundError("picture")
                w = q.get("w", [None])[0]
                body, ctype = picture_bytes(src, int(w) if w and w.isdigit() else None)
                self._send(200, body, ctype)
            elif u.path == "/api/suite/wanted":
                self._json(production.board(self.cfg, q.get("id", [current_game(self.cfg)])[0]))
            elif u.path == "/api/suite/review":
                self._json(production.review(self.cfg, q.get("id", [current_game(self.cfg)])[0], self.state))
            elif u.path == "/api/suite/job":
                try:
                    self._json(production.job_view(self.cfg, q.get("id", [current_game(self.cfg)])[0], q.get("jid", [""])[0], self.state))
                except production.ProductionRefused as e:
                    self._json({"error": str(e)}, 404)
            elif u.path == "/api/suite/make":
                self._json(picture.kinds(self.cfg, q.get("id", [current_game(self.cfg)])[0]))
            elif u.path == "/api/suite/calledout":
                self._json({"drafts": finishing.called_out(self.cfg)})
            elif u.path == "/api/suite/library":
                self._json(finishing.library(self.cfg, q.get("id", [current_game(self.cfg)])[0]))
            elif u.path == "/api/suite/whereused":
                self._json({"hits": finishing.where_used(self.cfg, q.get("block", [""])[0])})
            elif u.path == "/api/suite/bakeoffs":
                self._json(finishing.bakeoffs(self.cfg, q.get("id", [current_game(self.cfg)])[0]))
            elif u.path == "/api/suite/handoffs":
                self._json(finishing.handoffs(self.cfg))
            elif u.path == "/api/suite/characters":
                gid = q.get("id", [current_game(self.cfg)])[0]
                self._json({"characters": cast.listing(self.cfg, gid)})
            elif u.path == "/api/suite/character":
                gid = q.get("id", [current_game(self.cfg)])[0]
                try:
                    self._json(cast.page(self.cfg, gid, q.get("cid", [""])[0]))
                except cast.CastRefused as e:
                    self._json({"error": str(e)}, 404)
            elif u.path == "/suite/charref":
                gid = q.get("id", [current_game(self.cfg)])[0]
                pg = cast.page(self.cfg, gid, q.get("cid", [""])[0])
                v = next((x for x in pg["variants"] if x["name"] == q.get("variant", [""])[0]), None)
                i = int(q.get("i", ["-1"])[0])
                if v is None or not (0 <= i < len(v["references"])) or not v["references"][i]["exists"]:
                    raise FileNotFoundError("reference")
                src = Path(v["references"][i]["path"])
                if src.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"):
                    raise FileNotFoundError("reference")
                body, ctype = picture_bytes(src, int(q.get("w", ["360"])[0] or 360))
                self._send(200, body, ctype)
            elif u.path == "/suite/text":
                what = q.get("what", ["log"])[0]
                if what == "worklog":
                    root = games.game_root(self.cfg, q.get("id", [current_game(self.cfg)])[0])
                    body = _tail(Path(root) / "WORKBENCH_LOG.md", 2000) if root else "(no game)"
                else:
                    logs = sorted(cfgmod.path_of(self.cfg, "logs").glob("forge_*.log"))
                    body = _tail(logs[-1]) if logs else "(no log yet)"
                self._send(200, body.encode("utf-8"), "text/plain; charset=utf-8")
            else:
                super().do_GET()
        except FileNotFoundError:
            self._send(404, b"not found", "text/plain")
        except Exception:  # noqa: BLE001
            log.error("suite GET %s: %s", self.path, traceback.format_exc())
            self._send(500, b"error - see the forge log", "text/plain")

    def _send_file_ranged(self, p: Path, ctype: str):
        """An audio file, with byte ranges (a browser's player seeks with them — the loop-seam button needs that)."""
        size = p.stat().st_size
        rng = self.headers.get("Range") or ""
        start, end = 0, size - 1
        partial = rng.startswith("bytes=")
        if partial:
            a, _, b = rng[6:].split(",")[0].partition("-")
            try:
                if a:
                    start = int(a)
                    end = int(b) if b else size - 1
                else:
                    start = max(0, size - int(b))
            except ValueError:
                partial, start, end = False, 0, size - 1
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        with open(p, "rb") as f:
            f.seek(start)
            body = f.read(end - start + 1)
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(body)))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/suite/upload":
            return self._upload(parse_qs(u.query))
        if not u.path.startswith("/api/suite/act/"):
            return super().do_POST()
        if self.headers.get("X-Forge") != "1":
            self._send(403, b"forbidden", "text/plain")
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            name = u.path.rsplit("/", 1)[-1]
            r = act(self.cfg, name, body)
            log.info("suite: %s → %s", name, r.get("message"))
            self._json(r)
        except ValueError as e:
            self._json({"ok": False, "message": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            log.error("suite POST %s: %s", self.path, traceback.format_exc())
            self._json({"ok": False, "message": f"{type(e).__name__}: {e}"}, 500)


    def _upload(self, q: dict):
        """A file dropped on a task's card, streamed in (a WAV can be hundreds of MB): the raw body goes to
        <game>/_incoming/<stamp>-<name>.part in 1 MB pieces, is renamed only when every byte has arrived, and only then
        handed to the area's own delivery (tasks.accept). The kind is checked from the name before a byte is written."""
        if self.headers.get("X-Forge") != "1":
            self._send(403, b"forbidden", "text/plain")
            return
        self.close_connection = True          # a refused upload isn't read to the end; this connection isn't reused
        gid = q.get("game", [current_game(self.cfg)])[0]
        tid = q.get("task", [""])[0]
        name = tasks.safe_name(q.get("name", ["file"])[0])
        who = settings.identity() or ""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            root = games.game_root(self.cfg, gid)
            if not root or not root.is_dir():
                raise tasks.TaskRefused(f"the game folder for {gid} isn't reachable")
            if not who or settings.is_assistant(who):
                raise tasks.TaskRefused("uploading to a task is a person's act — a session asks for a file with a work order instead")
            card = tasks.find_card(self.cfg, gid, tid, who, self.state)
            tasks.check_kind(card, name)
            if n <= 0:
                raise tasks.TaskRefused("the file was empty")
            inc = tasks.incoming_dir(root)
            inc.mkdir(parents=True, exist_ok=True)
            tasks.sweep_incoming(root)
            stamp = settings.now().strftime("%Y%m%d-%H%M%S")
            part = inc / f"{stamp}-{name}.part"
            got = 0
            with open(part, "wb") as f:
                while got < n:
                    chunk = self.rfile.read(min(1 << 20, n - got))
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
            if got < n:
                log.warning("suite: upload of %s stopped at %d of %d bytes — nothing delivered", name, got, n)
                try:
                    part.unlink()
                except OSError:
                    pass
                self._json({"ok": False, "message": "the upload stopped half-way — nothing was delivered"}, 400)
                return
            staged = part.with_name(part.name[:-5])
            os.replace(part, staged)
            r = tasks.accept(self.cfg, gid, tid, staged, name, who, self.state)
            areas._badge_cache.pop(gid, None)
            log.info("suite: upload %s → %s: %s", name, tid, r.get("message"))
            self._json(r)
        except tasks.TaskRefused as e:
            log.info("suite: upload %s → %s refused: %s", name, tid, e)
            self._json({"ok": False, "message": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            log.error("suite upload: %s", traceback.format_exc())
            self._json({"ok": False, "message": f"{type(e).__name__}: {e}"}, 500)


def about(cfg: dict) -> dict:
    """Settings → About and This computer: the version, the tests' last result, where the log is, who you are, and the
    folder each game is read from."""
    root = cfgmod.ROOT
    version = ""
    for f in ("COMMIT_MESSAGE.last.txt", "CHANGELOG.md"):
        p = root / f
        if p.is_file():
            for l in p.read_text(encoding="utf-8", errors="replace").splitlines():
                l = l.strip().lstrip("#").strip()
                if l:
                    version = l[:200]
                    break
        if version:
            break
    tests = None
    tp = cfgmod.path_of(cfg, "logs") / "tests_latest.txt"
    if tp.is_file():
        tail = [l for l in tp.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        tests = {"line": tail[-1] if tail else "", "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(tp.stat().st_mtime))}
    logs = sorted(cfgmod.path_of(cfg, "logs").glob("forge_*.log"))
    return {"version": version, "tests": tests, "log": str(logs[-1]) if logs else str(cfgmod.path_of(cfg, "logs")),
            "identity": settings.identity(), "settings_file": str(settings.PATH), "forge": str(root),
            "games": [{"id": g["id"], "name": g["name"], "root": g.get("root"), "reachable": g["root_exists"],
                       "overridden": bool(settings.game_root_override(g["id"])), "from_game": _game_cfg_root(cfg, g["id"])}
                      for g in games.listing(cfg)],
            "system": osopen.system(), "settings": {k: settings.load().get(k) for k in settings.KEYS},
            "worker_here": worker.here(), "worker_pc": runwords.worker_pc(),
            "timezones": ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles",
                          "America/Anchorage", "Pacific/Honolulu", "Europe/London", "Europe/Berlin", "Asia/Tokyo", "Australia/Sydney", "UTC"]}


def _game_cfg_root(cfg: dict, gid: str) -> str | None:
    try:
        return games.game_cfg(cfg, gid).get("game_root")
    except Exception:  # noqa: BLE001
        return None


def make_server(cfg: dict, port: int = PORT):
    from http.server import ThreadingHTTPServer
    SuiteHandler.state = ui.State(cfg)
    SuiteHandler.cfg = cfg
    return ThreadingHTTPServer((HOST, port), SuiteHandler)


def serve(cfg: dict, port: int = PORT, open_browser: bool = True) -> int:
    url = f"http://{HOST}:{port}/"
    try:
        srv = make_server(cfg, port)
    except OSError:
        print(f"The suite is already running — opening {url}")
        if open_browser:
            webbrowser.open(url)
        return 0
    log.info("suite: serving %s", url)
    print(f"RPG_Forge suite: {url}   (close this window to stop it — the art worker is not affected)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


SHELL = Path(__file__).with_name("shell.html").read_text(encoding="utf-8")
