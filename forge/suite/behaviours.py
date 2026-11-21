"""Behaviours (BUILD 31) — what each character does off duty, as cards; a preview by place and era; and coverage.

When the party walks into an inn, a bar, a shop or a square, they split up and each does what *they* would do there. A
game keeps one deck a character (`<game>/<behaviours_dir>/<id>.json`, the game's own format, below); this tab shows the
decks as cards, previews which could fire in a place in an era for everyone in the party, and shows where somebody has
nothing to do. **Approving is the owner's**: a session may read and preview; only a person turns a card "approved".
Saving goes through the suite's safe path (safesave), and every approval is one journal line.

A deck:  {"id", "character", "status", "behaviours": [ {"id", "status", "source", "weight",
          "when": {"place": [..], "era": [..], "present": [..], "absent": [..], "with": [ids], "without": [ids], "if": {..}},
          "do": {"go": .., "bark" | "barks" | "dialogue" | "sing" | "idle": ..}, "reactions": [{"who", "line"}],
          "npc_reaction": ".."} ] }       — files whose name starts with "_" are not decks (the room's reactions).
`forge/` names no game. Adapter hooks (optional):
    behaviours_dir() -> str              the folder, relative to the game folder (default "data/behaviours")
    behaviours_places() -> [{"id", "name", "town", "place", "present": [..]}]   the places a preview can pick
    behaviours_eras() -> [str]           the eras a preview can pick (default ["any"])
"""
from __future__ import annotations
import json
from pathlib import Path

from ..log import get
from . import journal, safesave, settings

log = get("suite")
MIN_EACH = 3            # the owner's bar (BUILD 31: "every party member in the first town has at least three behaviours")


class BehaviourRefused(ValueError):
    pass


def _hook(adp, name, default):
    fn = getattr(adp, name, None)
    if not callable(fn):
        return default
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — a hook that fails says so; it never breaks the page
        log.warning("behaviours: the adapter's %s failed: %s", name, e)
        return default


def rel_dir(adp) -> str:
    return str(_hook(adp, "behaviours_dir", "data/behaviours")).strip("/\\") or "data/behaviours"


def has_decks(adp) -> bool:
    return bool(adp) and (Path(adp.root) / rel_dir(adp)).is_dir() and any(_deck_files(adp))


def _deck_files(adp):
    d = Path(adp.root) / rel_dir(adp)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if not p.name.startswith("_"))


def _list(v):
    return v if isinstance(v, list) else [v]


def fits(b: dict, place: str, era: str, present: list, party: list) -> bool:
    """The game's own rule, read the same way (a `when` key that cannot be judged here — "if" — counts as maybe yes)."""
    w = b.get("when") or {}
    if place and "place" in w and place not in _list(w["place"]):
        return False
    if era and era != "any" and "era" in w and era not in _list(w["era"]):
        return False
    if any(p not in present for p in _list(w.get("present", []))):
        return False
    if any(p in present for p in _list(w.get("absent", []))):
        return False
    if party and any(i not in party for i in _list(w.get("with", []))):
        return False
    if party and any(i in party for i in _list(w.get("without", []))):
        return False
    return True


def _summary(b: dict) -> str:
    d = b.get("do") or {}
    if d.get("sing"):
        s = d["sing"]
        return f"takes the stage — sings {s.get('track', '?')}" + (f" when {s['with']} is in the party" if s.get("with") else "")
    for k in ("bark", "dialogue"):
        if d.get(k):
            return str(d[k])
    if d.get("barks"):
        return " / ".join(map(str, d["barks"]))
    return str(d.get("go", "stay"))


def decks(adp) -> list[dict]:
    out = []
    for p in _deck_files(adp):
        rel = f"{rel_dir(adp)}/{p.name}"
        try:
            d = adp.load(rel)
        except Exception as e:  # noqa: BLE001
            out.append({"id": p.stem, "file": rel, "error": str(e), "behaviours": []})
            continue
        rows = []
        for b in d.get("behaviours", []):
            rows.append({"id": b.get("id", ""), "status": b.get("status", "draft"), "source": b.get("source", ""),
                         "weight": b.get("weight", 1), "when": b.get("when") or {}, "go": (b.get("do") or {}).get("go", "stay"),
                         "what": _summary(b), "reactions": b.get("reactions", []), "npc_reaction": b.get("npc_reaction", "")})
        out.append({"id": d.get("id", p.stem), "character": d.get("character", p.stem), "status": d.get("status", "draft"),
                    "file": rel, "behaviours": rows})
    return out


