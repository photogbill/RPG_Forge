"""Playtest notes in the same inbox (BUILD 17, suite spec §8 B7).

The game's note key writes one JSON line per note — category, the words, where the tester was (map, era, the dialogue,
the nearest person, the paintings on screen), a screenshot — into its playtest folder (the adapter's `playtest_dir()`,
default `playtest/`): `notes.jsonl`, `shots/`, and for Art notes `art_feedback.json`.

**Taking them in** (Notes → Playtest notes → Take in, or `python -m forge playtest in`) routes every note not seen yet:

* **Art** → the forge's redo drafts (Art → Review → Called out), through the same take-in the finishing screens use;
  a note on a stand-in bumps that picture's priority instead.
* **Writing** → a note pinned where the words are: the conversation's first line when the note names one, else the
  place (`place:<id>`) the map belongs to — so it shows in the read-through, for whoever is addressed.
* **Music** → a note pinned to the place, tagged for the music.
* **Bug, Balance, Other** → a work order for whoever is addressed.

…and each category arrives as **a letter in the Mail** — one thread per category, the notes listed with their
screenshots attached — so they land in the same inbox as everything else. A note is never taken in twice
(`<game_root>/playtest_inbox/routed.jsonl` records where each went). Nothing in the game's playtest folder is changed.
"""
from __future__ import annotations
import hashlib, json, os
from datetime import datetime
from pathlib import Path

from ..log import get
from . import journal, settings

log = get("suite")
ROUTES = {"Art": "art", "Writing": "writing", "Music": "music", "Bug": "task", "Balance": "task", "Other": "task"}
CATEGORIES = ("Art", "Bug", "Writing", "Music", "Balance", "Other")


def _dir_rel(adp) -> str:
    if adp is not None and callable(getattr(adp, "playtest_dir", None)):
        try:
            return str(adp.playtest_dir()).strip("/") or "playtest"
        except Exception as e:  # noqa: BLE001
            log.warning("playtest: the adapter's playtest_dir() failed (%s); using playtest/", e)
    return "playtest"


def folder(root: Path, adp=None) -> Path:
    return Path(root) / _dir_rel(adp)


def art_file(cfg: dict, gid: str) -> str | None:
    """The game's art_feedback.json as a path, if this computer can reach it (for the finishing screens' take-in)."""
    from . import games
    try:
        root = games.game_root(cfg, gid)
        adp = games.adapter(cfg, gid) if games.has_adapter(cfg, gid) else None
    except Exception as e:  # noqa: BLE001
        log.warning("playtest: no game folder for %s (%s)", gid, e)
        return None
    if not root:
        return None
    return str(folder(root, adp) / "art_feedback.json")


def _routed_path(root: Path) -> Path:
    return Path(root) / "playtest_inbox" / "routed.jsonl"


def _routed(root: Path) -> dict[str, dict]:
    p = _routed_path(root)
    out: dict[str, dict] = {}
    if p.is_file():
        for raw in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(raw)
            except ValueError:
                continue
            if e.get("note"):
                out[e["note"]] = e
    return out


