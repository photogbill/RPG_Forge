"""Every area its own tab (BUILD 26) — the sidebar of areas, the way ATK has them.

The suite used to have two halves (Art | Story) with a side menu each. Now it is **one sidebar of areas** (Home · Status ·
Messages · Tasks · Story · Music · Art · Characters · Workshop · Notes · Settings), each with a strip of **tabs**. This file
is the one list of them: every area, every tab, the address it lives at (`#music/needed`), the screen that paints it,
and **what it needs** to work — so a page whose data isn't there yet says what's missing and which build or step brings
it, instead of an error or a blank. A tab whose screen isn't built yet is listed too (`planned`), with its build number.

`needs(cfg, gid)` works out, for the chosen game, whether each need is met. Nothing here names a game: the words are
generic and the game picker decides whose data fills them. Paths in addresses use "/" on every computer.
"""
from __future__ import annotations
import json, time
from pathlib import Path

from .. import config as cfgmod
from ..log import get
from . import games, journal, mail, notes, orders, settings, worker

log = get("suite")

# A need: id → (what it is, in plain words; what brings it when it's missing)
NEEDS: dict[str, tuple[str, str]] = {
    "game": ("the game's folder", "pick a game whose folder this computer can reach (the dot by the picker is red when it can't)"),
    "adapter": ("the game's adapter (games/<id>/workbench_adapter.py)", "copy games/_example/workbench_adapter.py for the game"),
    "journal": ("the game's journal", "it starts with the first signed action in the suite"),
    "worker": ("the art worker on this computer", "it runs on the PC with the NVIDIA card (install.bat there); this computer can still review what's in the folders"),
    "out": ("the forge's pictures folder (out/)", "it appears with the first finished picture"),
    "mail": ("the game's mail folder", "it appears with the first letter (Messages → write one)"),
    "work_orders": ("the game's work orders", "they appear with the first order (Tasks → For Claude → add one)"),
    "music_slots": ("the game's list of music slots", "the game's adapter lists them (music_slots()); a game build writes the list"),
    "music_dir": ("the game's music folder", "it appears with the first brief or profile (Music)"),
    "score_inbox": ("the game's score inbox folder", "make the folder the adapter names for finished tracks"),
    "characters": ("the character registry (games/<id>/characters)", "Characters → make the first character"),
    "notes": ("the game's notes", "they appear with the first note (press N on a line in the read-through)"),
    "builds_hook": ("a build queue the game's adapter can read (builds())", "add a builds() hook to the game's adapter"),
    "completeness_hook": ("the game's own completeness checklist (completeness())", "add a completeness() hook to the game's adapter"),
    "places": ("the game's places and lines", "the game's adapter lists them (places(), lines())"),
    "settings": ("this computer's settings (local/suite.json)", "they are written the first time you say who you are"),
    "playtest": ("the game's playtest notes", "they appear with the first note taken while playing (the game's note key)"),
}


# needs that are simply empty until first use (no letters yet, no notes yet): shown grey ("nothing yet"), never red
SOFT = {"journal", "mail", "work_orders", "music_dir", "score_inbox", "notes", "settings", "playtest"}


def _t(tid, name, screen, needs=(), planned=None, holds="", **kw):
    d = {"id": tid, "name": name, "screen": screen, "needs": list(needs), "planned": planned, "holds": holds}
    d.update(kw)
    return d


