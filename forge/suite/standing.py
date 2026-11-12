"""Where the game stands (BUILD 17, suite spec §8 B9) — the top of Home.

n of m for what the game is made of (its own completeness checklist, lines approved, songs, the questions still open),
and **the next most useful thing for each of us**: for the person at this computer (their Tasks, best first) and for
the assistants (their work orders, then the idea box, playtest notes not taken in, data that contradicts a ruling,
questions the rulings book already answers, the game's own biggest gap). Read-only; worked out each time from the same
data the areas use. A part that can't be worked out is left out — it never guesses.
"""
from __future__ import annotations
import time

from ..log import get
from . import games, ideas, mail, orders, playtest, rulings, settings

log = get("suite")
PRI = {"now": 0, "soon": 1, "someday": 2}


def _safe(name, fn, default=None):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — one part that can't be worked out never takes Home down
        log.warning("standing: %s: %s", name, e)
        return default


def data(cfg: dict, gid: str, ui_state=None) -> dict:
    t0 = time.time()
    who = settings.identity() or ""
    root = games.game_root(cfg, gid) if gid else None
    if not root or not root.is_dir():
        return {"available": False, "why": "the game's folder isn't reachable from this computer"}
    adp = _safe("adapter", lambda: games.adapter(cfg, gid)) if games.has_adapter(cfg, gid) else None
    tiles: list[dict] = []

    def tile(label, have, of, go, detail=""):
        if of is None:
            return
        st = "met" if of and have >= of else "partly" if have else "not"
        tiles.append({"label": label, "have": have, "of": of, "state": st, "go": go, "detail": detail,
                      "pct": int(round(100 * have / of)) if of else 0})

    if adp is not None:
        def _lines():
            from . import readthrough
            tw = readthrough.towns(adp)
            tile("Lines approved", sum(t["approved"] for t in tw), sum(t["lines"] for t in tw), "story/read",
                 f"{sum(t['flagged'] for t in tw)} flagged as generic")
        _safe("lines", _lines)

        def _music():
            from . import music
            c = music.counts(music.slots(adp))
            tile("Songs & score in hand", c["delivered"] + c["in game"], c["total"] - c["inherits"], "music/needed",
                 f"{c['needed']} still needed")
        _safe("music", _music)
        comp = _safe("completeness", lambda: __import__("forge.suite.status", fromlist=["completeness"]).completeness(cfg, gid), {})
        for t in (comp or {}).get("tiles", [])[:8]:
            v = str(t.get("value") or "")
            if " of " in v:
                a, _, b = v.partition(" of ")
                try:
                    tile(t["label"], int(a.replace(",", "")), int(b.replace(",", "")), t.get("go") or "status/game", t.get("detail", ""))
                except ValueError:
                    pass
    letters = _safe("mail", lambda: mail.all_letters(root), []) or []
    open_q = mail.open_questions_by_letter(letters) if letters else {}
    asked = sum(len(l.questions) for l in letters)
    if asked:
        tile("Questions answered", asked - sum(open_q.values()), asked, "messages/inbox", f"{sum(open_q.values())} still open")

    # ---- the next most useful thing, for each of us
    nxt_me: list[dict] = []
    if who:
        b = _safe("tasks", lambda: __import__("forge.suite.tasks", fromlist=["board"]).board(cfg, gid, who, ui_state), {}) or {}
        for c in (b.get("next") or [])[:3]:
            nxt_me.append({"title": c.get("title"), "why": c.get("effort") or "", "go": c.get("go") or "tasks/for-you"})
    nxt_ai: list[dict] = []
    ords = _safe("orders", lambda: orders.listing(root, "claude", "open"), []) or []
    ords.sort(key=lambda o: (PRI.get(o.get("priority"), 3), o.get("created", "")))
    for o in ords[:2]:
        nxt_ai.append({"title": o["title"], "why": f"work order from {o['by']} ({o['priority']})", "go": "tasks/for-claude"})
    pt = _safe("playtest", lambda: playtest.inbox(root, adp), {}) or {}
    if pt.get("new"):
        nxt_ai.append({"title": f"Take in {pt['new']} playtest note(s)", "why": "notes from playing, not routed yet", "go": "notes/playtest"})
    ic = _safe("ideas", lambda: ideas.counts(root), {}) or {}
    if ic.get("open"):
        nxt_ai.append({"title": f"Sort {ic['open']} idea(s) in the idea box", "why": "say where each went", "go": "notes/ideas"})
    cf = _safe("conflicts", lambda: rulings.conflicts(root, adp), []) or []
    if cf:
        nxt_ai.append({"title": f"{len(cf)} data field(s) contradict a ruling", "why": cf[0]["message"], "go": "notes/rulings"})
    if letters and open_q:
        def _ruled():
            by_id = {l.id: l for l in letters}
            n = 0
            for lid, k in open_q.items():
                if k:
                    l = by_id[lid]
                    done = mail.answered_ids(letters)
                    n += len(rulings.check_questions(root, [q for q in l.questions if f"{lid}#{q.get('id')}" not in done], adp))
            return n
        n = _safe("ruled", _ruled, 0) or 0
        if n:
            nxt_ai.append({"title": f"{n} open question(s) the rulings book already answers", "why": "close them with the ruling instead of waiting",
                           "go": "notes/rulings"})
    gaps = sorted((t for t in tiles if t["state"] != "met" and t["of"]), key=lambda t: t["pct"])
    if gaps and len(nxt_ai) < 4:
        g = gaps[0]
        nxt_ai.append({"title": f"{g['label']}: {g['have']} of {g['of']}", "why": "the game's biggest gap right now", "go": g["go"]})
    rs = _safe("rulings", lambda: rulings.summary(root, adp), {}) or {}
    return {"available": True, "tiles": tiles, "next_me": nxt_me, "next_ai": nxt_ai[:5], "who": who,
            "memory": {"rulings": rs.get("count"), "conflicts": len(cf), "ideas_open": ic.get("open", 0),
                       "playtest_new": pt.get("new", 0)},
            "took_ms": int((time.time() - t0) * 1000)}
