"""commit_check — keep games and people out of RPG_Forge's commit messages (2026-11-21).

RPG_Forge is a tool for making games, and its history is public: a commit message says what the forge can now do — never
which game it was for, and never who asked, who wrote it or who ran it (no names, no quotes, no Co-Authored-By lines).
push.bat runs this on the message before it commits; a message that names a game or a person stops the push.

    python -m forge.commit_check COMMIT_MESSAGE.txt      exit 0 = clean, 1 = names a game (the lines are printed)
    python -m forge.commit_check --text "one line"
    python -m forge.commit_check --words                 every word it looks for, and where each came from

What it looks for, for every game folder in games/ except _example:
  - the game's id and its folder paths (games/<id>/, local/<id>/), in either slash direction;
  - the adapter's display name, and the names of its places and people (when the adapter loads on this PC);
  - games/<id>/private_words.txt — one word or phrase a line (# starts a comment), for anything else to keep out.
    A line starting with "!" ALLOWS that word instead (a false alarm you want to let through).
And for people, from this PC: every game's "owner" (forge.game.json), the suite identity (local/suite.json), git's
user.name and user.email, the GitHub account in the origin URL, local/private_words.txt (personal words, one a line,
never pushed), the assistants' names and attribution lines (Co-Authored-By, Claude-Session).
Matching ignores case. Words shorter than 4 letters are skipped (too many false alarms).
Nothing here names a game: the words all come from the games on this PC.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def words() -> dict[str, str]:
    """{word: where it came from}."""
    found: dict[str, str] = {}
    gdir = ROOT / "games"
    if not gdir.is_dir():
        return found
    allowed = set()
    for d in gdir.iterdir():
        pw = d / "private_words.txt"
        if pw.is_file():
            for line in pw.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if line.startswith("!") and line[1:].strip():
                    allowed.add(line[1:].strip().lower())

    def person(w, why):
        w = (w or "").strip()
        if len(w) >= 3 and w.lower() not in allowed and w.lower() not in (k.lower() for k in found):
            found[w] = why

    import json
    import subprocess
    for w in ("Co-Authored-By", "Claude-Session", "Claude Fable", "Claude Opus", "Fable", "Opus"):
        person(w, "an author or attribution")
    try:
        person(json.loads((ROOT / "local" / "suite.json").read_text(encoding="utf-8")).get("identity"), "this PC's identity")
    except Exception:  # noqa: BLE001
        pass
    for d in gdir.iterdir():
        try:
            person(json.loads((d / "forge.game.json").read_text(encoding="utf-8")).get("owner"), f"{d.name}: its owner")
        except Exception:  # noqa: BLE001
            pass
    for key in ("user.name", "user.email"):
        try:
            v = subprocess.run(["git", "config", key], capture_output=True, text=True, cwd=ROOT).stdout.strip()
            if v and "noreply" not in v:
                person(v, f"git {key}")
                if "@" in v:
                    person(v.split("@")[0], f"git {key}")
        except Exception:  # noqa: BLE001
            pass
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, cwd=ROOT).stdout
        m = re.search(r"github\.com[/:]([^/]+)/", url)
        if m:
            person(m.group(1), "the GitHub account")
    except Exception:  # noqa: BLE001
        pass
    lp = ROOT / "local" / "private_words.txt"
    if lp.is_file():
        for line in lp.read_text(encoding="utf-8").splitlines():
            person(line.split("#", 1)[0], "local/private_words.txt")

    def add(w, why):
        w = (w or "").strip()
        if w.startswith("!") or w.lower() in allowed:
            return
        for v in {w, w.replace(" ", "_")}:      # "Linden Mills" is also linden_mills in file and id names
            if len(v) >= 4 and v.lower() not in (k.lower() for k in found):
                found[v] = why

    for d in sorted(p for p in gdir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        gid = d.name
        add(gid, f"{gid}: the game's id")
        add(gid.replace("_", " "), f"{gid}: the game's id")
        for pre in ("games", "local"):
            found[f"{pre}/{gid}"] = f"{gid}: its folder"
        pw = d / "private_words.txt"
        if pw.is_file():
            for line in pw.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0]
                add(line, f"{gid}: private_words.txt")
        try:
            from . import config as cfgmod
            from .suite import games as gm
            a = gm.adapter(cfgmod.load(), gid)
            add(getattr(a, "name", ""), f"{gid}: the adapter's name")
            add(re.sub(r"^the\s+", "", getattr(a, "name", ""), flags=re.I), f"{gid}: the adapter's name")
            for p in a.places():
                add(getattr(p, "name", ""), f"{gid}: a place")
            for p in a.people():
                add(getattr(p, "name", ""), f"{gid}: a person")
        except Exception:  # noqa: BLE001 — the adapter may not load here (game folder elsewhere); the rest still counts
            pass
    return found


def check(text: str, ws: dict[str, str] | None = None) -> list[tuple[int, str, str]]:
    ws = words() if ws is None else ws
    norm = text.replace("\\", "/")
    out = []
    pats = [(w, why, re.compile(r"(?<![A-Za-z0-9])" + re.escape(w.replace("\\", "/")) + r"(?![A-Za-z0-9])", re.I))
            for w, why in ws.items()]
    for n, line in enumerate(norm.splitlines(), 1):
        for w, why, rx in pats:
            if rx.search(line):
                out.append((n, w, why))
    return out


def main(argv: list[str]) -> int:
    if argv[:1] == ["--words"]:
        for w, why in words().items():
            print(f"{w!r:40} {why}")
        return 0
    if argv[:1] == ["--text"]:
        text = " ".join(argv[1:])
    elif argv:
        p = Path(argv[0])
        if not p.is_file():
            return 0
        text = p.read_text(encoding="utf-8", errors="replace")
    else:
        print(__doc__)
        return 2
    hits = check(text)
    if not hits:
        return 0
    lines = text.replace("\\", "/").splitlines()
    print("This commit message names a game or a person. RPG_Forge's history says only what the forge can do.")
    print("Describe what changed in the FORGE (code, tools, docs). No game, no names, no quotes, no Co-Authored-By.\n")
    seen = set()
    for n, w, why in hits:
        if n in seen:
            continue
        seen.add(n)
        names = sorted({h[1] for h in hits if h[0] == n})
        print(f"  line {n}: {lines[n-1][:150]}")
        print(f"           names: {', '.join(names)}  ({why})")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
