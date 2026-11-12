# Floor plans — the generator (BUILD 29)

A town's sheet + an archetype + an era + a seed → a plan set: the town map, an interior for every door that opens, and
(for a Buried Town) the level below. Each map comes with a greybox and a **paint guide**. Nothing is written into a game
until a person approves a plan.

```
floor_plans.bat                                  every place the game can lay out, the suggested archetype and why
floor_plans.bat <place> war|after [archetype]    four candidates (seeds 1–4)
python -m forge layout sheets
python -m forge layout generate <place> --era war|after [--archetype <id>] [--seed 1] [--count 4] [--px 32]
python -m forge layout show <folder>             the plan as text: S the spawn, @ the story element
python -m forge layout check <folder>            the plan's checks + the game's own map rules, again
python -m forge layout approve <folder>          a person only: copy the maps into the game
python -m forge layout archetypes                the library
```

Candidates go to `out/layout/<game>/<place>/<era>/<archetype>/seed_<n>/`:

| file | what |
|---|---|
| `<id>.json` | the map in the game's own format (the adapter's `layout_map`), else the generic one below |
| `<id>_greybox.png` | walkable vs blocking — the game's placeholder tiles when its adapter offers them |
| `<id>_paintguide.png` | flat colour per region, the story element in magenta (`forge/layout/tiles.py` PAINT) |
| `<id>.layout.json` | why: archetype, seed, attempt, districts, buildings, kit pieces, story element, notes, unknowns |
| `plan_set.json` | the set, its check results, and each map's generated hash |

Cell `x, y` covers pixels `x*px … x*px+px-1` in both pictures (px 32 by default, `--px` to change).

## How a plan is made (`forge/layout/town.py`)

1. **Macro — districts.** The archetype's layout rule draws the arteries first (the road the town grew along), the
   features (rings, spokes, a river and its bridge, decks over a drop, a wall inside a wall, a glass disc…) and
   splits what's left into districts with a role each.
2. **Meso — lots and buildings.** The sheet's required buildings first, then the archetype's signature building, then
   the two **upgrade places** (a weapon/armor smith and an accessory shop, with the tier the town sells), then filler.
   Doors face streets; every door is joined to the street by a path; nothing is built on an artery. Only a few houses
   open (three by default) — every open door is another map the game carries.
3. **Micro — interiors.** Each open door gets a room from the kit library (`kits.py`): inn, store, gas station, diner,
   clinic, church, workshop, hall, house, vault — furniture, the keeper's mark, the upgrade counter. *Ruined* collapses a
   corner and spills rubble; *underground* turns the walls to ragged rock. Every room has one door back to the street.
4. **Texture.** Wave Function Collapse (`wfc.py`) fills empty ground with crop rows, rubble fields, fence runs or kept
   lawns. Filler only: it never touches a path, and anything it puts down that would cut a path turns to rubble.
5. **Checks** (`check.py`). Every door, spawn, mark and upgrade place reachable from the spawn; no road ending in the
   middle of nowhere (unless the archetype allows it); the story element visible from the spawn; one door per
   interior and one way back; every target exists. A plan that fails is tried again with the next attempt number —
   still deterministic — and records which attempt passed.

**Same sheet + archetype + era + seed → the same bytes**, on every computer.

## The archetypes (`forge/layout/archetypes.py`)

◆ proposals, except the Buried Town (✦ William, 2026-11-11). The generator never assigns an archetype to a real place
and never invents one: the game's adapter *suggests* from the place's own sheet and says why; the person who owns the
game assigns (in the game's data). `python -m forge layout archetypes` prints each one's pitch, story element and
upgrade places for both eras.

## A sheet (what a game's adapter gives the generator)

```json
{"id": "ember_crossing", "name": "Ember Crossing", "size": "hamlet | town | city", "terrain": "river | mountain | desert",
 "required": [{"kind": "inn", "label": "INN", "ref": "data/places/x.json#/services/0"}],
 "signature": {"kind": "hall", "label": "THE MINE HEAD"},
 "tiers": {"weapon": 1, "armor": 1, "accessory": 0},
 "vehicles": ["truck", "bus"], "wrecks": ["the tank line"], "unknowns": ["terrain: not on the sheet"]}
```

Building kinds: `archetypes.KINDS`. Unknowns are listed in `layout.json`, never guessed.

Sizes (tiles): hamlet 56×36 · **town 80×52** (the default) · city 100×64 — slightly larger than the first pass
(William, 2026-11-12). A sheet's `look` and `music` (its own words for this era) go into the plan's notes and the
map, so the painting brief and the town's music slot carry that town's look and theme.

## A game's hooks (all optional; `forge/suite/adapter.py`)

- `town_sheets()` — one sheet per place, with `archetypes: {"war": {"ids", "how", "why"}, "after": …}` and unknowns.
- `layout_map(plan, top, interiors, sheet)` — a plan as the game's own map (tiles, glyphs, entity types).
- `layout_check(maps)` — the game's own map rules in plain words (run on every write and before approving).
- `layout_install(maps, folder, who)` — write approved maps into the game; never over a map it already has.
- `layout_tile_image()` — the game's placeholder tiles for the greybox.

`games/_example/workbench_adapter.py` has a small working version of each.

## The generic map (no `layout_map`)

`{"id", "name", "tile_size": 32, "legend": {glyph: semantic tile}, "rows": [...], "entities": [...]}` with the
semantic tiles of `tiles.py` and the entities of `plan.py` (spawn, door, upgrade, npc, story, label).

## Art → Floor plans (BUILD 29, second part)

In the suite (`forge.bat` → Art → **Floor plans**):
- **Pick a town, an era and an archetype** (the suggested ones first, with why, and what the sheet doesn't say).
  **Generate 4** lays out four candidates (the next unused seeds) side by side as paint guides; **Reroll** adds one more.
- **Open** one: every map of its set (the town, the rooms behind its doors, the level below), drawn on a grid. **Paint**
  with a brush (wall, floor, door, road, path, ground, rubble, fence, water — or *story*, which moves the story element).
  The checks run as you paint; **Save edits** writes it back, and from then on a reroll never writes over it. Undo and
  Discard are there. The map's outer edge stays closed except at its gates.
- **Approve** (a person's): the maps go into the game through its adapter, never over a map it already has. For this
  game the adapter then puts the paint guide where the scene kit paints from (`assets/scenes/<map>_greybox.png` at the
  painted size, the magenta turned pale so it doesn't tint the painting; the magenta guide as `_paintguide.png` and the
  element alone as `_story.png`), runs `tools/songs_needed.py` (every map needs a music slot), and the suite remakes the
  production plan — the scene is on **Art → Wanted**, its scene-kit job painting over the guide. Nothing is queued.
- **Send to <owner>**: a candidate goes to the Mail with a question, its paint guide attached.

The approved maps are in the game's data but nothing leads to them yet: wiring a town's travel node to its new map
(instead of its hand-made one) is a game build's job, not the suite's.
