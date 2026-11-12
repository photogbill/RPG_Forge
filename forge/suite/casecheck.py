"""Case in file references (BUILD 27). Windows and macOS usually don't care whether a name is upper or lower case; Linux
(and a game exported to some platforms) does. `report(cfg)` lists every reference the suite knows of — a music slot's
file, a delivered track, a brief, a song version, a letter's attachment — whose case differs from the file on disk.
It reports; it never renames anything. `doctor` prints it.
"""
from __future__ import annotations
import os
from pathlib import Path

from . import games, mail


def case_of(root: Path, rel: str) -> str | None:
    """The reference as the disk spells it, if it exists only in a different case; None when it matches or is missing."""
    cur = Path(root)
    parts = [p for p in str(rel).replace("\\", "/").split("/") if p and p != "."]
    out, differs = [], False
    for p in parts:
        try:
            names = os.listdir(cur)
        except OSError:
            return None
        if p in names:
            hit = p
        else:
            low = [n for n in names if n.lower() == p.lower()]
            if not low:
                return None
            hit, differs = low[0], True
        out.append(hit)
        cur = cur / hit
    return "/".join(out) if differs else None


def references(adp) -> list[tuple[str, str]]:
    """(where it's referenced, the relative path) for everything the suite points at in this game."""
    refs: list[tuple[str, str]] = []
    try:
        from . import music
        for s in music.slots(adp):
            f = str(s.get("file") or "")
            if f.startswith("res://"):
                f = "project/" + f[len("res://"):]
            if f and "://" not in f:
                refs.append((f"music slot {s['id']}", f))
            for key in ("brief",):
                if s.get(key):
                    refs.append((f"music slot {s['id']} {key}", str(s[key])))
            for v in s.get("versions") or []:
                if v.get("file"):
                    refs.append((f"music slot {s['id']} song v{v.get('n')}", v["file"]))
            if (s.get("delivered") or {}).get("file"):
                refs.append((f"music slot {s['id']} delivery", s["delivered"]["file"]))
    except Exception:  # noqa: BLE001 — a game without music still gets its letters checked
        pass
    for l in mail.all_letters(adp.root):
        for a in l.attachments:
            refs.append((f"letter {l.id}", a))
    return refs


def report(cfg: dict) -> list[str]:
    lines = []
    for gid in games.game_ids(cfg):
        root = games.game_root(cfg, gid)
        if not root or not root.is_dir() or not games.has_adapter(cfg, gid):
            continue
        try:
            adp = games.adapter(cfg, gid)
        except Exception:  # noqa: BLE001
            continue
        bad = [(w, r, d) for w, r in references(adp) if (d := case_of(root, r))]
        if bad:
            lines.append(f"· {gid}: {len(bad)} reference(s) whose upper/lower case differs from the file on disk (fine on Windows "
                         "and a Mac, broken on Linux) — fix the reference or rename the file:")
            lines += [f"    {w}: {r}  ← on disk: {d}" for w, r, d in bad[:30]]
        else:
            lines.append(f"✓ {gid}: every file reference matches the disk's upper/lower case")
    return lines
