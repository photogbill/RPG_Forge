"""The interior kit library — parametrised rooms a door opens into.

Each kit is a room template: its size range, its furniture pattern, who stands where, and (for the places where
gear gets better) the upgrade counter. Variants change the same kit, not the plan:
  ruined       collapse rules — a fallen corner turned to rubble, a breach in a wall, furniture knocked out
  underground  the cave shell — the walls are rock with a ragged edge
Every interior has one way out: a door at the bottom wall back to the street, with the 'start' spawn above it.
"""
from __future__ import annotations

from . import tiles as T
from .grid import Grid, Rect
from .plan import Plan

# kit: (min w, min h, max w, max h) including walls
KITS: dict[str, dict] = {
    "inn":         {"size": (14, 10, 16, 11), "pattern": "beds", "keeper": "innkeeper"},
    "store":       {"size": (12, 8, 14, 9), "pattern": "shelves", "keeper": "shopkeeper"},
    "gas_station": {"size": (12, 8, 13, 9), "pattern": "shelves", "keeper": "clerk"},
    "diner":       {"size": (12, 8, 14, 9), "pattern": "tables", "keeper": "cook"},
    "clinic":      {"size": (12, 9, 14, 10), "pattern": "beds", "keeper": "medic"},
    "church":      {"size": (12, 12, 14, 14), "pattern": "pews", "keeper": "preacher"},
    "workshop":    {"size": (12, 8, 14, 9), "pattern": "benches", "keeper": "smith"},
    "hall":        {"size": (16, 10, 18, 11), "pattern": "long_table", "keeper": "clerk"},
    "house":       {"size": (10, 8, 11, 8), "pattern": "rooms", "keeper": "resident"},
    "vault":       {"size": (10, 8, 11, 9), "pattern": "racks", "keeper": "guard"},
}


