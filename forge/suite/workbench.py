"""The Story workbench, second half (BUILD 07b): People, Quests, Voice sheets, Find & replace, Play from here.

All of it reads through the game's adapter (people(), quests(), lines(), places()) and writes through the suite's safe
path (safesave / approval) — checked by the game's validator, backed up, journaled, and **approved means his**: a session's
edit to something the owner approved becomes a proposal. Song words stay locked (the adapter's `locked()`).

- **People** (`people`, `person`): a page per character — the fields the game reads (text and display fields editable;
  numbers only behind "I mean it", since balance has its own report), the sheet and portrait in use (a stand-in is marked
  wanted), every line they speak anywhere grouped by place, and their reactions (the adapter's optional `reactions()`).
- **Quests** (`quests`, `quest`): giver, town, era, the steps in order, the reward, the missed condition, the three
  `remembered` branches (done / not done / failed) side by side, every text field editable, the status.
- **Voice sheets** (`voice`, `save_voice`, `voices_for`): per person and per place — how they talk, words they'd never use,
  three lines that are exactly right. Kept in `<game>/voices/<person|place>/<id>.json`. A field a person wrote is theirs:
  a session may fill an empty field but never overwrite one.
- **Find & replace** (`find`, `replace`): every hit across lines, quests and place sheets, previewed before anything
  changes; applied one field at a time through the safe path; locked words are shown and skipped.
- **Play from here** (`play`): only when the adapter has `play_command(place, era)`.
"""
from __future__ import annotations
import json, re, subprocess
from pathlib import Path

from ..log import get
from . import journal, names, notes as notesmod, safesave, settings
from .adapter import as_dict

log = get("suite")
TEXT_KEYS = {"title", "text", "line", "name", "summary", "greeting", "description", "voice", "notes", "who"}


class WorkbenchRefused(ValueError):
    """Nothing was written; the message says why."""


# ---------------------------------------------------------------- helpers
def _ptr_get(doc, ptr: str):
    cur = doc
    for p in [x for x in ptr.split("/") if x != ""]:
        p = p.replace("~1", "/").replace("~0", "~")
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    return cur


def _esc(k) -> str:
    return str(k).replace("~", "~0").replace("/", "~1")


def _obj(adp, ref) -> dict:
    rel, _, ptr = str(ref).partition("#")
    return _ptr_get(adp.load(rel), ptr)


def _norm(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).split())


def _place_names(adp) -> dict:
    try:
        return {p.id: p.name for p in adp.places()}
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------- People
def _speaks(person, who: str) -> bool:
    w = _norm(who)
    if not w:
        return False
    keys = {_norm(person.id), _norm(person.name)}
    first = _norm(person.name).split(" ")[0] if person.name else ""
    return w in keys or (first and w.split(" ")[0] == first and len(first) > 2)


def _owner(ppl, who):
    """The one person a line's speaker is: an exact id or name first; a first name only when no one matches exactly
    and only one person has that first name."""
    w = _norm(who)
    if not w:
        return None
    exact = [p for p in ppl if w in (_norm(p.id), _norm(p.name))]
    if exact:
        return exact[0]
    loose = [p for p in ppl if _speaks(p, who)]
    return loose[0] if len(loose) == 1 else None


def people(adp) -> list[dict]:
    lines = adp.lines()
    ppl = list(adp.people())
    owners: dict = {}
    for l in lines:
        o = _owner(ppl, l.who)
        if o is not None:
            owners[o.id] = owners.get(o.id, 0) + 1
    out = []
    for p in ppl:
        n = owners.get(p.id, 0)
        out.append({"id": p.id, "name": p.name, "kind": p.kind, "lines": n, "stand_in": _stand_in(adp, p.sheet)})
    out.sort(key=lambda x: (-x["lines"], x["name"].lower()))
    return out


def _stand_in(adp, path) -> bool:
    s = str(path or "")
    if not s:
        return True
    if "placeholder" in s.lower() or "stand_in" in s.lower():
        return True
    if s.startswith("res://"):
        return not (adp.root / "project" / s[6:]).is_file()
    return not (adp.root / s).is_file() if "/" in s else False


