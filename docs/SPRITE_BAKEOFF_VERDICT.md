# Sprite bake-off verdict (sprite_samplers_v2, 2026-11-10)

1,456 SDXL renders of Sarah's sprite (4 checkpoints x 12 LoRAs + none x 14 samplers x 2 seeds). Read with
`out/_peek/v2_*.jpg`.

**Faces are solved locally:** 48 head crops on ArtUniverse and RealVis — clean, even eyes every time; a seed gives
the same face across all samplers (a face can be locked by seed).

## Use for sprites
- **Checkpoint: ArtUniverseSDXL_v8** (painted game look, clean full body, flat light). RealVisXL_V5 as the
  photographic alternative / portraits.
- **Sampler: dpmpp_2m karras, 28 steps** — samplers barely differ on these checkpoints; seed and LoRA matter more.
- **LoRAs:** none needed for faces. `SpriteSheet` and `Sprite_sheet_generator_2` make multi-view turnarounds on
  ArtUniverse — under test (hair_test_v1 D).

## Dropped for sprite work (William, 2026-11-10: "remove models that obviously won't be used")
- `sd_xl_base_1.0` — invents shields/blades/rifles not in the prompt.
- `SDVN6-RealXL-Detailface` — crops at the thigh, glamour drift (cleavage, cut-outs); portraits at most.
- `gmic icon_V5` — an icon checkpoint.
- `Pixel_Xl_V1` — real pixel art; wrong for the 1080p painted ruling.
- `FinalFantasy_Tactics_Sprite_Sheet`, `SpriteSheet (1)` — pure noise grids on 3 of 4 checkpoints.
Their unrun jobs were moved to `jobs/_cancelled_sprite_v1/`.

## Still missing (the prompt)
No cobalt in the hair, eyes not violet, no trefoil on the core → hair_test_v1 / hair_test_prerap_v1 (William's
hair block + weighted violet eyes; flat-light twin; Pre-Raphaelite twin).
