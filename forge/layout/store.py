"""Writing a plan set to disk, and approving it into a game.

A plan set (a town and its interiors and levels) is written to the forge's out folder:
  out/layout/<game>/<place>/<era>/<archetype>/seed_<n>/
      <id>.json            the map in the game's own format (its adapter's layout_map), else the generic format
      <id>_greybox.png     walkable greybox, pixel-aligned with the rows
      <id>_paintguide.png  flat colour regions + the story element in magenta (the scene kit repaints from it)
      <id>.layout.json     why it is the way it is (archetype, seed, kit pieces, districts, story element)
      <id>.plan.json       the plan itself in the generator's own words (what the editor loads and saves)
      plan_set.json        the set: which plans, the seed, the check results, each map's generated hash, the sheet

Never regenerated over: a folder whose set is approved, or whose maps were edited by hand (their rows no longer match
the hash recorded when they were generated), refuses a write. Approving copies the maps into the game through its
adapter — a person only (approved means theirs), never over a map the game already has unless it is the same one.
"""
from __future__ import annotations
import hashlib, json, os
from datetime import datetime
from pathlib import Path

from ..log import get
from . import render, tiles as T
from .plan import Plan

log = get("layout")

GLYPHS = {T.GROUND: ".", T.ROAD: "=", T.PATH: "_", T.FLOOR: "-", T.WALL: "#", T.ROOF: "R", T.WATER: "~", T.DOOR: "D",
          T.RUBBLE: ",", T.FIELD: '"', T.FENCE: "|", T.ROCK: "^", T.GLASS: "*", T.BRIDGE: "b", T.DROP: "v",
          T.VEHICLE: "V", T.FURNITURE: "f"}


class LayoutError(RuntimeError):
    pass


def folder(cfg: dict, game: str, place: str, era: str, archetype: str, seed: int) -> Path:
    from .. import config as cfgmod
    return cfgmod.path_of(cfg, "out") / "layout" / game / place / era / archetype / f"seed_{seed}"


def rows_hash(rows: list[str]) -> str:
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16]


def _resolve(top: Plan) -> dict:
    """plan id → {door target → the id of the map it opens} for every plan in the set."""
    by_building = {}
    for p in top.all_plans():
        for c in p.children:
            if c.kind == "interior":
                by_building[(p.id, c.for_building)] = c.id
    return by_building


def generic_map(p: Plan, interiors: dict) -> dict:
    rows = ["".join(GLYPHS[t] for t in row) for row in p.grid.c]
    used = sorted({ch for r in rows for ch in r})
    ents = []
    for e in p.entities:
        e = dict(e)
        if e["type"] == "door":
            to = str(e.get("to", ""))
            if to.startswith("interior:"):
                e["to"] = interiors.get((p.id, to[9:]), to)
            elif to.startswith("plan:"):
                e["to"] = to[5:]
        ents.append(e)
    return {"id": p.id, "name": p.name, "tile_size": 32, "legend": {ch: GLYPHS_INV[ch] for ch in used},
            "rows": rows, "entities": ents}


GLYPHS_INV = {v: k for k, v in GLYPHS.items()}


def export(top: Plan, adapter=None, sheet: dict | None = None) -> dict:
    """Every plan of the set as a map dict, keyed by map id (the game's format when its adapter has layout_map)."""
    interiors = _resolve(top)
    out = {}
    for p in top.all_plans():
        m = None
        if adapter is not None and hasattr(adapter, "layout_map"):
            m = adapter.layout_map(p, top, interiors, sheet or {})
        if m is None:
            m = generic_map(p, interiors)
        out[m["id"]] = m
    return out


def protected(fol: Path) -> str | None:
    """Why this folder must not be written over, or None."""
    ps = Path(fol) / "plan_set.json"
    if not ps.exists():
        return None
    try:
        s = json.loads(ps.read_text(encoding="utf-8"))
    except Exception:
        return "its plan_set.json doesn't read — left alone"
    if s.get("approved_by"):
        return f"approved by {s['approved_by']} on {s.get('approved_at', '?')}"
    if s.get("edited"):
        return f"edited by hand ({s.get('edited')})"
    for mid, h in (s.get("hashes") or {}).items():
        f = Path(fol) / f"{mid}.json"
        if f.exists():
            try:
                rows = json.loads(f.read_text(encoding="utf-8")).get("rows") or []
            except Exception:
                return f"{mid}.json doesn't read — left alone"
            if rows_hash(rows) != h:
                return f"{mid}.json was edited by hand"
    return None


