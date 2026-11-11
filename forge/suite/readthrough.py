"""The town read-through (BUILD 07, roadmap §5 screen 1) — one place, one era, everything it says, in the order a player
meets it; edit in place, approve / draft / flag as generic / note, and a sameness meter that is honest about being
mechanical.

The suite knows places, lines, quests and status; the game's adapter supplies the order and the sheet through optional
hooks (defaults in brackets):
  place_sheet(place, era) → [{label, file, pointer, field, text}]   the place's own fields shown on top [its string fields]
  line_order(place)       → {ref: rank}                                the order a player meets the lines [file order]
  place_words(place)      → set of words that belong to this place     for the meter [its name and summary words]
  place_greeting(place, era) → the greeting its people use, or None    for the meter [none]
A line whose era is empty is shown in every era. Writes go through safesave / approval / notes like everything else.
"""
from __future__ import annotations
import difflib, re
from pathlib import Path

from . import notes as notesmod
from .adapter import as_dict
from .safesave import file_hash

ERAS_ALL = "all"
STOP = set("""the a an and or but of to in on at for with from by is are was were be been it its this that these those you your
yours he him his she her they them their we us our i me my mine not no so if then than as just only all any some every what who
when where why how there here have has had do does did will would can could should may might must shall get got go going come
let make made like one two very now still ever never again more most much many too also out up down off over into onto about
back away yes yeah oh well okay sir maam ma'am don't can't won't it's i'm you're that's there's we're they're i'll you'll""".split())


def _norm(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(s).lower().replace("’", "'").replace("'", "")).split())


def _words(s) -> set:
    return {w for w in re.findall(r"[a-z][a-z']+", str(s).lower().replace("’", "'")) if w not in STOP and len(w) > 2}


def towns(adp) -> list[dict]:
    lines = adp.lines()
    by: dict = {}
    for l in lines:
        if l.place:
            c = by.setdefault(l.place, {"lines": 0, "approved": 0, "flagged": 0})
            c["lines"] += 1
            c["approved"] += l.status == "approved"
            c["flagged"] += l.status == "flagged"
    out = []
    for p in adp.places():
        c = by.get(p.id, {"lines": 0, "approved": 0, "flagged": 0})
        out.append({"id": p.id, "name": p.name, "eras": p.eras, "dev": p.dev, "status": p.status, **c})
    out.sort(key=lambda x: (x["dev"], x["name"].lower()))
    return out


def _sheet(adp, place, era) -> list[dict]:
    fn = getattr(adp, "place_sheet", None)
    if fn:
        return fn(place.id, era) or []
    rel = str(place.ref).split("#")[0]
    d = adp.load(rel)
    return [{"label": k, "file": rel, "pointer": f"/{k}", "field": None, "text": v} for k, v in d.items()
            if isinstance(v, str) and k not in ("id", "status", "approved_by", "kind")]


def _in_era(line_era, era) -> bool:
    return era == ERAS_ALL or not line_era or line_era in ("all", era)


def page(adp, place_id: str, era: str = ERAS_ALL) -> dict:
    places = {p.id: p for p in adp.places()}
    place = places.get(place_id)
    if place is None:
        raise ValueError(f"there is no place '{place_id}'")
    eras = list(place.eras or [])
    all_lines = adp.lines()
    mine = [l for l in all_lines if l.place == place_id and _in_era(l.era, era)]
    order = (getattr(adp, "line_order", None) or (lambda _p: {}))(place_id) or {}
    pos = {str(l.ref): i for i, l in enumerate(mine)}
    mine.sort(key=lambda l: (order.get(str(l.ref), 10_000), pos[str(l.ref)]))
    nc = notesmod.counts(adp.root)
    meter = sameness(adp, place, era, mine, all_lines)
    files = sorted({str(l.ref).split("#")[0] for l in mine} | {s["file"] for s in _sheet(adp, place, era)})
    hashes = {}
    for f in files:
        try:
            hashes[f] = file_hash(adp.path(f).read_bytes())
        except OSError:
            pass
    rows = []
    for i, l in enumerate(mine):
        d = as_dict(l)
        d["n"] = i + 1
        d["file"], d["pointer"] = str(l.ref).split("#", 1)
        d["notes"] = nc.get(str(l.ref), 0)
        d["meter"] = meter["by_ref"].get(str(l.ref), [])
        rows.append(d)
    quests = [as_dict(q) for q in adp.quests() if q.place == place_id and _in_era(q.era, era)]
    for q in quests:
        q["file"], q["pointer"] = q["ref"].split("#", 1)
        q["notes"] = nc.get(q["ref"], 0)
    sheet = _sheet(adp, place, era)
    for s in sheet:
        s["ref"] = f"{s['file']}#{s['pointer']}"
        s["notes"] = nc.get(s["ref"], 0)
    c = {"lines": len(rows), "approved": sum(r["status"] == "approved" for r in rows), "flagged": sum(r["status"] == "flagged" for r in rows),
         "draft": sum(r["status"] in (None, "draft") for r in rows), "locked": sum(bool(r["locked"]) for r in rows),
         "meter": sum(bool(r["meter"]) for r in rows), "notes": sum(r["notes"] for r in rows)}
    return {"place": as_dict(place), "era": era, "eras": eras, "sheet": sheet, "lines": rows, "quests": quests, "counts": c,
            "meter": {k: v for k, v in meter.items() if k != "by_ref"}, "hashes": hashes,
            "place_notes": notesmod.threads(adp.root, f"place:{place_id}")}


