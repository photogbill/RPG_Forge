# Job types

Generated from `forge/schema.py` — do not edit by hand.

## `scene_card`  (GPU)

A painted scene card (a cutscene vignette, a location card, a record sleeve): text → image via ComfyUI → downscale to card_size → optional palette snap. Output: card.png, raw.png, prov.json.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `card_size` (None), `render_scale` (None), `palette` (None), `snap` (True), `style_prefix` (None), `workflow` (None), `checkpoint` (None), `steps` (28), `cfg` (6.0), `game` (None), `variants` (1)

## `concept`  (GPU)

A location concept painting — the single image a kit is derived from (the gas station at dusk, the inn's common room). Rendered large; no palette snap. Output: concept.png, prov.json.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `size` ([1536, 864]), `style_prefix` (None), `workflow` (None), `checkpoint` (None), `steps` (30), `cfg` (6.0), `game` (None), `variants` (2)

## `portrait`  (GPU)

A seed-locked portrait set: one seed, one base prompt, a list of expression/stance phrases; each phrase renders once with the same seed so the face holds. Output: <expr>.png ×N + contact sheet.

Required: `prompt`, `expressions`

Optional (default): `negative` (None), `seed` (12345), `size` ([768, 768]), `out_size` ([128, 128]), `palette` (None), `snap` (False), `style_prefix` (None), `workflow` (None), `checkpoint` (None), `steps` (30), `cfg` (6.0), `game` (None)

## `prop`  (GPU)

A prop sprite (gas pump, bed, counter): rendered on a flat key colour → background removed → trimmed → downscaled to target_h → palette snap. Output: prop.png (RGBA), raw.png, prov.json.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `size` ([768, 768]), `target_h` (64), `key_color` ('#ff00ff'), `palette` (None), `snap` (True), `style_prefix` (None), `workflow` (None), `checkpoint` (None), `steps` (28), `cfg` (6.0), `game` (None), `variants` (3)

## `tile_texture`  (GPU)

A tileable surface (asphalt, siding, grass): rendered → made seamless → downscaled to tile_size → palette snap → seam score + N jittered variants. Output: tile.png, variants.png, raw.png, prov.json.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `size` ([512, 512]), `tile_size` (32), `palette` (None), `snap` (True), `style_prefix` (None), `workflow` (None), `checkpoint` (None), `steps` (28), `cfg` (6.0), `game` (None), `variants` (4)

## `palette_snap`  (CPU)

Snap one or more images to a palette in OKLab (nearest perceptual colour), alpha preserved. Output: <name>.png per input + report.json (colour counts).

Required: `inputs`

Optional (default): `palette` (None), `dither` (None), `hysteresis` (0.0), `game` (None)

## `pixelize`  (CPU)

Turn a large generated image into pixel art: detect the pixel grid (or take `scale`), downscale cell-by-cell (mode/median/center), optional palette snap. Output: <name>.png + report.json.

Required: `inputs`

Optional (default): `scale` (None), `method` ('mode'), `palette` (None), `snap` (False), `target` (None), `game` (None)

## `remove_bg`  (CPU)

Flood-fill a flat background from the corners to alpha, trim, optionally pad to a size. Output: <name>.png (RGBA).

Required: `inputs`

Optional (default): `key_color` (None), `tolerance` (28), `trim` (True), `pad_to` (None), `anchor` ('bottom')

## `contact_sheet`  (CPU)

A labelled grid of images for review (this is how Claude looks at a batch). Output: contact.png.

Required: `inputs`

Optional (default): `cols` (4), `cell` ([288, 162]), `labels` (None), `title` (None)

## `pack_sheet`  (CPU)

Pack frames into a sprite sheet with uniform cells (row-major), e.g. 8 facings × N frames. Output: sheet.png + sheet.json (cell size, order).

Required: `inputs`

Optional (default): `cols` (8), `cell` (None), `anchor` ('bottom')

## `godot_tileset`  (CPU)

Write a Godot 4 TileSet .tres for a tile strip PNG (which tiles collide). Output: <name>.tres.

Required: `png`, `tile_size`, `blocking`

Optional (default): `res_path` (None)

## `overworld`  (CPU)

PLANNED — pull public-domain layers (Natural Earth, TIGER, GNIS, 3DEP, NLCD), compress the scale, emit a biome/road/town map in the game's format. Submitting one today returns 'not implemented'.

Required: `region`

Optional (default): `scale` ('fe6'), `layers` (['naturalearth'])