def _write_json(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, p)


def plan_to_dict(p: Plan) -> dict:
    return {"id": p.id, "kind": p.kind, "name": p.name, "archetype": p.archetype, "era": p.era, "seed": p.seed,
            "attempt": p.attempt, "rows": ["".join(GLYPHS[t] for t in row) for row in p.grid.c], "entities": p.entities,
            "districts": p.districts, "buildings": p.buildings, "story": p.story, "kit": p.kit, "notes": p.notes,
            "unknowns": p.unknowns, "problems": p.problems, "states": p.states, "metrics": p.metrics,
            "for_building": p.for_building, "children": [c.id for c in p.children]}


def plan_from_dict(d: dict) -> Plan:
    from .grid import Grid
    rows = d["rows"]
    g = Grid(len(rows[0]), len(rows))
    g.c = [[GLYPHS_INV[ch] for ch in r] for r in rows]
    return Plan(id=d["id"], kind=d["kind"], grid=g, entities=list(d.get("entities") or []), archetype=d.get("archetype", ""),
                era=d.get("era", ""), seed=int(d.get("seed") or 0), attempt=int(d.get("attempt") or 0),
                districts=list(d.get("districts") or []), buildings=list(d.get("buildings") or []), story=d.get("story"),
                kit=list(d.get("kit") or []), notes=list(d.get("notes") or []), unknowns=list(d.get("unknowns") or []),
                problems=list(d.get("problems") or []), states=dict(d.get("states") or {}), metrics=dict(d.get("metrics") or {}),
                name=d.get("name", ""), for_building=d.get("for_building", ""))


def load_set(fol: Path) -> tuple[Plan, dict]:
    """The plan set in a folder, rebuilt (the town and its children) — for the editor and for approving."""
    fol = Path(fol)
    s = json.loads((fol / "plan_set.json").read_text(encoding="utf-8"))
    plans = {mid: plan_from_dict(json.loads((fol / f"{mid}.plan.json").read_text(encoding="utf-8"))) for mid in s["maps"]}
    for mid, p in plans.items():
        d = json.loads((fol / f"{mid}.plan.json").read_text(encoding="utf-8"))
        p.children = [plans[c] for c in d.get("children") or [] if c in plans]
    return plans[s["top"]], s


def _emit(top: Plan, fol: Path, adapter, sheet: dict | None, px: int) -> tuple[dict, list]:
    fol.mkdir(parents=True, exist_ok=True)
    maps = export(top, adapter, sheet)
    tile_image = adapter.layout_tile_image() if adapter is not None and hasattr(adapter, "layout_tile_image") else None
    for p, (mid, m) in zip(top.all_plans(), maps.items()):
        _write_json(fol / f"{mid}.json", m)
        rec = p.layout_record()
        rec["map_id"] = mid
        _write_json(fol / f"{mid}.layout.json", rec)
        _write_json(fol / f"{mid}.plan.json", plan_to_dict(p))
        render.greybox(p, px, tile_image).save(fol / f"{mid}_greybox.png")
        render.paint_guide(p, px).save(fol / f"{mid}_paintguide.png")
    game_problems = adapter.layout_check(maps) if adapter is not None and hasattr(adapter, "layout_check") else []
    return maps, game_problems


def write(top: Plan, fol: Path, adapter=None, sheet: dict | None = None, px: int = 32) -> dict:
    fol = Path(fol)
    why = protected(fol)
    if why:
        raise LayoutError(f"not writing over {fol} — {why}. Reroll (a new seed) instead.")
    maps, game_problems = _emit(top, fol, adapter, sheet, px)
    s = {"top": next(iter(maps)), "place": (sheet or {}).get("id"), "archetype": top.archetype, "era": top.era,
         "seed": top.seed, "attempt": top.attempt, "maps": list(maps), "px": px,
         "hashes": {mid: rows_hash(m["rows"]) for mid, m in maps.items()},
         "problems": list(top.problems), "game_problems": game_problems, "unknowns": list(top.unknowns),
         "written": datetime.now().isoformat(timespec="seconds"), "sheet": sheet or {}}
    _write_json(fol / "plan_set.json", s)
    log.info("layout: wrote %d maps to %s (problems %d, game problems %d)", len(maps), fol, len(top.problems), len(game_problems))
    return s


