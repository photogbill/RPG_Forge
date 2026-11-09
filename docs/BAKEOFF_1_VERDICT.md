# Bake-off 1 — verdict (sdxl_v1, 2026-11-08 → 09)

*1,280 renders: 5 SDXL checkpoints × (15 compatible LoRAs + none) × 16 prompts (8 asset kinds × 2), one seed, identical sampler (dpmpp_2m/karras, 25 steps, cfg 6, 1024²). Zero failures. Reviewed by Fable on 2026-11-09 from the `by_category` trees (review sheets in `out/bakeoff/sdxl_v1/review/`). Read with William's direction of the same morning in mind: **as high resolution as we can; vivid, beautiful where appropriate, horrific where appropriate, good composition** — FF6's density, not its pixels.*

## The one-paragraph answer

The painterly checkpoints are superb at exactly what the game now needs — composed, vivid, 16:9 painted scenes at 1024 px and up — and nothing here can make a usable animated sprite sheet. So: **paint the world with SDXL, build characters another way.** Per asset kind: **ArtUniverseSDXL_v8** for painted scenes, concept art, props and glossy inventory icons (the most *vivid*; the best light); **sd_xl_base_1.0** as the painterly alternate (less gloss, more illustration; pairs best with the LoRAs); **RealVisXL_V5** for the horrific/realist set (ruins, Level Seven) and photographic textures to downscale; **SDVN6-RealXL-Detailface** for faces when realism is wanted; **gmic_icon_V5** for flat hand-drawn icons and stylised props only (its anime cast is wrong for portraits and its saturation wrong for scenes). LoRAs: **Retro_Illustration** (warm illustrated finish, better composition), **rpg_portrait** (portraits), **game_icon_v1.0** (inventory icon look), **Pixel_Xl_V1** (HD-pixel look — the only pixel LoRA that keeps detail at 1024), **FFTALevel4** (true 16-bit style — a *reference* generator, not the game's look), **DD_Table_RPG** (top-down tabletop layouts), **fantasy_map-heavy** (overrides everything into a parchment map — overworld only), **Synthetic_Breed** (new; untested; robots — Sentinels). Avoid: **FinalFantasy_Tactics_Sprite_Sheet** and **SpriteSheet (1)** (noise on 4 of 5 checkpoints — broken or mis-tagged), **SpriteSheet** (noise on 2), **amano_yoshitaka_xl** (a named-artist style LoRA — William's rule is that we build our own style; it also failed on 2 checkpoints), **TileMapStyle_v1** (did nothing visible), **HadesLevel** (does little outside its genre).

## Per checkpoint

| Checkpoint | Character | Best at | Weak at |
|---|---|---|---|
| **ArtUniverseSDXL_v8** | glossy, cinematic, saturated; strong light and atmosphere | scene cards and concept paintings (the gas station at dusk was the best image of the run), props, vivid icons, "beautiful" portraits | portraits drift toward airbrushed glamour; everyone is a cover model |
| **sd_xl_base_1.0** | painterly illustration, honest colour, takes LoRAs well | portraits with character (base + rpg_portrait / Retro_Illustration), scenes when ArtUniverse over-glosses, the HD-pixel hybrid with Pixel_Xl | flatter light than ArtUniverse; generic-fantasy faces without a LoRA |
| **RealVisXL_V5.0** | photoreal | the horrific register (ruins, bodies, the black site), textures to downscale into tiles, reference photography | too real for a stylised game's portraits unless the style prefix pulls it back |
| **SDVN6-RealXL-Detailface** | photoreal, soft, good faces | face studies, realism portraits, pixel tiles with FFTALevel4/Pixel_Xl (surprisingly good) | same as RealVis; softer composition |
| **gmic_icon_V5-000180** | hand-drawn icon / anime cast, flat colour | inventory icons, stylised single props, isometric "game asset" sheets | scenes (cartoon, too bright), portraits (anime), realism of any kind |

## Per asset kind (what to use from Monday)