def _fields(rec: dict, base: str) -> list[dict]:
    out = []
    for k, v in rec.items():
        if str(k).startswith("_"):
            continue
        ptr = f"{base}/{_esc(k)}"
        if isinstance(v, str):
            out.append({"key": k, "pointer": ptr, "kind": "text", "value": v})
        elif isinstance(v, bool) or isinstance(v, (int, float)):
            out.append({"key": k, "pointer": ptr, "kind": "stat", "value": v})
        else:
            out.append({"key": k, "pointer": ptr, "kind": "data", "value": v})
    return out


def person(adp, pid: str) -> dict:
    p = next((x for x in adp.people() if x.id == pid), None)
    if p is None:
        raise WorkbenchRefused(f"there is no person '{pid}' in this game")
    rel, _, ptr = str(p.ref).partition("#")
    rec = _obj(adp, p.ref)
    pn = _place_names(adp)
    by_place: dict = {}
    ppl = list(adp.people())
    for l in adp.lines():
        o = _owner(ppl, l.who)
        if o is not None and o.id == p.id:
            d = as_dict(l)
            d["ref"] = str(l.ref)
            by_place.setdefault(l.place or "", []).append(d)
    groups = [{"place": k, "name": pn.get(k, k or "(no place)"), "lines": v} for k, v in sorted(by_place.items(), key=lambda kv: (kv[0] == "", kv[0]))]
    reactions = []
    fn = getattr(adp, "reactions", None)
    if callable(fn):
        try:
            reactions = fn(pid) or []
        except Exception as e:  # noqa: BLE001
            log.warning("workbench: reactions for %s: %s", pid, e)
    return {"id": p.id, "name": p.name, "kind": p.kind, "file": rel, "pointer": ptr, "hash": safesave.file_hash(adp.path(rel).read_bytes()),
            "fields": _fields(rec, ptr), "sheet": p.sheet, "portrait": p.portrait, "stand_in": _stand_in(adp, p.sheet),
            "places": groups, "count": sum(len(g["lines"]) for g in groups), "reactions": reactions,
            "voice": voice(adp, "person", pid), "status": adp.status_of(rec)[0] if isinstance(rec, dict) else None,
            "play": callable(getattr(adp, "play_command", None))}


def edit_field(adp, ref: str, value, who: str, expected_hash: str | None = None, i_mean_it: bool = False) -> dict:
    """One field of anything (a person, a quest, a reaction line) through the safe path. A number or true/false only
    with i_mean_it — balance has its own report."""
    rel, _, ptr = str(ref).partition("#")
    try:
        cur = _ptr_get(adp.load(rel), ptr)
    except (KeyError, IndexError, ValueError):
        raise WorkbenchRefused(f"{ref} isn't in the file any more")
    if isinstance(cur, (dict, list)):
        raise WorkbenchRefused("that's a whole block, not a field — edit its parts")
    if isinstance(cur, bool) or isinstance(cur, (int, float)):
        if not i_mean_it:
            raise WorkbenchRefused("that's a number the game's balance uses — tick “I mean it” to change it")
        if isinstance(cur, bool):
            value = str(value).strip().lower() in ("1", "true", "yes", "on")
        else:
            try:
                value = int(value) if isinstance(cur, int) and re.fullmatch(r"-?\d+", str(value).strip()) else float(value)
            except ValueError:
                raise WorkbenchRefused(f"'{value}' isn't a number")
    else:
        value = str(value)
    return safesave.edit(adp, rel, [("set", ptr, value)], who, expected_hash=expected_hash, reason="workbench edit")


# ---------------------------------------------------------------- Quests
def quests(adp) -> list[dict]:
    pn = _place_names(adp)
    out = []
    for q in adp.quests():
        out.append({"id": q.id, "title": q.title, "place": q.place, "place_name": pn.get(q.place, q.place or ""),
                    "era": q.era, "giver": q.giver, "status": q.status or "draft", "steps": len(q.steps)})
    out.sort(key=lambda x: (x["place_name"] or "~", x["era"] or "", x["title"].lower()))
    return out


