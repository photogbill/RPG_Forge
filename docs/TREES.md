# Trees by species (BUILD 36, BUILD 84 part 5)

A tree is grown by rule from a **species sheet** and a **seed**, never guessed from a picture. One seed is one tree; the
next seed is its sibling, never its copy. `--bare` leaves the leaves off (winter, a dead tree, an ocotillo's dry months).

- The forge's sheets: `forge/threed/species/<name>.json`. A game's own: `games/<id>/threed/species/<name>.json` (a game's
  sheet of the same name wins; the Trees tab's sliders write them).
- On the world list: `{"id": "...", "kind": "tree", "species": "live_oak", "seed": 7, "real_size_m": {"height": 8.5}}`.
  The tree is grown at the sheet's own size and then given the height the entry asks for.
- By hand: `python -m forge 3d grow <species> [--seed N] [--count 4] [--bare]`, or the Trees tab.

## The species

| Sheet | What it is | Leaf | Grown at |
|---|---|---|---|
| `broadleaf` | a big old broadleaf, a trunk as wide as a car | heart | 14 m |
| `young_broadleaf` | a young street tree of the same kind | heart | 7 m |
| `linden` | American basswood as a young street tree: broad rounded crown, grey bark, low branching | heart | 6.5 m |
| `live_oak` | short thick trunk, limbs almost level, a dark crown far wider than tall | oval | 9.5 m |
| `pecan` | tall, upright, a long clean trunk, an oval open crown | lance | 20 m |
| `mesquite` | small, crooked, forks at the ground, an airy grey-green crown | feather | 5 m |
| `ashe_juniper` | the hill country's "cedar": dark, dense, branching from the ground | scale | 6 m |
| `bald_cypress` | tall straight trunk on a wide buttress, a narrow crown high up | feather | 24 m |
| `cottonwood` | very tall, thick pale trunk, a broad open crown | delta | 22 m |
| `saguaro` | a ribbed column, a domed top, three arms that leave level and turn up | (form `column`) | 8.5 m |
| `ocotillo` | a spray of long thin canes from one foot, a red spike at each tip | (form `canes`) | 4.5 m |
| `yucca` | a soaptree yucca: trunk, skirt of dead blades, two heads, a flower stalk | (form `rosette`) | 3.2 m to the heads |

## What a sheet may say

`{"name", "about", "numbers": {...}}`. Every number has a default (the big broadleaf's), so a sheet gives only what differs.

**The crown-filling grower** (`form: broadleaf`, the default): `height`, `trunk_radius`, `fork_height`, `limbs`,
`limb_tilt [from, to]`, `crown_centre_z`, `crown_radius`, `crown_half_height`, `crown_floor`, `masses`, `mass_radius`,
`attractors`, `step`, `reach`, `close`, `twig_radius`, `pipe`, `leaf_card [smallest, largest]`, `cards_per_twig`. The Trees
tab has a slider for each. New in BUILD 84:

- `leaf`: the sprig painted on the leaf cards: `heart`, `oval`, `delta`, `lance`, `feather`, `scale`.
- `leaf_tint [r, g, b]`: multiplies the sprig's own green (a live oak darker, a mesquite greyer).
- `bark [r, g, b]`: the bark's light colour. `flare`, `flare_height`: how the trunk widens at the foot.

What a tree's .glb carries: the wood (mesh `M_bark`) in the bark's one colour, and the leaf cards (mesh `N_leaves`) with
their sprig picture. Blender's own furrowed bark is in the forge's pictures only; a .glb cannot carry it. (Until BUILD 84
the wood's .glb material carried no colour at all, which a game shows as white.)

**Three plants no crown-filling rule can grow**, each built by its own rule; their colours are on the mesh (one material,
a colour a vertex, both faces shown), with no leaf cards and no bark picture:

- `form: column` (a saguaro): `height`, `trunk_radius`, `ribs`, `rib_depth`, `arms` (0 = a young spear), `arm_from`,
  `arm_reach`, `arm_top`.
- `form: canes` (an ocotillo): `height`, `canes`, `cane_radius`, `cane_lean [from, to]` degrees, `bloom` (share of canes
  with a flower spike). Bare: grey canes, no flowers.
- `form: rosette` (a yucca): `height` (to the top of the heads), `trunk_radius`, `heads`, `blades`, `blade [shortest,
  longest]`, `blade_width`, `skirt`, `stalk` (metres above a head; 0 or bare = none). The height an entry asks for is to
  the top of the whole plant, stalk included.

A sheet that says none of the new things grows exactly the tree it grew before: the same seed gives the same tree, to the
vertex (checked for `broadleaf` and `young_broadleaf` when this was built).

## Making another species

Copy the nearest sheet, change its numbers, grow three seeds and look at the pictures (`out/3d/trees/`). A new **leaf** is
one line of half-widths in `LEAF_SHAPES` (stalk to tip) and one in `SPRIG_LAYOUT` in `forge/threed/blender/grow_tree.py`,
and a painted `sprig_<leaf>.png` beside it for a Blender whose Python cannot paint. A new **form** is a function there
that returns vertices, faces and a colour a vertex.

Not done yet: a palm (a rosette of fronds on a tall trunk is a fourth form), a pine's whorled tiers, and bark that reaches
the game as a picture with its furrows.

Tests: `tests/test_build84_trees.py` (each species grows through the world queue against the stand-in Blender, and for
real where Python has Blender inside).
