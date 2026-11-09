# The Turing Accords — forge configuration

`forge.game.json` carries the game's look (palette, style prefix, sizes, default model). Batches live in
`batches/`; each batch file keeps an `approved` list so a later session knows what has been taken into the
game. Approved assets are copied, with their `prov.json`, into the game repo's `project/assets/…`.

| Batch | What | Status |
|---|---|---|
| `gate_law_cards.json` | the 21 vignette cards of *No Slaves in Synthetic Land* (IV-T3) | queued when the GPU worker first runs |

The bible lives in `D:\Turing Accords Game` — `18_Visual_Pipeline_Free_Options.md` (the density and palette laws),
`19_Character_Visual_Briefs.md` (every portrait and sprite brief), `Set_Pieces/` (per-scene cards).
