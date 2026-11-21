# Materials: every channel, a second source, no repeats, wear as a layer (BUILD 87)

A surface that only has a colour picture looks like a photograph of a floor. A surface with a true normal map,
height, roughness and occlusion looks like a floor when a lamp moves over it. This is how the forge makes the
second kind, from two programs it already had and was not using fully.

Code: `forge/materials/`. Job types: `ff_channel_proof`, `ff_channels`, `mm_material`, `material_mix`,
`material_decal` (plug-in `forge/plugins/materials.py`; fields in `docs/JOB_TYPES.md`).

## What to double-click, in order

| File | What it does | How long | Card? |
|---|---|---|---|
| `materials_1_filter_forge.bat` | The proof; then true channels for the library's Filter Forge pictures; three seeds and a mix for each ground; decals; sheets | the proof: minutes. The rest: about five minutes a material | no |
| `materials_2_all_picks.bat` | The same channels for every kept pick of the game's cull file | long (about seven renders a pick); carries on where it stopped | no |
| `materials_3_material_maker.bat` | Checks the six graphs against the installed node library, then exports each in each state at 2048 | a minute or two a material, plus waiting for the card | yes, under the card lock |
| `materials_sheets.bat` | The sheets again | seconds | no |

Each command queues its jobs under its own batch and runs only those, in its own window. It does not start, stop or
feed the art worker, and jobs other people left waiting stay where they are. Everything it does is written to
`logs/materials.log`; reports and sheets go to `out/materials/<game>/`.

## Part 1 — Filter Forge: every channel

**What Filter Forge's own help says** (read 2026-11-19: *Render Channels*, *Presets*, *Command-Line Renderer*):

- A preset stores the state of the Render Channels menu, beside its controls, lighting and anti-aliasing.
- The command line's task file has no element for the channel. The only way to a channel is a preset.
- A library filter's own presets are inside the filter file. Presets a person adds to a library filter are kept
  somewhere else, and the command-line renderer **skips** them; the help's advice is to copy the filter to another
  folder and point the task at the copy. So the route the forge had before (save a Normal preset by hand in the
  Filter Forge window and give the forge its number) could not have worked for a library filter.
- The menu, in order. Legacy surface filters: Final, Diffuse, Bump, Normal, Specular Strength, Specular Exponent,
  Metallicity, Ambient Occlusion, Reflective Occlusion. PBR surface filters: Final, Albedo, Height, Normal,
  Roughness, Metallic, Emission, Occlusion. Simple filters: Final only.

**What the help does not say** is how a preset writes the menu's state down. Every preset's `<Settings>` carries
`map_type="0"`, so the forge takes that to be it — and **proves it by rendering**, because a name is not evidence:

1. For one filter it writes working copies into the job's own folder, one a number, with every preset's `map_type`
   set to that number (so the preset number means what it always meant).
2. It renders each copy small and names what came back by what the picture *is*: the same as the final picture; a
   normal map (its pixels are unit vectors, blue up); a grey map whose slopes agree with that normal map (height);
   a colour map; a flat grey.
3. Those anchors must sit where the menu's order puts them. Only then are the other grey maps — roughness,
   occlusion, the specular pair — named by the order.
4. The answer is kept in `local/ff_channels.json`, per filter type. Delete that file to learn again.

The verdict is `yes`, `partial` (normal and height can be told, the order could not be confirmed) or `no` (every
number rendered the final picture: the renderer does not take the channel from `map_type` in a copy). Every proof
writes `proof.png` — each number's picture with its name — which is what to look at when the verdict is not yes.

