"""The safe-save path — the only way the suite (or a session using it) writes a game's data file.

    temp file → the game's own validator → backup → atomic replace → journal

1. **Two writers.** The caller says which version it read (`expected_hash`, sha256 of the bytes). If the file changed
   underneath (a build session, Notepad), nothing is written: the result carries both versions so the person chooses.
2. **It can't break the game.** The new bytes go to `<game_root>/_workbench_tmp/…/<folder>/<file>` and the game's
   validator checks them there (same file name and folder name, so a checker that keys on them still works). On a
   problem, nothing is written and the problems come back in plain words.
3. **Backup** of the version being replaced: `<game_root>/_workbench_backups/<date>/<path>.<HHMMSS>.<ext>`.
4. **Atomic replace** (os.replace on the same drive) — a reader sees the old file or the new one, never half.
5. **Journal**: one line per change (journal.py).

`edit()` is the field-level entry point the screens use: ids are never editable, locked files and lines (a song's
own words) refuse, and an item someone approved becomes a *proposed change* for them instead of an edit
(approval.py). Unknown fields are preserved byte for byte because the file is never re-serialised (jsondoc.py).
"""
from __future__ import annotations
import hashlib, os, secrets, time
from datetime import datetime
from pathlib import Path

from ..log import get
from . import approval, journal, settings
from .jsondoc import JsonDoc, JsonDocError, split_pointer

log = get("suite")


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SaveConflict(Exception):
    def __init__(self, rel: str, expected: str, current_bytes: bytes):
        super().__init__(f"{rel} changed since it was opened — someone else saved it; nothing was written")
        self.rel, self.expected, self.current_bytes = rel, expected, current_bytes
        self.current_hash = file_hash(current_bytes)


class SaveRefused(Exception):
    def __init__(self, rel: str, problems: list[str]):
        super().__init__(f"{rel} was not saved: " + "; ".join(problems))
        self.rel, self.problems = rel, problems


def _backup(adp, rel: str, data: bytes, now: datetime) -> str:
    p = Path(rel)
    stem, ext = p.stem, p.suffix
    base = adp.root / "_workbench_backups" / f"{now:%Y-%m-%d}" / p.parent
    base.mkdir(parents=True, exist_ok=True)
    name = f"{stem}.{now:%H%M%S}{ext}"
    n = 1
    while (base / name).exists():
        n += 1
        name = f"{stem}.{now:%H%M%S}-{n}{ext}"
    (base / name).write_bytes(data)
    return (base / name).relative_to(adp.root).as_posix()


def _cleanup(tmp: Path, top: Path) -> None:
    try:
        if tmp.exists():
            tmp.unlink()
        d = tmp.parent
        while d != top.parent and d.exists():
            d.rmdir()
            d = d.parent
    except OSError:
        pass        # a session's shell may not delete; a leftover empty temp folder is harmless


def save(adp, rel: str, new_bytes: bytes, expected_hash: str, now: datetime | None = None) -> dict:
    """Write `new_bytes` to the game file `rel` the safe way. Raises SaveConflict / SaveRefused; nothing is written then.
    Returns {"changed": bool, "hash": new hash, "backup": backup path or None}."""
    now = now or settings.now()
    if adp.is_locked_file(rel):
        raise SaveRefused(rel, [f"{rel} is locked (a song's own words, or a file the suite never writes)"])
    target = adp.path(rel)
    current = target.read_bytes()
    if file_hash(current) != expected_hash:
        raise SaveConflict(rel, expected_hash, current)
    if new_bytes == current:
        return {"changed": False, "hash": expected_hash, "backup": None}
    top = adp.root / "_workbench_tmp" / f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
    tmp = top / target.parent.name / target.name
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(new_bytes)
    try:
        problems = adp.validate(rel, tmp)
        if problems:
            raise SaveRefused(rel, problems)
        again = target.read_bytes()                  # the narrow window between validation and replace
        if file_hash(again) != expected_hash:
            raise SaveConflict(rel, expected_hash, again)
        backup = _backup(adp, rel, current, now)
        for attempt in range(6):
            try:
                os.replace(tmp, target)
                break
            except PermissionError:
                if attempt == 5:
                    raise SaveRefused(rel, [f"{rel} is open in another program that will not let go of it — close it and save again"]) from None
                time.sleep(0.25 * (attempt + 1))
    finally:
        _cleanup(tmp, top)
    h = file_hash(new_bytes)
    log.info("suite: saved %s (%s → %s), backup %s", rel, expected_hash[:10], h[:10], backup)
    return {"changed": True, "hash": h, "backup": backup}


def _norm(changes) -> list[dict]:
    out = []
    for c in changes:
        if isinstance(c, dict):
            out.append(dict(c))
        elif c[0] == "set":
            out.append({"op": "set", "pointer": c[1], "value": c[2]})
        elif c[0] == "add":
            out.append({"op": "add", "pointer": c[1], "key": c[2], "value": c[3]})
        elif c[0] == "put":                        # set the field if it exists, else add it to its parent object
            out.append({"op": "put", "pointer": c[1], "value": c[2]})
        else:
            raise ValueError(f"unknown change {c!r}")
    return out


