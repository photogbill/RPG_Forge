"""Tasks — a to-do list, not an inbox (BUILD 26 B2; William, 2026-11-11: "If it looks too much like email for the tasks,
I might miss some — my email box has 20000 unread emails").

**Gathered for the person, not filed by them.** `gather()` collects everything in the game that is waiting on the person
at this install, one card per thing to do:
- work orders addressed to them;
- letters that still have open questions — one card per letter (a letter with no question is not a task; a brief's
  letter and a music profile's letter are folded into the brief's and the profile's card);
- music briefs waiting for their answer; songs written and waiting for the track; delivered vocals whose words still need
  confirming as sung;
- music profiles with open spots (one card per profile);
- pictures waiting in Review & approve (one card with the count);
- builds marked waiting on them in the game's build queue (the adapter's optional `builds()` hook);
- open notes addressed to them (a note with `to`, or a question an assistant pinned).

A card leaves the list in only two ways: it gets **done** (the thing itself changes — the questions answered, the track
delivered — or the person ticks it), or it is **dismissed with a reason**. Reading a card changes nothing. Ticks and
dismissals are kept in `<game>/work_orders/_ticked.json` with the card's *signature* (a letter's open count, the number
of pictures waiting…): when that changes, the card comes back. Every tick and dismissal is journaled (kind "task").

**Files on the card.** A card that wants a file (`wants`) takes it right there. It goes through the same door as the
area — a track through music.deliver (cemented), a sheet through Sprite intake, anything else into the folder the order
names — never copied into the game raw. Big files arrive as a stream into `<game>/_incoming/`, and only a finished
upload is handed on (`accept()`), so a browser closed half-way delivers nothing.
"""
from __future__ import annotations
import json, os, re, shutil
from datetime import datetime
from pathlib import Path

from ..log import get
from . import games, journal, mail, notes, orders, settings

log = get("suite")

KINDS_EXT = {
    "audio": (".ogg", ".mp3", ".wav", ".flac", ".m4a", ".opus"),
    "image": (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".psd", ".gif"),
    "sheet": (".png", ".jpg", ".jpeg", ".webp"),
    "text": (".md", ".txt", ".pdf", ".docx", ".rtf", ".odt", ".json"),
}
EFFORT_RANK = {"a minute": 0, "ten minutes": 1, "a sitting": 2}
NEXT_N = 7
OVERDUE_DAYS = 7


class TaskRefused(ValueError):
    """The rule said no; nothing was written."""


# ---------------------------------------------------------------- ticks and dismissals
def _ticked_path(root: Path) -> Path:
    return orders.folder(root) / "_ticked.json"


