"""The journal — one line per action anyone takes through the suite (William's rule, suite spec §8 rule 1).

`<game_root>/journal/<yyyy-mm>.jsonl`, one JSON object per line: when, **who** (the signed name), what kind, which
object, before → after, a link, a note. An edit, an approval, a flag, a note, a music assignment, a letter, a queued
render, a delivery — every one appends here, from the GUI and from Claude sessions alike (`append()`; command line:
`python -m forge journal add …`). `WORKBENCH_LOG.md` in the game folder is a readable view of the newest entries,
rebuilt after each append — not a second record.

Appends are single writes with O_APPEND, so the GUI and a session can write at the same time without a lock file
(a session's shell cannot delete files, so lock files would be left behind).
"""
from __future__ import annotations
import json, os
from datetime import datetime
from pathlib import Path

from ..log import get
from . import settings

log = get("suite")
VIEW_ENTRIES = 300
KINDS = ("edit", "approve", "flag", "draft", "note", "propose", "accept", "decline", "music", "letter", "queue",
         "deliver", "conflict", "refused", "test", "session", "setting", "order", "seen", "art")


def folder(game_root: Path) -> Path:
    return Path(game_root) / "journal"


def _short(v, n: int = 2000):
    if isinstance(v, str) and len(v) > n:
        return v[:n] + f"… ({len(v)} characters)"
    return v


def append(game_root: Path, who: str, kind: str, obj: str | None = None, before=None, after=None,
           link: str | None = None, note: str | None = None, when: datetime | None = None, view: bool = True) -> dict:
    if not who:
        raise ValueError("a journal line needs a name (who) — set the identity first")
    when = when or settings.now()
    entry = {"time": when.isoformat(timespec="seconds"), "who": str(who), "kind": str(kind)}
    for k, v in (("obj", obj), ("before", before), ("after", after), ("link", link), ("note", note)):
        if v is not None:
            entry[k] = _short(v)
    d = folder(game_root)
    d.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(str(d / f"{when:%Y-%m}.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
    log.info("journal: %s %s %s %s", entry["who"], entry["kind"], entry.get("obj", ""), entry.get("note", "") or "")
    if view:
        try:
            write_view(game_root)
        except OSError as e:          # the record is the .jsonl; a view that cannot be rewritten is only a warning
            log.warning("journal: WORKBENCH_LOG.md not rewritten: %s", e)
    return entry


def read(game_root: Path, since: str | None = None, who: str | None = None, kinds=None, limit: int | None = None) -> list[dict]:
    """Entries oldest first. `since` is an ISO time (string compare works: the format is fixed)."""
    out: list[dict] = []
    d = folder(game_root)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.jsonl")):
        if since and p.stem < since[:7]:
            continue
        for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            try:
                e = json.loads(raw)
            except ValueError:
                continue                    # a torn line (power cut mid-write) is skipped, not fatal
            if since and str(e.get("time", "")) <= since:
                continue
            if who and e.get("who") != who:
                continue
            if kinds and e.get("kind") not in kinds:
                continue
            out.append(e)
    return out[-limit:] if limit else out


def _fmt(v) -> str:
    if v is None:
        return ""
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = s.replace("\n", " ⏎ ")
    return s if len(s) <= 220 else s[:217] + "…"


def write_view(game_root: Path) -> Path:
    entries = read(game_root)[-VIEW_ENTRIES:]
    lines = ["# Workbench log — a readable view of the journal", "",
             f"*Rebuilt after every journal line; the record itself is `journal/*.jsonl`. Newest first; the last {VIEW_ENTRIES}.*", ""]
    for e in reversed(entries):
        head = f"- **{e.get('time', '?').replace('T', ' ')}** · {e.get('who', '?')} · {e.get('kind', '?')}"
        if e.get("obj"):
            head += f" · `{e['obj']}`"
        lines.append(head)
        if "before" in e or "after" in e:
            lines.append(f"  - before: {_fmt(e.get('before'))}")
            lines.append(f"  - after: {_fmt(e.get('after'))}")
        if e.get("note"):
            lines.append(f"  - {_fmt(e['note'])}")
        if e.get("link"):
            lines.append(f"  - see {e['link']}")
    p = Path(game_root) / "WORKBENCH_LOG.md"
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p
