"""The generator's own words for what a cell is — semantic tiles, not any game's tiles.

A plan is drawn in these. A game's adapter turns each one into its own tile (and glyph) when the plan is exported;
the paint guide colours them so a painting model can repaint the layout region by region.
"""
from __future__ import annotations

GROUND = "ground"      # open ground: grass, dirt, sand — the adapter picks by terrain
ROAD = "road"          # an artery or street
PATH = "path"          # sidewalk, footpath, queue lane, the strip in front of a door
FLOOR = "floor"        # inside a building, a plaza paved, a deck
WALL = "wall"          # a wall (blocking)
ROOF = "roof"          # a building seen from above on a town map (blocking; its inside is its own map)
WATER = "water"        # river, pond, flooded drain (blocking)
DOOR = "door"          # walkable gap where a door entity stands
RUBBLE = "rubble"      # broken ground, walkable cover
FIELD = "field"        # crops, a lawn kept on purpose (walkable)
FENCE = "fence"        # fence, rope barrier, barricade, berm (blocking)
ROCK = "rock"          # natural rock, cave wall, mountain (blocking)
GLASS = "glass"        # fused ground (walkable; nothing is built on it)
BRIDGE = "bridge"      # a deck over water or a drop (walkable)
DROP = "drop"          # a fall: between decks, a shaft (blocking)
VEHICLE = "vehicle"    # a parked or wrecked vehicle used as a wall (blocking)
FURNITURE = "furniture"  # counters, beds, pews, racks inside an interior (blocking)

ALL = (GROUND, ROAD, PATH, FLOOR, WALL, ROOF, WATER, DOOR, RUBBLE, FIELD, FENCE, ROCK, GLASS, BRIDGE, DROP,
       VEHICLE, FURNITURE)
BLOCKING = frozenset({WALL, ROOF, WATER, FENCE, ROCK, DROP, VEHICLE, FURNITURE})
WALKABLE = frozenset(t for t in ALL if t not in BLOCKING)
# what a line of sight can't pass (low things — fences, rubble, furniture, vehicles, water — can be seen over)
SIGHT_BLOCKING = frozenset({WALL, ROOF, ROCK})

# The paint guide: flat regions the scene kit repaints from. The story element is always magenta.
STORY_COLOUR = (255, 0, 255)
PAINT = {
    GROUND: (96, 140, 72), ROAD: (58, 58, 62), PATH: (172, 170, 160), FLOOR: (204, 182, 140),
    WALL: (88, 88, 104), ROOF: (150, 62, 42), WATER: (40, 92, 204), DOOR: (255, 204, 0),
    RUBBLE: (132, 112, 90), FIELD: (156, 176, 60), FENCE: (112, 80, 40), ROCK: (78, 68, 60),
    GLASS: (170, 232, 232), BRIDGE: (142, 102, 60), DROP: (8, 8, 10), VEHICLE: (70, 92, 82),
    FURNITURE: (122, 82, 58),
}
# Greybox: the same regions in greys, so walkable vs blocking reads at a glance.
GREY = {t: ((60, 60, 66) if t in BLOCKING else (190, 190, 186)) for t in ALL}
GREY.update({ROAD: (150, 150, 150), DOOR: (230, 210, 120), WATER: (70, 90, 130), ROOF: (96, 80, 80),
             DROP: (10, 10, 12), GLASS: (210, 230, 230)})


def blocking(t: str) -> bool:
    return t in BLOCKING
