"""The idea box (BUILD 17, suite spec §8 B8) — one key, one line, from anywhere.

Press **I** anywhere in the suite (or `python -m forge idea "…"`): a song idea, a town, a joke for later. It is filed
with the date, who had it, and **what they were looking at** (the suite address, e.g. `story/read/augusta`, and the
object if there was one). Ideas are kept until someone sorts them — into a task, a note pinned where it belongs, a letter,
or a file in the game — and the idea then says **where it went**. Sessions sort them and say so; nothing is deleted.

`<game_root>/ideas/ideas.jsonl`, append-only (O_APPEND — the GUI and a session can write at once, no lock file):
an idea `{id, time, who, text, at, obj, label}`; sorting it is a later line `{sorts, time, who, to, where, note}`.
"""
from __future__ import annotations
import json, os, secrets
from datetime import datetime
from pathlib import Path

from . import journal, settings

DESTS = ("task", "note", "letter", "file", "kept", "dropped")


def path(root: Path) -> Path:
    return Path(root) / "ideas" / "ideas.jsonl"


def _all(root: Path) -> list[dict]:
    p = path(root)
    if not p.is_file():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            try:
                out.append(json.loads(raw))
            except ValueError:
                continue
    return out


def _append(root: Path, e: dict) -> None:
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(e, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def add(root: Path, who: str, text: str, at: str | None = None, obj: str | None = None, label: str | None = None,
        when: datetime | None = None) -> dict:
    if not who:
        raise ValueError("an idea is signed — set who you are first")
    text = " ".join(str(text or "").split())
    if not text:
        raise ValueError("the idea is empty")
    if len(text) > 2000:
        raise ValueError("an idea is one line — keep it under 2,000 characters (write a letter for more)")
    when = when or settings.now()
    e = {"id": f"{when:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}", "time": when.isoformat(timespec="seconds"), "who": str(who),
         "text": text}
    for k, v in (("at", at), ("obj", obj), ("label", label)):
        if v:
            e[k] = str(v)[:300]
    _append(root, e)
    journal.append(root, who, "note", "ideas", note=f"idea: {text[:300]}" + (f" — while looking at {label or at}" if (label or at) else ""),
                   link=e["id"], when=when)
    return e


def find(root: Path, idea_id: str) -> dict | None:
    return next((i for i in listing(root, "all") if i["id"] == idea_id), None)


def sort(root: Path, idea_id: str, who: str, to: str, where: str = "", note: str = "", when: datetime | None = None) -> dict:
    """Say where an idea went (a task id, a note's object, a letter id, a file path) — or that it is kept / dropped."""
    if not who:
        raise ValueError("sorting is signed — set who you are first")
    if to not in DESTS:
        raise ValueError(f"an idea goes to one of: {', '.join(DESTS)}")
    i = find(root, idea_id)
    if i is None:
        raise FileNotFoundError(f"no idea {idea_id}")
    if to in ("task", "note", "letter", "file") and not str(where).strip():
        raise ValueError("say where it went (the task, the note's place, the letter or the file)")
    when = when or settings.now()
    e = {"sorts": idea_id, "time": when.isoformat(timespec="seconds"), "who": str(who), "to": to}
    if where:
        e["where"] = str(where)[:400]
    if note:
        e["note"] = str(note)[:1000]
    _append(root, e)
    journal.append(root, who, "note", "ideas", note=f"idea sorted → {to}{(': ' + str(where)) if where else ''} — “{i['text'][:160]}”",
                   link=idea_id, when=when)
    return e


def to_task(root: Path, idea_id: str, who: str, for_: str, priority: str = "soon", title: str | None = None) -> dict:
    from . import orders
    i = find(root, idea_id)
    if i is None:
        raise FileNotFoundError(f"no idea {idea_id}")
    o = orders.add(root, who, for_, title or i["text"][:140], detail=f"From the idea box ({i['who']}, {i['time'][:16].replace('T', ' ')}): "
                   f"{i['text']}" + (f"\nWhile looking at: {i.get('label') or i.get('at')}" if i.get("at") or i.get("label") else ""),
                   priority=priority, obj=i.get("obj") or i.get("at"))
    sort(root, idea_id, who, "task", where=f"work order {o['id']} for {o['for']}")
    return o


def to_note(root: Path, idea_id: str, who: str, obj: str, label: str | None = None, to: str | None = None) -> dict:
    from . import notes
    i = find(root, idea_id)
    if i is None:
        raise FileNotFoundError(f"no idea {idea_id}")
    n = notes.add(root, obj, who, f"{i['text']}  (idea from {i['who']}, {i['time'][:10]})", tag="idea", label=label, to=to)
    sort(root, idea_id, who, "note", where=f"a note on {label or obj}")
    return n


def listing(root: Path, state: str = "open") -> list[dict]:
    """Ideas newest first; state open (not sorted yet, or kept) | sorted | all. Each carries `sorted` (the latest line)."""
    rows = _all(root)
    sorts: dict[str, dict] = {}
    for r in rows:
        if r.get("sorts"):
            sorts[r["sorts"]] = r
    out = []
    for r in rows:
        if r.get("sorts") or not r.get("id"):
            continue
        s = sorts.get(r["id"])
        done = bool(s) and s["to"] != "kept"
        if state == "open" and done or state == "sorted" and not done:
            continue
        out.append({**r, "sorted": s, "open": not done})
    out.sort(key=lambda r: r["time"], reverse=True)
    return out


def counts(root: Path) -> dict:
    allr = listing(root, "all")
    return {"open": sum(1 for r in allr if r["open"]), "sorted": sum(1 for r in allr if not r["open"]), "all": len(allr)}
