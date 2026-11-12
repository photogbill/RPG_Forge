"""Status — met or not met, at a glance (BUILD 26 B3; William, 2026-11-11: "a status page that shows tasks that have been
met or not met, so I can glance at that screen and easily tell what needs to be done").

Read-only. Every tile is worked out each time the page opens from the same data the areas use — no status is typed in
by hand, so it can't drift. A tile that can't be worked out is grey ("none"); it never guesses green. Every tile has a
**go**: the address where the thing gets done.

States: met (green) · partly (amber, with how far) · not (red, with what's missing) · none (grey, can't tell) ·
planned (grey, the build that brings it).
"""
from __future__ import annotations
import re
from datetime import datetime

from ..log import get
from . import areas, games, mail, notes, settings, worker

log = get("suite")


def _tile(tid, area, label, state, value="", detail="", go=None, big=False):
    return {"id": tid, "area": area, "label": label, "state": state, "value": value, "detail": detail, "go": go, "big": big}


def _frac(a: int, b: int) -> str:
    return "met" if b and a >= b else "partly" if a else "not"


def glance(cfg: dict, gid: str, ui_state=None) -> dict:
    who = settings.identity() or ""
    root = games.game_root(cfg, gid) if gid else None
    has_root = bool(root and root.is_dir())
    adp = None
    if has_root and games.has_adapter(cfg, gid):
        try:
            adp = games.adapter(cfg, gid)
        except Exception as e:  # noqa: BLE001
            log.warning("status: adapter %s: %s", gid, e)
    rows: dict[str, list] = {a["id"]: [] for a in areas.AREAS}

    def guard(area, tid, label, go, fn):
        try:
            t = fn()
            if t:
                rows[area].append(t)
        except Exception as e:  # noqa: BLE001 — a tile that can't be worked out is grey
            log.warning("status: tile %s: %s", tid, e)
            rows[area].append(_tile(tid, area, label, "none", "?", f"couldn't work it out ({type(e).__name__})", go, True))

    # ---- the big tiles, from what each area knows
    def t_tasks():
        from . import tasks
        cards = tasks.gather(cfg, gid, who, ui_state)
        if not who:
            return _tile("tasks", "tasks", "Tasks", "none", "?", "say who you are first (bottom left)", "tasks/for-you", True)
        over = [c for c in cards if c["overdue"]]
        oldest = max(cards, key=lambda c: c.get("age_days") or 0) if cards else None
        st = "met" if not cards else "not" if over else "partly"
        det = "nothing waiting on you" if not cards else (
            f"{len(over)} overdue · oldest: {oldest['title']}" if over else f"oldest: {oldest['title']}")
        return _tile("tasks", "tasks", "Tasks open", st, str(len(cards)), det, "tasks/for-you", True)
    guard("tasks", "tasks", "Tasks", "tasks/for-you", t_tasks)

    def t_msg():
        if not has_root or not who:
            return _tile("questions", "messages", "Questions open", "none", "?", "the game's folder isn't reachable" if not has_root
                         else "say who you are first (bottom left)", "messages/inbox", True)
        letters = mail.all_letters(root)
        ob = mail.open_questions_by_letter(letters)
        mine = mail.folder_for(who) if who else None
        n = sum(v for k, v in ob.items() if any(l.id == k and l.folder in (mine, "archive") for l in letters))
        nl = sum(1 for k, v in ob.items() if v and any(l.id == k and l.folder in (mine, "archive") for l in letters))
        return _tile("questions", "messages", "Questions open", "met" if not n else "not", str(n),
                     "every question answered" if not n else f"in {nl} letter(s)", "messages/inbox", True)
    guard("messages", "questions", "Questions open", "messages/inbox", t_msg)

    def t_music():
        if adp is None:
            return _tile("music", "music", "Music", "none", "?", "no adapter for this game", "music/needed", True)
        from . import music
        try:
            ss = music.slots(adp)
        except Exception as e:  # noqa: BLE001
            return _tile("music", "music", "Music", "not", "—", f"the game's music list couldn't be read: {e}", "music/needed", True)
        if not ss:
            return _tile("music", "music", "Music", "not", "0", "no music list — the adapter lists no slots", "music/needed", True)
        c = music.counts(ss)
        have = c["delivered"] + c["in game"]
        tot = c["total"] - c["inherits"]
        det = " · ".join(f"{c[k]} {k}" for k in music.STATES) + f" · {c['own']} are {music._o(adp)}'s"
        return _tile("music", "music", "Music", _frac(have, tot), f"{have} of {tot}", det, "music/needed", True)
    guard("music", "music", "Music", "music/needed", t_music)

    def t_story():
        if adp is None:
            return None
        from . import readthrough
        tw = readthrough.towns(adp)
        lines = sum(t["lines"] for t in tw)
        ok = sum(t["approved"] for t in tw)
        places = [t for t in tw if t["lines"]]
        read = sum(1 for t in places if t["approved"] == t["lines"])
        rows["story"].append(_tile("lines", "story", "Lines approved in places", _frac(ok, lines), f"{ok} of {lines}",
                                   f"{sum(t['flagged'] for t in tw)} flagged", "story/read", True))
        return _tile("places", "story", "Places read through", _frac(read, len(places)), f"{read} of {len(places)}",
                     "a place is read through when every line in it is approved", "story/read", True)
    guard("story", "places", "Places read through", "story/read", t_story)

    def t_art():
        if ui_state is None:
            return None
        from . import production
        n = len(production.review(cfg, gid, ui_state, limit=500)["waiting"])
        rows["art"].append(_tile("review", "art", "Waiting for review", "met" if not n else "partly", str(n),
                                 "nothing waiting" if not n else "pictures made for the game, not yet decided", "art/review", True))
        w = worker.state(cfg)
        wst = {"rendering": "met", "idle": "met", "stopped": "none", "stopped-mid-job": "not", "unknown": "none"}[w["state"]]
        rows["art"].append(_tile("worker", "art", "The art worker", wst, w["state"].replace("-", " "), w["words"], "home/today", True))
        from ..night4 import guard as dg
        limit = float(cfg.get("disk_guard_gb", 40))
        try:
            free = round(dg.free_gb(cfg), 1)
        except OSError:
            return _tile("disk", "art", "Disk guard", "none", "?", "couldn't read the free space", "home/today", True)
        return _tile("disk", "art", "Disk guard", "met" if free >= limit else "not", f"{free:,.0f} GB",
                     f"the guard pauses the queue under {limit:,.0f} GB", "home/today", True)
    guard("art", "art", "Art", "art/review", t_art)

    def t_notes():
        if not has_root:
            return None
        n = len(notes.threads(root, open_only=True))
        return _tile("notes", "notes", "Open notes", "met" if not n else "partly", str(n),
                     "no open notes" if not n else "pinned to lines, places, slots …", "notes/open", True)
    guard("notes", "notes", "Open notes", "notes/open", t_notes)

    # ---- each tab's needs line, as a small tile
    nd = areas.needs(cfg, gid)
    for a in areas.AREAS:
        for t in a["tabs"]:
            addr = f"{a['id']}/{t['id']}"
            n = nd[addr]
            if n["planned"]:
                st, val = "planned", f"BUILD {n['planned']:02d}"
            else:
                st = {True: "met", False: "not", None: "none"}[n["met"]]
                val = {"met": "✓", "not": "✗", "none": "—"}[st]
            rows[a["id"]].append(_tile(f"needs:{addr}", a["id"], t["name"], st, val, n["line"], addr))

    tiles = [t for a in areas.AREAS for t in rows[a["id"]]]
    tally = {"met": 0, "partly": 0, "not": 0}
    for t in tiles:
        if t["state"] in tally:
            tally[t["state"]] += 1
    return {"rows": [{"area": a["id"], "name": a["name"], "icon": a["icon"], "color": a["color"], "tiles": rows[a["id"]]}
                     for a in areas.AREAS if rows[a["id"]]],
            "tally": tally, "read_at": datetime.now().strftime("%H:%M:%S")}


