"""Read a build queue written in markdown (BUILD 26 — for an adapter's optional `builds()` hook).

The queue is the game's own file; the suite only reads it. The format it understands is a table whose first cell is a
mark — `[ ]` to do · `[~]` started · `[x] <date>` done · `[!]` waiting on the owner — then the build's number, where it
runs, its title, what it needs and its size:

    | [x] 2026-11-10 | 01 | SUITE | Foundations | — | 1 |

A started build's **Progress** line is read from its own file (`BUILD_<nn>_*.md`, the line starting `**Progress`), and a
waiting build's reason from the text after the mark (`[!] his ruling on the towns`). Nothing here names a game.
"""
from __future__ import annotations
import re
from pathlib import Path

ROW = re.compile(r"^\|\s*\[(?P<m>[ x~!])\]\s*(?P<after>[^|]*)\|\s*(?P<n>\d{1,3})\s*\|\s*(?P<where>[^|]*)\|\s*(?P<title>[^|]*)\|\s*(?P<needs>[^|]*)\|\s*(?P<size>[^|]*)\|")
MARKS = {"x": "x", "~": "~", "!": "!", " ": " "}


def _plain(s: str) -> str:
    return re.sub(r"\*\*|\*|`", "", str(s)).strip()


def read(queue: Path, builds_dir: Path | None = None) -> list[dict]:
    queue = Path(queue)
    if not queue.is_file():
        return []
    builds_dir = Path(builds_dir) if builds_dir else queue.parent
    out = []
    for line in queue.read_text(encoding="utf-8", errors="replace").splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        mark = MARKS[m.group("m")]
        after = m.group("after").strip()
        n = m.group("n").zfill(2)
        b = {"n": n, "mark": mark, "where": _plain(m.group("where")), "title": _plain(m.group("title")),
             "needs": _plain(m.group("needs")), "size": _plain(m.group("size")),
             "done_on": after if mark == "x" else None, "waiting_for": (after or None) if mark == "!" else None,
             "progress": None, "file": None}
        f = next(iter(sorted(builds_dir.glob(f"BUILD_{n}_*.md"))), None)
        if f:
            b["file"] = f.name
            if mark in ("~", "!"):
                for l in f.read_text(encoding="utf-8", errors="replace").splitlines()[:12]:
                    if l.startswith("**Progress"):
                        b["progress"] = _plain(l)[:600]
                        break
        out.append(b)
    return out