**If the verdict is no.** Then the menu's state is written some other way, and the forge has to be shown one
example (this route has not been tried; it is built from the help's own words). Copy one library filter's `.ffxml`
into Filter Forge's *My Filters* folder — the help's own advice for the command line — and open that copy in Filter
Forge. Choose Normal in *Filter > Render Channels*, then *Presets > Add Preset*: a preset of a filter of your own is
saved inside its `.ffxml`. That file then holds one preset that differs from its neighbours only in the menu's
state. Give its path to the forge lane and the encoding is read off it; nothing more is saved by hand, however many
picks there are.

**The working copies** are removed when the render is done (kept only when it failed, to be looked at). The forge
still stores a filter's *path* and nothing else; a filter is never committed, moved or passed on.

**A channel set** (`ff_channels`) is the final picture and its channels from one preset at one size, so they sit
exactly on each other: `<slot>.png`, `<slot>_n.png` (OpenGL: green up), `<slot>_height.png` (16-bit, white = high),
`<slot>_rough.png`, `<slot>_ao.png`, `<slot>_metal.png` where there is any metal. `channels.json` says of each
channel which of three things it is:

- **true** — Filter Forge's own channel, with the number it came from;
- **worked out** — a legacy surface filter has no roughness channel, so roughness is `1 − Specular Strength ×
  Specular Exponent` (a strong, tight highlight is a smooth surface). It is a reading of two true channels, not a
  guess from the picture, and it is labelled;
- **FALLBACK / MISSING** — the channel did not come back; the normal is then guessed from the picture's brightness
  as before, and the report says so in capitals.

The normal map is checked against the height map and turned to OpenGL if it came back the other way. Each job also
draws `moving_light.png`: the same piece of surface with a lamp carried across it, **before** (normal guessed from
brightness, no roughness) over **after** (the true channels).

**Beside the picture.** With `beside`, the set is also put next to the picture it belongs to, under the names the
texture library already uses: `<name>_ffnormal.png` (which `3d relief` puts in use as `<name>_n.png` the next time
it runs — BUILD 63's rule that a true normal wins), `<name>_height.png`, `<name>_rough.png`, `<name>_ao.png`, and
`<name>_channels.json`. Two guards: the job's own final picture must *be* the picture already there (else its
channels would not sit on it, and nothing is written), and a file that exists is never written over.

**One geometry.** Where the picture in use is the healed one (`…_tile.png`), the whole set is healed together:
the roll and the cut are taken from the final picture and applied to every channel
(`ffchannels.tile_together`). The older `filter_forge` job's `tileable: true` did not until 2026-11-20: it healed each
channel by itself, which moved each by its own amount. It heals a set the same way now (`tileable.tile_channels`), and
writes the game's normal from the healed one (`<slot>_n_tile.png`).

## Part 2 — Material Maker, driven

**How it exports from the command line** was read from the installed program itself (Material Maker 1.8, the
script `parse_args` inside `material_maker.exe`; its doc page is older than its code):

    material_maker.exe --export-material -t "Godot/Godot 4 ORM" -o <folder> --size 2048 --output-file <name> <graph.ptex>

- The first word after the program is skipped by its parser, so it has to be `--export-material` itself.
- `-t`: an export profile of the Material node. `Godot/Godot 4 ORM` writes `<name>_albedo.png`, `<name>_orm.png`
  (red occlusion, green roughness, blue metal), `<name>_normal.png`, `<name>_heightmap.png`, `<name>_emission.png`
  — each only when that input of the Material node is connected.
- `--size` is in pixels (2048 if left out). `-o` is made if it is missing.
- It prints `Done` and quits. After a mistake it prints and does **not** quit, so the forge gives it a time limit
  and stops it.
- It draws on the graphics card, in a small window. The forge holds its card lock around every export, so it runs
  between two of the 3D queue's models.
- Its settings and cache are pointed at `local/material_maker_data` (as `material_maker.bat` does).

**A job** (`mm_material`) checks the graph against the installed node library first (`mm.lint`: a node type that
is not there, a connection to a port that is not there, a loop, a channel not connected), writes a patched copy
into its own folder, exports, splits the ORM picture, checks the normal against the height, measures the wrap
seam, and writes the same file names a Filter Forge set has, with `<slot>_emission.png` where the graph glows.

**Seed.** In Material Maker every random node's seed has its parent graph's seed added, so the top graph's `seed`
moves the whole surface together. That is the job's `seed`.

**Named parameters and states.** A graph's side file `<graph>.json` names parameters from 0 to 1 and says which
node parameter each one moves, between which two values — nearly always how much of one layer is blended in. A
**setting** is a named set of values. Every forge graph has two: `broken` (cracked, ashed, marked) and `mended`
(filled, swept, washed) — one surface in two states. Which era of a game wears which state is the game's to say
(`"states"` in its `materials.json`).

**The six graphs** (`forge/materials/graphs/`, written by `forge/materials/mmgraph.py`):

| Graph | What it is | Named parameters |
|---|---|---|
| `canvas` | heavy olive tent cloth, a weave you can count | cracks (fray, tears), stains, ash, mend (washed, bleached) |
| `fused_glass` | sand turned to glass: green-black pools, bubbles, crazing | cracks, ash (dust dulling it), mend (worn smooth) |
| `whitewash_brick` | limewash on red brick | coverage (how much paint is left), cracks, ash |
| `chalked_wall` | grey plaster people have written on | chalk (fresh marks or their ghosts), cracks, ash, mend |
| `ash_crust` | fire ash set by rain into a cracked crust | cracks, ash (charcoal flecks), mend (rained in, paler) |
| `caliche` | the pale lime crust of dry ground | cracks, ash, mend (cracks filled pale) |

They are built only from node types whose parameters were read from the installed library and which the program's
own examples use the same way. **They were written without being seen**: the session that wrote them could not
run Material Maker. Expect to tune numbers after the first export. To tune one, open the `.ptex` in Material
Maker (`material_maker.bat`), move things, save — it stays the forge's graph, and its side file still applies as
long as the node names it mentions are kept. To change one from code, edit its recipe in `mmgraph.py` and run
`python -m forge.materials graphs`.

## Part 3 — No repeats, and wear as a layer

**Three seeds, mixed** (`material_mix`). The same ground rendered three times with three variations, then chosen
between point by point by a smooth noise that wraps. The result tiles at twice the width, and inside that width
the eye finds no tile; where there is a height map the higher surface wins the edge between two seeds. The job
measures it (`repeat_of_one_seed` against `repeat_of_the_mix`: 1 is an exact repeat) and also writes the mask
(`<name>_mixmask.png`) for an engine that would rather mix live.

**Decals** (`material_decal`). One picture of cracks, scorch, grime or scratches becomes a layer: colour with
see-through, its own normal map, roughness — fading to nothing at its edge. `alpha_from` says what makes it solid
(`dark` for cracks on white, `light` for smoke on black, `alpha` for a picture with its own see-through, `key`,
`streaks` for runs the forge draws itself); `tint` gives it one colour; `relief` says whether it is cut into the
ground or lies on it.

**A place's ground, wear on and off** (`python -m forge.materials sheets`). The game's `materials.json` gives a
place its ground materials, its decals and a list of where they lie in each era. The forge draws the ground once
from the place plan's own rectangles and looks at it twice from a standing height, under one fixed sun, with only
the decal list different. These pictures show the **ground only** — no buildings, no props, not the game's light
— and say so on the picture. Drawing decals in the game itself is the game's work; what the forge hands over is
the decal files and the list.

## Part 4 — The sheets

One sheet a town (`out/materials/<game>/towns/<town>.png`): each of its surfaces with every channel, a piece
under the lamp and a ball, the licence lines at the foot, and a line naming what is not on the sheet and why. A
row whose normal is still guessed says **NO CHANNEL SET YET** in its title.

Every lamp picture is drawn in numpy and stamped *forge preview — not the game's look*: it is for judging a
channel set on any computer, not for judging the game.

## What a game says (`games/<id>/materials/materials.json`)

    {"library": "games/<id>/ref/materials",
     "cull": "<path>/_filter_forge_cull.json",
     "licences": ["…"],
     "states": {"<era>": "broken", "<era>": "mended"},
     "towns": {"<town>": {"label": "…", "materials": [{"word": "asphalt", "picks": ["9339-1"]}, {"word": "canvas", "graph": "canvas"}]}},
     "grounds": ["asphalt", "gravel"],
     "places": {"<place>": {"plan": "…place.json", "window": [x, y, w, h], "stand": [x, y], "eye_m": 1.7, "looks_at": [x, y],
                            "materials": {"asphalt": {"pick": "9339-1", "tile_m": 4}},
                            "decals": {"cracks": {"pick": "11797-2", "alpha_from": "dark", "tint": [0.02, 0.02, 0.02]}},
                            "layers": {"<era>": [{"decal": "cracks", "at": [x, y], "size_m": 8, "turn": 35}], "<era>": []}}}}

It is a proposal file: nothing in it approves anything, and nothing here changes a game's data.

## Licences

Filter Forge: rendered results carry the tool's licence line from the forge's tool register, as before; filters
themselves are never copied out or passed on. Material Maker is MIT-licensed free software and what it exports is
the maker's own; the six graphs are part of the forge. A mix or a decal carries the licence of the pictures it
was made from.