| Asset | Pick | Alternate | Notes |
|---|---|---|---|
| **Painted scene backgrounds** (the map art, 16:9) | ArtUniverse · no LoRA or Retro_Illustration 0.5 | base · Retro_Illustration | the main visual of the game under the hi-res decision; render 1344×768 → upscale ×2 → fit 1920×1080; the "horrific" scenes go to RealVis first and get graded against ArtUniverse |
| **Scene cards / vignettes** (Gate Law, Set Pieces) | ArtUniverse | base | same as above at card size |
| **Concept paintings** (towns, dungeons, key moments) | ArtUniverse | RealVis for ruins | already strong without a style prefix |
| **Portraits** (5–7 expressions each) | base · rpg_portrait 0.7 (seed-locked) | ArtUniverse for Aphrodite, Sarah's Guardian — the "beautiful" faces | decide after the style bake-off; consistency across expressions is the real test, not one render; a per-character LoRA later |
| **Inventory icons** | ArtUniverse · game_icon_v1.0 | gmic_icon_V5 · game_icon_v1.0 (softer, hand-drawn) | game_icon_v1.0 gives the unified "game icon" read on every checkpoint |
| **Props / objects** (key-background isolation) | ArtUniverse | base | gmic turns a gas pump into a cartoon gadget — off-brand |
| **Tiles** (procedural dungeons, the overworld) | SDVN6 or base · Pixel_Xl_V1 (flat-shaded, downscales cleanly) | RealVis · no LoRA → forge pixel ops (photo textures snapped down) | FFTALevel4 makes genuine 16-bit floors but adds objects — prompt "no objects"; at 96-px tiles the HD-pixel look (Pixel_Xl) is the better fit |
| **Town / dungeon layout references** | FFTALevel4 on any checkpoint (16-bit reference), base/RealVis no LoRA (painted isometric) | DD_Table_RPG for top-down room plans | not tilemaps — references and slicing stock |
| **Sprites — animated sheets** | **none** | — | SDXL produces rows of near-identical standing poses, never a walk cycle; the tiny chibi rows from gmic are inconsistent. Characters are built another way (see `10.1b`): painted turnarounds (SpriteGen2_SpaceCandy gives clean 3-view turnarounds on ArtUniverse/RealVis) → cut-out rig, or PixelLab / Retro Diffusion for pixel sheets, or the artist friend |
| **Enemy design sheets** (static) | ArtUniverse · Pixel_Xl_V1 or Retro_Illustration (the big pixel mech was excellent) | SDVN6 · HadesLevel | single-pose battle sprites can come from these after the forge's pixel-grid snap |
| **Overworld / parchment maps** | fantasy_map-heavy on base | — | the only use for that LoRA |
| **Expression sheets** | base · SpriteSheet (a grid of the same face in expressions — happened by accident on the Sarah portrait) | — | worth a deliberate test with a seed lock |

## Findings worth remembering

- **The pixel LoRAs are style converters, not sprite makers.** FFTALevel4 turns any scene into a convincing 16-bit tableau (the Gate Law kitchen with sprites, the juke joint, whole towns) — great for *reference* and for deciding what "FF6 density" means in a frame; useless for an actual sheet. Pixel_Xl_V1 keeps detail at 1024 and reads as *HD pixel art* — the one bridge between painted and pixel if the sprites end up pixel.
- **Key-background isolation works** on every realistic checkpoint (the magenta backdrop stayed clean) — props are a solved problem.
- **The two SpriteSheet LoRAs from the same training set (`128078`) are broken** on most checkpoints (pure noise). Their siblings from that set (DD_Table_RPG, Synthetic_Breed, futuristic_stlye) work, so it is the files, not the base. Drop the two from every future suite.
- **Composition is the checkpoint's job, not the LoRA's.** ArtUniverse composed the gas station (car, canopy glow, mountains, wet asphalt) without being told; the others gave a competent postcard. Prompt the *picture* (subject, light, camera), let the checkpoint compose.
- **"Horrific where appropriate"** was not in the first suite's prompts. The style bake-off adds Augusta's glass field and Level Seven; expect RealVis to lead there and ArtUniverse to be more beautiful than frightening.
- **The game's base viewport moves to 1920×1080** (`10.1b`). Render scenes at 1344×768 and upscale ×2 (4x-UltraSharp or RealESRGAN-x2 through ComfyUI — the forge needs an `upscale` step; `models/upscale_models/` is empty — a `pull_model` entry is the first job).

## Ratings file
No `bakeoff rate` entries yet — the verdicts above are the ratings. When the style bake-off lands, rate the winning cells so the index shows them.
