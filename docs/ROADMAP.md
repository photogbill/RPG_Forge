# Roadmap

Built in the order the game needs it. Each module is useful alone the day it lands.

## v0.1 — the skeleton (done)
Queue · CLI · schema · logging · CPU ops (OKLab palette snap with hysteresis, grid detection + cell
downscale, flood-fill alpha, contact/sprite sheets, seamless tiles, Godot TileSet writer) · ComfyUI
driver with a template workflow · GPU handlers (scene_card, concept, portrait, prop, tile_texture) ·
model registry with licences · Windows .bat install/run · safetensors header inspection (SD1.5/SDXL/FLUX, triggers) · SDXL graph builder with LoRA chains · the **bake-off** (checkpoint × LoRA × prompt suite → grids + html + ratings) · 24 tests.

## v0.2 — environments end to end (next)
The first location from concept to lit map, so the whole pipeline is seen once before scaling:
1. **`kit_from_concept`** — an approved concept painting + a crop list (`[{"name": "pump", "box": [x, y, w, h], "kind": "prop" | "tile"}]`)
   → props on alpha and tile textures, all from the same image, so the kit is coherent.
2. **Autotile builder** — base tile + edge mask → the 47-tile blob set (corners, edges, inner corners)
   as a strip + the Godot terrain `.tres`; same rules for every material.
3. **Lighting layer recipe** — a Godot `CanvasModulate` + point-light pass with presets (dusk, neon,
   sodium, dawn) and the time-of-day curve.
4. **Style LoRA** — once ~50–100 tiles/props are approved, a `train_lora` job (kohya/ai-toolkit in the
   ComfyUI env) producing `models/loras/<game>_style.safetensors`; after that every new render matches.
5. FLUX.2 klein 4B and Qwen-Image-Edit workflow exports; `img2img`/`edit` handlers.

## v0.3 — people
1. **Portrait LoRA per principal** — from a seed-locked set the person approved; after that, fifty
   portraits of the same face.
2. **Sprite route A (3D proxy)** — approved front/side reference → image-to-3D (Hunyuan3D 2 / TripoSR)
   → auto-rig → Blender renders of a walk cycle from 8 orthographic angles → `pixelize` to the hero
   cell → `pack_sheet`. The Dead Cells method; every piece runs locally.
3. **Sprite route B (paperdoll)** — one base body per build (adult, child, 7-foot synthetic) drawn once
   (by hand or route A), clothes/hair/skin as palette-indexed layers composited by a `paperdoll` job.
   This is how an FF6-sized cast ships on time.
4. `hysteresis` snapping across animation frames (already in `palette.py`) wired into `pack_sheet`.

## v0.4 — the world
1. **`overworld`** — pull Natural Earth (coasts, rivers, states, major roads, places), Census TIGER
   (every road, by class), USGS GNIS (names), USGS 3DEP (elevation → relief and biome), NLCD (land cover);
   compress the scale non-linearly (towns at full size, the space between shrunk; road class = travel
   cost); emit the game's biome/road/town map. Deterministic and re-runnable when the scale changes.
2. **Underground sites** — seed procedural dungeons at real places from public records: the USGS
   Mineral Resources Data System (abandoned mines), decommissioned Atlas/Titan missile silos, salt
   caverns. In *The Turing Accords* these are Valkyrie's foundries and the party's safe houses.
3. **Dungeon generators** — BSP rooms (facilities), cellular caves (mines), wave-function-collapse
   (ruined cities) → the engine's ASCII map format + `on_enter` hooks.

## Always
- Every handler writes `prov.json`. Every CPU op has a test. Every .bat prints what it is doing and
  where the log is. Nothing is written outside the repo.
