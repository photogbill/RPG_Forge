"""A plan: one map's grid, its entities and the reasons it is the way it is.

Entities are generic (the adapter turns them into a game's own):
  spawn {name}                        where the player stands on arrival
  door {id, to, spawn}                to = "travel" (leave the place), "plan:<id>" (another plan of this set),
                                      or "interior:<building id>"; spawn = the spawn it lands on
  upgrade {id, kind, tier, label}     kind weapon | armor | accessory — where gear gets better (the game's shop binds to it)
  npc {id, role}                      a mark: someone stands here (keeper, guard, pilgrim…) — no words, no sheet
  story {id, what, w, h}              the one story element (the paint guide's magenta)
  label {text}                        a sign, for the greybox
  chest {id}                          a mark for a pickup
"""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass, field

from .grid import Grid


@dataclass
class Plan:
    id: str
    kind: str                     # town | level | interior
    grid: Grid
    entities: list = field(default_factory=list)
    archetype: str = ""
    era: str = ""
    seed: int = 0
    attempt: int = 0
    districts: list = field(default_factory=list)
    buildings: list = field(default_factory=list)
    story: dict | None = None
    kit: list = field(default_factory=list)      # the kit pieces used
    notes: list = field(default_factory=list)
    unknowns: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    states: dict = field(default_factory=dict)   # a second state of the same map (e.g. night): {"entities": [...]}
    children: list = field(default_factory=list)  # interiors and levels reached from this plan
    metrics: dict = field(default_factory=dict)
    name: str = ""
    for_building: str = ""         # an interior: the building id it is the inside of

    @property
    def w(self) -> int:
        return self.grid.w

    @property
    def h(self) -> int:
        return self.grid.h

    def all_plans(self) -> list["Plan"]:
        out = [self]
        for c in self.children:
            out += c.all_plans()
        return out

    def ent(self, type_: str, **kw) -> dict:
        e = {"type": type_, **kw}
        self.entities.append(e)
        return e

    def of(self, type_: str) -> list[dict]:
        return [e for e in self.entities if e.get("type") == type_]

    def spawn_names(self) -> list[str]:
        return [str(e.get("name")) for e in self.of("spawn")]

    def rows_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.grid.c, separators=(",", ":")).encode()).hexdigest()[:16]

    def layout_record(self) -> dict:
        """Why it is the way it is — written as <id>.layout.json, read by the GUI."""
        return {
            "id": self.id, "kind": self.kind, "name": self.name, "archetype": self.archetype, "era": self.era,
            "seed": self.seed, "attempt": self.attempt, "size": [self.w, self.h],
            "districts": self.districts, "buildings": self.buildings, "story": self.story,
            "kit": self.kit, "notes": self.notes, "unknowns": self.unknowns, "problems": self.problems,
            "metrics": self.metrics, "states": sorted(self.states), "for_building": self.for_building,
            "children": [c.id for c in self.children], "generated_hash": self.rows_hash(),
        }
