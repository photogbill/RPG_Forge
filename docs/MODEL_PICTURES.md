# Icons and portraits from the models (BUILD 91)

The world queue makes a game's things and people as 3D models around the clock. The pictures a game also needs of
them — an icon for every item, a portrait for every principal — are taken **from those models**, so a thing looks
like itself wherever it is seen, and nobody paints it twice.

Code: `forge/threed/modelpics.py`, the Blender script `forge/threed/blender/picture_model.py`, the plug-in
`forge/plugins/modelpics.py` (job types `model_icon`, `model_portrait`; fields in `docs/JOB_TYPES.md`).

## What to double-click

`icons_from_models.bat` — takes every icon and portrait that can be taken and writes the sheets. Run it again any
time: a picture is taken again only when its model is new or was made again (`icons_from_models.bat again` takes
all). It renders with Blender's Cycles **on the processor** — no graphics card, no ComfyUI — so it may run while the
3D queue runs. On the two processor cores the building session had, an icon took ten to forty seconds and a
portrait about a minute and a half; a PC with more cores is quicker.

Results, in `out/pictures/<game>/`:

| File | What it is |
|---|---|
| `icons/<item id>.png` | 512, clear background (RGBA). Beside each, a `.json` saying which model it came from |
| `icons_sheet.png` | every item icon taken, named; amber = a stand-in (see *near*) |
| `also/`, `icons_also_sheet.png` | made things a hand could hold that no item names yet |
| `portraits/<name>.png` | 768, clear background; `<name>_<expression>.png` where a body carries expressions (the `.json` beside a portrait names its own files, so `hero_boy` is never taken for an expression of `hero`) |
| `portraits_sheet.png` | every portrait, and an empty frame for each name whose body is not made |
| `MISSING.md` | which items wait for a thing that is on the world list but not made, and which have no model at all |

Each picture is also a forge job with its own `prov.json`: which model, which try of the world queue, and that
model's licence lines — so it can go through Review like any other picture.

## The rule for an icon (the same for every thing)

- Clear background; the camera has no perspective, so every icon stands on one footing whatever the thing's size.
- Three-quarter view: 35 degrees round from the front, 22 degrees up.
- `auto_view` (on) adjusts that by one rule, never by taste: the thing's longer ground side is laid across the
  frame; a long thing (a rifle, a sword) lies along the frame's diagonal so it fills its square; and a thing that
  lies flat on the ground (a pistol, a chip, a note) is looked at from higher up, so it is seen and not sighted
  along.
- One fixed key light from the upper left, and a low even fill so no side goes black.
- A thing that still fills less than a third of its square is flagged; give that one its own `az` / `el` in the
  table (with `"auto_view": false`).

## The rule for a portrait

- Head and shoulders, framed by the body's own head bone; through a long lens, a little to one side.
- At rest: the body's idle motion (first frame), with the head set upright and facing where the body faces — an
  idle motion often looks at the floor.
- The faces are smoothed for the picture (a body made from a picture comes faceted, with every seam split).
- Light: one warm key close to the face, falling off to dark, and a faint rim from behind. The rim takes a colour
  only for a character who owns one (`"rim": [r, g, b]` in the table).
- One more picture for each expression (shape key) the body carries. Bodies made so far carry none: expressions
  live in the animation, so today a portrait is *at rest* only.

**What a portrait is, honestly.** These bodies were made to be seen small on a stage. Close up, a face shows that:
soft, a little crude. The portrait is a true picture of the body the player will see walking about — which is its
worth — and it is also the best *starting picture* for a painted portrait (the forge's `repaint` job keeps the
pose, the clothes and the colours and repaints the face), when a game wants its portraits finer than its bodies.

## What a game says (`games/<id>/pictures/`, proposal files)

`items_to_models.json`:

    {"items_file": "<the game's items data>", "size": 512,
     "items": {"<item id>": {"world": "<world-list id>", "fit": "exact" | "near", "note": "…"},
               "<item id>": {"world": null, "group": "a pack (one model, three tiers)"}},
     "also": ["<world id>", …]}

- **exact** — the made thing *is* the item.
- **near** — a made thing that reads right at icon size but is not the named thing. Its icon is taken and shown
  amber, as a stand-in, until the item's own thing is on the world list.
- **world: null** — no model anywhere. `group` says how few distinct models would cover a family of items (three
  packs are one model in three tiers). These are for whoever keeps the world list; this code never writes a list.

`portraits.json`:

    {"size": 768, "portraits": {"<name>": {"world": "<body id>", "rim": [r, g, b], "note": "…"},
                                "<name>": {"model": "<a .glb somewhere else>"}}}

Nothing in either file approves anything or changes a game's data.
