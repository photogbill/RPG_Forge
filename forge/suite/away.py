"""While you were away — one digest of what everyone else did since a correspondent last worked (spec §8 B1).

Built from the journal. "Since they last worked" is when that name last caught up — a session's start marker
(`python -m forge away --who "<name>" --mark`) or a "Got it" in the inbox — so what someone does while a session is
running reaches the next session's digest. Lines someone rewrote are shown as word diffs, because
how a person rewrites is the best guide to their voice. The same digest, the other way round, is the card at the top
of the person's inbox: what the assistants did while they were gone.
"""
from __future__ import annotations
import difflib, json
from pathlib import Path

from . import journal

ORDER = (("letter", "Letters"), ("edit", "Lines and fields rewritten"), ("approve", "Approved"), ("flag", "Flagged"),
         ("draft", "Marked draft"), ("propose", "Changes proposed to you"), ("accept", "Proposals accepted"),
         ("decline", "Proposals declined"), ("order", "Work orders"), ("music", "Music"), ("note", "Notes"),
         ("art", "Sprites and characters"), ("queue", "The art queue"), ("deliver", "Art delivered"), ("refused", "Saves the game refused"),
         ("conflict", "Save conflicts"))


def word_diff(before, after) -> str:
    """'old ~~words~~ **new words**' — readable in Markdown and as plain text."""
    a = before if isinstance(before, str) else json.dumps(before, ensure_ascii=False)
    b = after if isinstance(after, str) else json.dumps(after, ensure_ascii=False)
    aw, bw = a.split(), b.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=aw, b=bw, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(" ".join(aw[i1:i2]))
        if op in ("delete", "replace"):
            out.append("~~" + " ".join(aw[i1:i2]) + "~~")
        if op in ("insert", "replace"):
            out.append("**" + " ".join(bw[j1:j2]) + "**")
    return " ".join(x for x in out if x)


def last_worked(root: Path, who: str) -> str | None:
    """When `who` last caught up: their newest session start or "Got it" (kinds session / seen). Not simply their newest
    line — what someone else did *during* a session must reach the next session's digest. With no marker yet, their
    newest line of any kind; with no line at all, None (the digest covers everything)."""
    mine = journal.read(root, who=who)
    marks = [e for e in mine if e.get("kind") in ("session", "seen")]
    if marks:
        return marks[-1]["time"]
    return mine[-1]["time"] if mine else None


def digest(root: Path, who: str, since: str | None = None) -> dict:
    since = since or last_worked(root, who)
    entries = [e for e in journal.read(root, since=since) if e.get("who") != who and e.get("kind") not in ("session", "seen")]
    groups: dict[str, list] = {}
    for e in entries:
        k = e.get("kind")
        if k == "edit" and ("before" in e or "after" in e):
            e = {**e, "diff": word_diff(e.get("before") or "", e.get("after") or "")}
        groups.setdefault(k, []).append(e)
    people = sorted({e["who"] for e in entries})
    return {"who": who, "since": since, "count": len(entries), "people": people,
            "sections": [{"kind": k, "title": t, "entries": groups[k]} for k, t in ORDER if k in groups] +
                        [{"kind": k, "title": k, "entries": v} for k, v in groups.items() if k not in dict(ORDER)]}


def markdown(d: dict) -> str:
    when = (d["since"] or "the beginning").replace("T", " ")
    lines = [f"# While you were away — for {d['who']}", "",
             f"*Since {when}: {d['count']} thing(s) by {', '.join(d['people']) or 'nobody'}. Built from the journal.*", ""]
    if not d["count"]:
        lines.append("Nothing — nobody else has done anything through the suite since then.")
    for s in d["sections"]:
        lines += [f"## {s['title']} ({len(s['entries'])})", ""]
        for e in s["entries"]:
            head = f"- {e['time'].replace('T', ' ')[5:16]} · {e['who']}"
            if e.get("obj"):
                head += f" · `{e['obj']}`"
            lines.append(head)
            if e.get("diff"):
                lines.append(f"  - {e['diff']}")
            if e.get("note"):
                lines.append(f"  - {e['note']}")
        lines.append("")
    return "\n".join(lines)


def write(root: Path, who: str, since: str | None = None) -> tuple[Path, dict]:
    from .mail import group_of
    d = digest(root, who, since)
    p = Path(root) / "journal" / f"DIGEST_for_{group_of(who)}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown(d) + "\n", encoding="utf-8")
    return p, d
