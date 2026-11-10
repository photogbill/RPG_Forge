# Hand-off — RPG_Forge, Night 3 (Opus, 2026-11-09 22:50 → 23:45)

Plan: `docs/ROADMAP_NIGHT_3.md` (its Progress section is current). **Tests: 106 → 139, all green**
(`python -m pytest`; the GPU paths are tested against the fake ComfyUI).

## Contract changes

None. `scene_big` writes `scene.png` at the target size; `scene_state` writes the same six slot files as a kit (when its
base is a kit). Nothing the game reads changed.

## G0 — plug-ins on the live worker

The `ping` job ran at 22:54 — the worker had plug-in support. **Every Night 3 job type is a plug-in**; no file the
worker reloads (`queue.py`, `jobs/*`, `engines/*`, `bakeoff.py`, `pipeline.py`, the existing `ops/*`) was edited.
The worker log shows it picking them up (23:34): `scene_big`, `inpaint`, `scene_state`, `facings_pack`,
`anim_preview`, `turnaround_split`, `nine_slice`, `button_states`.

One lesson, now guarded: the Night 3 specs share one file (`forge/night3/specs.py`); a syntax error there took every
Night 3 type down in a fresh process (a running worker keeps its last good version). `tests/test_night3_plugins.py`
fails if any of them stops loading.

## Built

