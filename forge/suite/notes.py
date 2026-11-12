"""A note on anything (suite spec §8 B3) — any object (a line, a town, a quest, a person, a picture, a music slot) can
carry pinned notes, threaded and signed.

`<game_root>/notes/notes.jsonl`, one JSON object per line, appended (O_APPEND — the GUI and a session can write at the
same time with no lock file): {id, time, who, obj, text, tag, reply_to, resolves}. An object is named by its ref
(`data/dialogue/x.json#/lines/2`) or any stable key (`music:<slot>`, `place:<id>`). A note is never rewritten: a
reply is a new note with reply_to; closing a thread is a note that resolves it. Every note also goes to the journal
(kind "note"), so "while you were away" carries it to the next session.
"""
from __future__ import annotations
import json, os, secrets
from datetime import datetime
from pathlib import Path

from . import journal, settings

TAGS = ("note", "generic", "question", "idea")


def path(root: Path) -> Path:
    return Path(root) / "notes" / "notes.jsonl"


def _all(root: Path) -> list[dict]:
    p = path(root)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def add(root: Path, obj: str, who: str, text: str, tag: str = "note", reply_to: str | None = None,
        resolves: str | None = None, when: datetime | None = None, label: str | None = None,
        to: str | None = None) -> dict:
    if not who:
        raise ValueError("a note is signed — set who you are first")
    if not str(obj).strip():
        raise ValueError("a note needs something to be pinned to")
    if not str(text).strip() and not resolves:
        raise ValueError("the note is empty")
    if tag not in TAGS:
        raise ValueError(f"a note's tag is one of {', '.join(TAGS)}")
    when = when or settings.now()
    n = {"id": f"{when:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}", "time": when.isoformat(timespec="seconds"), "who": str(who),
         "obj": str(obj), "text": str(text).strip(), "tag": tag}
    if label:
        n["label"] = str(label)[:200]
    if to:
        n["to"] = str(to)          # BUILD 26: a note addressed to someone becomes a card on their Tasks
    if reply_to:
        n["reply_to"] = reply_to
    if resolves:
        n["resolves"] = resolves
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(n, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    what = "resolved a note" if resolves else (f"{tag}: " if tag != "note" else "") + n["text"]
    journal.append(root, who, "note", obj, note=what + (f" — on {label}" if label else ""), when=when)
    return n


def threads(root: Path, obj: str | None = None, open_only: bool = False) -> list[dict]:
    """Threads (a first note and its replies), newest activity first; one object's, or all."""
    notes = _all(root)
    resolved = {n["resolves"] for n in notes if n.get("resolves")}
    heads = [n for n in notes if not n.get("reply_to") and not n.get("resolves") and (obj is None or n["obj"] == obj)]
    out = []
    for h in heads:
        replies = [n for n in notes if n.get("reply_to") == h["id"]]
        t = {**h, "replies": replies, "open": h["id"] not in resolved,
             "last": max([h["time"]] + [r["time"] for r in replies])}
        if open_only and not t["open"]:
            continue
        out.append(t)
    out.sort(key=lambda t: t["last"], reverse=True)
    return out


def counts(root: Path) -> dict:
    """obj → number of open threads on it."""
    c: dict = {}
    for t in threads(root, open_only=True):
        c[t["obj"]] = c.get(t["obj"], 0) + 1
    return c
