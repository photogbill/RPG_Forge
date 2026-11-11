"""Approved means his — William's rule (suite spec §8 rule 2) as primitives every screen and session uses.

An item (a line, a quest, a town sheet field — any JSON object) carries `status` (draft / approved / flagged) and,
once a person approves it, `approved_by` (their name). Anything a person approved or wrote is theirs: a Claude
session may not change it silently. An edit to it is saved as a **proposed change** — before and after, with a
reason — in `<game_root>/proposals/<id>.json`, which arrives in the owner's inbox (the Mail, BUILD 03) to accept or
decline. If the data moved since the proposal was made, accepting it refuses and says so; it is never forced.

Who may edit directly: anyone, on an item nobody approved; the person who approved it; a person (not an assistant)
on an item marked approved with no name on it. Everyone else proposes.
"""
from __future__ import annotations
import json, os, re, secrets
from datetime import datetime
from pathlib import Path

from ..log import get
from . import journal, settings
from .jsondoc import JsonDoc, split_pointer, join_pointer

log = get("suite")


def item_of(doc: JsonDoc, field_pointer) -> tuple[str, str | None, str | None]:
    """The nearest enclosing object of a field that carries approval marks (status / approved_by / draft); else the
    field's own parent object. Returns (item pointer, status, approved_by)."""
    parts = split_pointer(field_pointer)
    first = None
    for cut in range(len(parts) - 1, -1, -1):
        ptr = parts[:cut]
        v = doc.get(ptr, None)
        if isinstance(v, dict):
            if first is None:
                first = ptr
            if "approved_by" in v or "status" in v or "draft" in v:
                st = v.get("status") or ("draft" if v.get("draft") is True else None)
                return join_pointer(ptr), st, v.get("approved_by") or None
    return join_pointer(first or []), None, None


def may_edit(status: str | None, approved_by: str | None, who: str) -> bool:
    if approved_by:
        return who == approved_by
    if status == "approved":
        return not settings.is_assistant(who)
    return True


def folder(root: Path) -> Path:
    return Path(root) / "proposals"


def _write(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def propose(adp, rel: str, changes: list[dict], who: str, reason: str, base_hash: str, now: datetime | None = None) -> dict:
    from .safesave import _field_pointer
    now = now or settings.now()
    doc = adp.read_doc(rel)
    first = _field_pointer(changes[0])
    item, status, owner = item_of(doc, first)
    slug = re.sub(r"[^a-z0-9]+", "-", Path(rel).stem.lower()).strip("-")[:30] or "change"
    pid = f"{now:%Y%m%d-%H%M%S}-{slug}-{secrets.token_hex(2)}"
    p = {"id": pid, "status": "open", "created": now.isoformat(timespec="seconds"), "from": who,
         "to": owner or "whoever approved it", "file": rel, "item": item, "reason": reason, "base_hash": base_hash,
         "changes": [{**c, "field": _field_pointer(c), "before": doc.get(_field_pointer(c), None)} for c in changes]}
    _write(folder(adp.root) / f"{pid}.json", p)
    journal.append(adp.root, who, "propose", f"{rel}#{item}", before=[c["before"] for c in p["changes"]],
                   after=[c["value"] for c in p["changes"]], note=reason or None, link=f"proposals/{pid}.json", when=now)
    return p


def load(root: Path, pid: str) -> dict:
    return json.loads((folder(root) / f"{pid}.json").read_text(encoding="utf-8"))


def list_open(root: Path) -> list[dict]:
    d = folder(root)
    out = []
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            try:
                x = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if x.get("status") == "open":
                out.append(x)
    return out


def accept(adp, pid: str, who: str, now: datetime | None = None) -> dict:
    """The owner takes the change: it is applied through the safe path, if the data still says what it said."""
    from .safesave import save, file_hash, SaveRefused, SaveConflict
    now = now or settings.now()
    p = load(adp.root, pid)
    if p.get("status") != "open":
        return {"ok": False, "message": f"that proposal is already {p.get('status')}"}
    if settings.is_assistant(who) or (p.get("to") not in (None, "whoever approved it") and who != p.get("to")):
        return {"ok": False, "message": f"only {p.get('to')} can accept this change"}
    data = adp.path(p["file"]).read_bytes()
    doc = JsonDoc.from_bytes(data)
    moved = [c["field"] for c in p["changes"] if doc.get(c["field"], None) != c["before"]]
    if moved:
        p.update(status="stale", decided_by=who, decided_at=now.isoformat(timespec="seconds"),
                 note="the data changed since this was proposed: " + ", ".join(moved))
        _write(folder(adp.root) / f"{pid}.json", p)
        journal.append(adp.root, who, "decline", f"{p['file']}#{p['item']}", note=p["note"], link=f"proposals/{pid}.json", when=now)
        return {"ok": False, "message": p["note"]}
    from .safesave import apply_change
    for c in p["changes"]:
        apply_change(doc, c)
    try:
        r = save(adp, p["file"], doc.to_bytes(), file_hash(data), now=now)
    except (SaveRefused, SaveConflict) as e:
        return {"ok": False, "message": str(e)}
    p.update(status="accepted", decided_by=who, decided_at=now.isoformat(timespec="seconds"))
    _write(folder(adp.root) / f"{pid}.json", p)
    journal.append(adp.root, who, "accept", f"{p['file']}#{p['item']}", before=[c["before"] for c in p["changes"]],
                   after=[c["value"] for c in p["changes"]], note=f"proposed by {p['from']}", link=r.get("backup"), when=now)
    return {"ok": True, "message": "applied", **r}


def decline(adp, pid: str, who: str, note: str = "", now: datetime | None = None) -> dict:
    now = now or settings.now()
    p = load(adp.root, pid)
    if p.get("status") != "open":
        return {"ok": False, "message": f"that proposal is already {p.get('status')}"}
    p.update(status="declined", decided_by=who, decided_at=now.isoformat(timespec="seconds"), note=note)
    _write(folder(adp.root) / f"{pid}.json", p)
    journal.append(adp.root, who, "decline", f"{p['file']}#{p['item']}", note=note or None, link=f"proposals/{pid}.json", when=now)
    return {"ok": True, "message": "declined"}


def mark(adp, rel: str, item_pointer: str, status: str, who: str, expected_hash: str | None = None,
         now: datetime | None = None) -> dict:
    """Set an item's status. Approving also signs it (`approved_by`). Goes through the safe path like any edit;
    an approved item's owner is the only one who can un-approve it (anyone else's attempt becomes a proposal)."""
    from .safesave import edit
    if status not in ("draft", "approved", "flagged"):
        return {"ok": False, "refused": [f"status must be draft, approved or flagged — not {status!r}"]}
    if status == "approved" and settings.is_assistant(who):
        return {"ok": False, "refused": ["approving is a person's call — an assistant marks draft or flagged, or proposes"]}
    doc = adp.read_doc(rel)
    changes = [("add", item_pointer, "status", status)]
    if status == "approved":
        changes.append(("add", item_pointer, "approved_by", who))
    elif (doc.get(item_pointer, {}) or {}).get("approved_by"):
        changes.append(("set", item_pointer.rstrip("/") + "/approved_by", None))   # no longer approved → no longer signed
    kind = {"approved": "approve", "flagged": "flag", "draft": "draft"}[status]
    return edit(adp, rel, changes, who, expected_hash=expected_hash, kind=kind, now=now)
