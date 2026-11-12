"""Art → Floor plans (BUILD 29, second part): the generator in the suite.

    view(cfg, game)                         the game's town sheets (suggested archetypes and why, unknowns), the archetype
                                            library, and every candidate already written (newest first)
    generate(cfg, game, place, era, aid, count, who)   `count` new candidates side by side (the next unused seeds)
    open_set(cfg, game, folder, map_id)     one candidate: every map of its set, the grid in the generator's own tiles,
                                            its entities, story element, notes and checks — what the editor draws
    check(cfg, game, folder, map_id, edits) the checks on an edit not yet saved (live, nothing written)
    save(cfg, game, folder, map_id, edits, who)        save an edit (the set is protected from then on)
    approve(cfg, game, folder, who)         a person only: the maps into the game (adapter.layout_install), then what
                                            follows (the paint guide where the scene kit paints from, the music slots),
                                            then the production plan is remade so the scene is on the Wanted board
    send(cfg, game, folder, question, who)  a candidate to the owner by mail, its paint guide attached

Candidates live in the forge's out folder (out/layout/<game>/…); nothing reaches the game until it is approved.
"""
from __future__ import annotations
import json
from pathlib import Path

from .. import config as cfgmod
from ..layout import archetypes, check as lcheck, store, tiles as T, town
from ..log import get
from . import games, journal, settings

log = get("suite")


class FloorPlanRefused(ValueError):
    pass


def _adp(cfg, game):
    if not games.has_adapter(cfg, game):
        raise FloorPlanRefused(f"games/{game} has no adapter, so it has no town sheets to lay out")
    return games.adapter(cfg, game)


def _root(cfg, game) -> Path:
    return cfgmod.path_of(cfg, "out") / "layout" / game


def _folder(cfg, game, rel: str) -> Path:
    """A candidate folder from its path relative to out/layout/<game>/ — nowhere else."""
    base = _root(cfg, game).resolve()
    p = (base / str(rel or "")).resolve()
    if base not in p.parents or not (p / "plan_set.json").exists():
        raise FloorPlanRefused("that isn't a floor plan of this game")
    return p


def _rel(cfg, game, p: Path) -> str:
    return Path(p).resolve().relative_to(_root(cfg, game).resolve()).as_posix()


def _sign(cfg, game, who, obj, note):
    root = games.game_root(cfg, game)
    if who and root and root.is_dir():
        try:
            journal.append(root, who, "art", obj, note=note)
        except Exception as e:  # noqa: BLE001
            log.warning("floorplans: journal line not written (%s)", e)


def _summary(cfg, game, ps_path: Path) -> dict:
    s = json.loads(ps_path.read_text(encoding="utf-8"))
    fol = ps_path.parent
    return {"folder": _rel(cfg, game, fol), "place": s.get("place"), "era": s.get("era"), "archetype": s.get("archetype"),
            "seed": s.get("seed"), "attempt": s.get("attempt"), "top": s.get("top"), "maps": len(s.get("maps") or []),
            "problems": s.get("problems") or [], "game_problems": s.get("game_problems") or [],
            "unknowns": s.get("unknowns") or [], "approved_by": s.get("approved_by"), "edited": s.get("edited"),
            "written": s.get("written"), "guide": f"{s.get('top')}_paintguide.png", "protected": store.protected(fol)}


def candidates(cfg, game, place: str | None = None) -> list[dict]:
    root = _root(cfg, game)
    if not root.is_dir():
        return []
    out = [_summary(cfg, game, p) for p in root.rglob("plan_set.json")]
    if place:
        out = [c for c in out if c["place"] == place]
    return sorted(out, key=lambda c: (c.get("written") or ""), reverse=True)


def view(cfg, game) -> dict:
    adp = _adp(cfg, game)
    sheets = adp.town_sheets() if hasattr(adp, "town_sheets") else []
    return {"sheets": sheets, "archetypes": archetypes.listing(), "candidates": candidates(cfg, game),
            "paint": {t: "#%02x%02x%02x" % c for t, c in T.PAINT.items()}, "story_colour": "#ff00ff",
            "brush": ["wall", "floor", "door", "road", "path", "ground", "rubble", "fence", "water", "story"],
            "who": settings.identity(), "owner": adp.owner,
            "sizes": {k: list(v) for k, v in town.SIZES.items()}}


def _sheet(adp, place, era):
    sheets = {s["id"]: s for s in (adp.town_sheets() if hasattr(adp, "town_sheets") else [])}
    if place not in sheets:
        raise FloorPlanRefused(f"no town sheet '{place}'")
    gs = sheets[place]
    return gs, (adp.sheet_for(gs, era) if hasattr(adp, "sheet_for") else gs)