| Item | What | Where | Try it |
|---|---|---|---|
| G1 | Morning report: per batch done/failed (causes folded, with counts)/still queued/skipped-as-done, wall time, s/render by checkpoint, slowest, models with licence colour, thumbnail strip, bake-off link, what to run next. Checked on the 2026-11-08 run: 1,280 sdxl_v1 renders, 6h49m, 0 failed; the 20 sdxl_v1_quick failures fold into one cause | `forge/night_report.py` | `night_report.bat` |
| G2 | `review --compact` (≤ 12 cells, ≤ 2,000 px, ≤ 1.5 MB, labels name only what differs, `review_index.json`), `--prompt P`, `--pairs A,B` (side by side + 1:1 crop). Built on finish_v1 (8 sheets, 16 pairs, largest 0.75 MB) and one sdxl_v1 prompt (7 sheets). sdxl_v1 whole is ~10 min of image loading — fine on the PC | `forge/review_compact.py` | `review_compact.bat finish_v1` |
| G3 | `scene_big`: small whole scene (or `source` = an existing painting) → climb ≤ 2× per step (William's ruling; `max_step`) → tiled img2img per tile with ControlNet **tile** (+ **canny** from the greybox) → feathered merge → seam scores + sheet. `op tiles-demo`: 6144×3072 → 25 tiles, worst seam 0.03 | `forge/ops/bigtiles.py`, `forge/night3/big.py`, `forge/plugins/scene_big.py` | `op.bat tiles-demo` |
| G4 | `inpaint` (SDXL with the job's own checkpoint: VAEEncode → SetLatentNoiseMask, nodes checked in the installed ComfyUI's `nodes.py`; no new model, no new licence) and `scene_state` (mask from two greyboxes, grown + feathered, refused over 35 %; repaints only the mask's padded box at ~1 MP; **bit-identical outside the mask, tested**; a kit's companions rebuilt and composited only inside the mask) | `forge/ops/state_mask.py`, `forge/night3/inpaint.py`, `forge/plugins/inpaint.py` | `op.bat state-mask --base … --state … --out …` |
| G5 | `kit check`: slots, sizes vs wanted.json, normals (facing, flat, banding comb), depth (range, ground at the bottom, ground share), glow share, back-plane holes, over-plane share, walk rings/doors/spawns + footing when the map is readable. Gas-station kit: PASS (map not readable here). `out/_tests/night3/broken_kit`: FAIL — normals at the wrong size, depth inverted; warns on glow 100 %. `approve --set` (CLI and dashboard) refuses on a fail | `forge/kitcheck.py` | `kit_check.bat 20261109-205640-c3_n3_kit_gas_station-f6be` |
| G6 | Prompt library: `games/turing_accords/prompts/*.json` blocks, `{{block}}` expanded by `submit` and `bakeoff submit` (job records `prompt_blocks`, `prompt_library`, `prompt_template`); unknown block, loop, placeholder (`TODO…`) or never-list word refuses the submit, naming job and word; `--skip-done` re-queues only jobs whose expanded text changed; `prompts list/show/where-used/check/ab`. **Shelves shipped as placeholders only.** `never.json` seeded with `amano`, `yoshitaka`; `lora_triggers_forbidden` empty for William to fill | `forge/prompts.py` | `prompts.bat` |
| G10 | `brief missing`: one draft per missing painting — scene_kit / scene_big / scene_state / "waiting for its base" — with `{{skin.*}}` / `{{era.*}}` references, greybox, size; table to `out/reports/missing_<date>.md`. Ran on the last wanted.json (24 maps, all scene_big or scene_kit; no greyboxes, no states, no templates yet in that export) | `forge/brief_missing.py` | `paint_missing.bat` |
| G11 | Room families: maps sharing `template` (or an identical greybox) → one control image, one seed, `{{layout.<template>}}` once, members differ only in skin/era references (tested on three towns); `review --family <template>` | same + `review_compact.build_family` | `review.bat x --family inn_small` |
| G7 | `facings_pack` (poses → 1152×216, one height, one baseline, game order, mirroring, edge report), `anim_preview` (GIF per facing + turntable), `turnaround_split` | `forge/ops/sprites.py`, `forge/plugins/sprites.py` | `op.bat facings-pack --in poses --out folder --mirror W>E` |
| G8 | `credits` → `out/reports/CREDITS_MODELS.md`; zero approvals today (valid report); problems listed loudly | `forge/credits.py` | `credits.bat` |
| G9 | Dashboard: **Report** link (`/report` → newest report, `/out/…` read-only), kit-check dot on cards (click → check.png), **A/B** (tick two cards → side by side + differing fields), "running: … then: …" | `forge/ui.py` | `ui.bat` |
| G12 | `nine_slice` (trim, margins detected or given, snapped to ×3, tileable centre, Godot `patch_margin_*` JSON, stretched preview — corners stay 1:1, tested) and `button_states` (tone only) | `forge/ops/ui_pieces.py`, `forge/plugins/ui_pieces.py` | `op.bat nine-slice --in panel.png --out folder` |

All new commands are in `forge/cli_night3.py` (registered in `cli.COMMANDS`); `.bat`s: `night_report`, `review_compact`,
`kit_check`, `prompts`, `paint_missing`, `credits`, `op`.

## What ran on the GPU — and what is waiting

Only G0 (`ping`). At 23:09 William stopped the worker, so the G3/G4 proofs are **queued in a folder for him**:
**`night3_tests\run_night3_tests.bat`** — 8 jobs, ~15–25 min: `scene_big` on four existing paintings (four
checkpoints, 1920×1080 → 3840×2160, one 2× climb, 6 tiles each) and one street from a synthetic greybox; `scene_state`
on the gas-station kit with a hand-made rectangle (the done-when); `inpaint` on the ruin painting with an oval; a
greybox-driven `scene_state`. The .bat requeues the stopped job, parks the bake-off, runs only the tests, then resumes
the bake-off. All 8 ran end to end against the fake ComfyUI first (each `outside_mask_max_diff` 0). **Next session:
read `out/*g3_*/contact.png` + `seam_sheet.jpg` and `out/*g4_*/contact.png`.** If a run fails, `jobs/failed/` has why.

## Left in `docs/WIRE_NIGHT_3.md` (empty queue only)

W1 `scene_kit big: true`; W2 `scene_layers fill: "inpaint"`; W3 `prov.json` carries the prompt-library fields.

## For William

1. The prompt library shipped **empty on purpose** (placeholder blocks that refuse to expand). The words are yours and
   Fable's — `games\turing_accords\prompts\library.json`.
2. `never.json` blocks the two words of the artist-named LoRA. Add any trigger words you read off model pages to
   `lora_triggers_forbidden`.
3. `kit check` and `brief missing` read map fields I could not see (the game folder was not connected here — the access
   request was declined): `template`, `skin`, `era`, `state_of`, walk rings as `walk`, `doors`, `spawns`. The game
   session should confirm the names; each is one place to change.

## Surprises from reading the run

- `sdxl_v1` still had 282 cells pending from the new-LoRA additions when the night started; finish_v1 was mid-way.
- The 20 `sdxl_v1_quick` failures from 11-08 are one cause (`int()` of a batch name) — a bug fixed since; harmless.
- The VM's clock is UTC: a job submitted from the Linux side gets a UTC id/timestamp (the G0 ping's id says 03:53).
  Jobs submitted on the PC are unaffected.