def _append_routed(root: Path, e: dict) -> None:
    p = _routed_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(e, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def read(root: Path, adp=None) -> list[dict]:
    """Every note the game wrote, oldest first, each with a stable id (a hash of its line)."""
    p = folder(root, adp) / "notes.jsonl"
    if not p.is_file():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            r = json.loads(raw)
        except ValueError:
            continue                        # a torn last line (the game was closed mid-write) waits for the next look
        if not isinstance(r, dict):
            continue
        r["id"] = "pt-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        r["category"] = r.get("category") if r.get("category") in CATEGORIES else "Other"
        out.append(r)
    return out


def _place_of(adp, map_id: str) -> str | None:
    if adp is None or not map_id:
        return None
    try:
        for p in adp.places():
            if map_id == p.id or map_id in (p.maps or []):
                return p.id
    except Exception as e:  # noqa: BLE001
        log.warning("playtest: places not read (%s)", e)
    return None


def _line_of(adp, dialogue: str) -> tuple[str | None, str | None]:
    """The first line of the named conversation: (ref, place)."""
    if adp is None or not dialogue:
        return None, None
    try:
        for l in adp.lines():
            if l.source == dialogue or str(l.ref.file).rsplit("/", 1)[-1].rsplit(".", 1)[0] == dialogue:
                return str(l.ref), l.place
    except Exception as e:  # noqa: BLE001
        log.warning("playtest: lines not read (%s)", e)
    return None, None


def _where_words(r: dict) -> str:
    bits = []
    for k, label in (("map", "map"), ("era", "era"), ("context", "in"), ("dialogue", "talk"), ("nearest", "near"),
                     ("battle", "battle"), ("minigame", "minigame"), ("cue", "cue")):
        v = r.get(k)
        if v not in (None, "", -1, 0):
            bits.append(f"{label} {v}")
    return " · ".join(bits)


def inbox(root: Path, adp=None) -> dict:
    """What the Playtest notes tab shows: every note with its category, where it was taken, its screenshot (relative to
    the game folder), the route it takes, and — once taken in — where it went."""
    rows = read(root, adp)
    routed = _routed(root)
    base = folder(root, adp)
    out = []
    for r in reversed(rows):
        shot = r.get("shot") or ""
        shot_rel = None
        if shot:
            sp = Path(str(shot).replace("user://", ""))
            sp = sp if sp.is_absolute() else base / sp
            if sp.is_file():
                try:
                    shot_rel = sp.relative_to(Path(root)).as_posix()
                except ValueError:
                    shot_rel = None
        place = _place_of(adp, r.get("map", ""))
        out.append({"id": r["id"], "time": r.get("time", ""), "tester": r.get("tester", ""), "category": r["category"],
                    "text": r.get("text", ""), "where": _where_words(r), "map": r.get("map", ""), "era": r.get("era", ""),
                    "place": place, "dialogue": r.get("dialogue", ""), "shot": shot_rel, "route": ROUTES[r["category"]],
                    "routed": routed.get(r["id"]), "build": r.get("build", ""), "party": r.get("party", [])})
    by = {c: sum(1 for x in out if x["category"] == c) for c in CATEGORIES}
    return {"notes": out, "by_category": by, "new": sum(1 for x in out if not x["routed"]), "folder": _dir_rel(adp),
            "has_file": (base / "notes.jsonl").is_file()}


def take_in(cfg: dict, gid: str, who: str, to: str = "Claude", when: datetime | None = None) -> dict:
    """Route every new note (see the module's words) and write one letter per category to `to`."""
    from . import games, mail, notes, orders
    if not who:
        raise ValueError("taking in the notes is signed — set who you are first")
    root = games.game_root(cfg, gid)
    if not root or not Path(root).is_dir():
        raise FileNotFoundError(f"the game folder for {gid} isn't reachable")
    adp = games.adapter(cfg, gid) if games.has_adapter(cfg, gid) else None
    when = when or settings.now()
    box = inbox(root, adp)
    new = [n for n in reversed(box["notes"]) if not n["routed"]]           # oldest first
    if not new:
        return {"ok": True, "message": "No new playtest notes — every note is already taken in.", "taken": 0, "letters": []}
    report = {"art": None, "notes": 0, "orders": 0}
    art_new = [n for n in new if n["route"] == "art"]
    if art_new:
        try:
            from ..night4 import feedback
            report["art"] = feedback.take_in(cfg, art_file(cfg, gid), gid)
        except FileNotFoundError as e:
            report["art"] = {"error": str(e)}
        except Exception as e:  # noqa: BLE001 — art drafts failing must not lose the other notes
            log.error("playtest: art take-in failed: %s", e)
            report["art"] = {"error": f"{type(e).__name__}: {e}"}
    by_cat: dict[str, list] = {}
    for n in new:
        where = ""
        try:
            if n["route"] == "art":
                a = report["art"] or {}
                where = ("Art → Review → Called out (a redo draft, or a priority bump on a stand-in)" if not a.get("error")
                         else f"Called out couldn't take it ({a['error']}) — it waits here")
            elif n["route"] in ("writing", "music"):
                ref, lplace = _line_of(adp, n["dialogue"])
                obj = ref or (f"place:{n['place'] or lplace}" if (n["place"] or lplace) else f"playtest:{n['map'] or 'somewhere'}")
                label = (f"{n['dialogue']} (first line)" if ref else (n["place"] or lplace or n["map"] or "a playtest note"))
                notes.add(root, obj, who, f"[playtest · {n['category']}] {n['text'] or '(no words — see the screenshot)'}"
                          + (f"  — {n['where']}" if n["where"] else ""), tag="note", label=label, to=to, when=when)
                report["notes"] += 1
                where = f"a note on {label} (Notes → Open notes)"
            else:
                o = orders.add(root, who, to, f"[{n['category']}] {(n['text'] or 'a note with a screenshot')[:120]}",
                               detail=f"Playtest note, {n['time'][:16].replace('T', ' ')} ({n['tester'] or 'tester'}): {n['text']}\n"
                                      f"Where: {n['where'] or '—'}" + (f"\nScreenshot: {n['shot']}" if n["shot"] else ""),
                               priority="now" if n["category"] == "Bug" else "soon", obj=f"playtest:{n['id']}")
                report["orders"] += 1
                where = f"work order {o['id']} for {o['for']}"
        except Exception as e:  # noqa: BLE001
            log.error("playtest: note %s not routed: %s", n["id"], e)
            where = f"not routed ({type(e).__name__}: {e}) — it waits here"
            continue
        _append_routed(root, {"note": n["id"], "time": when.isoformat(timespec="seconds"), "who": who, "route": n["route"],
                              "where": where, "category": n["category"]})
        n["went"] = where
        by_cat.setdefault(n["category"], []).append(n)
    letters = []
    prior = {l.subject: l for l in mail.all_letters(root) if l.subject.startswith("Playtest notes — ")}
    for cat, ns in by_cat.items():
        subject = f"Playtest notes — {cat}"
        body = [f"{len(ns)} new {cat.lower()} note(s) from playing, taken in by {who}. Each went where it can be worked on:", ""]
        atts = []
        for n in ns:
            body.append(f"- **{n['time'][:16].replace('T', ' ')}** · {n['tester'] or 'tester'} · {n['where'] or 'somewhere'}")
            body.append(f"  “{n['text'] or '(no words — the screenshot says it)'}”")
            body.append(f"  → {n['went']}")
            if n["shot"]:
                atts.append(n["shot"])
        first = prior.get(subject) or prior.get(f"Re: {subject}")
        l = mail.send(root, who, to, subject if not first else f"Re: {subject}", "\n".join(body), attachments=atts,
                      thread_id=first.thread if first else None, in_reply_to=first.id if first else None, when=when)
        letters.append(l.id)
    taken = sum(len(v) for v in by_cat.values())
    msg = (f"Took in {taken} playtest note(s): " + ", ".join(f"{len(v)} {k.lower()}" for k, v in by_cat.items())
           + f" — {len(letters)} letter(s) to {to}" + (f"; {report['orders']} work order(s)" if report["orders"] else "")
           + (f"; {report['notes']} note(s) pinned" if report["notes"] else "") + ".")
    journal.append(root, who, "draft", "playtest notes", note=msg, when=when)
    return {"ok": True, "message": msg, "taken": taken, "letters": letters, "report": report}
