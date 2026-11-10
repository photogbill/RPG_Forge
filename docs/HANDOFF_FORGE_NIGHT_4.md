# Hand-off — RPG_Forge, Night 4 (Opus, 2026-11-10 14:02 → evening)

Plan: `docs/ROADMAP_NIGHT_4.md` (its Progress section is updated). **Tests: 155 → 189, all green.** The worker ran
the FLUX sprite bake-off the whole time, so **Part A only**: every job type is a plug-in (the live worker logged
loading `night4_sprites` at 14:18 and `night4_tools` at 14:43), no edit to queue/jobs/engines/bakeoff/pipeline/ops.
Part B is left exact in `docs/WIRE_NIGHT_4.md`.

## Git (F0) — nothing was lost; run `push.bat` as usual

No failed push and no lock files. The 02:47 push (`368d5a0`, on GitHub) **contains** Night 3, Night 3B and the sprite
run — 60+ files. It carries the title "Krea 2 cut…" because each session appended to the waiting `COMMIT_MESSAGE.txt`
(the CLAUDE.md rule) and `push.bat` takes the first line as the title. CLAUDE.md now says to rewrite the first line
when appending. Not yet pushed: the 4 edited sprite suites, `hair_test_*` (3), `SPRITE_BAKEOFF_VERDICT.md`, and all of
Night 4 — `COMMIT_MESSAGE.txt` is written. `jobs/_cancelled*/` (3,318 files) is now git-ignored.

## One thing I got wrong, and undid

While testing `produce queue` against the live repo I ran it with `--kinds scene_card`. Those 21 Gate Law cards have
real prompts, so it **queued them** into your live queue (priority 25, below the bake-off). None had started; I moved
all 21 to `jobs/_cancelled_n4_produce_test/` within a minute. The bake-off was not touched. CLAUDE.md now tells
assistant sessions never to run `produce queue` without `--dry` here.

## Night 3 GPU tests (`run_night3_tests.bat`) — you ran them; all 8 done

- **Big scenes (G3):** worst tile-overlap disagreement 3.4–5.0 grey levels out of 255 across the five (RealVis worst).
  On the seam sheet of the worst one I see no tile edges.
- **States (G4):** outside the mask the result is identical to the base (max difference 0) in all three. The
  greybox-made state changed 1.3% of the frame (mask 3.5%), far under the 35% limit.

## What was built

| Item | What | Try it |
|---|---|---|
| F1 | Your sheets → the sprite contract (one row S…SE, 144×216). Any grid or backdrop, labels dropped, one scale, feet on one baseline. **It asks you** whether the guess is right; no file editing needed. A photo instead of a sheet is refused in plain words | `sprite_intake.bat "<sheet>" sarah guardian` |
| F2 | Registry: Sarah guardian/warrior (facts, locked seed 24101 *provisional*, holster = asymmetric) + 23 cast stubs; `character_set`; `review --character` | `characters.bat list` |
| F3 | `produce plan` (227 jobs, ~8 GPU h, ~4 GB — rough; only `render` time is measured), `queue` (refuses while blocks are TODO), `status`; `deliver` + ledger + undo; disk guard + 24 h report; housekeeping | `produce.bat plan` · `produce_watch.bat` |
| §4 | Towns: every map draft carries town/era/state/look and `{{culture.<town>}}`/`{{fate.*}}`; a town shares one seed; enclaves as per-block states; `review --town` / `--atlas` | (needs town data in the game, see WIRE) |
| F4 | `icon_batch`: one seed per category, 256 + 512 px, a contact sheet per category | via produce |
| F5 | `feedback_in.bat`: F9 notes → redo drafts (never queued) + bumps; dashboard **Called out** | `feedback_in.bat` |
| F6 | `photo_plate` + people guard (`games/turing_accords/refs.local.json`, git-ignored) | — |
| F7 | `tileable`: Wet Stone seam 2.30 → 0.74, Wood 16.5 → 0.75 (`out/_tests/night4/tileable/`). `filter_forge` takes `"tileable": true` | — |
| F8 | Model shelf: 50 files; **22.6 GB could go** — 0.5 GB dropped by a verdict or non-commercial, 22.1 GB is MOSS ×3, FLUX.3 klein and LoRAs nothing here can run *today* (your call) | `models_report.bat` |

**Contract changes: none** to anything the game reads today. Proposals for the game session are in WIRE §"Contract
questions" (town fields, validator file, icon paths, a Warrior Sarah slot, the feedback file).

## What you run, in order

1. `push.bat`
2. **`sprite_intake.bat "<your first Gemini sheet>" sarah guardian`**: answer its questions; look at `sheet.png`.
3. `models_report.bat`: read the list and delete in Explorer only what you agree with. The forge deletes nothing.
4. When a long queue runs: leave `produce_watch.bat` open beside it.

## What Fable must write before `produce queue` runs

`produce.bat queue` prints the full list. In total, 222 TODO blocks: **160 `sleeve.*`** (one per song, each
placeholder holds the song's title), **25 `place.*`** (one per map, each holds the game's own notes), and the shared
ones: `style.house/.prop/.sleeve/.enemy/.vignette`, `ui.house`, `icon.house` + 6 families, `char.sarah.guardian/.warrior`,
`neg.sarah`, 8 `mood.*`, 3 `pose.*`, plus Night 3's examples. Smaller first steps work: `produce.bat queue --lanes
first` needs only `style.house` and the eight `place.*` of the first hour.

## Limits, said plainly

- **Intake has not seen one of your real sheets.** It passed five synthetic sheets; the only real one in the forge was a
  photo portrait, which it now refuses. Your first sheet is the real test.
- The GPU paths (`character_set`, `icon_batch`, `photo_plate`, tileable's inpaint polish) are tested only against the
  fake ComfyUI.
- On the CPU, tileable on strongly directional textures (wood grain) leaves a visible splice line where the top of
  the texture meets the bottom. The wrap itself is seamless; the GPU polish is meant for that line.
- Questions only you can answer: is `hero_sarah_light` the Part 1 hologram (a third Sarah variant)? Which seed is
  Sarah's face (from hair_test_v1/v2)?

## For the next build plan (William, 2026-11-10 afternoon, after the hand-off)

**ON HOLD (William, 2026-11-10 15:46): items 1 and 2 wait until he has a solution — no rush; do not plan them yet.**

1. **A face reference for a character.** Lock a character's face to a photograph, by path, never copied into the
   repo. Use only licence-clean routes: IP-Adapter Plus Face on SDXL, or FLUX.2 klein reference editing (check each
   licence before wiring). **Not** InstantID, IP-Adapter FaceID or PuLID, because their face-recognition models are
   non-commercial research only. The registry gains `face_reference` per variant, and a bake-off on one seed shows
   which route holds the face.
2. **Kelly's face (William's wife) for one of the Synthetic Ranch Sarahs.** Details to be worked out later; William
   thinks it's doable. Gate: **Kelly's OK first** — her face would be in the Ranch scenes. Needs: a registry entry
   for that synthetic, a frontal photo (the red-hood portrait is a profile with eyes lowered, too little for a face
   lock), and the photo guard taught a named, consenting person (today it accepts `people: none | william` only).
3. **The president's face:** William decides when the time comes; nothing to do now.
4. **Sarah's light variant** is in the registry (`hero_sarah_light`); its look block `char.sarah.light` is Fable's to
   write — William's blue hologram images are the reference.