def edit(top: Plan, map_id: str, edits: list) -> Plan:
    """Paint cells of one plan of the set: edits = [[x, y, semantic tile] or [x, y, "story"], …]. Returns the plan.
    'story' moves the story element's top-left to that cell (its size kept). Doors and spawns stay where they are."""
    from . import tiles as T
    p = next((q for q in top.all_plans() if q.id == map_id), None)
    if p is None:
        raise LayoutError(f"no map {map_id} in this set")
    for e in edits or []:
        x, y, t = int(e[0]), int(e[1]), str(e[2])
        if not p.grid.ok(x, y):
            raise LayoutError(f"cell {x},{y} is outside the {p.w}x{p.h} map")
        if t == "story":
            if not p.story:
                raise LayoutError("this map has no story element to move")
            p.story = {**p.story, "x": x, "y": y}
            for ent in p.entities:
                if ent["type"] == "story":
                    ent["x"], ent["y"] = x, y
            continue
        if t not in T.ALL:
            raise LayoutError(f"'{t}' is not a tile the generator knows ({', '.join(T.ALL)})")
        if x in (0, p.w - 1) or y in (0, p.h - 1):
            if not (t == T.DOOR and p.grid.get(x, y) == T.DOOR):
                if t not in T.BLOCKING:
                    raise LayoutError("the map's outer edge stays closed — only its gates are open")
        p.grid.set(x, y, t)
    return p


def save_edit(fol: Path, top: Plan, adapter, who: str, px: int | None = None) -> dict:
    """Write an edited set back to its folder. From then on the folder is protected: a reroll never writes over it."""
    from . import check
    fol = Path(fol)
    s = json.loads((fol / "plan_set.json").read_text(encoding="utf-8"))
    if s.get("approved_by"):
        raise LayoutError(f"approved by {s['approved_by']} — an approved plan isn't edited here (reroll, or edit it in the game)")
    if not who:
        raise LayoutError("say who you are first — an edit is signed")
    top.problems = check.problems(top)
    maps, game_problems = _emit(top, fol, adapter, s.get("sheet") or {}, int(px or s.get("px") or 32))
    s.update({"hashes": {mid: rows_hash(m["rows"]) for mid, m in maps.items()}, "problems": list(top.problems),
              "game_problems": game_problems, "edited": f"{who}, {datetime.now().isoformat(timespec='seconds')}"})
    _write_json(fol / "plan_set.json", s)
    log.info("layout: %s edited %s (problems %d)", who, fol, len(top.problems))
    return s


def approve(fol: Path, adapter, who: str, now: datetime | None = None) -> dict:
    """Copy an approved set's maps into the game. A person only; refuses on any problem."""
    from ..suite import settings
    fol = Path(fol)
    if not who or settings.is_assistant(who):
        raise LayoutError("approving a plan is a person's call (approved means theirs) — send it to them instead")
    s = json.loads((fol / "plan_set.json").read_text(encoding="utf-8"))
    if s.get("approved_by"):
        raise LayoutError(f"already approved by {s['approved_by']}")
    maps = {mid: json.loads((fol / f"{mid}.json").read_text(encoding="utf-8")) for mid in s["maps"]}
    if s.get("problems"):
        raise LayoutError("it still has problems: " + "; ".join(s["problems"][:3]))
    probs = adapter.layout_check(maps) if hasattr(adapter, "layout_check") else []
    if probs:
        raise LayoutError("the game's check refuses it: " + "; ".join(probs[:3]))
    if not hasattr(adapter, "layout_install"):
        raise LayoutError("this game's adapter can't take maps from the generator yet (no layout_install)")
    done = adapter.layout_install(maps, fol, who)
    after = []
    if hasattr(adapter, "layout_after_install"):
        try:
            after = adapter.layout_after_install(maps, fol, who) or []
        except Exception as e:  # noqa: BLE001 — the maps are in; say what didn't follow
            after = [f"after installing: {type(e).__name__}: {e}"]
    s["after"] = after
    s["approved_by"] = who
    s["approved_at"] = (now or datetime.now()).isoformat(timespec="seconds")
    s["installed"] = done
    _write_json(fol / "plan_set.json", s)
    log.info("layout: %s approved %s → %s", who, fol, done)
    return s
