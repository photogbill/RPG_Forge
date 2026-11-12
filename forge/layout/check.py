"""The constraint check every plan passes before it is written: plain-words problems, empty when it is sound.

  · every door, spawn, mark, upgrade place and the story element is reachable from the 'start' spawn
  · no artery ends in the middle of nowhere (unless the archetype allows it — decks, convoys)
  · the story element is visible from the spawn (a town or a level)
  · doors match their targets: one door per interior, each interior has one way back, every target exists
  · everything is inside the map
"""
from __future__ import annotations

from . import archetypes, tiles as T
from .plan import Plan

DEST = frozenset({T.FLOOR, T.BRIDGE, T.PATH, T.DOOR, T.GLASS, T.RUBBLE, T.VEHICLE, T.FENCE, T.DROP})


def dead_ends(p: Plan) -> list[tuple[int, int]]:
    """Road tips that stop on plain ground away from the map's edge."""
    g = p.grid
    out = []
    for y in range(2, g.h - 2):
        for x in range(2, g.w - 2):
            if g.c[y][x] != T.ROAD:
                continue
            around = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]
            roads = sum(1 for c in around if g.get(*c) == T.ROAD)
            if roads > 3:
                continue
            if any(g.get(*c) in DEST for c in around):
                continue
            # a turn's outer corner looks like an end close up; an end has little road around it
            wide = sum(1 for dy in range(-2, 3) for dx in range(-2, 3) if g.get(x + dx, y + dy) == T.ROAD)
            if wide > 6:
                continue
            out.append((x, y))
    return out


def _plan_problems(p: Plan, ids: set, parent: Plan | None) -> list[str]:
    g = p.grid
    out = []
    pre = "" if p.kind == "town" else f"{p.id}: "
    for e in p.entities:
        if not (0 <= e.get("x", -1) < g.w and 0 <= e.get("y", -1) < g.h):
            out.append(f"{pre}{e['type']} {e.get('id', e.get('name', ''))} is outside the map")
    starts = [e for e in p.of("spawn") if e.get("name") == "start"]
    if len(starts) != 1:
        out.append(f"{pre}needs exactly one 'start' spawn (has {len(starts)})")
        return out
    s = (starts[0]["x"], starts[0]["y"])
    if not g.walkable(*s):
        out.append(f"{pre}the start spawn stands on {g.get(*s)}")
        return out
    reach = g.flood(s)
    for e in p.entities:
        if e["type"] in ("door", "spawn", "npc", "upgrade"):
            if (e["x"], e["y"]) not in reach and not e.get("hidden_ok"):
                out.append(f"{pre}{e['type']} '{e.get('id', e.get('name', ''))}' at {e['x']},{e['y']} can't be reached")
    if p.story:
        cells = [(x, y) for y in range(p.story["y"], p.story["y"] + p.story["h"])
                 for x in range(p.story["x"], p.story["x"] + p.story["w"])]
        if not any(c in reach for c in cells):
            out.append(f"{pre}the story element ({p.story['what']}) can't be reached")
        if p.kind in ("town", "level") and not any(g.sees(s, c, set(cells)) for c in cells):
            out.append(f"{pre}the story element ({p.story['what']}) isn't visible from the spawn")
    elif p.kind in ("town", "level"):
        out.append(f"{pre}has no story element")
    # doors and targets
    doors = p.of("door")
    kids = {c.for_building: c for c in p.children if c.kind == "interior"}
    for d in doors:
        to = str(d.get("to", ""))
        if not to:
            out.append(f"{pre}door '{d.get('id')}' goes nowhere")
        elif to.startswith("interior:"):
            if to[9:] not in kids:
                out.append(f"{pre}door '{d.get('id')}' opens into an interior that wasn't built ({to[9:]})")
        elif to.startswith("plan:"):
            if to[5:] not in ids:
                out.append(f"{pre}door '{d.get('id')}' leads to a plan that isn't in the set ({to[5:]})")
        elif to != "travel":
            out.append(f"{pre}door '{d.get('id')}' has an unknown target '{to}'")
    for bid, kid in kids.items():
        n = sum(1 for d in doors if d.get("to") == f"interior:{bid}")
        if n != 1:
            out.append(f"{pre}building {bid} has {n} doors into its interior (needs 1)")
        back = [d for d in kid.of("door") if d.get("to") == f"plan:{p.id}"]
        if len(back) != 1:
            out.append(f"{kid.id}: needs exactly one way back to {p.id} (has {len(back)})")
        elif back[0].get("spawn") not in p.spawn_names():
            out.append(f"{kid.id}: its way back lands on spawn '{back[0].get('spawn')}', which {p.id} doesn't have")
    for b in p.buildings:
        if b.get("door") and b.get("interior") and b["id"] not in kids:
            out.append(f"{pre}building {b['id']} has a door but no interior")
    if p.kind == "town" and not any(d.get("to") == "travel" for d in doors):
        out.append(f"{pre}has no way out to the road")
    if p.kind == "interior" and not doors:
        out.append(f"{pre}has no way out")
    if p.kind in ("town", "level") and p.archetype:
        if not archetypes.ARCHETYPES.get(p.archetype, {}).get("dead_ends_ok"):
            de = dead_ends(p)
            if de:
                out.append(f"{pre}{len(de)} road cells end in the middle of nowhere (first at {de[0][0]},{de[0][1]})")
    return out


def problems(top: Plan) -> list[str]:
    plans = top.all_plans()
    ids = {p.id for p in plans}
    if len(ids) != len(plans):
        return ["two plans in the set share an id"]
    out = []

    def walk(p, parent):
        out.extend(_plan_problems(p, ids, parent))
        for c in p.children:
            walk(c, p)
    walk(top, None)
    return out