def board(adp) -> dict:
    """Every deck as cards, the places and eras a preview can pick, and coverage: where somebody has too little to do."""
    ds = decks(adp)
    places = _hook(adp, "behaviours_places", []) or []
    eras = _hook(adp, "behaviours_eras", ["any"]) or ["any"]
    party = [d["character"] for d in ds]
    cov, thin = {}, []
    for d in ds:
        row = {}
        for pl in places:
            for era in eras:
                n = sum(1 for b in d["behaviours"] if fits({"when": b["when"]}, pl.get("place", ""), era, pl.get("present", []), party))
                row[f"{pl['id']}|{era}"] = n
        cov[d["character"]] = row
        lows = [k for k, n in row.items() if n < MIN_EACH]
        if lows:
            thin.append({"character": d["character"], "where": lows[:12], "count": len(lows)})
    counts = {"decks": len(ds), "behaviours": sum(len(d["behaviours"]) for d in ds),
              "approved": sum(1 for d in ds for b in d["behaviours"] if b["status"] == "approved")}
    return {"decks": ds, "places": places, "eras": eras, "coverage": cov, "thin": thin, "min": MIN_EACH, "counts": counts,
            "folder": rel_dir(adp)}


def preview(adp, place_id: str, era: str, party: list | None = None) -> dict:
    """Which behaviours could fire in this place, in this era, for each member of the party (all decks by default)."""
    places = {p["id"]: p for p in (_hook(adp, "behaviours_places", []) or [])}
    pl = places.get(place_id)
    if not pl:
        raise BehaviourRefused(f"no place '{place_id}' — the game's adapter lists {len(places)}")
    ds = decks(adp)
    party = party or [d["character"] for d in ds]
    out = []
    for d in ds:
        if d["character"] not in party:
            continue
        could = [b for b in d["behaviours"] if fits({"when": b["when"]}, pl.get("place", ""), era, pl.get("present", []), party)]
        out.append({"character": d["character"], "could": could, "count": len(could), "enough": len(could) >= MIN_EACH})
    return {"place": pl, "era": era, "members": out}


def approve(adp, deck_id: str, bid: str, who: str, approve_it: bool = True) -> dict:
    """The owner approves (or takes back) one card. Sessions may not: they propose, he decides."""
    if not who:
        raise BehaviourRefused("say who you are first (Settings)")
    if settings.is_assistant(who):
        raise BehaviourRefused("approving a behaviour is the owner's — a session can only propose it")
    d = next((x for x in decks(adp) if x["id"] == deck_id), None)
    if not d:
        raise BehaviourRefused(f"no deck '{deck_id}'")
    rel = d["file"]
    raw = adp.path(rel).read_bytes()
    doc = json.loads(raw.decode("utf-8-sig"))
    row = next((b for b in doc.get("behaviours", []) if b.get("id") == bid), None)
    if row is None:
        raise BehaviourRefused(f"no behaviour '{bid}' in {deck_id}")
    before = row.get("status", "draft")
    after = "approved" if approve_it else "draft"
    if before == after:
        return {"ok": True, "changed": False, "status": after}
    row["status"] = after
    if approve_it:
        row["approved_by"] = who
        row["approved_on"] = settings.now().date().isoformat()
    new = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    res = safesave.save(adp, rel, new, safesave.file_hash(raw))
    journal.append(adp.root, who, "edit", f"{rel}#{bid}/status", before=before, after=after, note=f"behaviour {bid} {after}")
    log.info("behaviours: %s %s %s by %s", deck_id, bid, after, who)
    return {"ok": True, "changed": True, "status": after, "backup": res.get("backup")}
