"""Work orders — two lists that make the work visible both ways (suite spec §8 B2, BUILD 03).

"For <someone>": a thing to do, with a priority and (optionally) the object it is about — a line, a town, a picture,
a letter's question (`object` is any ref string: `project/data/towns/x.json#/after`, `job:<id>`, `mail:<id>#q2`).
Anyone adds one, to anyone; the person working at the PC fills the assistants' list from anywhere in the suite, and a
session fills the person's list with what only they can do (songs to make, sheets to draw, places to check on a map).
A session starts at the top of its list and closes each order saying what it did.

Files, so both sides can read them without the suite: `<game_root>/work_orders/for_<group>/<id>.json` (a group is the
first word of a name, as in the Mail). Closing moves nothing and deletes nothing: the file gets status done/dropped.
"""
from __future__ import annotations
import json, os
from datetime import datetime
from pathlib import Path

from . import journal, settings
from .mail import group_of, slug

PRIORITIES = ("now", "soon", "someday")


def folder(root: Path) -> Path:
    return Path(root) / "work_orders"


def _write(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def add(root: Path, by: str, for_name: str, title: str, detail: str = "", priority: str = "soon",
        obj: str | None = None, when: datetime | None = None) -> dict:
    if not by:
        raise ValueError("a work order is signed — set who you are first")
    if not str(title).strip():
        raise ValueError("a work order needs a line saying what to do")
    if priority not in PRIORITIES:
        raise ValueError(f"priority is one of {', '.join(PRIORITIES)}")
    when = when or settings.now()
    g = group_of(for_name)
    oid = f"{when:%Y%m%d-%H%M%S}-{slug(title, 32)}"
    p = folder(root) / f"for_{g}" / f"{oid}.json"
    n = 1
    while p.exists():
        n += 1
        p = p.with_name(f"{oid}-{n}.json")
    d = {"id": p.stem, "for": for_name, "group": g, "title": " ".join(str(title).split()), "detail": detail.strip(),
         "priority": priority, "object": obj or None, "by": by, "created": when.isoformat(timespec="seconds"),
         "status": "open"}
    _write(p, d)
    journal.append(root, by, "order", obj or f"work_orders/for_{g}/{p.name}", note=f"for {for_name} ({priority}): {d['title']}", when=when)
    return d


def _all(root: Path):
    d = folder(root)
    if not d.is_dir():
        return
    for sub in sorted(x for x in d.iterdir() if x.is_dir() and x.name.startswith("for_")):
        for f in sorted(sub.glob("*.json")):
            try:
                yield f, json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue


def listing(root: Path, group: str | None = None, status: str | None = "open") -> list[dict]:
    rank = {p: i for i, p in enumerate(PRIORITIES)}
    out = [o for _f, o in _all(root) if (group is None or o.get("group") == group_of(group))
           and (status is None or o.get("status") == status)]
    return sorted(out, key=lambda o: (rank.get(o.get("priority"), 9), o.get("created", "")))


def groups(root: Path, extra=()) -> list[str]:
    """Every group with a list (or about to have one): those with orders, plus the given names' groups."""
    gs = {o.get("group") for _f, o in _all(root)} | {group_of(n) for n in extra if n}
    return sorted(g for g in gs if g)


def close(root: Path, order_id: str, who: str, note: str = "", status: str = "done", when: datetime | None = None) -> dict:
    if status not in ("done", "dropped", "open"):
        raise ValueError("status is done, dropped or open")
    when = when or settings.now()
    for f, o in _all(root):
        if o.get("id") == order_id:
            o.update(status=status, closed_by=who if status != "open" else None,
                     closed_at=when.isoformat(timespec="seconds") if status != "open" else None, note=note or o.get("note"))
            _write(f, o)
            journal.append(root, who, "order", o.get("object") or f"work_orders/{f.parent.name}/{f.name}",
                           note=f"{status}: {o['title']}" + (f" — {note}" if note else ""), when=when)
            return o
    raise FileNotFoundError(order_id)
