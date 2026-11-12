# Tiles — the materials bake-off and the autotile builder (BUILD 30)

## The materials bake-off
Which source makes the best surface for each material: **SDXL ArtUniverse**, **FLUX.2 [klein] 4B** (distilled and base,
Apache-2.0 — the 9B is non-commercial and left out) and **Filter Forge** (texture filters matched to a material by the
words in their names; a material nothing matches is listed, never guessed).

```
bakeoff_materials.bat            plan it and queue it (resumable — run again, it skips what's queued or done)
bakeoff_materials.bat report     contact sheets + scores → out\bakeoff\materials\MATERIALS_VERDICT.md
python -m forge tiles materials | plan | submit | report | pick <material> <source> | weathering plan|submit
```

The material list is the game's (`material_list()` in its adapter), else the forge's first pass (23 materials,
`forge/tiles/materials.py`). Each is processed the same way: made seamless when its seam scores over 1.0 (offset and
heal), normals from Filter Forge's own normal channel when it rendered one, else from luminance — **kept at its own full
resolution**. Scores: seam (about 1.0 or less is seamless) · repetition (lower repeats less when tiled) · normals (lit
from four directions, 0–1) · palette (distance to the game's paintings) · seconds. The order on each sheet is a
suggestion; **the pick is a person's** (`tiles pick`, or Art → Bake-offs in the GUI to come).

The **weathering** pass (the War and the After from a picked Peace tile): img2img repaints at two strengths against
Filter Forge effect filters whose names say rust, grime, dirt, burn, crack… Planned from the picks.

## The autotile builder
```
python -m forge tiles build <name> --floor <material|file> [--edge <material|file>] [--wall <material|file>]
       [--kind blob47|set16] [--style soft|hard|ragged|crumbly] [--px N | --scale 2] [--variants 6] [--seed 0]
```
Writes `out/tiles/<game>/<name>/`: `<name>.png` + `_n.png` (the tile atlas and its normals), `_decals.png` + `_n`,
`_masks.png`, `_world_a.png`/`_world_b.png` (+ `_n`), and `<name>.json` (every tile's kind, neighbour bits in Godot's
own names — top_side, top_right_corner… — and whether it blocks).

- **blob47** — the 47-tile set of A on B, plus B's fill tile (Godot "Match Corners and Sides"); **set16** — the corner
  set (Godot "Match Corners"). Transitions are painted by a mask, never generated, so every material joins the same way;
  along every tile border the mask depends only on what the two neighbours agree on, so any two tiles meet without a seam.
- **walls** — top, front and cap from one crop of the wall material (the faces line up); the front faces the viewer.
- **variants** — the inside differs, the border stays the base's, so every variant joins every other tile.
- **decals** — cracks, stains, scorch, debris as RGBA overlays with normals, scattered by a map, never baked in.
- **normals** — every tile, tangent space, OpenGL (green = up), the scene kit's convention.

### Resolution (William, 2026-11-12: "the highest resolution tiles, so the game looks vivid and sharp")
Two ways to draw, both written every time:
- **World textures — the sharp way.** The material stays at its own resolution (up to 4096 px) as one seamless texture
  laid across the map in world space, so one period spans many tiles (a 1024 px material over 192 px tiles repeats every
  5⅓ tiles instead of every tile). The tiles carry only the transition masks; the game's tile shader samples A and B at
  full resolution and blends them by the mask. This is the default for the game (the shader lands with the Godot side).
- **Baked tiles** at **2× the game's tile size** by default (192 px for a 96 px game), so they stay crisp at 4K or when
  the camera zooms; `--scale 3` or `--px` for more. Each baked tile shows one period of the material.
For more source detail, upscale the picked material before building (Gigapixel 4× → 4096 px).

## Still to come (BUILD 30, second part)
The Godot side — TileSet `.tres` with terrain sets, peering bits and collision from the manifest, the world-space tile
shader, a dungeon template naming its tileset, `gen:foundry:<seed>` drawn with real tiles, normals and lights — and the
Art → Tiles tab.
