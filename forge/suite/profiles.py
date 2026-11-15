"""Character profiles (BUILD 42) — every character on one editable page, and a board that shows what is missing.

The owner's notebook for the cast: the place he writes a thing down the moment he thinks of it, and the place a session
looks first. It is not the game's balance data and it does not replace the game's canon document.

**Where they live.** One file per character in the *game's* folder — `<game>/<profiles_dir>/<id>.json` (default
`profiles/`), with `_schema.json` beside them. Outside the game's own data on purpose: a character of a later game can
have a profile without anything of theirs entering this one. `forge/` names no game: the schema is the game's, and the
page is drawn from it, so the next game defines its own page without a line of forge code.

**The five states** (the owner's rule: results coloured by how they were produced). Every entry of a *rows* section
(this game: Arms — up close · at range · other) carries one, the same colour everywhere:

    songs     a source line is quoted and its song named            (anyone may set it — with the quote)
    owner     the owner's word: he typed it or ruled it, with a date  (a person; a session only by citing his ruling)
    proposed  a session's suggestion he has not answered              (sessions)
    open      nobody knows yet                                        (anyone; an empty row is open)
    none      none, on purpose, with his reason                       (a person; a session only by citing his ruling)

Anything a person types becomes *owner* at once. A session may never set *owner* or *none* on its own: it may only
write down a ruling the owner made, recorded in the rulings book (rulings.py), by its id — the same rule as the book's.

**Saving** goes through the suite's safe path (safesave.save: temp → check → backup → atomic replace), with the
profile schema as the checker (never the game's data validator — a profile is not game data). Every change is one
journal line (kind "edit", so it reaches the digest, "while you were away"); an Arms entry a person sets or confirms is
also written into the rulings book. **Undo** puts back the version before your last change, if nobody changed the
file since. The profile never writes into the game's data: a confirmed weapon the game lacks becomes a work order.

Adapter hooks (all optional; games/_example/workbench_adapter.py shows each):
    profiles_dir() -> str                         the folder, relative to the game folder (default "profiles")
    profile_lyrics() -> [{song, singer, lines: [str], file}]   what "find it in the songs" searches
    profile_game_view(pid) -> {in_data, file, rows: {row: [{id, name}]}, says: str}   what the game's own data gives
    profile_links(pid) -> [{label, address | path, exists, note}]   body, 3D model, walk sheet … (read-only pointers)
    profile_voice(pid) -> {text, address} | None   the voice as the music profile has it; None → "ask <owner>"
    profile_seeds() -> [seed]                      what the first fill writes (see fill())
"""
from __future__ import annotations
import hashlib, json, os, re, secrets
from datetime import datetime
from pathlib import Path

from ..log import get
from . import journal, settings

log = get("suite")

STATES = ("songs", "owner", "proposed", "open", "none")
ASSISTANT_STATES = ("songs", "proposed", "open")           # what a session may set on its own
RANK = {"owner": 5, "songs": 4, "proposed": 3, "open": 1}   # the state a board cell shows when a row has several entries
DEFAULT_STATE_LOOK = {
    "songs": {"label": "in the songs", "color": "#4aa8ff"},
    "owner": {"label": "the owner's word", "color": "#f0b040"},
    "proposed": {"label": "proposed", "color": "#b58cff"},
    "open": {"label": "open", "color": "#ff6b6b"},
    "none": {"label": "none, on purpose", "color": "#8d8d99"},
}
DEFAULT_WEAPON_WORDS = ("sword", "blade", "knife", "knives", "dagger", "gun", "guns", "coilgun", "coil gun", "rifle",
                        "pistol", "sidearm", "revolver", "shotgun", "laser", "wire", "spear", "shield", "fist", "fists",
                        "claw", "claws", "whip", "bow", "arrow", "hammer", "axe", "cannon", "missile", "torch", "taser",
                        "gauntlet", "gauntlets", "uranium", "sabot", "rail", "railgun", "plasma", "emitter", "blaster")
SIMPLE_KINDS = ("text", "longtext", "list", "choice", "multi", "number")


class ProfileRefused(ValueError):
    pass


# ---------------------------------------------------------------- where, and the schema
def _adapter_call(adp, name, *a, default=None):
    fn = getattr(adp, name, None)
    if not callable(fn):
        return default
    try:
        return fn(*a)
    except Exception as e:  # noqa: BLE001 — a game hook that fails says so; it never breaks the page
        log.warning("profiles: the adapter's %s failed: %s", name, e)
        return default


def rel_dir(adp) -> str:
    d = _adapter_call(adp, "profiles_dir", default=None)
    return str(d or "profiles").strip("/\\").replace("\\", "/")


def folder(adp) -> Path:
    return Path(adp.root) / rel_dir(adp)


def schema_path(adp) -> Path:
    return folder(adp) / "_schema.json"


def has_schema(adp) -> bool:
    return bool(adp) and schema_path(adp).is_file()


def load_schema(adp) -> dict:
    p = schema_path(adp)
    if not p.is_file():
        raise ProfileRefused(f"this game has no profile schema yet ({rel_dir(adp)}/_schema.json) — copy the example game's "
                             "and change its sections, or ask a session to write one")
    s = json.loads(p.read_text(encoding="utf-8-sig"))
    s.setdefault("sections", [])
    looks = dict(DEFAULT_STATE_LOOK)
    for k, v in (s.get("states") or {}).items():
        if k in looks and isinstance(v, dict):
            looks[k] = {**looks[k], **v}
    owner = str(s.get("owner") or getattr(adp, "owner", "") or "the owner")
    if "states" not in s or "label" not in (s.get("states") or {}).get("owner", {}):
        looks["owner"] = {**looks["owner"], "label": f"{owner}'s word"}
    s["states"], s["owner"] = looks, owner
    return s


def rows_section(schema: dict) -> dict | None:
    """The section the board is drawn from (schema 'board.section', else the first 'rows' section)."""
    want = (schema.get("board") or {}).get("section")
    for sec in schema["sections"]:
        if sec.get("kind") == "rows" and (not want or sec["id"] == want):
            return sec
    return None


def _ids(adp) -> list[str]:
    d = folder(adp)
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json") if not p.name.startswith("_"))


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")