def generate(cfg, game, place: str, era: str, aid: str | None, count: int = 4, who: str | None = None,
             size: str | None = None) -> dict:
    if era not in archetypes.ERAS:
        raise FloorPlanRefused("the era is war or after")
    adp = _adp(cfg, game)
    gs, sheet = _sheet(adp, place, era)
    aid = aid or ((gs.get("archetypes", {}).get(era) or {}).get("ids") or [None])[0]
    if not aid:
        raise FloorPlanRefused(f"{place} has no archetype yet — choose one")
    archetypes.get(aid)
    if size:
        if size not in town.SIZES:
            raise FloorPlanRefused(f"the size is one of {', '.join(town.SIZES)}")
        sheet = {**sheet, "size": size}
    made, seed = [], 1
    count = max(1, min(int(count or 4), 8))
    while len(made) < count and seed < 1000:
        fol = store.folder(cfg, game, place, era, aid, seed)
        if not (fol / "plan_set.json").exists():
            p = town.generate(sheet, aid, era, seed)
            store.write(p, fol, adp, sheet)
            made.append(_summary(cfg, game, fol / "plan_set.json"))
        seed += 1
    _sign(cfg, game, who, f"floorplan:{place}", f"{len(made)} {aid} candidates for {place} ({era}), seeds "
          f"{', '.join(str(c['seed']) for c in made)}")
    return {"made": made, "archetype": aid}


def open_set(cfg, game, rel: str, map_id: str | None = None) -> dict:
    fol = _folder(cfg, game, rel)
    top, s = store.load_set(fol)
    plans = top.all_plans()
    p = next((q for q in plans if q.id == map_id), top)
    lay = json.loads((fol / f"{p.id}.layout.json").read_text(encoding="utf-8"))
    return {"summary": _summary(cfg, game, fol / "plan_set.json"),
            "maps": [{"id": q.id, "kind": q.kind, "name": q.name} for q in plans],
            "map": {"id": p.id, "kind": p.kind, "name": p.name, "w": p.w, "h": p.h,
                    "rows": ["".join(store.GLYPHS[t] for t in row) for row in p.grid.c],
                    "glyphs": store.GLYPHS, "entities": p.entities, "story": p.story, "notes": lay.get("notes") or [],
                    "buildings": p.buildings, "districts": p.districts},
            "problems": lcheck.problems(top), "game_problems": s.get("game_problems") or []}


def check(cfg, game, rel: str, map_id: str, edits: list) -> dict:
    fol = _folder(cfg, game, rel)
    top, _s = store.load_set(fol)
    try:
        store.edit(top, map_id, edits)
    except store.LayoutError as e:
        return {"ok": False, "problems": [str(e)]}
    probs = lcheck.problems(top)
    return {"ok": not probs, "problems": probs}


def save(cfg, game, rel: str, map_id: str, edits: list, who: str | None) -> dict:
    if not who:
        raise FloorPlanRefused("say who you are first — an edit is signed")
    fol = _folder(cfg, game, rel)
    adp = _adp(cfg, game)
    top, _s = store.load_set(fol)
    try:
        store.edit(top, map_id, edits)
        s = store.save_edit(fol, top, adp, who)
    except store.LayoutError as e:
        raise FloorPlanRefused(str(e))
    _sign(cfg, game, who, f"floorplan:{s.get('place')}", f"edited {map_id} ({len(edits)} cells) in {rel}")
    return _summary(cfg, game, fol / "plan_set.json")


def approve(cfg, game, rel: str, who: str | None) -> dict:
    if not who or settings.is_assistant(who):
        raise FloorPlanRefused("approving a floor plan is a person's call — send it to them instead")
    fol = _folder(cfg, game, rel)
    adp = _adp(cfg, game)
    try:
        s = store.approve(fol, adp, who)
    except (store.LayoutError, ValueError) as e:
        raise FloorPlanRefused(str(e))
    plan_note = ""
    try:
        from . import production
        production.make_plan(cfg, game, who)          # the new scenes join the Wanted board and the plan (nothing queued)
        plan_note = "The production plan was remade: the scene is on Art → Wanted with its paint guide."
    except Exception as e:  # noqa: BLE001
        plan_note = f"The production plan wasn't remade ({type(e).__name__}: {e}) — run produce.bat plan."
    _sign(cfg, game, who, f"floorplan:{s.get('place')}", f"approved {rel}: {len(s.get('installed') or [])} maps into the game")
    return {**_summary(cfg, game, fol / "plan_set.json"), "installed": s.get("installed") or [], "after": s.get("after") or [],
            "plan": plan_note}


def send(cfg, game, rel: str, question: str, who: str | None) -> dict:
    from . import mail
    if not who:
        raise FloorPlanRefused("say who you are first — a letter is signed")
    fol = _folder(cfg, game, rel)
    s = _summary(cfg, game, fol / "plan_set.json")
    root = games.game_root(cfg, game)
    if not root or not root.is_dir():
        raise FloorPlanRefused("the game folder isn't reachable, so there's no Mail to send it through")
    adp = _adp(cfg, game)
    owner = adp.owner
    a = archetypes.get(s["archetype"])
    body = (f"A floor plan for **{s['place']}** ({s['era']}) — {a['name']}, seed {s['seed']}.\n\n"
            f"Its paint guide is attached (the story element is the magenta block). It's in Art → Floor plans as "
            f"`{rel}`.\n\n" + (f"Problems the checks found: {'; '.join(s['problems'][:4])}\n\n" if s["problems"] else "")
            + (f"Unknowns: {'; '.join(s['unknowns'][:4])}\n\n" if s["unknowns"] else "") + f"— {who}")
    q = (question or "").strip() or f"Is this the right layout for {s['place']} in the {s['era']}?"
    letter = mail.send(root, who, owner, f"A floor plan for {s['place']} ({s['era']}): {a['name']}, seed {s['seed']}", body,
                       questions=[q], attachments=[str(fol / s["guide"])], adp=adp)
    return {"letter": letter.id, "to": owner}
