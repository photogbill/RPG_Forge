"""The Music board and composing together (BUILD 06 — suite spec, BUILD_06 file in the game folder).

The suite knows **slots, sheets, briefs and states**; the game's adapter says where they live (`music_paths()`), where a
delivered track goes (`deliver_target()`), how the game's music data points at it (`music_set_file()`) and where a
confirmed lyric is filed (`lyric_target()`). Nothing of a game's music — sheets, briefs, lyrics, audio — is ever
written into this repository.

A slot's **state** walks  needed → proposed → agreed → written → delivered → in game.
- needed / in game / "written" for a song that already exists come from the game itself (the adapter's slots);
- proposed / agreed / written / delivered are the board's record (`<game>/music/board.json` by default), one entry per
  slot: its history, the brief and its letter, every version of the song (who wrote it), and the delivery;
- the board never goes backwards past what the game reports: a slot the game already plays is "in game".

The rules (spec D): a session proposes and drafts; it never marks its own lyric approved, never delivers, and never
replaces a delivered track — a delivered slot is **cemented**: by whom and when are recorded, and from then on only a
person can change its audio. No lyric is drafted before the owner (the adapter's `owner`) says yes: writing needs the
slot `agreed` (a person may write whenever they like — their words are theirs). A slot the owner keeps ("I'll write
this one") is `own` and no session touches it. Every change is journaled and signed.

The answer to a brief comes back through the Mail: the brief's letter carries one question whose answer is written
to the slot's `verdict` in the board file (the Mail's own applies_to path), and the board reads the verdict.
"""
from __future__ import annotations
import difflib, hashlib, json, os, re
from datetime import datetime
from pathlib import Path

from ..log import get
from . import journal, mail, settings

log = get("suite")

STATES = ("needed", "proposed", "agreed", "written", "delivered", "in game")
VERDICTS = {"yes": "agreed", "yes, but…": "agreed", "no": "needed", "I'll write this one": "needed", "not yet": "proposed"}
VERDICT_CHOICES = list(VERDICTS)
AUDIO_EXT = (".ogg", ".mp3", ".wav", ".flac", ".m4a", ".opus")
AUDIO_MIME = {".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac", ".m4a": "audio/mp4",
              ".opus": "audio/ogg"}
OPEN = "open"


class MusicRefused(ValueError):
    """The rule said no; nothing was written. The message says why in plain words."""


def slug(s: str, n: int = 60) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower().replace("’", "").replace("'", "")).strip("-")[:n].strip("-") or "slot"


def _now() -> datetime:
    return settings.now()


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _o(adp) -> str:
    return getattr(adp, "owner", None) or "the owner"


def is_person(who: str | None) -> bool:
    return bool(who) and not settings.is_assistant(who)


# ---------------------------------------------------------------- files
def paths(adp) -> dict:
    p = {"board": "music/board.json", "styles": "music/styles", "songs": "music/songs", "briefs": "music/briefs",
         "inbox": "score_inbox", "audio": "music/audio"}
    fn = getattr(adp, "music_paths", None)
    if fn:
        p.update(fn() or {})
    return p