def apply_change(doc: JsonDoc, c: dict) -> None:
    if c["op"] == "set":
        doc.set(c["pointer"], c["value"])
    elif c["op"] == "add":
        doc.add(c["pointer"], c["key"], c["value"])
    elif c["op"] == "put":
        parts = split_pointer(c["pointer"])
        if doc.has(parts):
            doc.set(parts, c["value"])
        else:
            doc.add(parts[:-1], parts[-1], c["value"])
    else:
        raise JsonDocError(f"unknown change {c['op']!r}")


def _field_pointer(c: dict) -> str:
    parts = split_pointer(c["pointer"])
    if c["op"] == "add":
        parts = parts + [c["key"]]
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def edit(adp, rel: str, changes, who: str, expected_hash: str | None = None, reason: str | None = None,
         kind: str = "edit", now: datetime | None = None) -> dict:
    """Apply field changes to one data file through the safe path. `changes`: [("set", pointer, value) |
    ("add", object_pointer, key, value) | {"op": …}]. Returns one of
      {"ok": True, "changed": bool, "hash", "backup"}
      {"ok": True, "proposed": {...}}            — an approved item: it went to its owner as a proposed change
      {"ok": False, "refused": [problems]}
      {"ok": False, "conflict": {"current_hash", "theirs": {pointer: value}, "yours": {pointer: value}}}"""
    now = now or settings.now()
    if not who:
        return {"ok": False, "refused": ["set who you are first (the identity setting) — every change is signed"]}
    changes = _norm(changes)
    data = adp.path(rel).read_bytes()
    cur_hash = file_hash(data)
    try:
        doc = JsonDoc.from_bytes(data)
    except JsonDocError as e:
        return {"ok": False, "refused": [f"{rel}: {e}"]}
    if expected_hash and expected_hash != cur_hash:
        theirs = {_field_pointer(c): doc.get(_field_pointer(c), None) for c in changes}
        yours = {_field_pointer(c): c["value"] for c in changes}
        journal.append(adp.root, who, "conflict", rel, note="the file changed underneath; nothing written", when=now)
        return {"ok": False, "conflict": {"file": rel, "current_hash": cur_hash, "theirs": theirs, "yours": yours}}
    problems, needs_owner = [], []
    for c in changes:
        fp = _field_pointer(c)
        if split_pointer(fp)[-1:] == ["id"]:
            problems.append(f"{fp}: ids are never edited here (other files point at them)")
            continue
        why = adp.locked(rel, fp)
        if why:
            problems.append(f"{fp}: locked — {why}")
            continue
        item, status, owner = approval.item_of(doc, fp)
        if not approval.may_edit(status, owner, who):
            needs_owner.append((c, fp, item, owner))
    if problems:
        journal.append(adp.root, who, "refused", rel, note="; ".join(problems), when=now)
        return {"ok": False, "refused": problems}
    if needs_owner:
        p = approval.propose(adp, rel, changes, who, reason or "", cur_hash, now=now)
        return {"ok": True, "proposed": p}
    before = {_field_pointer(c): doc.get(_field_pointer(c), None) for c in changes}
    try:
        for c in changes:
            apply_change(doc, c)
    except JsonDocError as e:
        return {"ok": False, "refused": [str(e)]}
    try:
        r = save(adp, rel, doc.to_bytes(), cur_hash, now=now)
    except SaveRefused as e:
        journal.append(adp.root, who, "refused", rel, note="; ".join(e.problems), when=now)
        return {"ok": False, "refused": e.problems}
    except SaveConflict as e:
        cd = JsonDoc.from_bytes(e.current_bytes)
        theirs = {_field_pointer(c): cd.get(_field_pointer(c), None) for c in changes}
        yours = {_field_pointer(c): c["value"] for c in changes}
        return {"ok": False, "conflict": {"file": rel, "current_hash": e.current_hash, "theirs": theirs, "yours": yours}}
    if r["changed"]:
        for c in changes:
            fp = _field_pointer(c)
            journal.append(adp.root, who, kind, f"{rel}#{fp}", before=before[fp], after=c["value"],
                           note=reason, link=r["backup"], when=now, view=False)
        try:
            journal.write_view(adp.root)
        except OSError:
            pass
        # BUILD 17: a change that makes the data say something other than a ruling pinned to it — saved (the person may
        # mean it), but warned about and journalled, so it never passes silently
        from . import rulings
        fps = [_field_pointer(c) for c in changes]
        touched = lambda p: any(p == f or p.startswith(f + "/") or f.startswith(p + "/") for f in fps)
        warns = rulings.after_edit(adp, rel, who, touched)
        if warns:
            r = {**r, "warnings": [w["message"] for w in warns], "ruling_conflicts": warns}
    return {"ok": True, **r}