def make_id(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    return (s or "someone")[:64]


def path_of(adp, pid: str) -> Path:
    if not _ID_RE.match(str(pid or "")):
        raise ProfileRefused(f"'{pid}' is not a profile id (lower-case letters, digits, _ and -)")
    return folder(adp) / f"{pid}.json"


def _hash(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def blank(schema: dict, pid: str, name: str) -> dict:
    d: dict = {"id": pid}
    for sec in schema["sections"]:
        k = sec.get("kind") or "fields"
        if k == "fields":
            d[sec["id"]] = {f["id"]: ([] if f.get("kind") in ("list", "multi") else "") for f in sec.get("fields") or []}
        elif k == "rows":
            d[sec["id"]] = {r["id"]: {"entries": [], "none": None} for r in sec.get("rows") or []}
        elif k == "questions":
            d[sec["id"]] = []
    first = next((s for s in schema["sections"] if (s.get("kind") or "fields") == "fields"), None)
    if first is not None:
        nf = next((f["id"] for f in first.get("fields") or [] if f["id"] == "name"), None)
        if nf:
            d[first["id"]][nf] = name
    d["_marks"] = {}
    return d


def name_of(schema: dict, p: dict) -> str:
    for sec in schema["sections"]:
        v = (p.get(sec["id"]) or {}) if (sec.get("kind") or "fields") == "fields" else {}
        if isinstance(v, dict) and v.get("name"):
            return str(v["name"])
    return str(p.get("id") or "?")


# ---------------------------------------------------------------- the checker (what safesave runs on the temp copy)
def check(schema: dict, p: dict, rulings_by: dict | None = None) -> list[str]:
    """Problems with a profile, in plain words. `rulings_by`: ruling id → who made it (to check cited rulings)."""
    out: list[str] = []
    if not isinstance(p, dict) or not _ID_RE.match(str(p.get("id") or "")):
        return ["a profile needs an id (lower-case letters, digits, _ and -)"]
    for sec in schema["sections"]:
        k, sid = sec.get("kind") or "fields", sec["id"]
        v = p.get(sid)
        if k == "fields":
            if v is None:
                continue
            if not isinstance(v, dict):
                out.append(f"{sid} should be a set of fields")
                continue
            for f in sec.get("fields") or []:
                fv, fk = v.get(f["id"]), f.get("kind") or "text"
                if fv in (None, ""):
                    continue
                if fk in ("list", "multi") and not isinstance(fv, list):
                    out.append(f"{sid}.{f['id']} should be a list")
                elif fk in ("text", "longtext") and not isinstance(fv, str):
                    out.append(f"{sid}.{f['id']} should be words")
                elif fk == "number" and not isinstance(fv, (int, float)):
                    out.append(f"{sid}.{f['id']} should be a number")
                elif fk == "choice" and f.get("choices") and fv not in f["choices"]:
                    out.append(f"{sid}.{f['id']}: '{fv}' is not one of {', '.join(f['choices'])}")
                elif fk == "multi" and f.get("choices") and any(x not in f["choices"] for x in fv):
                    out.append(f"{sid}.{f['id']}: only {', '.join(f['choices'])}")
        elif k == "rows":
            if v is None:
                continue
            for r in sec.get("rows") or []:
                row = (v or {}).get(r["id"]) or {}
                for e in row.get("entries") or []:
                    st = e.get("state")
                    if st not in ("songs", "owner", "proposed", "open"):
                        out.append(f"{sid}.{r['id']}: an entry's state '{st}' is not one of songs, owner, proposed, open")
                        continue
                    if st == "songs" and not ((e.get("source") or {}).get("text") and (e.get("source") or {}).get("song")):
                        out.append(f"{sid}.{r['id']}: '{e.get('what')}' is marked in the songs but quotes no line and song")
                    if st == "owner":
                        out += _owner_problem(e, f"{sid}.{r['id']}: '{e.get('what')}'", rulings_by)
                nn = row.get("none")
                if nn:
                    if not str(nn.get("reason") or "").strip():
                        out.append(f"{sid}.{r['id']}: none, on purpose, needs the reason")
                    out += _owner_problem(nn, f"{sid}.{r['id']}: none, on purpose", rulings_by)
    return out


def _owner_problem(e: dict, what: str, rulings_by: dict | None) -> list[str]:
    by = str(e.get("by") or "")
    if by and not settings.is_assistant(by):
        return []
    rid = (e.get("source") or {}).get("ruling") or e.get("ruling")
    if not rid:
        return [f"{what} is set as the owner's word by {by or 'nobody'} — only a person sets that, or a session citing his ruling"]
    if rulings_by is not None:
        made = rulings_by.get(rid)
        if made is None:
            return [f"{what} cites ruling {rid}, which isn't in the rulings book"]
        if settings.is_assistant(made):
            return [f"{what} cites ruling {rid}, which an assistant made — a ruling is a person's"]
    return []


def _rulings_by(root: Path) -> dict:
    from . import rulings
    return {e.get("id"): e.get("by") for e in rulings._recorded_raw(root) if e.get("id")}


class _ProfileFiles:
    """What safesave.save needs from an adapter, for a profile file: the game folder, paths inside it, and the profile
    checker in place of the game's own data validator."""

    def __init__(self, adp, schema: dict):
        self.adp, self.schema, self.root = adp, schema, adp.root

    def is_locked_file(self, rel: str) -> bool:
        return False

    def path(self, rel: str) -> Path:
        return self.adp.path(rel)

    def validate(self, rel: str, temp_path: Path) -> list[str]:
        try:
            d = json.loads(Path(temp_path).read_text(encoding="utf-8"))
        except ValueError as e:
            return [f"{rel}: not JSON ({e})"]
        return check(self.schema, d, _rulings_by(self.adp.root))


def _dump(d: dict) -> bytes:
    return (json.dumps(d, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


# ---------------------------------------------------------------- reading
def read(adp, pid: str) -> tuple[dict, str]:
    p = path_of(adp, pid)
    if not p.is_file():
        raise ProfileRefused(f"there is no profile '{pid}'")
    b = p.read_bytes()
    return json.loads(b.decode("utf-8-sig")), _hash(b)


def cell(schema: dict, row: dict | None, row_def: dict) -> dict:
    """One board cell: {state, text, n, entries: [...]}."""
    row = row or {}
    ents = row.get("entries") or []
    if row.get("none"):
        return {"state": "none", "text": "none — " + str(row["none"].get("reason") or ""), "n": 0, "entries": []}
    if not ents:
        return {"state": "open", "text": "", "n": 0, "entries": []}
    best = max(ents, key=lambda e: RANK.get(e.get("state"), 0))
    shown = [e for e in ents if e.get("state") != "open" and str(e.get("what") or "").strip()]
    text = " · ".join(str(e.get("what")) for e in shown) or str(best.get("what") or "")
    return {"state": best.get("state") or "open", "text": text, "n": len(ents),
            "entries": [{"what": e.get("what"), "state": e.get("state")} for e in ents]}


def differs(adp, schema: dict, p: dict) -> list[str]:
    """Where the profile and the game's own data disagree, in plain words. Changes nothing."""
    gv = _adapter_call(adp, "profile_game_view", p.get("id"), default=None)
    sec = rows_section(schema)
    if not gv or not sec:
        return []
    name = name_of(schema, p)
    out = []
    rows = p.get(sec["id"]) or {}
    for r in sec.get("rows") or []:
        game = list((gv.get("rows") or {}).get(r["id"]) or [])
        row = rows.get(r["id"]) or {}
        ents = [e for e in row.get("entries") or [] if e.get("state") != "open"]
        linked = {str(e.get("game_id") or "").strip() for e in ents} - {"", "not yet"}
        gids = {g["id"] for g in game}
        label = r.get("label", r["id"]).lower()
        if row.get("none") and game:
            out.append(f"{label}: the profile says none, on purpose; the game's data gives {name} "
                       + ", ".join(f"{g['id']} ({g.get('name', '')})" for g in game))
            continue
        for g in game:
            if g["id"] not in linked:
                said = " · ".join(str(e.get("what")) for e in ents) or "nothing yet"
                out.append(f"{label}: the game's data gives {name} {g['id']} ({g.get('name', '')}); the profile says: {said}")
        known = set(gv.get("known") or [])          # ids the game's data has for them that are not row items (abilities …)
        for gid in sorted(linked - gids - known):
            out.append(f"{label}: the profile links '{gid}', which the game's data doesn't give {name}"
                       + ("" if gv.get("in_data", True) else f" — {name} isn't in the game's data at all"))
    return out


def board(adp) -> dict:
    schema = load_schema(adp)
    sec = rows_section(schema)
    who_sec = next((s for s in schema["sections"] if (s.get("kind") or "fields") == "fields"), None)
    lines = []
    for pid in _ids(adp):
        try:
            p, _ = read(adp, pid)
        except (ProfileRefused, ValueError) as e:
            lines.append({"id": pid, "name": pid, "error": str(e), "cells": {}, "flags": []})
            continue
        w = (p.get(who_sec["id"]) or {}) if who_sec else {}
        cells = {r["id"]: cell(schema, (p.get(sec["id"]) or {}).get(r["id"]), r) for r in (sec.get("rows") or [])} if sec else {}
        flags = []
        if any(c["state"] == "open" for c in cells.values()):
            flags.append("open")
        for rid, c in cells.items():                 # "no <row>": nothing there, on purpose or not yet
            if c["state"] in ("none", "open"):
                flags.append(f"no:{rid}")
        dif = differs(adp, schema, p)
        if dif:
            flags.append("differs")
        lines.append({"id": pid, "name": name_of(schema, p), "kind": w.get("kind") or "", "games": w.get("games") or [],
                      "line": w.get("line") or "", "cells": cells, "flags": flags, "differs": dif,
                      "questions": len([q for q in p.get("questions") or [] if not q.get("closed")]),
                      "order": w.get("order") if isinstance(w.get("order"), (int, float)) else 999})
    lines.sort(key=lambda x: (x.get("order", 999), x["name"].lower()))
    counts = {s: sum(1 for l in lines for c in l["cells"].values() if c["state"] == s) for s in STATES}
    return {"schema": schema, "rows": sec.get("rows") if sec else [], "section": sec["id"] if sec else None,
            "header": (schema.get("board") or {}).get("header", ""), "lines": lines, "counts": counts,
            "folder": rel_dir(adp), "words_file": f"{rel_dir(adp)}/_weapon_words.txt"}


def page(adp, pid: str) -> dict:
    schema = load_schema(adp)
    p, h = read(adp, pid)
    voice = _adapter_call(adp, "profile_voice", pid, default=None)
    return {"profile": p, "hash": h, "schema": schema, "name": name_of(schema, p),
            "links": _adapter_call(adp, "profile_links", pid, default=[]) or [],
            "voice": voice or {"text": f"ask {schema['owner']}", "ask": True},
            "game_view": _adapter_call(adp, "profile_game_view", pid, default=None),
            "differs": differs(adp, schema, p), "undo": _can_undo(adp, pid),
            "file": f"{rel_dir(adp)}/{pid}.json"}


# ---------------------------------------------------------------- writing: one safe save per change
def _history(adp) -> Path:
    return folder(adp) / "_history"


def _hist_append(adp, pid: str, entry: dict) -> None:
    d = _history(adp)
    d.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(d / f"{pid}.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def _seq(adp, pid: str) -> int:
    h = _hist(adp, pid)
    return (max((int(e.get("n") or 0) for e in h), default=0) + 1) if h else 1


def _hist(adp, pid: str) -> list[dict]:
    p = _history(adp) / f"{pid}.jsonl"
    if not p.is_file():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return out


def _write(adp, schema: dict, pid: str, new: dict, who: str, what: str, before_hash: str | None,
           expected_hash: str | None = None, obj_ptr: str = "", before_val=None, after_val=None,
           now: datetime | None = None, undo_of: str | None = None) -> dict:
    """The one way a profile is written. Returns {"ok": True, "hash", "backup"} or raises ProfileRefused."""
    from . import safesave
    if not who:
        raise ProfileRefused("set who you are first — every change is signed")
    now = now or settings.now()
    rel = f"{rel_dir(adp)}/{pid}.json"
    target = path_of(adp, pid)
    data = _dump(new)
    if before_hash is None:                      # a new profile
        if target.exists():
            raise ProfileRefused(f"there is already a profile '{pid}'")
        probs = check(schema, new, _rulings_by(adp.root))
        if probs:
            raise ProfileRefused("; ".join(probs))
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{pid}.{secrets.token_hex(3)}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        r = {"changed": True, "hash": _hash(data), "backup": None}
    else:
        if expected_hash and expected_hash != before_hash:
            raise ProfileRefused(f"{name_of(schema, new)}'s page changed since you opened it (someone else saved it) — "
                                 "nothing was written; open it again")
        try:
            r = safesave.save(_ProfileFiles(adp, schema), rel, data, before_hash, now=now)
        except safesave.SaveRefused as e:
            raise ProfileRefused("; ".join(e.problems)) from None
        except safesave.SaveConflict:
            raise ProfileRefused(f"{name_of(schema, new)}'s page changed underneath (someone else saved it) — nothing was "
                                 "written; open it again") from None
    if r["changed"]:
        journal.append(adp.root, who, "edit", f"{rel}#{obj_ptr}", before=before_val, after=after_val,
                       note=f"profile — {what}", link=r.get("backup"), when=now)
        _hist_append(adp, pid, {"n": _seq(adp, pid), "time": now.isoformat(timespec="seconds"), "who": who, "what": what,
                                "before": before_hash, "after": r["hash"], "backup": r.get("backup"), "undid": undo_of})
    return {"ok": True, **r}


def _mark(p: dict, ptr: str, who: str, now: datetime) -> None:
    p.setdefault("_marks", {})[ptr] = {"by": who, "time": now.isoformat(timespec="seconds")}


def _person_touched(p: dict, ptr: str) -> bool:
    m = (p.get("_marks") or {}).get(ptr)
    return bool(m) and not settings.is_assistant(m.get("by"))


def add(adp, name: str, who: str, pid: str | None = None, now: datetime | None = None) -> dict:
    """Add a character — a name is all it asks."""
    schema = load_schema(adp)
    name = " ".join(str(name or "").split())
    if not name:
        raise ProfileRefused("a new character needs a name")
    pid = pid or make_id(name)
    base, n = pid, 1
    while path_of(adp, pid).exists():
        n += 1
        pid = f"{base}_{n}"
    now = now or settings.now()
    p = blank(schema, pid, name)
    _mark(p, "/" + (next((s["id"] for s in schema["sections"] if (s.get("kind") or "fields") == "fields"), "who")) + "/name", who, now)
    _write(adp, schema, pid, p, who, f"added {name}", None, now=now, after_val=name)
    return {"ok": True, "id": pid, "message": f"{name} has a page now."}


def _field_def(schema: dict, section: str, field: str) -> dict:
    sec = next((s for s in schema["sections"] if s["id"] == section), None)
    if not sec or (sec.get("kind") or "fields") != "fields":
        raise ProfileRefused(f"there is no section '{section}' of fields")
    f = next((x for x in sec.get("fields") or [] if x["id"] == field), None)
    if not f:
        raise ProfileRefused(f"there is no field '{field}' in {sec.get('label', section)}")
    if f.get("readonly"):
        raise ProfileRefused(f"{f.get('label', field)} is read from elsewhere and isn't edited here")
    return f


def set_field(adp, pid: str, section: str, field: str, value, who: str, expected_hash: str | None = None,
              now: datetime | None = None) -> dict:
    schema = load_schema(adp)
    f = _field_def(schema, section, field)
    p, h = read(adp, pid)
    now = now or settings.now()
    k = f.get("kind") or "text"
    if k == "number":
        try:
            value = None if value in (None, "") else (float(value) if "." in str(value) else int(value))
        except ValueError:
            raise ProfileRefused(f"{f.get('label', field)} is a number") from None
        if value is None:
            value = ""
    elif k in ("list", "multi"):
        if isinstance(value, str):
            value = [x.strip() for x in re.split(r"[\n;]|,(?![^()]*\))", value) if x.strip()]
        value = [str(x) for x in (value or [])]
    elif k != "number":
        value = "" if value is None else str(value)
    ptr = f"/{section}/{field}"
    if settings.is_assistant(who) and _person_touched(p, ptr):
        raise ProfileRefused(f"{f.get('label', field)} on {name_of(schema, p)}'s page is {_marks_by(p, ptr)}'s — add a note or an "
                             "open question instead")
    before = (p.get(section) or {}).get(field)
    if before == value:
        return {"ok": True, "changed": False, "hash": h, "message": "No change."}
    p.setdefault(section, {})[field] = value
    _mark(p, ptr, who, now)
    r = _write(adp, schema, pid, p, who, f"{f.get('label', field)} set", h, expected_hash, ptr, before, value, now)
    return {**r, "message": "Saved."}


def _marks_by(p: dict, ptr: str) -> str:
    return str(((p.get("_marks") or {}).get(ptr) or {}).get("by") or "someone")


def _row(schema: dict, p: dict, section: str, row: str) -> dict:
    sec = next((s for s in schema["sections"] if s["id"] == section and s.get("kind") == "rows"), None)
    if not sec:
        raise ProfileRefused(f"there is no section of rows '{section}'")
    if row not in {r["id"] for r in sec.get("rows") or []}:
        raise ProfileRefused(f"there is no row '{row}' in {sec.get('label', section)}")
    rows = p.setdefault(section, {})
    return rows.setdefault(row, {"entries": [], "none": None})


def _row_label(schema: dict, section: str, row: str) -> str:
    sec = next((s for s in schema["sections"] if s["id"] == section), {})
    return next((r.get("label", row) for r in sec.get("rows") or [] if r["id"] == row), row)


def _norm_entry(e: dict, who: str, now: datetime, adp=None) -> dict:
    """An entry as it is stored, with the state rules applied for whoever is writing it."""
    src = dict(e.get("source") or {})
    for k in list(src):
        if src[k] in (None, ""):
            src.pop(k)
    st = str(e.get("state") or "").strip()
    person = not settings.is_assistant(who)
    if person:
        # a person's entry: the owner's word, unless they chose a lyric line (in the songs) or marked it open
        if st == "songs" and src.get("text") and src.get("song"):
            pass
        elif st == "open":
            pass
        else:
            st = "owner"
            src.setdefault("kind", "owner")
            src.setdefault("date", now.date().isoformat())
    else:
        if st == "owner":
            rid = src.get("ruling")
            if not rid:
                raise ProfileRefused("a session can't set the owner's word — it can write down a ruling he made, by its id, "
                                     "or propose")
            if adp is not None:
                made = _rulings_by(adp.root).get(rid)
                if made is None:
                    raise ProfileRefused(f"ruling {rid} isn't in the rulings book")
                if settings.is_assistant(made):
                    raise ProfileRefused(f"ruling {rid} was made by {made} — a ruling is a person's")
        elif st not in ASSISTANT_STATES:
            st = "proposed"
        if st == "songs" and not (src.get("text") and src.get("song")):
            raise ProfileRefused("'in the songs' quotes the line and names its song")
    what = " ".join(str(e.get("what") or "").split())
    if not what and st != "open":
        raise ProfileRefused("say what it is")
    out = {"id": str(e.get("id") or f"e{now:%H%M%S}{secrets.token_hex(2)}"), "what": what, "state": st, "source": src,
           "seen_in": str(e.get("seen_in") or "").strip(), "game_id": str(e.get("game_id") or "").strip(),
           "by": who, "time": now.isoformat(timespec="seconds")}
    if str(e.get("note") or "").strip():
        out["note"] = str(e["note"]).strip()
    return out


def _to_book(adp, schema: dict, p: dict, row_label: str, text: str, who: str, now: datetime) -> str | None:
    """An Arms entry a person sets or confirms is a ruling: write it into the rulings book too."""
    if settings.is_assistant(who):
        return None
    from . import rulings
    try:
        e = rulings.record(adp.root, who, f"{name_of(schema, p)} — {row_label.lower()}: {text}", by=who,
                           source=f"Characters → Profiles, {now:%Y-%m-%d %H:%M}", when=now, tags=["profile", str(p.get("id"))])
        return e["id"]
    except Exception as ex:  # noqa: BLE001 — the profile is saved; a book line that fails is only a warning
        log.warning("profiles: ruling not written: %s", ex)
        return None


def add_entry(adp, pid: str, section: str, row: str, entry: dict, who: str, expected_hash: str | None = None,
              now: datetime | None = None) -> dict:
    schema = load_schema(adp)
    p, h = read(adp, pid)
    now = now or settings.now()
    r = _row(schema, p, section, row)
    e = _norm_entry(entry, who, now, adp)
    label = _row_label(schema, section, row)
    if e["state"] == "owner" and not settings.is_assistant(who):
        rid = _to_book(adp, schema, p, label, e["what"], who, now)
        if rid:
            e["source"]["ruling"] = rid
    r.setdefault("entries", []).append(e)
    if r.get("none") and e["state"] in ("owner", "songs") and not settings.is_assistant(who):
        r["none"] = None                          # a person giving the row a weapon ends "none, on purpose"
    ptr = f"/{section}/{row}/entries/{len(r['entries']) - 1}"
    out = _write(adp, schema, pid, p, who, f"{label}: added {e['what'] or 'an open entry'} ({e['state']})", h, expected_hash,
                 ptr, None, e["what"], now)
    return {**out, "entry": e, "message": f"{label}: {e['what'] or 'open'} — saved as {schema['states'][e['state']]['label']}."}


def _find_entry(r: dict, eid: str) -> tuple[int, dict]:
    for i, e in enumerate(r.get("entries") or []):
        if e.get("id") == eid:
            return i, e
    raise ProfileRefused(f"there is no entry '{eid}' in that row")


def edit_entry(adp, pid: str, section: str, row: str, eid: str, changes: dict, who: str,
               expected_hash: str | None = None, now: datetime | None = None) -> dict:
    schema = load_schema(adp)
    p, h = read(adp, pid)
    now = now or settings.now()
    r = _row(schema, p, section, row)
    i, e = _find_entry(r, eid)
    if settings.is_assistant(who) and e.get("by") and not settings.is_assistant(e["by"]):
        raise ProfileRefused(f"that entry is {e['by']}'s — propose yours as a new entry, or ask him in an open question")
    changes = {k: v for k, v in (changes or {}).items() if k in ("what", "source", "seen_in", "game_id", "note", "state")}
    merged = {**e, **changes}
    if "state" not in changes:
        what_changed = " ".join(str(changes.get("what", e.get("what")) or "").split()) != e.get("what")
        # anything a person types becomes his word at once (a lyric quote stays beside it as its evidence)
        merged["state"] = "owner" if (what_changed and not settings.is_assistant(who)) else e.get("state")
    new = _norm_entry({**merged, "id": eid}, who, now, adp)
    label = _row_label(schema, section, row)
    if new["state"] == "owner" and not settings.is_assistant(who) and (new["what"] != e.get("what") or e.get("state") != "owner"):
        rid = _to_book(adp, schema, p, label, new["what"], who, now)
        if rid:
            new["source"]["ruling"] = rid
    r["entries"][i] = new
    out = _write(adp, schema, pid, p, who, f"{label}: {e.get('what')} → {new['what']} ({new['state']})", h, expected_hash,
                 f"/{section}/{row}/entries/{i}", e.get("what"), new["what"], now)
    return {**out, "entry": new, "message": "Saved."}


def confirm_entry(adp, pid: str, section: str, row: str, eid: str, who: str, expected_hash: str | None = None,
                  now: datetime | None = None) -> dict:
    """A person confirms an entry: it becomes his word (a lyric source is kept beside it) and goes into the book."""
    if settings.is_assistant(who):
        raise ProfileRefused("confirming is the owner's — a session can propose")
    schema = load_schema(adp)
    p, h = read(adp, pid)
    now = now or settings.now()
    r = _row(schema, p, section, row)
    i, e = _find_entry(r, eid)
    label = _row_label(schema, section, row)
    new = dict(e)
    src = dict(e.get("source") or {})
    if e.get("state") != "songs":
        new["state"] = "owner"
    src["confirmed"] = {"by": who, "date": now.date().isoformat()}
    rid = _to_book(adp, schema, p, label, e.get("what") or "", who, now)
    if rid:
        src["ruling"] = rid
    new["source"], new["by"], new["time"] = src, who, now.isoformat(timespec="seconds")
    r["entries"][i] = new
    out = _write(adp, schema, pid, p, who, f"{label}: confirmed {e.get('what')}", h, expected_hash,
                 f"/{section}/{row}/entries/{i}/state", e.get("state"), new["state"], now)
    return {**out, "message": f"Confirmed — {e.get('what')} is your word now, and it's in the rulings book."}


def remove_entry(adp, pid: str, section: str, row: str, eid: str, who: str, expected_hash: str | None = None,
                 now: datetime | None = None) -> dict:
    schema = load_schema(adp)
    p, h = read(adp, pid)
    now = now or settings.now()
    r = _row(schema, p, section, row)
    i, e = _find_entry(r, eid)
    if settings.is_assistant(who) and e.get("by") and not settings.is_assistant(e["by"]):
        raise ProfileRefused(f"that entry is {e['by']}'s — only he takes it off")
    r["entries"].pop(i)
    label = _row_label(schema, section, row)
    out = _write(adp, schema, pid, p, who, f"{label}: took off {e.get('what')}", h, expected_hash,
                 f"/{section}/{row}/entries/{i}", e.get("what"), None, now)
    return {**out, "message": f"Taken off (Undo puts it back)."}


def set_none(adp, pid: str, section: str, row: str, reason: str, who: str, ruling: str | None = None,
             expected_hash: str | None = None, now: datetime | None = None) -> dict:
    """None, on purpose, with the reason — the owner's call (a session only by citing his ruling)."""
    schema = load_schema(adp)
    p, h = read(adp, pid)
    now = now or settings.now()
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise ProfileRefused("say why there is none — the reason is the point")
    if settings.is_assistant(who):
        if not ruling:
            raise ProfileRefused("'none, on purpose' is the owner's call — a session can only write down a ruling he made, by its id")
        made = _rulings_by(adp.root).get(ruling)
        if made is None or settings.is_assistant(made):
            raise ProfileRefused(f"ruling {ruling} isn't a ruling of his in the book")
    r = _row(schema, p, section, row)
    label = _row_label(schema, section, row)
    nn = {"reason": reason, "by": who, "time": now.isoformat(timespec="seconds"), "source": {"date": now.date().isoformat()}}
    if ruling:
        nn["source"]["ruling"] = ruling
    elif not settings.is_assistant(who):
        rid = _to_book(adp, schema, p, label, f"none, on purpose — {reason}", who, now)
        if rid:
            nn["source"]["ruling"] = rid
    before = r.get("none")
    r["none"] = nn
    out = _write(adp, schema, pid, p, who, f"{label}: none, on purpose — {reason}", h, expected_hash,
                 f"/{section}/{row}/none", (before or {}).get("reason"), reason, now)
    return {**out, "message": f"{label}: none, on purpose."}


def clear_none(adp, pid: str, section: str, row: str, who: str, expected_hash: str | None = None,
               now: datetime | None = None) -> dict:
    schema = load_schema(adp)
    p, h = read(adp, pid)
    r = _row(schema, p, section, row)
    nn = r.get("none")
    if not nn:
        return {"ok": True, "changed": False, "message": "It wasn't marked none."}
    if settings.is_assistant(who) and not settings.is_assistant(nn.get("by")):
        raise ProfileRefused("that 'none, on purpose' is the owner's — only he lifts it")
    r["none"] = None
    label = _row_label(schema, section, row)
    out = _write(adp, schema, pid, p, who, f"{label}: no longer none", h, expected_hash, f"/{section}/{row}/none",
                 nn.get("reason"), None, now)
    return {**out, "message": f"{label} is open again."}


def add_question(adp, pid: str, text: str, who: str, expected_hash: str | None = None, now: datetime | None = None) -> dict:
    schema = load_schema(adp)
    p, h = read(adp, pid)
    now = now or settings.now()
    text = " ".join(str(text or "").split())
    if not text:
        raise ProfileRefused("the question is empty")
    sec = next((s["id"] for s in schema["sections"] if s.get("kind") == "questions"), "questions")
    qs = p.setdefault(sec, [])
    q = {"id": f"q{now:%m%d%H%M%S}{secrets.token_hex(1)}", "text": text, "by": who, "time": now.isoformat(timespec="seconds")}
    qs.append(q)
    out = _write(adp, schema, pid, p, who, f"open question: {text[:80]}", h, expected_hash, f"/{sec}/{len(qs) - 1}", None, text, now)
    return {**out, "question": q, "message": "Added to the open questions."}


def close_question(adp, pid: str, qid: str, who: str, note: str = "", now: datetime | None = None) -> dict:
    schema = load_schema(adp)
    p, h = read(adp, pid)
    now = now or settings.now()
    sec = next((s["id"] for s in schema["sections"] if s.get("kind") == "questions"), "questions")
    for i, q in enumerate(p.get(sec) or []):
        if q.get("id") == qid:
            q["closed"] = {"by": who, "time": now.isoformat(timespec="seconds"), "note": str(note or "").strip()}
            out = _write(adp, schema, pid, p, who, f"question closed: {q['text'][:80]}", h, None, f"/{sec}/{i}/closed", None, "closed", now)
            return {**out, "message": "Closed — it stays on the page, struck through."}
    raise ProfileRefused("there is no such question")


def mail_question(adp, pid: str, qid: str, who: str, now: datetime | None = None) -> dict:
    """One click: the question as a letter to the owner (from a session) or to Claude (from the owner himself)."""
    from . import mail
    schema = load_schema(adp)
    p, h = read(adp, pid)
    now = now or settings.now()
    sec = next((s["id"] for s in schema["sections"] if s.get("kind") == "questions"), "questions")
    qs = p.get(sec) or []
    i, q = next(((i, q) for i, q in enumerate(qs) if q.get("id") == qid), (None, None))
    if q is None:
        raise ProfileRefused("there is no such question")
    owner = schema["owner"]
    to = owner if settings.is_assistant(who) or who != owner else "Claude"
    name = name_of(schema, p)
    body = (f"{to},\n\nA question from {name}'s profile (Characters → Profiles → {name}):\n\n> {q['text']}\n\n"
            f"Asked by {q.get('by')} on {str(q.get('time', ''))[:10]}. Your answer comes back to the page as a note.\n\n{who}")
    try:
        letter = mail.send(adp.root, who, to, f"{name}: {q['text'][:60]}", body,
                           questions=[{"id": f"profile-{pid}-{qid}", "question": q["text"],
                                       "why": f"from {name}'s profile — {rel_dir(adp)}/{pid}.json"}], when=now, adp=adp)
    except Exception as e:  # noqa: BLE001 — e.g. the rulings book already answers it
        hits = getattr(e, "hits", None)
        if hits:
            raise ProfileRefused("the rulings book already answers this: " + "; ".join(
                f"{r['rulings'][0].get('text', '')[:140]}" for r in hits[:1])) from None
        raise ProfileRefused(str(e)) from None
    q["mailed"] = {"letter": letter.id, "to": to, "time": now.isoformat(timespec="seconds")}
    out = _write(adp, schema, pid, p, who, f"question mailed to {to}", h, None, f"/{sec}/{i}/mailed", None, letter.id, now)
    return {**out, "message": f"Sent to {to} as a letter.", "letter": letter.id}


def work_order(adp, pid: str, section: str, row: str, eid: str, who: str, now: datetime | None = None) -> dict:
    """A weapon the profile has and the game's data lacks → a work order; a later game build adds the item."""
    from . import orders
    schema = load_schema(adp)
    p, _ = read(adp, pid)
    r = _row(schema, p, section, row)
    _, e = _find_entry(r, eid)
    if e.get("state") not in ("owner", "songs"):
        raise ProfileRefused("only a confirmed entry (his word, or in the songs) becomes a work order — confirm it first")
    name = name_of(schema, p)
    label = _row_label(schema, section, row)
    o = orders.add(adp.root, who, "Claude", f"Add {name}'s {e['what']} ({label.lower()}) to the game's data",
                   detail=(f"{name}'s profile has it as {schema['states'][e['state']]['label']}"
                           + (f" — “{e['source'].get('text')}” ({e['source'].get('song')})" if e["source"].get("text") else "")
                           + f". The game's data doesn't give it yet. A game build adds the item and its numbers; the profile "
                           f"changes nothing in the game's data itself."),
                   priority="someday", obj=f"{rel_dir(adp)}/{pid}.json#/{section}/{row}", when=now)
    return {"ok": True, "message": "A work order for Claude now (Tasks → For Claude).", "order": o}


def _undo_target(adp, pid: str) -> dict | None:
    """The newest change not yet undone (undos walk back one change at a time)."""
    undone: set = set()
    for e in reversed(_hist(adp, pid)):
        if e.get("undid") is not None:
            undone.add(e["undid"])
            undone.add(e.get("n"))
            continue
        if e.get("n") in undone:
            continue
        return e
    return None


def _can_undo(adp, pid: str) -> dict | None:
    t = _undo_target(adp, pid)
    if not t or not t.get("backup"):
        return None
    try:
        cur = _hash(path_of(adp, pid).read_bytes())
    except OSError:
        return None
    last = _hist(adp, pid)[-1]
    if last.get("after") != cur:
        return None
    return {"what": t.get("what"), "who": t.get("who"), "time": t.get("time")}


def undo(adp, pid: str, who: str, now: datetime | None = None) -> dict:
    """Put back the version before the last change — only if nobody changed the file since; signed like any change.
    Undo again to walk back one more."""
    schema = load_schema(adp)
    hist = _hist(adp, pid)
    t = _undo_target(adp, pid)
    if not hist or not t:
        raise ProfileRefused("nothing to undo on this page")
    cur_b = path_of(adp, pid).read_bytes()
    if hist[-1].get("after") != _hash(cur_b):
        raise ProfileRefused("the page changed outside the suite since the last edit — nothing undone; open it again")
    if not t.get("backup"):
        raise ProfileRefused("that was the page's first version — nothing before it to put back")
    if settings.is_assistant(who) and not settings.is_assistant(t.get("who")):
        raise ProfileRefused(f"that change was {t.get('who')}'s — only they undo it")
    old = (Path(adp.root) / t["backup"]).read_bytes()
    prev = json.loads(old.decode("utf-8-sig"))
    out = _write(adp, schema, pid, prev, who, f"undid: {t.get('what')}", _hash(cur_b), None, "", None, None, now,
                 undo_of=t.get("n"))
    return {**out, "message": f"Undone: {t.get('what')}."}


# ---------------------------------------------------------------- find it in the songs
def weapon_words(adp) -> list[str]:
    p = folder(adp) / "_weapon_words.txt"
    if p.is_file():
        ws = [l.split("#", 1)[0].strip().lower() for l in p.read_text(encoding="utf-8").splitlines()]
        ws = [w for w in ws if w]
        if ws:
            return ws
    return list(DEFAULT_WEAPON_WORDS)


def _word_re(words) -> re.Pattern:
    parts = sorted({re.escape(w).replace(r"\ ", r"[\s\-]?") for w in words}, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(parts) + r")(?:e?s)?\b", re.I)


def _names_re(names) -> re.Pattern | None:
    ns = sorted({n.strip() for n in names if n and len(n.strip()) >= 3}, key=len, reverse=True)
    if not ns:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in ns) + r")\b", re.I)


def find_in_songs(adp, pid: str, limit: int = 80, window: int = 5) -> dict:
    """Every lyric line with the character's name — or sung by them — near a weapon word, with its song. Lines are
    quoted as written, never changed."""
    schema = load_schema(adp)
    p, _ = read(adp, pid)
    who_sec = next((s for s in schema["sections"] if (s.get("kind") or "fields") == "fields"), None)
    w = (p.get(who_sec["id"]) or {}) if who_sec else {}
    names = [w.get("name") or name_of(schema, p)] + list(w.get("other_names") or [])
    nre = _names_re(names)
    wre = _word_re(weapon_words(adp))
    songs = _adapter_call(adp, "profile_lyrics", default=[]) or []
    hits = []
    for s in songs:
        lines = [str(x) for x in s.get("lines") or []]
        singer = str(s.get("singer") or "")
        sung_by = bool(nre and nre.search(singer))
        for i, line in enumerate(lines):
            m = wre.search(line)
            if not m:
                continue
            lo, hi = max(0, i - window), min(len(lines), i + window + 1)
            named_here = bool(nre and nre.search(line))
            near_at = [j for j in range(lo, hi) if j != i and nre and nre.search(lines[j])]
            if not (named_here or near_at or sung_by):
                continue
            score = (3 if named_here else (2 + (1 - min(abs(j - i) for j in near_at) / (window + 1))) if near_at else 1)
            show = sorted({*range(max(0, i - 1), min(len(lines), i + 2)), *(near_at[:1] if near_at and not named_here else [])})
            hits.append({"song": s.get("song") or "?", "singer": singer, "line": line.strip(), "word": m.group(1).lower(),
                         "context": [lines[j].strip() for j in show], "file": s.get("file") or "", "score": score,
                         "why": "named in the line" if named_here else ("named nearby" if near_at else f"sung by {singer}")})
    hits.sort(key=lambda h: -h["score"])
    seen, out = set(), []
    for h in hits:
        k = (h["song"], h["line"])
        if k in seen:
            continue
        seen.add(k)
        out.append(h)
    return {"names": [n for n in names if n], "words": weapon_words(adp), "songs": len(songs), "hits": out[:limit],
            "more": max(0, len(out) - limit)}


# ---------------------------------------------------------------- the first fill: safe to run again
def fill(adp, who: str, seeds: list[dict] | None = None, dry: bool = False, now: datetime | None = None) -> dict:
    """Write the game's seeds (adapter.profile_seeds()) into the profiles. Never overwrites a field or an entry a person
    touched; never adds an entry that is already there (same words, same source); a row a person marked none is left
    alone. A seed: {"id", "<fields section>": {field: value}, "<rows section>": {row: {"entries": [...], "none": {...}}},
    "questions": ["…"], "notes"/"ties"…: {field: value}}. Entries the owner made carry source.ruling (his ruling's id)."""
    schema = load_schema(adp)
    now = now or settings.now()
    if seeds is None:
        seeds = _adapter_call(adp, "profile_seeds", default=None)
        if seeds is None:
            raise ProfileRefused("this game's adapter has no profile_seeds() — nothing to fill from")
    rb = _rulings_by(adp.root)
    made, changed, kept, entries_added, skipped = [], [], 0, 0, []
    qsec = next((s["id"] for s in schema["sections"] if s.get("kind") == "questions"), None)
    for seed in seeds:
        pid = str(seed.get("id") or "")
        try:
            target = path_of(adp, pid)
        except ProfileRefused as e:
            skipped.append(f"{pid}: {e}")
            continue
        exists = target.is_file()
        if exists:
            p, h = read(adp, pid)
        else:
            nm = ""
            for sec in schema["sections"]:
                if (sec.get("kind") or "fields") == "fields" and isinstance(seed.get(sec["id"]), dict):
                    nm = nm or seed[sec["id"]].get("name", "")
            p, h = blank(schema, pid, nm or pid), None
        before = json.dumps(p, sort_keys=True, ensure_ascii=False)
        for sec in schema["sections"]:
            k, sid = sec.get("kind") or "fields", sec["id"]
            sv = seed.get(sid)
            if sv is None:
                continue
            if k == "fields" and isinstance(sv, dict):
                cur = p.setdefault(sid, {})
                for f in sec.get("fields") or []:
                    if f["id"] not in sv or f.get("readonly"):
                        continue
                    ptr = f"/{sid}/{f['id']}"
                    if _person_touched(p, ptr):
                        kept += 1
                        continue
                    val = sv[f["id"]]
                    if (f.get("kind") or "text") in ("list", "multi"):
                        val = [str(x) for x in (val or [])]
                    if cur.get(f["id"]) in (None, "", []) or (p.get("_marks") or {}).get(ptr, {}).get("fill"):
                        if cur.get(f["id"]) != val:
                            cur[f["id"]] = val
                            p.setdefault("_marks", {})[ptr] = {"by": who, "time": now.isoformat(timespec="seconds"), "fill": True,
                                                               **({"from": seed.get("_from", {}).get(ptr)} if seed.get("_from", {}).get(ptr) else {})}
            elif k == "rows" and isinstance(sv, dict):
                rows = p.setdefault(sid, {})
                for r in sec.get("rows") or []:
                    srow = sv.get(r["id"])
                    if not srow:
                        continue
                    row = rows.setdefault(r["id"], {"entries": [], "none": None})
                    if row.get("none") and not settings.is_assistant(row["none"].get("by")):
                        kept += 1
                        continue
                    if srow.get("none") and not row.get("none"):
                        nn = srow["none"]
                        rid = (nn.get("source") or {}).get("ruling")
                        if rid and rb.get(rid) and not settings.is_assistant(rb[rid]):
                            row["none"] = {"reason": nn["reason"], "by": rb[rid], "recorded_by": who,
                                           "time": now.isoformat(timespec="seconds"), "source": dict(nn.get("source") or {})}
                        else:
                            skipped.append(f"{pid}.{r['id']}: 'none, on purpose' cites no ruling of the owner's — left open")
                    have = {(str(e.get("what", "")).lower(), str((e.get("source") or {}).get("text", ""))) for e in row.get("entries") or []}
                    have_what = {str(e.get("what", "")).lower() for e in row.get("entries") or [] if not settings.is_assistant(e.get("by"))}
                    for e in srow.get("entries") or []:
                        key = (str(e.get("what", "")).lower(), str((e.get("source") or {}).get("text", "")))
                        if key in have or (str(e.get("what", "")).lower() in have_what and e.get("state") != "songs"):
                            continue
                        st = e.get("state") or "proposed"
                        src = dict(e.get("source") or {})
                        ent = {"id": f"f{secrets.token_hex(3)}", "what": " ".join(str(e.get("what") or "").split()), "state": st,
                               "source": src, "seen_in": str(e.get("seen_in") or ""), "game_id": str(e.get("game_id") or ""),
                               "by": who, "time": now.isoformat(timespec="seconds")}
                        if e.get("note"):
                            ent["note"] = str(e["note"])
                        if st == "owner":
                            rid = src.get("ruling")
                            if not (rid and rb.get(rid) and not settings.is_assistant(rb[rid])):
                                skipped.append(f"{pid}.{r['id']}: '{ent['what']}' as the owner's word cites no ruling of his — proposed instead")
                                ent["state"] = "proposed"
                            else:
                                ent["by"], ent["recorded_by"] = rb[rid], who
                        if ent["state"] == "songs" and not (src.get("text") and src.get("song")):
                            ent["state"] = "proposed"
                        if not ent["what"] and ent["state"] != "open":
                            continue
                        row.setdefault("entries", []).append(ent)
                        have.add(key)
                        entries_added += 1
        if qsec and seed.get("questions"):
            qs = p.setdefault(qsec, [])
            texts = {q.get("text") for q in qs}
            for qt in seed["questions"]:
                if qt not in texts:
                    qs.append({"id": f"q{secrets.token_hex(3)}", "text": qt, "by": who, "time": now.isoformat(timespec="seconds")})
        after = json.dumps(p, sort_keys=True, ensure_ascii=False)
        if after == before and exists:
            continue
        probs = check(schema, p, rb)
        if probs:
            skipped.append(f"{pid}: " + "; ".join(probs))
            continue
        if dry:
            (changed if exists else made).append(pid)
            continue
        _write(adp, schema, pid, p, who, "filled from the game's sources (profiles fill)", h, None, "", None, None, now)
        (changed if exists else made).append(pid)
    return {"ok": True, "made": made, "changed": changed, "kept_for_person": kept, "entries_added": entries_added,
            "skipped": skipped, "dry": dry,
            "message": (f"{len(made)} new page(s), {len(changed)} updated, {entries_added} entr{'y' if entries_added == 1 else 'ies'} "
                        f"added; {kept} field(s) left alone because a person wrote them" + (" (nothing written — a dry run)" if dry else ""))}