def write_bytes(p: Path, data: bytes) -> None:
    """Write a whole file so a reader never sees half of it: temp + replace; where the drive refuses a replace (a
    session's shell on a folder that forbids deleting), the file is rewritten in place instead."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, p)
        return
    except OSError:
        pass
    with open(p, "r+b" if p.exists() else "wb") as f:
        f.write(data)
        f.truncate()


def _write_json(p: Path, d) -> None:
    write_bytes(p, (json.dumps(d, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


def load_board(adp) -> dict:
    p = adp.root / paths(adp)["board"]
    if not p.is_file():
        return {"slots": {}, "extra": []}
    d = json.loads(p.read_text(encoding="utf-8-sig") or "{}")
    d.setdefault("slots", {})
    d.setdefault("extra", [])
    return d


def save_board(adp, d: dict) -> None:
    d["_comment"] = ("The Music board's record (RPG_Forge suite, BUILD 06): per slot its state history, brief, song versions "
                     "and delivery. Written by the suite and by sessions through forge/suite/music.py; a slot's 'verdict' is "
                     "the owner's answer to its brief, written by the Mail.")
    _write_json(adp.root / paths(adp)["board"], dict(sorted(d.items(), key=lambda kv: kv[0] != "_comment")))


def _entry(board: dict, sid: str) -> dict:
    return board["slots"].setdefault(sid, {})


def _push(e: dict, who: str, frm: str | None, to: str, note: str, now: datetime) -> None:
    e.setdefault("history", []).append({"time": _iso(now), "who": who, "from": frm, "to": to, "note": note})
    e["state"] = to


# ---------------------------------------------------------------- the slots, merged with the board
def _game_slots(adp) -> list[dict]:
    from .adapter import as_dict
    out = []
    for s in adp.music_slots():
        d = as_dict(s)
        d["game_status"] = d.get("status")
        out.append(d)
    return out


def _effective(e: dict, game_status: str | None) -> str:
    st = e.get("state")
    v = e.get("verdict")
    if st == "proposed" and v in VERDICTS:
        st = VERDICTS[v]
    derived = {"in game": "in game", "written": "written"}.get(game_status or "", "needed")
    if game_status == "inherits" and not st:
        return "inherits"
    if not st:
        return derived
    if st in STATES and derived in STATES and STATES.index(derived) > STATES.index(st) and derived == "in game":
        return derived
    return st


def slots(adp, board: dict | None = None) -> list[dict]:
    board = board if board is not None else load_board(adp)
    out = _game_slots(adp)
    known = {s["id"] for s in out}
    for x in board.get("extra") or []:
        if x.get("id") in known:
            continue
        out.append({"id": x["id"], "ref": f"{paths(adp)['board']}#/extra", "purpose": x.get("purpose", ""), "scene": x.get("title", ""),
                    "kind": "opened", "vocal": x.get("vocal"), "singers": x.get("singers") or [], "file": None, "file_exists": False,
                    "status": "needed", "game_status": "needed", "opened_by": x.get("by"), "place": x.get("place"), "era": x.get("era")})
    for s in out:
        e = board["slots"].get(s["id"], {})
        s["state"] = _effective(e, s.get("game_status"))
        s["own"] = bool(e.get("own")) or (e.get("verdict") == "I'll write this one")
        s["shares"] = e.get("shares")
        s["own_ruling"] = e.get("own_ruling")
        s["verdict"] = e.get("verdict")
        s["brief"] = e.get("brief")
        s["letter"] = e.get("letter")
        s["versions"] = e.get("versions") or []
        s["delivered"] = e.get("delivered")
        s["lyric"] = e.get("lyric")
        s["cemented"] = bool((e.get("delivered") or {}).get("cemented"))
        s["history"] = (e.get("history") or [])[-6:]
        s["credits"] = _credits(e)
    by_id = {s["id"]: s for s in out}
    for s in out:
        src = by_id.get(s.get("shares") or "")
        if src:
            s["via"] = src["id"]
            s["state"] = src["state"]
    return out


def _credits(e: dict) -> list[dict]:
    c = []
    if e.get("brief_by"):
        c.append({"what": "brief", "by": e["brief_by"]})
    for v in e.get("versions") or []:
        c.append({"what": f"song v{v.get('n')}", "by": v.get("by")})
    if e.get("delivered"):
        c.append({"what": "the track", "by": e["delivered"].get("by")})
    return c


def find(adp, sid: str, board: dict | None = None) -> dict:
    for s in slots(adp, board):
        if s["id"] == sid:
            return s
    raise MusicRefused(f"there is no music slot '{sid}'")


def counts(ss: list[dict]) -> dict:
    c = {k: 0 for k in STATES}
    for s in ss:
        if s["state"] in c:
            c[s["state"]] += 1
    c["own"] = sum(1 for s in ss if s.get("own"))
    c["inherits"] = sum(1 for s in ss if s["state"] == "inherits")
    c["total"] = len(ss)
    return c


def next_useful(ss: list[dict], n: int = 5) -> list[dict]:
    """The needed work that fills the most of the board: slots that would all play one track are one piece of work;
    the system tracks (the menu, the road, the default fight) are heard most. The owner's own and shared slots are skipped."""
    groups: dict = {}
    for s in ss:
        if s["state"] != "needed" or s.get("own") or s.get("via"):
            continue
        key = s.get("track") or s.get("file") or s["id"]
        groups.setdefault(key, []).append(s)
    rows = []
    for key, g in groups.items():
        w = 3 if any(x.get("kind") == "system" for x in g) else 1
        first = g[0]
        if len(g) > 1:
            why = f"one track fills {len(g)} slots — " + "; ".join(x.get("scene") or x["id"] for x in g[:4]) + ("…" if len(g) > 4 else "")
        else:
            why = first.get("purpose") or first.get("scene") or ""
        rows.append({"id": first["id"], "slots": [x["id"] for x in g], "score": len(g) * w, "why": why,
                     "scene": first.get("scene") or first["id"], "vocal": first.get("vocal"), "track": first.get("track")})
    rows.sort(key=lambda r: (-r["score"], r["scene"]))
    return rows[:n]


def _norm(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).split())


def guess(name: str, ss: list[dict]) -> dict | None:
    """Which slot an inbox file most likely fills, by its name against each slot's file, track, id and scene."""
    stem = _norm(Path(name).stem)
    best = None
    for s in ss:
        if s.get("cemented"):
            continue
        cands = [s.get("track"), Path(str(s.get("file") or "")).stem, s["id"].split(":")[-1], s.get("scene")]
        for c in cands:
            c = _norm(c)
            if not c:
                continue
            r = 1.0 if c == stem else difflib.SequenceMatcher(None, stem, c).ratio()
            if best is None or r > best["score"]:
                best = {"id": s["id"], "score": round(r, 2), "scene": s.get("scene") or s["id"], "matched": c}
    return best if best and best["score"] >= 0.55 else None