AREAS: list[dict] = [
    {"id": "home", "icon": "⌂", "name": "Home", "color": "#f0b040", "tabs": [
        _t("today", "Today", "home", ("journal", "worker"))]},
    {"id": "status", "icon": "▣", "name": "Status", "color": "#46c776", "tabs": [
        _t("glance", "At a glance", "status"),
        _t("builds", "Builds", "status", ("builds_hook",)),
        _t("game", "The game", "status", ("completeness_hook",))]},
    {"id": "messages", "icon": "✉", "name": "Messages", "color": "#7aa7ff", "tabs": [
        _t("inbox", "Inbox", "mail", ("game", "mail"), box="inbox"),
        _t("sent", "Sent", "mail", ("game", "mail"), box="sent"),
        _t("drafts", "Drafts", "mail", ("game", "mail"), box="drafts"),
        _t("archive", "Archive", "mail", ("game", "mail"), box="archive")]},
    {"id": "tasks", "icon": "☑", "name": "Tasks", "color": "#ff8a4c", "tabs": [
        _t("for-you", "For you", "tasks", ("game",)),
        _t("for-claude", "For Claude", "orders", ("game", "work_orders")),
        _t("done", "Done", "tasksdone", ("game", "journal"))]},
    {"id": "story", "icon": "📖", "name": "Story", "color": "#7aa7ff", "tabs": [
        _t("read", "Read-through", "read", ("adapter", "places")),
        _t("people", "People", "people", ("adapter", "places")),
        _t("quests", "Quests", "quests", ("adapter",)),
        _t("voices", "Voice sheets", "voices", ("adapter",)),
        _t("find", "Find & replace", "find", ("adapter", "places")),
        _t("overview", "Overview", "overview", ("adapter",))]},
    {"id": "music", "icon": "♪", "name": "Music", "color": "#c58cff", "tabs": [
        _t("needed", "Needed", "music", ("adapter", "music_slots"), mtab="board"),
        _t("singers", "Singers", "music", ("adapter", "music_dir"), mtab="profiles"),
        _t("inbox", "Score inbox", "music", ("adapter", "score_inbox"), mtab="inbox"),
        _t("briefs", "Briefs & songs", "music", ("adapter", "music_dir"), mtab="briefs")]},
    {"id": "art", "icon": "🎨", "name": "Art", "color": "#f0b040", "tabs": [
        _t("wanted", "Wanted", "wanted", ("game",)),
        _t("make", "Make a picture", "make", ("worker",)),
        _t("review", "Review & approve", "review", ("out",)),
        _t("queue", "Queue & pictures", "queue", ("worker",)),
        _t("floorplans", "Floor plans", "floorplans", ("adapter",),
           holds="layouts made from each town's sheet: four candidates side by side, paint on the grid, approve into the game"),
        _t("provide", "User Needs To Provide Image", "provide", ("game",),
           holds="pictures the forge can't make well — each says why and what would help; drop the file on its card")]},
    {"id": "characters", "icon": "☺", "name": "Characters", "color": "#e98aa8", "tabs": [
        _t("characters", "Characters", "chars", ("characters",)),
        _t("intake", "Sprite intake", "intake", ("characters",))]},
    {"id": "workshop", "icon": "⚗", "name": "Workshop", "color": "#8fd0c0", "tabs": [
        _t("library", "Prompt library", "library"),
        _t("bakeoffs", "Bake-offs", "bakeoffs"),
        _t("models", "Models", "models"),
        _t("tools", "Outside tools", "tools")]},
    {"id": "notes", "icon": "✎", "name": "Notes", "color": "#e6c36a", "tabs": [
        _t("open", "Open notes", "notesopen", ("game", "notes")),
        _t("rulings", "Rulings", "rulings", ("game",),
           holds="every ruling the owner has made, in one book, searchable, each linked to where it applies"),
        _t("ideas", "Idea box", "ideas", ("game",),
           holds="ideas from anyone (press I anywhere), kept until someone turns one into a task, a note or a letter"),
        _t("playtest", "Playtest notes", "playtest", ("game", "playtest"),
           holds="notes taken while playing (the game's note key), taken in to where they can be worked on")]},
    {"id": "settings", "icon": "⚙", "name": "Settings", "color": "#9a98a6", "tabs": [
        _t("computer", "This computer", "settings", ("settings",),
           holds="where each game's folder is on this computer, who you are, the time zone, Godot"),
        _t("about", "About", "about")]},
]

# every screen that existed before BUILD 26 (a data-s in the old two menus) → its one new home
OLD_SCREENS: dict[str, str] = {
    "home": "home/today", "queue": "art/queue", "wanted": "art/wanted", "make": "art/make", "review": "art/review",
    "intake": "characters/intake", "chars": "characters/characters", "library": "workshop/library",
    "bakeoffs": "workshop/bakeoffs", "models": "workshop/models", "tools": "workshop/tools",
    "mail": "messages/inbox", "orders": "tasks/for-claude", "overview": "story/overview", "read": "story/read",
    "music": "music/needed",
}