def sameness(adp, place, era, mine, all_lines) -> dict:
    """Candidates, not verdicts: (1) a line that also appears — or nearly — in another place; (2) a line with no word
    that belongs to this place; (3) a speaker with two or more lines who never uses the place's greeting."""
    others: dict = {}
    for l in all_lines:
        if l.place and l.place != place.id and len(_norm(l.text)) > 12:
            others.setdefault(_norm(l.text), set()).add(l.place)
    other_keys = list(others)
    fn = getattr(adp, "place_words", None)
    local = set(fn(place.id)) if fn else (_words(place.name) | _words(place.summary))
    local = {w.lower() for w in local}
    gfn = getattr(adp, "place_greeting", None)
    greeting = gfn(place.id, era) if gfn else None
    by_ref: dict = {}
    dup = nolocal = 0
    for l in mine:
        if l.locked or str(l.text).lstrip().startswith("["):      # song words and [stage directions] aren't voices
            continue
        t = _norm(l.text)
        marks = []
        if t in others:
            marks.append("also in " + ", ".join(sorted(others[t])))
        elif len(t) > 24:
            close = difflib.get_close_matches(t, other_keys, n=1, cutoff=0.9)
            if close:
                marks.append("nearly the same as a line in " + ", ".join(sorted(others[close[0]])))
        if marks:
            dup += 1
        if local and len(_words(l.text)) >= 3 and not (_words(l.text) & local):
            marks.append("no word that belongs to this place")
            nolocal += 1
        if marks:
            by_ref[str(l.ref)] = marks
    quiet = []
    if greeting:
        g = _norm(greeting).split()[:3]
        g = " ".join(g)
        speakers: dict = {}
        for l in mine:
            if l.who and not l.locked:
                speakers.setdefault(l.who, []).append(_norm(l.text))
        for who, ts in speakers.items():
            if len(ts) >= 2 and g and not any(g in t for t in ts):
                quiet.append(who)
    return {"by_ref": by_ref, "duplicates": dup, "no_local_word": nolocal, "greeting": greeting,
            "never_greet": sorted(quiet), "local_words": sorted(local)[:40],
            "how": "mechanical: exact or ≥90% similar text elsewhere; no word from this place's name, sheet or customs; "
                   "speakers with 2+ lines who never use its greeting — candidates to look at, not judgements"}


def edit_line(adp, ref: str, field: str, value: str, who: str, expected_hash: str | None = None) -> dict:
    from . import safesave
    rel, _, ptr = ref.partition("#")
    return safesave.edit(adp, rel, [("set", f"{ptr}/{field}", value)], who, expected_hash=expected_hash, reason="read-through edit")


def mark(adp, ref: str, status: str, who: str, expected_hash: str | None = None, note: str | None = None, label: str | None = None) -> dict:
    from . import approval
    rel, _, ptr = ref.partition("#")
    r = approval.mark(adp, rel, ptr, status, who, expected_hash=expected_hash)
    if r.get("ok") and note:
        notesmod.add(adp.root, ref, who, note, tag="generic" if status == "flagged" else "note", label=label)
    return r