def _ticked(root: Path) -> dict:
    try:
        d = json.loads(_ticked_path(root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_ticked(root: Path, d: dict) -> None:
    orders._write(_ticked_path(root), d)


def _age_days(created: str | None, now: datetime) -> float:
    try:
        return max(0.0, (now - datetime.fromisoformat(str(created)[:19])).total_seconds() / 86400)
    except (TypeError, ValueError):
        return 0.0


def _effort_for_questions(n: int) -> str:
    return "a minute" if n <= 2 else "ten minutes" if n <= 6 else "a sitting"


def wants_label(w: dict | None) -> str:
    if not w:
        return ""
    n = int(w.get("count") or 1)
    k = w.get("kind") or "any"
    word = {"audio": "audio file", "image": "image", "sheet": "sprite sheet", "text": "document", "any": "file"}.get(k, "file")
    return f"{'one' if n == 1 else n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------- gathering
def _order_go(obj: str | None) -> str | None:
    if not obj:
        return None
    o = str(obj)
    if o.startswith("mail:"):
        return "messages/inbox/" + o[5:].split("#")[0]
    if o.startswith("job:"):
        return "art/review"
    if o.startswith("music:"):
        return "music/needed/" + o[6:]
    if o.startswith("place:"):
        return "story/read/" + o[6:]
    return None


def _goes_to_label(g: str | None, adp=None) -> str:
    if not g or g == "attach":
        return "kept with this order"
    if g.startswith("music:"):
        return "Music · " + g[6:]
    if g.startswith("sprite:"):
        return "Sprite intake · " + g[7:]
    return g.rstrip("/") + "/"


def gather(cfg: dict, gid: str, who: str | None, ui_state=None, now: datetime | None = None,
           include_ticked: bool = False) -> list[dict]:
    """Every open card for `who` in this game, ordered: things that unblock a build or a scene first, then the overdue,
    then the quick ones, then the rest."""
    now = now or settings.now()
    root = games.game_root(cfg, gid) if gid else None
    if not root or not root.is_dir() or not who:
        return []
    person = not settings.is_assistant(who)
    cards: list[dict] = []
    adp = None
    if games.has_adapter(cfg, gid):
        try:
            adp = games.adapter(cfg, gid)
        except Exception as e:  # noqa: BLE001
            log.warning("tasks: adapter for %s: %s", gid, e)

    # 1 · work orders addressed to them
    for o in orders.listing(root, mail.group_of(who), "open"):
        w = o.get("wants") if isinstance(o.get("wants"), dict) else None
        recv = o.get("received") or []
        c = {"id": f"order:{o['id']}", "kind": "order", "area": "tasks", "title": o["title"], "detail": o.get("detail") or "",
             "go": _order_go(o.get("object")), "from": o.get("by"), "effort": o.get("effort") or ("a minute" if w else "ten minutes"),
             "created": o.get("created"), "unblocks": o.get("priority") == "now" or bool(o.get("unblocks")),
             "sig": o["id"], "order": o["id"], "checkable": True}
        if o.get("provide"):          # a picture from the forge pool (provide.py) — also shown in Art → User Needs To Provide Image
            c["provide"] = str(o["provide"])
            c["area"] = "art"
        if w:
            c["wants"] = {"kind": w.get("kind") or "any", "count": int(w.get("count") or 1),
                          "ext": list(KINDS_EXT.get(w.get("kind") or "any", ()))}
            c["goes_to"] = o.get("goes_to") or "attach"
            c["wants_line"] = f"wants: {wants_label(w)} → {_goes_to_label(c['goes_to'])}"
            c["received"] = recv
            if c["wants"]["count"] > 1:
                c["progress"] = f"{len(recv)} of {c['wants']['count']}"
        cards.append(c)

    # 2 · music: briefs waiting for an answer, songs waiting for the track, vocals waiting for their words
    folded_letters: set[str] = set()
    folded_attach: set[str] = set()
    if adp is not None:
        try:
            from . import music
            ss = music.slots(adp)
            mp = music.paths(adp)
            for s in ss:
                scene = s.get("scene") or s["id"]
                if s.get("letter"):
                    folded_letters.add(s["letter"])
                if s.get("via") or s.get("own") and s["state"] == "needed":
                    continue
                e_hist = s.get("history") or []
                created = (e_hist[-1]["time"] if e_hist else None)
                if s["state"] == "proposed" and not s.get("verdict"):
                    cards.append({"id": f"brief:{s['id']}", "kind": "brief", "area": "music",
                                  "title": f"Answer the {scene} brief — yes / no / I'll write it",
                                  "go": f"music/needed/{s['id']}", "from": next((c["by"] for c in s.get("credits") or [] if c["what"] == "brief"), None),
                                  "effort": "a minute", "created": created, "unblocks": True, "sig": s["id"]})
                elif s["state"] == "written":
                    vs = s.get("versions") or []
                    # a song the board wrote waits to be made; a song already on an album only waits to be dropped in
                    cards.append({"id": f"track:{s['id']}", "kind": "track", "area": "music",
                                  "title": f"Make {scene} and drop the track here" if vs else f"Drop the track for {scene} here — the song is already written",
                                  "go": f"music/needed/{s['id']}", "from": (vs[-1].get("by") if vs else None),
                                  "effort": "a sitting" if vs else "a minute", "created": created, "unblocks": False, "sig": s["id"],
                                  "wants": {"kind": "audio", "count": 1, "ext": list(music.AUDIO_EXT)},
                                  "goes_to": f"music:{s['id']}",
                                  "wants_line": f"wants: one audio file → Music · {scene}"})
                elif s["state"] in ("delivered", "in game") and s.get("delivered") and s.get("vocal") in (True, "vocal") \
                        and not s.get("lyric") and (s.get("delivered") or {}).get("by") == who:
                    cards.append({"id": f"words:{s['id']}", "kind": "words", "area": "music",
                                  "title": f"Confirm the words of {scene} as you sang them",
                                  "go": f"music/needed/{s['id']}", "from": "the Music board", "effort": "ten minutes",
                                  "created": (s.get("delivered") or {}).get("at"), "unblocks": False, "sig": s["id"],
                                  "step": "one more step: the track is in — the words as sung are still to confirm"})
            # 3 · profiles with open spots
            for sh in music.sheets(adp):
                if sh["open"]:
                    folded_attach.add(f"{mp['styles']}/{sh['id']}")
                    cards.append({"id": f"profile:{sh['id']}", "kind": "profile", "area": "music",
                                  "title": f"Fill {sh['open']} open spot{'s' if sh['open'] != 1 else ''} in {sh['name']}'s music profile",
                                  "go": f"music/singers/{sh['id']}", "from": None, "effort": "ten minutes",
                                  "created": None, "unblocks": False, "sig": f"{sh['id']}:{sh['open']}", "count": sh["open"]})
                else:
                    folded_attach.add(f"{mp['styles']}/{sh['id']}")
        except Exception as e:  # noqa: BLE001
            log.warning("tasks: music cards for %s: %s", gid, e)

    # 4 · letters with open questions — one card per letter
    try:
        letters = mail.all_letters(root)
        open_by = mail.open_questions_by_letter(letters)
        mine = mail.folder_for(who)
        for l in letters:
            n = open_by.get(l.id, 0)
            if not n or l.folder not in (mine, "archive") or (l.folder == "archive" and mail.group_of(l.to) != mail.group_of(who)):
                continue
            if l.id in folded_letters:
                continue
            if any(Path(a).with_suffix("").as_posix() in folded_attach for a in l.attachments):
                continue
            cards.append({"id": f"letter:{l.id}", "kind": "letter", "area": "messages",
                          "title": f"Answer {n} question{'s' if n != 1 else ''} in “{l.subject}”",
                          "go": f"messages/inbox/{l.id}", "from": l.sender, "effort": _effort_for_questions(n),
                          "created": l.date, "unblocks": False, "sig": f"{l.id}:{n}", "count": n})
    except Exception as e:  # noqa: BLE001
        log.warning("tasks: letters for %s: %s", gid, e)

    # 5 · pictures waiting for review — one card with the count
    if ui_state is not None:
        try:
            from . import production
            n = len(production.review(cfg, gid, ui_state, limit=500)["waiting"])
            if n:
                cards.append({"id": "review", "kind": "review", "area": "art", "count": n,
                              "title": f"Review {n} picture{'s' if n != 1 else ''} waiting in Review & approve",
                              "go": "art/review", "from": "the art worker", "effort": "a minute" if n <= 3 else "ten minutes" if n <= 20 else "a sitting",
                              "created": None, "unblocks": False, "sig": str(n)})
        except Exception as e:  # noqa: BLE001
            log.warning("tasks: review count for %s: %s", gid, e)

    # 6 · builds waiting on the person (the adapter's optional builds() hook)
    if adp is not None and callable(getattr(adp, "builds", None)):
        try:
            for b in adp.builds() or []:
                if b.get("mark") == "!":
                    cards.append({"id": f"build:{b['n']}", "kind": "build", "area": "status",
                                  "title": f"BUILD {b['n']} waits on you — {b.get('waiting_for') or b.get('title')}",
                                  "go": "status/builds", "from": "the build queue", "effort": "ten minutes",
                                  "created": None, "unblocks": True, "sig": f"{b['n']}:{b.get('waiting_for') or ''}"})
        except Exception as e:  # noqa: BLE001
            log.warning("tasks: builds for %s: %s", gid, e)

    # 7 · open notes addressed to them
    try:
        g = mail.group_of(who)
        for t in notes.threads(root, open_only=True):
            to = t.get("to")
            if (to and mail.group_of(to) == g) or (not to and person and t.get("tag") == "question" and settings.is_assistant(t.get("who"))):
                cards.append({"id": f"note:{t['id']}", "kind": "note", "area": "notes",
                              "title": f"Answer the note on {t.get('label') or t['obj']}: “{t['text'][:90]}”",
                              "go": f"notes/open/{t['id']}", "from": t.get("who"), "effort": "a minute",
                              "created": t.get("time"), "unblocks": False, "sig": t["id"]})
    except Exception as e:  # noqa: BLE001
        log.warning("tasks: notes for %s: %s", gid, e)

    tk = _ticked(root)
    out = []
    for c in cards:
        t = tk.get(c["id"])
        if t and t.get("sig") == c.get("sig") and not include_ticked:
            continue
        age = _age_days(c.get("created"), now)
        c["age_days"] = round(age, 1)
        c["overdue"] = age > OVERDUE_DAYS
        c.setdefault("checkable", True)
        c.setdefault("wants", None)
        out.append(c)
    out.sort(key=lambda c: (0 if c["unblocks"] else 1 if c["overdue"] else 2, EFFORT_RANK.get(c["effort"], 1),
                            -(c["age_days"] or 0), c["title"].lower()))
    return out


def board(cfg: dict, gid: str, who: str | None, ui_state=None) -> dict:
    """For you: the top ~7 as Next, the rest grouped by area (folded on the page)."""
    cards = gather(cfg, gid, who, ui_state)
    rest: dict[str, list] = {}
    for c in cards[NEXT_N:]:
        rest.setdefault(c["area"], []).append(c)
    return {"count": len(cards), "overdue": sum(1 for c in cards if c["overdue"]), "next": cards[:NEXT_N],
            "groups": [{"area": k, "cards": v} for k, v in rest.items()], "who": who}


# ---------------------------------------------------------------- done and dismissed
def tick(cfg: dict, gid: str, card_id: str, who: str, reason: str = "", dismiss: bool = False, ui_state=None) -> dict:
    """Done (the checkbox) or dismissed with a reason. A work order is closed in its own file; any other card is kept
    out of the list until what it's about changes."""
    if not who:
        raise TaskRefused("set who you are first — a task is ticked by someone")
    if dismiss and not str(reason).strip():
        raise TaskRefused("dismissing a task needs a reason — one line is enough")
    root = games.game_root(cfg, gid)
    card = next((c for c in gather(cfg, gid, who, ui_state, include_ticked=True) if c["id"] == card_id), None)
    if card is None:
        raise TaskRefused("that task isn't open any more")
    verb = "dismissed" if dismiss else "done"
    if card["kind"] == "order":
        orders.close(root, card["order"], who, note=reason, status="dropped" if dismiss else "done")
    else:
        tk = _ticked(root)
        tk[card_id] = {"sig": card.get("sig"), "by": who, "at": settings.now().isoformat(timespec="seconds"),
                       "how": verb, "reason": reason.strip() or None, "title": card["title"]}
        _save_ticked(root, tk)
        journal.append(root, who, "task", card_id, note=f"{verb}: {card['title']}" + (f" — {reason.strip()}" if reason.strip() else ""))
    return {"ok": True, "message": "Dismissed — it's in Done with your reason." if dismiss else "Done.", "id": card_id}


def done(root: Path, who: str | None, limit: int = 150) -> list[dict]:
    """What was done and when, newest first — ticked tasks, closed orders, delivered tracks, answered letters (from the
    journal, so nothing vanishes without a trace)."""
    out = []
    for e in reversed(journal.read(root, kinds=("task", "order", "deliver", "letter", "approve"))):
        n = str(e.get("note") or "")
        if e["kind"] == "order" and not n.startswith(("done:", "dropped:")):
            continue
        if e["kind"] == "letter" and "answer" not in n.lower():
            continue
        if who and e.get("who") != who and e["kind"] != "order":
            continue
        out.append({"time": e.get("time"), "who": e.get("who"), "kind": e["kind"], "obj": e.get("obj"), "note": n})
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- files dropped on a card
def incoming_dir(root: Path) -> Path:
    return Path(root) / "_incoming"


def safe_name(name: str) -> str:
    from . import names
    n = Path(str(name).replace("\\", "/")).name
    n = re.sub(r"[^\w.\- ()]+", "_", n).strip(" .") or "file"
    return names.portable(n)


def check_kind(card: dict, filename: str) -> None:
    w = card.get("wants")
    if not w:
        raise TaskRefused("this task doesn't take a file")
    ext = Path(filename).suffix.lower()
    if w["kind"] != "any" and ext not in KINDS_EXT.get(w["kind"], ()):
        word = {"audio": "audio", "image": "an image", "sheet": "a sprite sheet (png, jpg, webp)", "text": "a document"}.get(w["kind"], w["kind"])
        raise TaskRefused(f"this one wants {word} — that's a {ext or 'file with no extension'}")


def find_card(cfg: dict, gid: str, card_id: str, who: str, ui_state=None) -> dict:
    card = next((c for c in gather(cfg, gid, who, ui_state, include_ticked=True) if c["id"] == card_id), None)
    if card is None:
        raise TaskRefused("that task isn't open any more")
    return card


def _dest_folder(root: Path, goes_to: str, order_id: str) -> Path:
    if not goes_to or goes_to == "attach":
        return orders.folder(root) / "attachments" / order_id
    p = (Path(root) / goes_to.replace("\\", "/").strip("/")).resolve()
    r = Path(root).resolve()
    if p != r and r not in p.parents:
        raise TaskRefused("the order names a folder outside the game — nothing written")
    for bad in ("journal", "mail", "work_orders/for_", ".git"):
        if p.relative_to(r).as_posix().startswith(bad):
            raise TaskRefused(f"files don't go into {bad} — nothing written")
    return p


def _unique(p: Path) -> Path:
    if not p.exists():
        return p
    i = 2
    while True:
        q = p.with_name(f"{p.stem}_{i}{p.suffix}")
        if not q.exists():
            return q
        i += 1


def _clear(p: Path) -> None:
    try:
        p.unlink()
    except OSError as e:          # a drive that forbids deleting keeps it; the next upload's sweep tries again
        log.info("tasks: kept %s in _incoming (%s)", p.name, e)


def accept(cfg: dict, gid: str, card_id: str, staged: Path, filename: str, who: str, ui_state=None) -> dict:
    """A finished upload in _incoming → through the area's own delivery. Returns what the card should show."""
    if not who or settings.is_assistant(who):
        _clear(staged)
        raise TaskRefused("uploading to a task is a person's act — a session asks for a file with a work order instead")
    card = find_card(cfg, gid, card_id, who, ui_state)
    try:
        check_kind(card, filename)
    except TaskRefused:
        _clear(staged)
        raise
    root = games.game_root(cfg, gid)
    g = card.get("goes_to") or "attach"
    size = staged.stat().st_size
    shown = {"name": filename, "bytes": size, "kind": card["wants"]["kind"]}
    if g.startswith("music:"):
        from . import music
        adp = games.adapter(cfg, gid)
        try:
            r = music.deliver(adp, g[6:], who, data=staged.read_bytes(), filename=filename)
        except music.MusicRefused as e:
            _clear(staged)
            raise TaskRefused(str(e))
        _clear(staged)
        shown.update(play=f"/suite/audio?id={gid}&slot={g[6:]}")
        if card["kind"] == "order":
            orders.close(root, card["order"], who, note=f"{filename} delivered to {g[6:]}")
        slot = music.find(adp, g[6:])
        step = None
        if slot.get("vocal") in (True, "vocal") and not slot.get("lyric"):
            step = "one more step: confirm the words as you sang them (Music → Needed, on its row)"
        return {"ok": True, "message": r["message"], "done": True, "step": step, "file": shown}
    if g.startswith("sprite:"):
        from . import sprites
        ch, _, var = g[7:].partition("/")
        try:
            p = sprites.save_upload(cfg, gid, ch, var or None, filename, staged.read_bytes())
            v = sprites.open_sheet(cfg, gid, ch, var or None, p, who=who)
        except sprites.IntakeRefused as e:
            _clear(staged)
            raise TaskRefused(str(e))
        _clear(staged)
        sprites._sign(cfg, gid, who, "art", f"sprite intake · {sprites.who_dir(ch, var or None)} · {p.name}",
                      note=f"took in a sheet from a task ({v['found']} figure(s) found)")
        _record(root, card, who, filename, size, str(p))
        return {"ok": True, "message": f"Kept {p.name} — {v['found']} figure(s) found.", "done": False,
                "step": "one more step: click each figure's facing in Characters → Sprite intake", "go": "characters/intake",
                "file": {**shown, "thumb": True}}
    # a folder in the game (or kept with the order)
    dest_dir = _dest_folder(root, g, card.get("order") or card_id.replace(":", "_"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = _unique(dest_dir / safe_name(filename))
    try:
        os.replace(staged, dest)
    except OSError:
        shutil.copyfile(staged, dest)
        _clear(staged)
    rel = dest.resolve().relative_to(Path(root).resolve()).as_posix()
    journal.append(root, who, "task", card_id, after=rel, note=f"file in: {filename} ({size:,} bytes) → {rel}")
    n_have = _record(root, card, who, filename, size, rel)
    need = int(card["wants"].get("count") or 1)
    finished = n_have >= need
    if finished and card["kind"] == "order":
        orders.close(root, card["order"], who, note=f"{n_have} file(s) in → {_goes_to_label(g)}")
    if card["wants"]["kind"] in ("image", "sheet"):
        shown["thumb_rel"] = rel
    return {"ok": True, "done": finished, "progress": f"{n_have} of {need}" if need > 1 else None,
            "message": f"{filename} is in → {rel}." + ("" if finished else f" {n_have} of {need} so far."), "file": shown}


def _record(root: Path, card: dict, who: str, filename: str, size: int, where: str) -> int:
    """What came in, kept on the work order itself; returns how many it now has."""
    if card["kind"] != "order":
        return 1
    for f, o in orders._all(root):
        if o.get("id") == card["order"]:
            o.setdefault("received", []).append({"name": filename, "bytes": size, "at": settings.now().isoformat(timespec="seconds"),
                                                 "by": who, "where": where})
            orders._write(f, o)
            return len(o["received"])
    return 1


def sweep_incoming(root: Path, max_age_s: float = 3600) -> None:
    """Half-finished uploads (.part) older than an hour are cleared; they were never handed on."""
    d = incoming_dir(root)
    if not d.is_dir():
        return
    import time
    for p in d.glob("*.part"):
        try:
            if time.time() - p.stat().st_mtime > max_age_s:
                p.unlink()
        except OSError:
            pass