def builds(cfg: dict, gid: str) -> dict:
    """The game's build queue as tiles (the adapter's optional builds() hook). A game without one has no Builds tab."""
    adp = games.adapter(cfg, gid) if gid and games.has_adapter(cfg, gid) else None
    fn = getattr(adp, "builds", None) if adp else None
    if not callable(fn):
        return {"available": False, "tiles": []}
    tiles = []
    for b in fn() or []:
        st = {"x": "met", "~": "partly", "!": "not", " ": "todo"}[b["mark"]]
        word = {"met": f"done {b.get('done_on') or ''}".strip(), "partly": "started", "not": "waiting on you", "todo": "to do"}[st]
        det = b.get("progress") if st in ("partly", "not") and b.get("progress") else b.get("waiting_for") or b.get("needs") or ""
        if st == "not" and b.get("waiting_for"):
            det = f"waiting for: {b['waiting_for']}" + (f" — {b['progress']}" if b.get("progress") else "")
        tiles.append({**_tile(f"build:{b['n']}", "status", f"{b['n']} · {b['title']}", "none" if st == "todo" else st, word, det,
                              "status/builds"), "where": b.get("where"), "n": b["n"], "todo": st == "todo"})
    tally = {"met": sum(t["state"] == "met" for t in tiles), "partly": sum(t["state"] == "partly" for t in tiles),
             "not": sum(t["state"] == "not" for t in tiles)}
    return {"available": True, "tiles": tiles, "tally": tally, "read_at": datetime.now().strftime("%H:%M:%S")}


_FRAC = re.compile(r"(\d[\d,]*)\s+of\s+(\d[\d,]*)")


def completeness(cfg: dict, gid: str) -> dict:
    """The game's own completeness checklist (the adapter's optional completeness() hook): [{item, met, have, of, detail, go}]."""
    adp = games.adapter(cfg, gid) if gid and games.has_adapter(cfg, gid) else None
    fn = getattr(adp, "completeness", None) if adp else None
    if not callable(fn):
        return {"available": False, "tiles": []}
    tiles = []
    for i, it in enumerate(fn() or []):
        have, of = it.get("have"), it.get("of")
        met = it.get("met")
        if met is None and have is not None and of:
            st = _frac(int(have), int(of))
        else:
            st = {True: "met", False: "not", None: "none"}[met if met in (True, False) else None]
        val = f"{have} of {of}" if have is not None and of else ("✓" if st == "met" else "✗" if st == "not" else "—")
        tiles.append(_tile(f"game:{i}", "status", it.get("item") or "?", st, val, it.get("detail") or "", it.get("go") or "status/game"))
    tally = {k: sum(t["state"] == k for t in tiles) for k in ("met", "partly", "not")}
    return {"available": True, "tiles": tiles, "tally": tally, "read_at": datetime.now().strftime("%H:%M:%S")}


def parse_line(s: str) -> dict:
    """"Maps painted: 0 of 77" → {item: "Maps painted", have: 0, of: 77, detail: …} — for adapters whose report is lines."""
    item, _, rest = str(s).partition(":")
    m = _FRAC.search(rest)
    if not m:
        return {"item": item.strip(), "met": None, "detail": rest.strip()}
    a, b = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
    return {"item": item.strip(), "have": a, "of": b, "detail": rest.strip()}