def inbox(adp, ss: list[dict] | None = None, board: dict | None = None) -> list[dict]:
    board = board if board is not None else load_board(adp)
    ss = ss if ss is not None else slots(adp, board)
    d = adp.root / paths(adp)["inbox"]
    if not d.is_dir():
        return []
    used = {}
    for sid, e in board["slots"].items():
        dv = e.get("delivered") or {}
        if dv.get("sha256"):
            used[dv["sha256"]] = sid
    out = []
    for p in sorted(d.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file() or p.suffix.lower() not in AUDIO_EXT:
            continue
        st = p.stat()
        h = _sha(p.read_bytes()) if st.st_size < 400_000_000 else ""
        out.append({"name": p.name, "bytes": st.st_size, "delivered_to": used.get(h), "guess": None if used.get(h) else guess(p.name, ss)})
    return out


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def board(adp) -> dict:
    b = load_board(adp)
    ss = slots(adp, b)
    singers = sorted({g.get("name") for s in ss for g in (s.get("singers") or []) if g.get("name") and g.get("name") != "ask"})
    return {"slots": ss, "counts": counts(ss), "next": next_useful(ss), "inbox": inbox(adp, ss, b),
            "filters": {"places": sorted({s["place"] for s in ss if s.get("place")}), "eras": sorted({s["era"] for s in ss if s.get("era")}),
                        "singers": singers, "states": list(STATES)},
            "sheets": sheets(adp), "paths": paths(adp), "owner": _o(adp),
            "verdicts": VERDICT_CHOICES}


def briefs_and_songs(adp) -> list[dict]:
    """Every brief and every song version, newest first, with who wrote it and the slot it's for (BUILD 26, Music →
    Briefs & songs). All of it read from the board's record — nothing new is stored."""
    b = load_board(adp)
    scenes = {}
    try:
        scenes = {s["id"]: s.get("scene") or s["id"] for s in slots(adp, b)}
    except Exception:  # noqa: BLE001 — a game whose slots can't be read still shows its record
        pass
    out = []
    for sid, e in (b.get("slots") or {}).items():
        if e.get("brief"):
            at = next((h["time"] for h in e.get("history") or [] if h.get("to") == "proposed"), None)
            out.append({"what": "brief", "slot": sid, "scene": scenes.get(sid, sid), "by": e.get("brief_by"), "at": at,
                        "file": e["brief"], "style": e.get("style"), "letter": e.get("letter"), "verdict": e.get("verdict")})
        for v in e.get("versions") or []:
            out.append({"what": f"song v{v.get('n')}", "slot": sid, "scene": scenes.get(sid, sid), "by": v.get("by"),
                        "at": v.get("at"), "file": v.get("file"), "title": v.get("title"), "note": v.get("note")})
        if e.get("lyric"):
            ly = e["lyric"] if isinstance(e["lyric"], dict) else {"file": e["lyric"]}
            out.append({"what": "words as sung", "slot": sid, "scene": scenes.get(sid, sid), "by": ly.get("by"),
                        "at": ly.get("at"), "file": ly.get("file"), "title": ly.get("title")})
    out.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    return out


# ---------------------------------------------------------------- style sheets (B / B2)
def sheets(adp) -> list[dict]:
    d = adp.root / paths(adp)["styles"]
    out = []
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            s = json.loads(p.read_text(encoding="utf-8-sig"))
        except ValueError:
            continue
        out.append({"id": s.get("id") or p.stem, "name": s.get("name") or p.stem, "kind": s.get("kind", "character"),
                    "open": len(open_spots(s)), "styles": len(s.get("styles") or []), "songs": len(s.get("songs") or [])})
    return out


def sheet(adp, sheet_id: str) -> dict:
    p = adp.root / paths(adp)["styles"] / f"{slug(sheet_id)}.json"
    if not p.is_file():
        raise MusicRefused(f"there is no style sheet '{sheet_id}'")
    s = json.loads(p.read_text(encoding="utf-8-sig"))
    s["_open"] = open_spots(s)
    return s


def sheet_for(adp, name: str) -> dict | None:
    try:
        return sheet(adp, name)
    except MusicRefused:
        return None


def is_open(v) -> bool:
    return isinstance(v, dict) and bool(v.get(OPEN))


def open_spots(s, pointer: str = "") -> list[dict]:
    """Every open spot in a sheet: [{pointer, question, asked}]."""
    out = []
    if is_open(s):
        return [{"pointer": pointer, "question": s.get("question", ""), "asked": s.get("asked", ""), "found": s.get("found", "")}]
    if isinstance(s, dict):
        for k, v in s.items():
            if not str(k).startswith("_"):
                out += open_spots(v, f"{pointer}/{k}")
    elif isinstance(s, list):
        for i, v in enumerate(s):
            out += open_spots(v, f"{pointer}/{i}")
    return out


def _spot(v) -> str:
    if v is None or v == "" or v == []:
        return "—"
    if is_open(v):
        return f"**open** — asked {v.get('asked') or '—'}" + (f" (found: {v['found']})" if v.get("found") else "")
    if isinstance(v, dict) and "value" in v:
        src = v.get("by") and f" — *{v['by']}*" or (v.get("source") and f" `[{v['source']}]`") or ""
        val = v["value"]
        return (", ".join(map(str, val)) if isinstance(val, list) else str(val)) + src
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return str(v)


def render_sheet(s: dict) -> str:
    """A profile as markdown, in the B2 order: the voice; style 1, 2, 3…; how their songs are built; style notes; open
    spots. The .json is the record; the .md is its readable view (rewritten whenever the .json changes)."""
    L = [f"# {s.get('name', s.get('id'))} — music profile", ""]
    L.append(f"*{s.get('kind', 'character')} · made by {s.get('made_by', '?')} {s.get('made', '')} from the evidence listed; "
             f"William's edits are his. {len(open_spots(s))} open spot(s).*")
    L += ["", "## 1. The voice — the constant", ""]
    v = s.get("voice") or {}
    for k, label in (("type", "Voice type and range"), ("delivery", "Delivery"), ("constant", "What stays the same whatever the genre"),
                     ("changes", "Where the voice changes over time")):
        L.append(f"- **{label}:** {_spot(v.get(k))}")
    for i, st in enumerate(s.get("styles") or [], 1):
        if is_open(st):
            L += ["", f"## 2.{i} Style {i} — {_spot(st)}", "", f"*{st.get('question', '')}*"]
            continue
        L += ["", f"## 2.{i} Style {i} — {_spot(st.get('name'))}", ""]
        for k, label in (("genre", "Genre words"), ("instruments", "Instruments"), ("tempo", "Tempo"), ("metre", "Metre"),
                         ("suno_input", "Suno style input (as used)"), ("when", "When they use it"), ("example", "Example song")):
            val = st.get(k)
            if k == "suno_input" and isinstance(val, dict) and val.get("value"):
                L.append(f"- **{label}:** `[{val.get('source', '')}]`")
                L.append(f"  ```\n  {val['value']}\n  ```")
            else:
                L.append(f"- **{label}:** {_spot(val)}")
    if s.get("styles_note"):
        L += ["", f"*About these styles:* {_spot(s['styles_note'])}"]
    if is_open(s.get("styles_split")):
        L += ["", f"*Whether these are separate styles:* {_spot(s['styles_split'])}"]
    b = s.get("built") or {}
    L += ["", "## 3. How their songs are built", ""]
    for o in b.get("observations") or []:
        fr = o.get("from") or []
        fr_s = ", ".join(fr) if len(fr) <= 6 else f"{len(fr)} songs — {', '.join(fr[:3])} …"
        L.append(f"- {o.get('text')}" + (f" *(from: {fr_s})*" if fr else ""))
    if b.get("returns_to"):
        L.append("- **Words they come back to:** " + "; ".join(f"{w['word']} ({len(w['songs'])} songs)" for w in b["returns_to"]))
    L.append(f"- **Words they never use:** {_spot(b.get('never'))}")
    if s.get("motifs"):
        L += ["", "**Motifs** (a phrase in more than one of their songs; first carried by):", ""]
        for m in s["motifs"]:
            L.append(f"- “{m['phrase']}” — first in *{m['first']}*; also {', '.join(m['songs'][1:])}")
    if s.get("lines"):
        L += ["", "**Lines that are most them** (by reference):", ""]
        for x in s["lines"]:
            L.append(f"- *{x['title']}* line {x['line']}: “{x['text']}” `[{x['file']}]`")
    L += ["", "## 4. Style notes", "", _spot(s.get("notes")) if s.get("notes") else "*(William's to write.)*"]
    L += ["", "## The songs, in story order", ""]
    for x in s.get("songs") or []:
        bits = [x.get("album") or "", x.get("tempo") and f"{x['tempo']}" or "", x.get("key") or "",
                "Suno input on disk" if x.get("suno") else ""]
        L.append(f"- *{x['title']}* — " + " · ".join(b for b in bits if b) + (f" `[{x['lyrics']}]`" if x.get("lyrics") else ""))
    if s.get("slots"):
        L += ["", "**Slots on the Music board that name them:** " + "; ".join(s["slots"])]
    if s.get("suno_craft"):
        L += ["", "## Suno craft notes (written down — William's rules, with where)", ""]
        for c in s["suno_craft"] if isinstance(s["suno_craft"], list) else []:
            L.append(f"- {_spot(c)}")
        if is_open(s["suno_craft"]):
            L.append(f"- {_spot(s['suno_craft'])}")
    ops = open_spots(s)
    L += ["", "## 5. Open spots", ""]
    L += [f"- `{o['pointer']}` — {o['question'] or 'open'} (asked {o['asked'] or '—'})" for o in ops] or ["*None.*"]
    if s.get("evidence"):
        L += ["", "## Evidence read", ""] + [f"- {e}" for e in s["evidence"]]
    return "\n".join(L) + "\n"


def save_sheet(adp, s: dict) -> None:
    s = {k: v for k, v in s.items() if not k.startswith("_")}
    d = adp.root / paths(adp)["styles"]
    sid = slug(s.get("id") or s.get("name"))
    _write_json(d / f"{sid}.json", s)
    write_bytes(d / f"{sid}.md", render_sheet(s).encode("utf-8"))


def fill_spot(adp, sheet_id: str, pointer: str, value, who: str, now: datetime | None = None) -> dict:
    """A person fills (or rewrites) one part of a profile — an open spot, the style notes, a style's 'when'. The value is
    theirs: {value, by, at}. A session proposes in a letter instead."""
    now = now or _now()
    if not is_person(who):
        raise MusicRefused("profiles are William's to change — a session asks in a letter (an open spot) instead")
    from .jsondoc import split_pointer
    s = sheet(adp, sheet_id)
    parts = split_pointer(pointer)
    if not parts:
        raise MusicRefused("which part of the profile?")
    cur = s
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else cur.setdefault(p, {})
    last = parts[-1]
    before = cur[int(last)] if isinstance(cur, list) else cur.get(last)
    new = {"value": value, "by": who, "at": _iso(now)}
    if isinstance(cur, list):
        cur[int(last)] = new
    else:
        cur[last] = new
    save_sheet(adp, s)
    journal.append(adp.root, who, "music", f"{paths(adp)['styles']}/{slug(sheet_id)}.json#{pointer}", before=before, after=value,
                   note="profile edited", when=now)
    return {"ok": True, "message": f"Saved — that part of the {s.get('name')} profile is yours now."}


# ---------------------------------------------------------------- the loop: propose · answer · write · deliver
def propose(adp, sid: str, who: str, brief: str, style: str | None = None, subject: str | None = None,
            now: datetime | None = None, send: bool = True) -> dict:
    """A brief for a needed slot: kept in the game's briefs folder, sent to the owner as a letter with one question (go
    ahead?), the slot → proposed. A vocal slot's brief names the style it uses from the singer's profile (style-N) or
    proposes a new one (style='new'); a style still open in the profile can't carry a brief."""
    now = now or _now()
    if not who:
        raise MusicRefused("a brief is signed — set who you are first")
    b = load_board(adp)
    s = find(adp, sid, b)
    if s.get("own"):
        raise MusicRefused(f"{s.get('scene') or sid} is {_o(adp)}'s own — no session proposes for it")
    if s["cemented"]:
        raise MusicRefused(f"{s.get('scene') or sid} is delivered and cemented — write {_o(adp)} a letter if something should change")
    if s["state"] not in ("needed", "proposed") and not is_person(who):
        raise MusicRefused(f"{s.get('scene') or sid} is already {s['state']} — a new brief would go backwards")
    if not str(brief).strip():
        raise MusicRefused("the brief is empty")
    style_note = _check_style(adp, s, style)
    rel = f"{paths(adp)['briefs']}/{slug(sid)}.md"
    n = 1
    while (adp.root / rel).exists():
        n += 1
        rel = f"{paths(adp)['briefs']}/{slug(sid)}.v{n}.md"
    head = (f"# Brief — {s.get('scene') or sid}\n\n*Slot `{sid}` · by {who}, {now:%Y-%m-%d %H:%M} · {style_note}*\n\n")
    write_bytes(adp.root / rel, (head + str(brief).strip() + "\n").encode("utf-8"))
    e = _entry(b, sid)
    frm = s["state"]
    e["brief"], e["brief_by"], e["style"] = rel, who, style
    e.pop("verdict", None)
    letter = None
    if send:
        owner = _o(adp)
        q = [{"id": "verdict", "question": f"The brief for “{s.get('scene') or sid}” — go ahead?", "choices": VERDICT_CHOICES,
              "applies_to": {"file": paths(adp)["board"], "pointer": "/slots/" + sid.replace("~", "~0").replace("/", "~1") + "/verdict"}}]
        _push(e, who, frm, "proposed", f"brief {rel}", now)
        save_board(adp, b)
        l = mail.send(adp.root, who, owner, subject or f"Music brief — {s.get('scene') or sid}",
                      str(brief).strip() + f"\n\n---\nThe brief is kept at `{rel}`. Answer below — **yes** / **yes, but…** "
                      "(say what in your reply) / **no** / **I'll write this one** / **not yet**. No lyric is drafted before a yes.\n\n"
                      f"[Open its row on the board](#music/needed/{sid})",
                      questions=q, attachments=[rel], when=now)
        letter = l.id
        e["letter"] = l.id
    else:
        _push(e, who, frm, "proposed", f"brief {rel} (no letter)", now)
    save_board(adp, b)
    journal.append(adp.root, who, "propose", f"music:{sid}", before=frm, after="proposed", link=rel,
                   note=f"brief{' sent as ' + letter if letter else ''}; {style_note}", when=now)
    return {"ok": True, "message": f"Brief sent to {_o(adp)} — the slot is proposed.", "brief": rel, "letter": letter}


def _check_style(adp, s: dict, style: str | None) -> str:
    names = [g.get("name") for g in (s.get("singers") or []) if g.get("name") and g.get("name") != "ask"]
    vocal = s.get("vocal")
    if vocal is False or vocal == "instrumental":
        return f"instrumental{' · style ' + style if style else ''}"
    if not style:
        raise MusicRefused("a song's brief names which style of the singer it uses (style-1, style-2 …) or proposes a new one (new)")
    if style == "new":
        return f"proposes a new style (joins the profile only if {_o(adp)} agrees)"
    for n in names:
        sh = sheet_for(adp, n)
        if not sh:
            continue
        for i, st in enumerate(sh.get("styles") or [], 1):
            if style in (f"style-{i}", st.get("id")):
                if any(is_open(st.get(k)) for k in ("name", "genre", "suno_input")) or is_open(st):
                    raise MusicRefused(f"{n}'s {style} is still open in the profile — a brief can't be proposed in it until {_o(adp)} says what it is")
                return f"{n}'s {style} ({_spot(st.get('name'))})"
        raise MusicRefused(f"{n}'s profile has no {style}")
    raise MusicRefused("none of this slot's singers has a profile yet — make the profile first (or propose a new style: new)")


def answer(adp, sid: str, who: str, verdict: str, note: str = "", now: datetime | None = None) -> dict:
    """The owner's answer to a brief, from the board (the Mail writes the same field). Only a person answers."""
    now = now or _now()
    if not is_person(who):
        raise MusicRefused("only a person answers a brief — a session can't agree with itself")
    if verdict not in VERDICTS:
        raise MusicRefused(f"the answer is one of: {', '.join(VERDICT_CHOICES)}")
    b = load_board(adp)
    s = find(adp, sid, b)
    e = _entry(b, sid)
    frm = s["state"]
    e["verdict"] = verdict
    to = VERDICTS[verdict]
    if verdict == "I'll write this one":
        e["own"] = True
    _push(e, who, frm, to, f"answered '{verdict}'" + (f": {note}" if note else ""), now)
    e.pop("verdict", None) if verdict in ("no", "I'll write this one") else None
    save_board(adp, b)
    journal.append(adp.root, who, "music", f"music:{sid}", before=frm, after=to, note=f"answer: {verdict}" + (f" — {note}" if note else ""), when=now)
    return {"ok": True, "message": {"agreed": "Agreed — the song can be written now.", "needed": "Back to needed.",
                                    "proposed": "Still proposed — not yet."}[to] + (" It's theirs; no session will touch it." if e.get("own") else "")}


def write_song(adp, sid: str, who: str, title: str, text: str, note: str = "", now: datetime | None = None) -> dict:
    """A version of the song (a Suno-ready file: style input, then the lyrics with section tags; notes after). Every
    version is kept. A session writes only an agreed slot that isn't the owner's own; a person writes whenever they like."""
    now = now or _now()
    if not who:
        raise MusicRefused("a song is signed — set who you are first")
    b = load_board(adp)
    s = find(adp, sid, b)
    person = is_person(who)
    if not person:
        if s.get("own"):
            raise MusicRefused(f"{s.get('scene') or sid} is {_o(adp)}'s own — no session writes it")
        if s["cemented"]:
            raise MusicRefused(f"{s.get('scene') or sid} is delivered — a delivered lyric is never changed by a session")
        if s["state"] not in ("agreed", "written"):
            raise MusicRefused(f"no lyric before {_o(adp)} says yes — {s.get('scene') or sid} is {s['state']}")
    if not str(text).strip() or not str(title).strip():
        raise MusicRefused("a song needs a title and its words")
    e = _entry(b, sid)
    vs = e.setdefault("versions", [])
    n = len(vs) + 1
    rel = f"{paths(adp)['songs']}/{slug(sid)}/{slug(title, 50)}.v{n}.md"
    write_bytes(adp.root / rel, (str(text).rstrip() + "\n").encode("utf-8"))
    vs.append({"n": n, "file": rel, "title": title, "by": who, "at": _iso(now), "note": note})
    frm = s["state"]
    to = frm if frm in ("delivered", "in game") else "written"
    _push(e, who, frm, to, f"song v{n} by {who}", now)
    save_board(adp, b)
    journal.append(adp.root, who, "music", f"music:{sid}", before=frm, after=to, link=rel, note=f"“{title}” v{n}" + (f" — {note}" if note else ""), when=now)
    return {"ok": True, "message": f"“{title}” v{n} is kept — the slot is {to}.", "file": rel, "version": n}


def _target(adp, s: dict, ext: str) -> str:
    fn = getattr(adp, "deliver_target", None)
    rel = fn(s, ext) if fn else None
    return rel or f"{paths(adp)['audio']}/{slug(s['id'])}{ext}"


def deliver(adp, sid: str, who: str, data: bytes | None = None, filename: str = "", inbox_name: str | None = None,
            loop_start: float | None = None, loop_end: float | None = None, trim_db: float | None = None,
            now: datetime | None = None) -> dict:
    """The owner drops a finished track on a row (or picks one from the inbox): copied into the game under the slot's file
    name, the music data pointed at it, and the slot **cemented** — delivered, by whom, when. Only a person delivers;
    a person may deliver again (the old file is backed up first)."""
    from . import safesave
    now = now or _now()
    if not is_person(who):
        raise MusicRefused("delivering a track is a person's — a session can only propose")
    if inbox_name:
        src = (adp.root / paths(adp)["inbox"] / Path(inbox_name).name)
        if not src.is_file():
            raise MusicRefused(f"{inbox_name} isn't in the inbox")
        data, filename = src.read_bytes(), src.name
    if not data:
        raise MusicRefused("the dropped file was empty")
    ext = Path(filename).suffix.lower()
    if ext not in AUDIO_EXT:
        raise MusicRefused(f"{filename}: not an audio file the game can play ({', '.join(AUDIO_EXT)})")
    b = load_board(adp)
    s = find(adp, sid, b)
    rel = _target(adp, s, ext)
    target = adp.path(rel)
    backup = None
    if target.is_file():
        old = target.read_bytes()
        if old == data:
            backup = "(same file)"
        else:
            backup = safesave._backup(adp, rel, old, now)
    if backup != "(same file)":
        write_bytes(target, data)
    msg = None
    fn = getattr(adp, "music_set_file", None)
    if fn:
        msg = fn(s, rel, who, loop_start=loop_start, loop_end=loop_end, trim_db=trim_db)
    e = _entry(b, sid)
    frm = s["state"]
    was = e.get("delivered")
    e["delivered"] = {"file": rel, "bytes": len(data), "sha256": _sha(data), "by": who, "at": _iso(now), "source": filename,
                      "loop_start": loop_start, "loop_end": loop_end, "trim_db": trim_db, "cemented": True}
    if was:
        e.setdefault("earlier_deliveries", []).append(was)
    _push(e, who, frm, "delivered", f"{filename} → {rel}", now)
    save_board(adp, b)
    journal.append(adp.root, who, "deliver", f"music:{sid}", before=(was or {}).get("file"), after=rel, link=backup if backup and backup != "(same file)" else None,
                   note=f"{filename} delivered and cemented" + (f"; {msg}" if msg else ""), when=now)
    st = find(adp, sid)["state"]
    return {"ok": True, "message": f"Delivered — {filename} is the track for {s.get('scene') or sid}, cemented to it."
            + (" The game already plays it." if st == "in game" else " A build wires it to its scene next.") + (f" ({msg})" if msg else ""),
            "file": rel, "state": st, "backup": backup}


def set_audio(adp, sid: str, who: str, loop_start: float | None = None, loop_end: float | None = None, trim_db: float | None = None,
              now: datetime | None = None) -> dict:
    """Loop points and volume trim of a delivered track (a person's — the track is cemented)."""
    now = now or _now()
    if not is_person(who):
        raise MusicRefused("the delivered track is cemented — a session can only propose a change")
    b = load_board(adp)
    s = find(adp, sid, b)
    e = _entry(b, sid)
    dv = e.get("delivered")
    if not dv:
        raise MusicRefused("nothing delivered on this slot yet")
    if loop_start is not None and loop_end is not None and float(loop_end) <= float(loop_start):
        raise MusicRefused("the loop ends before it starts")
    before = {k: dv.get(k) for k in ("loop_start", "loop_end", "trim_db")}
    dv.update(loop_start=loop_start, loop_end=loop_end, trim_db=trim_db)
    fn = getattr(adp, "music_set_file", None)
    msg = fn(s, dv["file"], who, loop_start=loop_start, loop_end=loop_end, trim_db=trim_db) if fn else None
    save_board(adp, b)
    journal.append(adp.root, who, "music", f"music:{sid}", before=before, after={"loop_start": loop_start, "loop_end": loop_end, "trim_db": trim_db},
                   note="loop / trim" + (f"; {msg}" if msg else ""), when=now)
    return {"ok": True, "message": "Loop and trim saved." + (f" ({msg})" if msg else "")}


def confirm_lyric(adp, sid: str, who: str, text: str, title: str = "", now: datetime | None = None) -> dict:
    """The words as delivered (the owner may have changed some), confirmed by them — only then filed into the game's
    lyric data, where they are canon and locked. An existing lyric file is never overwritten."""
    now = now or _now()
    if not is_person(who):
        raise MusicRefused("only a person confirms the words as delivered")
    b = load_board(adp)
    s = find(adp, sid, b)
    if s["state"] not in ("delivered", "in game"):
        raise MusicRefused("deliver the track first — the lyric is filed as delivered")
    if not str(text).strip():
        raise MusicRefused("the lyric is empty")
    title = title or (s["versions"][-1]["title"] if s["versions"] else s.get("scene") or sid)
    fn = getattr(adp, "lyric_target", None)
    rel = (fn(s, title) if fn else None) or f"{paths(adp)['songs']}/{slug(sid)}/as_delivered.txt"
    p = adp.path(rel)
    if p.exists():
        raise MusicRefused(f"{rel} already exists — a filed lyric is canon and never overwritten here")
    write_bytes(p, (str(text).rstrip() + "\n").encode("utf-8"))
    e = _entry(b, sid)
    e["lyric"] = {"file": rel, "by": who, "at": _iso(now)}
    save_board(adp, b)
    journal.append(adp.root, who, "music", f"music:{sid}", after=rel, note=f"lyric of “{title}” confirmed as delivered and filed", when=now)
    return {"ok": True, "message": f"Filed — the words of “{title}” are canon now ({rel}).", "file": rel}


def share(adp, sid: str, who: str, other: str | None, now: datetime | None = None) -> dict:
    now = now or _now()
    if not is_person(who):
        raise MusicRefused("which slots share a theme is a person's call — propose it in a letter")
    b = load_board(adp)
    find(adp, sid, b)
    if other:
        if other == sid:
            raise MusicRefused("a slot can't share its own theme")
        o = find(adp, other, b)
        if o.get("shares"):
            raise MusicRefused(f"{other} itself shares another slot's theme — point at that one")
    e = _entry(b, sid)
    before = e.get("shares")
    if other:
        e["shares"] = other
    else:
        e.pop("shares", None)
    save_board(adp, b)
    journal.append(adp.root, who, "music", f"music:{sid}", before=before, after=other, note="shares the theme of" if other else "no longer shares a theme", when=now)
    return {"ok": True, "message": f"It shares the theme of {other} now." if other else "It has its own theme again."}


def hold(adp, sid: str, who: str, on: bool = True, now: datetime | None = None) -> dict:
    """The owner keeps a slot for themselves (or lets it go)."""
    now = now or _now()
    if not is_person(who):
        raise MusicRefused("only a person marks a slot as their own")
    b = load_board(adp)
    find(adp, sid, b)
    e = _entry(b, sid)
    e["own"] = bool(on)
    if not on and e.get("verdict") == "I'll write this one":
        e.pop("verdict")
    save_board(adp, b)
    journal.append(adp.root, who, "music", f"music:{sid}", after=f"{_o(adp)}'s own" if on else "open to sessions", when=now)
    return {"ok": True, "message": "Theirs now — no session will touch it." if on else "Open to sessions again."}


def record_own(adp, sid: str, who: str, ruling: str, now: datetime | None = None) -> dict:
    """Record a slot as the owner's own from a ruling of theirs that is written down ("Slots that are his alone are marked
    so from the start"). Anyone may record it — a session too — but only with the ruling quoted and where it is; only a
    person can release it again (hold(..., on=False))."""
    now = now or _now()
    if not str(ruling).strip() or "[" not in ruling and ":" not in ruling:
        raise MusicRefused("quote the ruling and say where it is written (file and line, or the date of the letter)")
    b = load_board(adp)
    s = find(adp, sid, b)
    e = _entry(b, sid)
    if e.get("own"):
        return {"ok": True, "message": f"{s.get('scene') or sid} is already {_o(adp)}'s own."}
    e["own"], e["own_ruling"] = True, str(ruling).strip()
    _push(e, who, s["state"], s["state"], f"{_o(adp)}'s own — {ruling}", now)
    save_board(adp, b)
    journal.append(adp.root, who, "music", f"music:{sid}", after=f"{_o(adp)}'s own", note=f"recorded from the ruling: {ruling}", when=now)
    return {"ok": True, "message": f"{s.get('scene') or sid} is {_o(adp)}'s own (from the ruling)."}


def open_slot(adp, who: str, title: str, purpose: str = "", vocal=None, singers=None, now: datetime | None = None) -> dict:
    """'I've had an idea for a song' — a blank slot of the owner's own joins the board."""
    now = now or _now()
    if not is_person(who):
        raise MusicRefused("a session proposes a slot in a letter; a person opens it")
    if not str(title).strip():
        raise MusicRefused("give it a working title")
    b = load_board(adp)
    sid = "opened:" + slug(title, 50)
    if any(x.get("id") == sid for x in b["extra"]) or any(s["id"] == sid for s in _game_slots(adp)):
        raise MusicRefused(f"there is already a slot called {title}")
    names = [n.strip() for n in (singers if isinstance(singers, list) else str(singers or "").split(",")) if str(n).strip()]
    b["extra"].append({"id": sid, "title": title, "purpose": purpose, "vocal": vocal, "singers": [{"name": n} for n in names],
                       "by": who, "at": _iso(now)})
    _push(_entry(b, sid), who, None, "needed", "opened", now)
    save_board(adp, b)
    journal.append(adp.root, who, "music", f"music:{sid}", after="needed", note=f"opened a slot: {title}", when=now)
    return {"ok": True, "message": f"“{title}” is on the board.", "id": sid}


def audio_file(adp, sid: str | None = None, inbox_name: str | None = None) -> Path:
    """The file to play for a row (its delivered track, else what the game points at) or an inbox file."""
    if inbox_name:
        p = adp.root / paths(adp)["inbox"] / Path(inbox_name).name
    else:
        s = find(adp, sid or "")
        dv = s.get("delivered") or {}
        rel = dv.get("file")
        p = adp.path(rel) if rel else None
        if (p is None or not p.is_file()) and s.get("file_exists"):
            fn = getattr(adp, "local_file", None)
            p = fn(s) if fn else None
        if p is None:
            raise FileNotFoundError(sid)
    if not p.is_file() or p.suffix.lower() not in AUDIO_EXT:
        raise FileNotFoundError(str(p))
    return p