def _counter(g: Grid, r: Rect, plan: Plan, keeper: str):
    """A counter across the top third with the keeper behind it; returns the counter's front cells."""
    y = r.y + 3
    x0, x1 = r.x + 3, r.x2 - 4
    for x in range(x0, x1):
        g.set(x, y, T.FURNITURE)
    plan.ent("npc", id="keeper", role=keeper, x=(x0 + x1) // 2, y=y - 1)
    return [(x, y + 1) for x in range(x0, x1)]


def _furnish(g: Grid, r: Rect, plan: Plan, kit: dict, rng):
    p = kit["pattern"]
    inner = Rect(r.x + 1, r.y + 1, r.w - 2, r.h - 2)
    if p == "beds":
        for x in range(inner.x + 1, inner.x2 - 1, 3):
            g.set(x, inner.y, T.FURNITURE)
            g.set(x, inner.y + 1, T.FURNITURE)
        front = [(inner.x2 - 2, inner.y2 - 3)]
        g.set(inner.x + 1, inner.y2 - 3, T.FURNITURE)          # the desk
        plan.ent("npc", id="keeper", role=kit["keeper"], x=inner.x + 1, y=inner.y2 - 4)
        return front
    if p == "shelves":
        front = _counter(g, r, plan, kit["keeper"])
        for y in range(r.y + 5, r.y2 - 3, 2):
            for x in range(inner.x + 1, inner.x2 - 1):
                if (x - inner.x) % 4 != 0 and x not in (r.cx, r.cx - 1):
                    g.set(x, y, T.FURNITURE)
        return front
    if p == "tables":
        front = _counter(g, r, plan, kit["keeper"])
        for y in range(r.y + 5, r.y2 - 3, 2):
            for x in range(inner.x + 1, inner.x2 - 1, 3):
                if x not in (r.cx, r.cx - 1):
                    g.set(x, y, T.FURNITURE)
        return front
    if p == "pews":
        g.fill(Rect(r.cx - 1, inner.y, 2, 1), T.FURNITURE)    # the altar
        plan.ent("npc", id="keeper", role=kit["keeper"], x=r.cx, y=inner.y + 1)
        for y in range(inner.y + 3, inner.y2 - 2, 2):
            for x in range(inner.x + 1, inner.x2 - 1):
                if abs(x - r.cx) > 1:
                    g.set(x, y, T.FURNITURE)
        return [(r.cx, inner.y + 2)]
    if p == "benches":
        front = _counter(g, r, plan, kit["keeper"])
        for x in (inner.x, inner.x2 - 1):
            for y in range(r.y + 5, r.y2 - 3):
                g.set(x, y, T.FURNITURE)
        return front
    if p == "long_table":
        front = _counter(g, r, plan, kit["keeper"])
        g.fill(Rect(inner.x + 3, r.y + 6, inner.w - 6, 1), T.FURNITURE)
        return front
    if p == "rooms":
        x = inner.x + inner.w // 2
        for y in range(inner.y, inner.y2 - 3):
            g.set(x, y, T.WALL)
        g.set(x, inner.y + 1, T.FLOOR)                         # the doorway between the rooms
        g.set(inner.x, inner.y, T.FURNITURE)
        plan.ent("npc", id="resident", role=kit["keeper"], x=inner.x + 1, y=inner.y2 - 2)
        return [(inner.x + 2, inner.y2 - 2)]
    if p == "racks":
        for y in range(inner.y, inner.y2 - 3, 2):
            g.set(inner.x, y, T.FURNITURE)
            g.set(inner.x2 - 1, y, T.FURNITURE)
        plan.ent("npc", id="guard", role=kit["keeper"], x=r.cx, y=inner.y2 - 3)
        return [(r.cx, inner.y + 1)]
    return [(r.cx, r.cy)]


def _collapse(g: Grid, r: Rect, rng, keep: set):
    """Ruined: a fallen corner, a breach, some furniture gone."""
    cw, ch = max(2, r.w // 3), max(2, r.h // 3)
    corner = rng.choice([(r.x + 1, r.y + 1), (r.x2 - 1 - cw, r.y + 1)])
    for x, y in Rect(corner[0], corner[1], cw, ch).cells():
        if (x, y) not in keep and g.get(x, y) in (T.FLOOR, T.FURNITURE):
            g.set(x, y, T.RUBBLE)
    # the fallen roof spills along one wall (the outer wall stays closed: the room is still one map)
    side_x = r.x2 - 2 if corner[0] == r.x + 1 else r.x + 1
    for y in range(r.y + 2, r.y2 - 3):
        if (side_x, y) not in keep and g.get(side_x, y) == T.FLOOR and rng.random() < 0.5:
            g.set(side_x, y, T.RUBBLE)
    for y in range(r.y + 1, r.y2 - 1):
        for x in range(r.x + 1, r.x2 - 1):
            if g.get(x, y) == T.FURNITURE and (x, y) not in keep and rng.random() < 0.3:
                g.set(x, y, T.RUBBLE)


def _cave(g: Grid, r: Rect, rng, keep: set):
    """Underground: the walls are rock, and the room's edge is ragged."""
    for x, y in r.border():
        if g.get(x, y) == T.WALL:
            g.set(x, y, T.ROCK)
    for y in range(r.y + 1, r.y2 - 1):
        for x in range(r.x + 1, r.x2 - 1):
            edge = x in (r.x + 1, r.x2 - 2) or y in (r.y + 1,)
            if edge and (x, y) not in keep and g.get(x, y) == T.FLOOR and rng.random() < 0.35:
                g.set(x, y, T.ROCK)


def build(kind: str, pid: str, rng, variants: tuple = (), upgrades: list | None = None, tier=None,
          label: str = "", spawn_back: str = "") -> Plan:
    """An interior plan for a building of kit `kind`. upgrades: ["weapon", "armor"] / ["accessory"]."""
    kit = KITS.get(kind) or KITS["house"]
    mnw, mnh, mxw, mxh = kit["size"]
    w, h = rng.randint(mnw, mxw), rng.randint(mnh, mxh)
    g = Grid(w, h, T.FLOOR)
    r = Rect(0, 0, w, h)
    g.outline(r, T.WALL)
    plan = Plan(id=pid, kind="interior", grid=g, name=label or kind)
    plan.kit.append(f"interior:{kind}" + "".join(f"+{v}" for v in variants))
    dx = w // 2
    g.set(dx, h - 1, T.DOOR)
    plan.ent("door", id="out", to="back", spawn=spawn_back, x=dx, y=h - 1)
    plan.ent("spawn", name="start", x=dx, y=h - 2)
    front = _furnish(g, r, plan, kit, rng)
    keep = {(dx, h - 1), (dx, h - 2), (dx, h - 3)} | set(front)
    for e in plan.entities:
        keep.add((e["x"], e["y"]))
    for i, k in enumerate(upgrades or []):
        fx, fy = front[min(i * 2, len(front) - 1)] if front else (dx, h - 3)
        if g.get(fx, fy) != T.FLOOR:
            fx, fy = dx, h - 3
        plan.ent("upgrade", id=f"upgrade_{k}", kind=k, tier=tier, label=label, x=fx, y=fy)
        keep.add((fx, fy))
    if label:
        plan.ent("label", text=label, x=1, y=1)
    if "ruined" in variants:
        _collapse(g, r, rng, keep)
    if "underground" in variants:
        _cave(g, r, rng, keep)
    # nothing the kit put down may cut the room in two: clear any furniture that strands a floor cell
    start = (dx, h - 2)
    for _ in range(3):
        reach = g.flood(start)
        stranded = [(x, y) for y in range(h) for x in range(w) if g.walkable(x, y) and (x, y) not in reach]
        if not stranded:
            break
        for x, y in stranded:
            for n in g.n4(x, y):
                if g.get(*n) == T.FURNITURE:
                    g.set(*n, T.FLOOR)
    return plan
