"""The suite: one local web app for every game — `forge.bat` → http://127.0.0.1:8770

A game picker is the first control; two sides, **Art** and **Story**. Art's first screens are Home (the worker, the
queue, the disk, three safe buttons) and Queue & pictures (the dashboard that `ui.bat` has always shown — served by
the same code). Story shows what the suite can read from the chosen game until the Mail (BUILD 03) and the
Workbench (BUILD 07) arrive. BUILD 04 adds Sprite intake (click a figure, pick its facing → the game sheet) and
Characters (the registry as pages, the face sheet, make the set) — sprites.py and cast.py. BUILD 12 adds Make a
picture (picture.py), Review & approve → Deliver and the Wanted board (production.py). BUILD 14 adds Called out and
mark-up, the prompt library, bake-offs, models and outside tools (finishing.py).

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
from . import approval, away, cast, finishing, games, home, journal, mail, music, notes, orders, picture, production, readthrough, settings, sprites, worker

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
    if action.startswith(("mail_", "order_", "away_")):
        return act_story(cfg, action, body, who)
    if action.startswith(("intake_", "tool_", "char_", "wanted_", "review_", "deliver_", "make_", "fin_")):
        return act_art(cfg, action, body, who)
    if action.startswith("music_"):
        return act_music(cfg, action, body, who)
    if action.startswith("read_"):
        return act_read(cfg, action, body, who)
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
            if os.name == "nt":
                os.startfile(str(p))               # Explorer / the default editor — the same as double-clicking it
            else:
                subprocess.Popen(["xdg-open", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            if body.get("draft_id"):
                l = mail.send_edited_draft(root, str(body["draft_id"]), who, *args, questions=qs)
            else:
                l = mail.send(root, who, *args, questions=qs)
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
                           str(body.get("priority") or "soon"), body.get("object") or None)
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
                self._send(200, SHELL.encode("utf-8"), "text/html; charset=utf-8")
            elif u.path == "/art/queue":
                page = ui.PAGE.replace("</head>", "<style>header h1{display:none}</style></head>", 1)
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