def find(addr: str) -> tuple[dict, dict] | None:
    """'music/singers/wren' → (area, tab), or None."""
    parts = [p for p in str(addr or "").strip("#/").split("/") if p]
    if not parts:
        return None
    a = next((x for x in AREAS if x["id"] == parts[0]), None)
    if a is None:
        return None
    t = next((x for x in a["tabs"] if x["id"] == (parts[1] if len(parts) > 1 else a["tabs"][0]["id"])), None)
    return (a, t) if t else None


def addresses() -> list[str]:
    return [f"{a['id']}/{t['id']}" for a in AREAS for t in a["tabs"]]


# ---------------------------------------------------------------- what each tab needs, met or not
def _check(cfg: dict, gid: str, need: str, cache: dict) -> tuple[bool | None, str]:
    """(met, detail). met is None when it can't be worked out on this computer."""
    if need in cache:
        return cache[need]
    root = games.game_root(cfg, gid) if gid else None
    has_root = bool(root and root.is_dir())
    adp = None
    if has_root and games.has_adapter(cfg, gid):
        try:
            adp = games.adapter(cfg, gid)
        except Exception as e:  # noqa: BLE001
            log.warning("areas: adapter for %s didn't load: %s", gid, e)
    r: tuple[bool | None, str]
    try:
        if need == "game":
            r = (has_root, str(root) if has_root else "not reachable from this computer")
        elif need == "adapter":
            r = (adp is not None, "" if adp else "no workbench_adapter.py for this game")
        elif need == "journal":
            r = (has_root and journal.folder(root).is_dir(), "")
        elif need == "worker":
            from . import runwords
            r = ((cfgmod.path_of(cfg, "jobs").is_dir(), "the queue folder (jobs/)") if worker.here()
                 else (False, f"it runs on {runwords.worker_pc()}"))
        elif need == "out":
            r = (cfgmod.path_of(cfg, "out").is_dir(), "")
        elif need == "mail":
            r = (has_root and mail.mail_dir(root).is_dir(), "")
        elif need == "work_orders":
            r = (has_root and orders.folder(root).is_dir(), "")
        elif need == "music_slots":
            n = len(adp.music_slots()) if adp else 0
            r = (n > 0, f"{n} slot(s)" if n else "the adapter lists no music slots")
        elif need in ("music_dir", "score_inbox"):
            from . import music
            p = music.paths(adp)["styles" if need == "music_dir" else "inbox"] if adp else ""
            r = (bool(adp) and (root / p).is_dir(), p)
            if need == "music_dir" and adp and not r[0]:
                r = ((root / "music").is_dir(), "music/")
        elif need == "characters":
            r = ((games.games_dir(cfg) / gid / "characters").is_dir() if gid else False, "")
        elif need == "notes":
            r = (has_root and notes.path(root).is_file(), "")
        elif need == "builds_hook":
            r = (bool(adp) and callable(getattr(adp, "builds", None)), "")
        elif need == "completeness_hook":
            r = (bool(adp) and callable(getattr(adp, "completeness", None)), "")
        elif need == "places":
            n = len(adp.places()) if adp else 0
            r = (n > 0, f"{n} place(s)")
        elif need == "playtest":
            from . import playtest
            r = (has_root and (playtest.folder(root, adp) / "notes.jsonl").is_file(), playtest._dir_rel(adp) + "/notes.jsonl")
        elif need == "settings":
            r = (settings.PATH.is_file(), str(settings.PATH))
        else:
            r = (None, f"unknown need {need}")
    except Exception as e:  # noqa: BLE001 — a need that can't be worked out says so; it never breaks the page
        log.warning("areas: need %s for %s: %s", need, gid, e)
        r = (None, f"couldn't tell ({type(e).__name__})")
    cache[need] = r
    return r