def _texts(obj, base: str, key=None):
    """(pointer, text) for every human-readable string under obj."""
    if isinstance(obj, str):
        if key in TEXT_KEYS or key == "#item":
            yield base, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("_") or k in ("status", "approved_by", "id", "flag", "map", "minigame", "kind", "giver", "town",
                                                 "era", "place", "source"):
                continue
            yield from _texts(v, f"{base}/{_esc(k)}", k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _texts(v, f"{base}/{i}", "#item" if key in ("steps", "lines") and isinstance(v, str) else key)


def quest(adp, qid: str) -> dict:
    q = next((x for x in adp.quests() if x.id == qid), None)
    if q is None:
        raise WorkbenchRefused(f"there is no quest '{qid}' in this game")
    rel, _, ptr = str(q.ref).partition("#")
    rec = _obj(adp, q.ref)
    steps = []
    if isinstance(rec.get("stages"), list):
        for i, s in enumerate(rec["stages"]):
            if isinstance(s, dict) and "text" in s:
                steps.append({"text": s["text"], "pointer": f"{ptr}/stages/{i}/text", "objective": s.get("objective")})
    elif isinstance(rec.get("steps"), list):
        steps = [{"text": s, "pointer": f"{ptr}/steps/{i}"} for i, s in enumerate(rec["steps"]) if isinstance(s, str)]
    rem = rec.get("remembered") if isinstance(rec.get("remembered"), dict) else None
    branches = []
    if rem:
        for k, label in (("done", "did it"), ("not_done", "didn't"), ("failed", "failed")):
            b = rem.get(k)
            if isinstance(b, dict) and "line" in b:
                branches.append({"key": k, "label": label, "line": b["line"], "pointer": f"{ptr}/remembered/{k}/line"})
            else:
                branches.append({"key": k, "label": label, "line": None, "pointer": None})
    lines = []
    for l in adp.lines():
        if qid in str(l.when or "") or qid in str(l.source or "") or qid in str(l.ref):
            d = as_dict(l)
            d["ref"] = str(l.ref)
            lines.append(d)
    title_ptr = f"{ptr}/title" if "title" in rec else None
    texts = [{"pointer": p, "text": t} for p, t in _texts(rec, ptr)
             if p not in {s["pointer"] for s in steps} | {b["pointer"] for b in branches} | {title_ptr}]
    pn = _place_names(adp)
    return {"id": q.id, "title": q.title, "title_pointer": title_ptr, "file": rel, "pointer": ptr, "ref": str(q.ref),
            "hash": safesave.file_hash(adp.path(rel).read_bytes()), "place": q.place, "place_name": pn.get(q.place, q.place), "era": q.era,
            "giver": q.giver, "status": q.status or "draft", "approved_by": q.approved_by, "steps": steps,
            "reward": rec.get("reward"), "missed": rec.get("expires_when") or rec.get("missed") or rec.get("fails_when"),
            "available": rec.get("available_when"), "remembered": branches, "remembered_who": (rem or {}).get("who"),
            "lines": lines, "texts": texts, "notes": notesmod.threads(adp.root, str(q.ref)),
            "play": callable(getattr(adp, "play_command", None))}


# ---------------------------------------------------------------- Voice sheets (B5)
VOICE_FIELDS = ("talk", "never", "exact")


def _vpath(adp, kind: str, vid: str) -> Path:
    if kind not in ("person", "place"):
        raise WorkbenchRefused("a voice sheet is for a person or a place")
    return adp.root / "voices" / kind / f"{names.portable(re.sub(r'[^A-Za-z0-9_.-]+', '_', vid))}.json"


def voice(adp, kind: str, vid: str) -> dict:
    p = _vpath(adp, kind, vid)
    d = {"kind": kind, "id": vid, "talk": {"value": "", "by": None}, "never": {"value": [], "by": None},
         "exact": {"value": [], "by": None}}
    if p.is_file():
        try:
            d.update(json.loads(p.read_text(encoding="utf-8-sig")))
        except ValueError:
            log.warning("workbench: %s is not JSON — shown empty", p)
    d["file"] = p.relative_to(adp.root).as_posix()
    d["exists"] = p.is_file()
    return d


def save_voice(adp, kind: str, vid: str, field: str, value, who: str) -> dict:
    if not who:
        raise WorkbenchRefused("a voice sheet is signed — set who you are first")
    if field not in VOICE_FIELDS:
        raise WorkbenchRefused(f"a voice sheet has {', '.join(VOICE_FIELDS)}")
    d = voice(adp, kind, vid)
    cur = d.get(field) or {}
    had = cur.get("value")
    if settings.is_assistant(who) and had and cur.get("by") and not settings.is_assistant(cur.get("by")):
        raise WorkbenchRefused(f"{cur['by']} wrote this — a session may fill an empty field, never change theirs (send a note instead)")
    if field == "talk":
        value = str(value or "").strip()
    else:
        items = value if isinstance(value, list) else str(value or "").splitlines()
        value = [str(x).strip() for x in items if str(x).strip()]
        if field == "never":
            first: dict = {}
            for x in value:
                first.setdefault(x.lower(), x)
            value = sorted(first.values(), key=str.lower)
        if field == "exact" and len(value) > 3:
            raise WorkbenchRefused("three lines that are exactly right — not more")
    if value == had:
        return {"ok": True, "message": "Already so — nothing to change.", "sheet": d}
    d[field] = {"value": value, "by": who, "at": settings.now().isoformat(timespec="seconds")}
    p = _vpath(adp, kind, vid)
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: d[k] for k in ("kind", "id", *VOICE_FIELDS)}
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(keep, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        import os
        os.replace(tmp, p)
    except OSError:
        with open(p, "r+b" if p.exists() else "wb") as f:
            f.write(tmp.read_bytes())
            f.truncate()
    journal.append(adp.root, who, "edit", f"voice:{kind}:{vid}", before=had or None, after=value, note=f"voice sheet · {field}")
    return {"ok": True, "message": "Saved.", "sheet": voice(adp, kind, vid)}


def voices(adp) -> dict:
    """Every person and place, with whether their sheet has anything in it."""
    def filled(kind, vid):
        v = voice(adp, kind, vid)
        return sum(1 for f in VOICE_FIELDS if (v.get(f) or {}).get("value"))
    return {"people": [{"id": p.id, "name": p.name, "filled": filled("person", p.id)} for p in adp.people()],
            "places": [{"id": p.id, "name": p.name, "filled": filled("place", p.id)} for p in adp.places()]}


def never_hits(text: str, words) -> list[str]:
    t = " " + _norm(text) + " "
    return [w for w in words or [] if _norm(w) and f" {_norm(w)} " in t]


def voices_for(adp, place: str, lines: list[dict]) -> dict:
    """The read-through's side panel: the place's sheet and every speaker's, plus which lines use a never-word."""
    ppl = list(adp.people())
    speakers: dict = {}
    for l in lines:
        p = _owner(ppl, l.get("who"))
        if p and p.id not in speakers:
            speakers[p.id] = {"name": p.name, **voice(adp, "person", p.id)}
    pv = voice(adp, "place", place)
    hits = {}
    for l in lines:
        p = _owner(ppl, l.get("who"))
        words = list((pv.get("never") or {}).get("value") or [])
        if p:
            words += list((speakers[p.id].get("never") or {}).get("value") or [])
        h = never_hits(l.get("text") or "", words)
        if h:
            hits[l["ref"]] = h
    return {"place": pv, "people": list(speakers.values()), "never_hits": hits}


# ---------------------------------------------------------------- Find & replace
def _targets(adp):
    """(ref, label, text, locked-reason) for every searchable text: lines, quest texts, place sheets."""
    pn = _place_names(adp)
    for l in adp.lines():
        rel, _, ptr = str(l.ref).partition("#")
        tf = l.text_field or "text"
        why = l.lock_reason if l.locked else (adp.locked(rel, f"{ptr}/{tf}") or None)
        yield f"{rel}#{ptr}/{tf}", f"{l.who or '—'} · {pn.get(l.place, l.place or '')}", l.text, why
    for q in adp.quests():
        rel, _, ptr = str(q.ref).partition("#")
        try:
            rec = _obj(adp, q.ref)
        except Exception:  # noqa: BLE001
            continue
        for p, t in _texts(rec, ptr):
            yield f"{rel}#{p}", f"quest · {q.title}", t, adp.locked(rel, p)
    for pl in adp.places():
        rel = str(pl.ref).partition("#")[0]
        try:
            d = adp.load(rel)
        except Exception:  # noqa: BLE001
            continue
        for p, t in _texts(d, ""):
            yield f"{rel}#{p}", f"place · {pl.name}", t, adp.locked(rel, p)


def _pattern(q: str, case: bool, word: bool):
    if not q:
        raise WorkbenchRefused("type something to find")
    pat = re.escape(q)
    if word:
        pat = r"(?<![\w’'])" + pat + r"(?![\w’'])"
    return re.compile(pat, 0 if case else re.IGNORECASE)


def find(adp, q: str, repl: str | None = None, case: bool = False, word: bool = False, limit: int = 1000) -> dict:
    rx = _pattern(q, case, word)
    hits, seen = [], set()
    for ref, label, text, locked in _targets(adp):
        if ref in seen or not isinstance(text, str) or not rx.search(text):
            continue
        seen.add(ref)
        h = {"ref": ref, "label": label, "text": text, "count": len(rx.findall(text)), "locked": locked or None}
        if repl is not None:
            h["after"] = rx.sub(lambda m: repl, text)
        hits.append(h)
        if len(hits) >= limit:
            break
    return {"q": q, "hits": hits, "total": sum(h["count"] for h in hits), "files": len({h["ref"].split("#")[0] for h in hits}),
            "locked": sum(1 for h in hits if h["locked"])}


def replace(adp, q: str, repl: str, refs: list[str], who: str, case: bool = False, word: bool = False) -> dict:
    """Only the hits ticked in the preview; each one through the safe path, one field at a time."""
    if not who:
        raise WorkbenchRefused("a change is signed — set who you are first")
    rx = _pattern(q, case, word)
    changed, proposed, skipped = [], [], []
    for ref in refs:
        rel, _, ptr = str(ref).partition("#")
        try:
            cur = _ptr_get(adp.load(rel), ptr)
        except Exception:  # noqa: BLE001
            skipped.append({"ref": ref, "why": "not in the file any more"})
            continue
        why = adp.locked(rel, ptr)
        if why:
            skipped.append({"ref": ref, "why": why})
            continue
        if not isinstance(cur, str) or not rx.search(cur):
            skipped.append({"ref": ref, "why": "the text changed since the preview — find again"})
            continue
        r = safesave.edit(adp, rel, [("set", ptr, rx.sub(lambda m: repl, cur))], who, reason=f"find & replace: {q} → {repl}")
        if r.get("proposed"):
            proposed.append(ref)
        elif r.get("ok"):
            changed.append(ref)
        else:
            skipped.append({"ref": ref, "why": "; ".join(r.get("refused") or ["refused"])})
    msg = f"Changed {len(changed)}" + (f", sent {len(proposed)} as proposals (approved lines are the owner's)" if proposed else "") + \
          (f", skipped {len(skipped)}" if skipped else "") + "."
    return {"ok": True, "message": msg, "changed": changed, "proposed": proposed, "skipped": skipped}


# ---------------------------------------------------------------- Play from here
def play(adp, place: str | None, era: str | None, quest_id: str | None = None) -> dict:
    fn = getattr(adp, "play_command", None)
    if not callable(fn):
        raise WorkbenchRefused("this game's adapter can't start the game at a place (no play_command)")
    if quest_id:
        q = next((x for x in adp.quests() if x.id == quest_id), None)
        if q is None:
            raise WorkbenchRefused(f"there is no quest '{quest_id}'")
        rec = _obj(adp, q.ref)
        place, era = rec.get("map") or q.place, q.era or era
    try:
        cmd = fn(place, era if era not in (None, "", "all") else None)
    except ValueError as e:
        raise WorkbenchRefused(str(e))
    if not cmd:
        raise WorkbenchRefused(f"the game can't start at {place} — it has no map for it")
    log.info("workbench: play from here: %s", cmd)
    subprocess.Popen(cmd, cwd=str(adp.root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "message": f"Starting the game at {place}" + (f" ({era})" if era and era != "all" else "") + " — it opens in its own window."}