def needs(cfg: dict, gid: str) -> dict:
    """address → {met: True|False|None, line, missing: [...], planned}. The quiet line under every tab strip."""
    cache: dict = {}
    out = {}
    for a in AREAS:
        for t in a["tabs"]:
            items, missing, empty, unknown = [], [], [], False
            for n in t["needs"]:
                met, detail = _check(cfg, gid, n, cache)
                what, brings = NEEDS.get(n, (n, ""))
                if n == "worker" and met is False and detail:
                    brings = f"{detail}; this computer can still review what's in the folders"
                items.append({"id": n, "what": what, "met": met, "detail": detail, "soft": n in SOFT})
                if met is False and n in SOFT:
                    empty.append({"id": n, "what": what, "brings": brings})
                elif met is False:
                    missing.append({"id": n, "what": what, "brings": brings})
                if met is None:
                    unknown = True
            if t.get("planned"):
                line = f"Not built yet — BUILD {t['planned']:02d} brings it: {t['holds']}."
                met = None
            elif not t["needs"]:
                line, met = "Needs nothing from the game — the forge's own folders.", True
            elif missing:
                line = "Missing: " + "; ".join(f"{m['what']} — {m['brings']}" for m in missing) + "."
                met = False
            elif empty:
                line = "Nothing yet: " + "; ".join(f"{m['what']} — {m['brings']}" for m in empty) + "."
                met = None
            else:
                line = "Needs " + ", ".join(i["what"] for i in items) + " — " + ("✓ all there." if not unknown else "can't tell on this computer.")
                met = None if unknown else True
            out[f"{a['id']}/{t['id']}"] = {"met": met, "line": line, "missing": missing, "empty": empty, "items": items,
                                            "planned": t.get("planned")}
    return out


def public() -> list[dict]:
    """The registry as the page reads it."""
    return [{**{k: v for k, v in a.items() if k != "tabs"},
             "tabs": [{k: v for k, v in t.items()} for t in a["tabs"]]} for a in AREAS]


# ---------------------------------------------------------------- the sidebar's count badges
_badge_cache: dict[str, tuple[float, dict]] = {}


def badges(cfg: dict, gid: str, ui_state=None, fresh: bool = False) -> dict:
    """{area: count} — unread letters, open tasks, open notes, needed music slots, pictures waiting for review — plus
    the worker's state. An area whose data is missing counts 0; nothing here raises."""
    hit = _badge_cache.get(gid)
    if hit and not fresh and time.time() - hit[0] < 10:
        return hit[1]
    t0 = time.time()
    out = {"messages": 0, "tasks": 0, "notes": 0, "music": 0, "art": 0, "overdue": 0, "worker": "unknown"}
    who = settings.identity() or ""
    root = games.game_root(cfg, gid) if gid else None
    has_root = bool(root and root.is_dir())

    def safe(key, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log.warning("badges: %s for %s: %s", key, gid, e)

    if has_root and who:
        safe("messages", lambda: out.__setitem__("messages", mail.unread_count(root, who)))
    if has_root:
        safe("notes", lambda: out.__setitem__("notes", len(notes.threads(root, open_only=True))))

        def _memory():                  # BUILD 17: ideas waiting to be sorted and playtest notes not taken in count too
            from . import ideas, playtest
            adp = games.adapter(cfg, gid) if games.has_adapter(cfg, gid) else None
            out["ideas"] = ideas.counts(root)["open"]
            out["playtest"] = playtest.inbox(root, adp)["new"]
            out["notes"] += out["ideas"] + out["playtest"]
        safe("memory", _memory)
    if has_root and games.has_adapter(cfg, gid):
        def _mu():
            from . import music
            ss = music.slots(games.adapter(cfg, gid))
            out["music"] = sum(1 for s in ss if s["state"] == "needed" and not s.get("own") and not s.get("via"))
        safe("music", _mu)

    def _tasks():
        from . import tasks
        cards = tasks.gather(cfg, gid, who, ui_state)
        out["tasks"] = len(cards)
        out["overdue"] = sum(1 for c in cards if c.get("overdue"))
        out["art"] = next((c.get("count", 0) for c in cards if c["kind"] == "review"), 0)
    if has_root:
        safe("tasks", _tasks)
    safe("worker", lambda: out.__setitem__("worker", worker.state(cfg)["state"]))
    from . import runwords
    out["worker_here"], out["worker_pc"] = worker.here(), runwords.worker_pc()
    out["took_ms"] = int((time.time() - t0) * 1000)
    _badge_cache[gid] = (time.time(), out)
    return out


def remember_place(gid: str, addr: str) -> None:
    """The last place you were, per game, on this computer (local/suite.json — never pushed)."""
    if not gid or not find(addr):
        return
    d = settings.load()
    lp = dict(d.get("last_place") or {})
    lp[gid] = str(addr).strip("#/")[:300]
    settings.update(last_place=lp)


def last_place(gid: str) -> str | None:
    return (settings.load().get("last_place") or {}).get(gid)
